# backend/app/routes/conversation_routes.py

import logging
import uuid
from datetime import datetime, timezone as dt_timezone
from typing import List, Optional, Dict, Any
import json # Not strictly needed if only Pydantic is used for JSON (de)serialization

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, distinct, func, case, and_, String # Use String for casting
from sqlalchemy.orm import selectinload, Session

from app.database import get_async_db, get_db
from app import models, schemas, auth
from app.config import Settings, get_settings
from app.services.message_service import MessageService
from app.services.twilio_service import TwilioService
from app.services.appointment_ai_service import AppointmentAIService
from app.services.appointment_service import AppointmentService
from app.models import (
    AppointmentRequestStatusEnum,
    AppointmentRequest as AppointmentRequestModel,
    Customer as CustomerModel, # This is how CustomerModel is defined
    Message as MessageModel,
    OptInStatus, 
    SenderTypeEnum, 
    MessageTypeEnum,
    ConsentLog as ConsentLogModel,
)
from app.timezone_utils import get_utc_now
from pydantic import BaseModel
from enum import Enum  # Add this at the top with other imports

logger = logging.getLogger(__name__)

router = APIRouter(
    # Prefix and tags are managed in main.py
)

class InboxConversationItem(BaseModel):
    customer_id: int
    customer_name: str
    last_message_content: str
    last_message_timestamp: Optional[datetime] = None
    last_message_type: Optional[models.MessageTypeEnum] = None
    last_message_status: Optional[models.MessageStatusEnum] = None
    conversation_id: Optional[str] = None
    latest_appointment_request_id: Optional[int] = None
    latest_appointment_request_status: Optional[AppointmentRequestStatusEnum] = None
    latest_appointment_request_datetime_utc: Optional[datetime] = None
    latest_appointment_request_time_text: Optional[str] = None
    model_config = {'from_attributes': True, 'use_enum_values': True}

@router.get("/inbox", response_model=Dict[str, List[InboxConversationItem]])
async def get_open_conversations(
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    db: AsyncSession = Depends(get_async_db),
    appointment_status_filter: Optional[List[AppointmentRequestStatusEnum]] = Query(
        None,
        alias="appointment_status",
        description="Filter conversations by associated AppointmentRequest status."
    ),
    no_appointment_history: Optional[bool] = Query(False, description="Filter for conversations with no appointment history.")
):
    logger.info(
        f"Inbox: Fetching conversations for Business ID: {current_business.id}, "
        f"Appt Status Filter: {appointment_status_filter}, No Appt History: {no_appointment_history}"
    )

    latest_message_subquery = (
        select(
            MessageModel.customer_id.label("l_customer_id"),
            func.max(MessageModel.created_at).label("max_created_at")
        )
        .where(MessageModel.business_id == current_business.id)
        .group_by(MessageModel.customer_id)
        .subquery("latest_message_sub")
    )

    latest_appointment_subquery = (
        select(
            AppointmentRequestModel.customer_id.label("la_customer_id"),
            func.max(AppointmentRequestModel.updated_at).label("max_updated_at")
        )
        .where(AppointmentRequestModel.business_id == current_business.id)
        .group_by(AppointmentRequestModel.customer_id)
        .subquery("latest_appointment_sub")
    )

    confirmed_status_val = AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER.value
    reschedule_status_val = AppointmentRequestStatusEnum.OWNER_PROPOSED_RESCHEDULE.value

    stmt_customers_with_latest_interactions = (
        select(
            CustomerModel, # Selecting the ORM class CustomerModel as the first element
            MessageModel.content.label("last_message_content"),
            MessageModel.created_at.label("last_message_timestamp"),
            MessageModel.message_type.label("last_message_type"),
            MessageModel.status.label("last_message_status"),
            MessageModel.conversation_id.label("message_conversation_id"),
            AppointmentRequestModel.id.label("latest_appointment_request_id"),
            AppointmentRequestModel.status.label("latest_appointment_request_status"),
            case(
                (AppointmentRequestModel.status.cast(String) == confirmed_status_val, AppointmentRequestModel.confirmed_datetime_utc),
                (AppointmentRequestModel.status.cast(String) == reschedule_status_val, AppointmentRequestModel.owner_suggested_datetime_utc),
                else_=AppointmentRequestModel.parsed_requested_datetime_utc
            ).label("latest_appointment_request_datetime_utc"),
            case(
                (AppointmentRequestModel.status.cast(String) == confirmed_status_val, AppointmentRequestModel.parsed_requested_time_text),
                (AppointmentRequestModel.status.cast(String) == reschedule_status_val, AppointmentRequestModel.owner_suggested_time_text),
                else_=AppointmentRequestModel.parsed_requested_time_text
            ).label("latest_appointment_request_time_text")
        )
        .select_from(CustomerModel)
        .join(latest_message_subquery, CustomerModel.id == latest_message_subquery.c.l_customer_id)
        .join(MessageModel, and_(
            MessageModel.customer_id == latest_message_subquery.c.l_customer_id,
            MessageModel.created_at == latest_message_subquery.c.max_created_at,
            MessageModel.business_id == current_business.id
        ))
        .outerjoin(latest_appointment_subquery, CustomerModel.id == latest_appointment_subquery.c.la_customer_id)
        .outerjoin(AppointmentRequestModel, and_(
            AppointmentRequestModel.customer_id == latest_appointment_subquery.c.la_customer_id,
            AppointmentRequestModel.updated_at == latest_appointment_subquery.c.max_updated_at,
            AppointmentRequestModel.business_id == current_business.id
        ))
        .where(CustomerModel.business_id == current_business.id)
    )

    if appointment_status_filter:
        logger.info(f"Applying appointment status filter: {appointment_status_filter}")
        status_values = [s.value for s in appointment_status_filter]
        
        # Base status filter
        stmt_customers_with_latest_interactions = stmt_customers_with_latest_interactions.where(
            AppointmentRequestModel.status.in_(status_values)
        )
        
        # If the filter is specifically for "upcoming appointments" (i.e., CONFIRMED_BY_OWNER),
        # add a condition to ensure the appointment date is in the future.
        # This assumes the "upcoming_appointments" filter sends only AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER.
        if len(appointment_status_filter) == 1 and appointment_status_filter[0] == AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER:
            stmt_customers_with_latest_interactions = stmt_customers_with_latest_interactions.where(
                AppointmentRequestModel.confirmed_datetime_utc > get_utc_now() # Ensures the confirmed date is in the future
            )
            logger.info(f"Applied future date filter for CONFIRMED_BY_OWNER status.")
    
    if no_appointment_history:
        stmt_customers_with_latest_interactions = stmt_customers_with_latest_interactions.where(
            AppointmentRequestModel.id.is_(None)
        )
    
    stmt_customers_with_latest_interactions = stmt_customers_with_latest_interactions.order_by(
        desc(latest_message_subquery.c.max_created_at)
    )

    result_rows = await db.execute(stmt_customers_with_latest_interactions)
    customer_interactions_data = result_rows.all()

    response_list: List[InboxConversationItem] = []
    for row_data in customer_interactions_data:
        # CORRECTED: Access the CustomerModel ORM instance by its index (0) in the row
        customer_orm = row_data[0] 
        
        conv_id = str(row_data.message_conversation_id) if row_data.message_conversation_id else None
        if not conv_id: # Fallback logic for conversation_id
            conv_res = await db.execute(
                select(models.Conversation.id)
                .where(models.Conversation.customer_id == customer_orm.id, models.Conversation.business_id == current_business.id)
                .order_by(desc(models.Conversation.last_message_at)).limit(1)
            )
            conv_tuple = conv_res.first()
            if conv_tuple: conv_id = str(conv_tuple[0])

        response_list.append(
            InboxConversationItem(
                customer_id=customer_orm.id,
                customer_name=customer_orm.customer_name or f"Customer ({customer_orm.phone[-4:] if customer_orm.phone else 'N/A'})",
                last_message_content=(row_data.last_message_content or "")[:75] + ('...' if len(row_data.last_message_content or "") > 75 else ''),
                last_message_timestamp=row_data.last_message_timestamp,
                last_message_type=row_data.last_message_type,
                last_message_status=row_data.last_message_status,
                conversation_id=conv_id,
                latest_appointment_request_id=row_data.latest_appointment_request_id,
                latest_appointment_request_status=row_data.latest_appointment_request_status,
                latest_appointment_request_datetime_utc=row_data.latest_appointment_request_datetime_utc,
                latest_appointment_request_time_text=row_data.latest_appointment_request_time_text,
            )
        )
    logger.info(f"Inbox: Returning {len(response_list)} conversations for Business ID {current_business.id}")
    return {"conversations": response_list}


@router.get("/customer/{customer_id}", response_model=schemas.ConversationResponseSchema)
async def get_conversation_history(
    customer_id: int,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    db: AsyncSession = Depends(get_async_db),
    settings: Settings = Depends(get_settings)
):
    logger.info(f"History: Fetching conversation for customer {customer_id} for business '{current_business.business_name}' (ID: {current_business.id})")

    stmt_customer = (
        select(CustomerModel)
        .options(
            selectinload(CustomerModel.business),
            selectinload(CustomerModel.tags)
        )
        .where(CustomerModel.id == customer_id)
        .where(CustomerModel.business_id == current_business.id)
    )
    result_customer = await db.execute(stmt_customer)
    customer_orm: Optional[CustomerModel] = result_customer.scalar_one_or_none()

    if not customer_orm:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")
    if not customer_orm.business:
        logger.error(f"History: Business profile not loaded for customer {customer_id} (Business ID: {customer_orm.business_id})")
        raise HTTPException(status_code=500, detail="Associated business data missing.")

    business_tz_str = customer_orm.business.timezone if customer_orm.business.timezone else "UTC"
    try:
        business_tz = pytz.timezone(business_tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"History: Unknown timezone '{business_tz_str}' for business {current_business.id}. Defaulting to UTC.")
        business_tz = pytz.utc

    # --- MODIFICATION START: Fetch latest consent and prepare customer DTO ---
    actual_latest_consent_status: Optional[str] = None
    actual_latest_consent_updated: Optional[datetime] = None

    stmt_latest_consent_log = (
        select(ConsentLogModel.status, ConsentLogModel.updated_at)
        .where(ConsentLogModel.customer_id == customer_orm.id)
        .where(ConsentLogModel.business_id == current_business.id)
        .order_by(desc(ConsentLogModel.updated_at))
        .limit(1)
    )
    result_latest_consent_log = await db.execute(stmt_latest_consent_log)
    latest_consent_log_entry = result_latest_consent_log.first()

    if latest_consent_log_entry:
        actual_latest_consent_status = latest_consent_log_entry.status
        actual_latest_consent_updated = latest_consent_log_entry.updated_at

    tags_for_dto: List[schemas.TagRead] = []
    if customer_orm.tags and hasattr(schemas, 'TagRead'):
        try:
            tags_for_dto = [schemas.TagRead.model_validate(tag) for tag in customer_orm.tags]
        except Exception as e_tag_val:
            logger.error(f"Error validating tags for customer {customer_orm.id}: {e_tag_val}")
            tags_for_dto = []
    elif customer_orm.tags:
        logger.warning("schemas.TagRead not found, cannot validate tags.")
        tags_for_dto = []

    customer_data_for_dto = {
        "id": customer_orm.id,
        "customer_name": customer_orm.customer_name,
        "phone": customer_orm.phone,
        "sms_opt_in_status": customer_orm.sms_opt_in_status.value if isinstance(customer_orm.sms_opt_in_status, Enum) else customer_orm.sms_opt_in_status,
        "latest_consent_status": actual_latest_consent_status,
        "latest_consent_updated": actual_latest_consent_updated,
        "tags": tags_for_dto,
        "timezone": customer_orm.timezone if hasattr(customer_orm, 'timezone') and customer_orm.timezone else customer_orm.business.timezone,
        # --- ADDING MISSING REQUIRED FIELDS ---
        "business_id": customer_orm.business_id, # Added
        "created_at": customer_orm.created_at,   # Added
        # --- Optionally, include other common fields if they are part of CustomerRead ---
        # "updated_at": getattr(customer_orm, 'updated_at', None),
        # "notes": getattr(customer_orm, 'notes', None),
        # "email": getattr(customer_orm, 'email', None),
        # "lifecycle_stage": getattr(customer_orm, 'lifecycle_stage').value if hasattr(customer_orm, 'lifecycle_stage') and isinstance(getattr(customer_orm, 'lifecycle_stage'), Enum) else getattr(customer_orm, 'lifecycle_stage', None),
    }
    
    customer_read_dto = schemas.CustomerRead.model_validate(customer_data_for_dto)
    # --- MODIFICATION END ---

    # ... (The rest of the function remains unchanged from your latest version) ...
    # For example:
    stmt_messages = (
        select(models.Message)
        .where(models.Message.customer_id == customer_id)
        .where(models.Message.business_id == current_business.id)
        .order_by(models.Message.created_at.asc())
    )
    result_messages = await db.execute(stmt_messages)
    messages_from_db_orm = result_messages.scalars().all()

    temp_message_list = []
    for msg_record_orm in messages_from_db_orm:
        if msg_record_orm.is_hidden and msg_record_orm.message_type != models.MessageTypeEnum.AI_DRAFT:
            continue
        temp_message_list.append({
            "id": str(msg_record_orm.id),
            "text": msg_record_orm.content,
            "type": msg_record_orm.message_type.value,
            "status": msg_record_orm.status.value if msg_record_orm.status else None,
            "direction": "inbound" if msg_record_orm.message_type == models.MessageTypeEnum.INBOUND else "outbound",
            "timestamp": msg_record_orm.created_at,
            "sender_name": customer_orm.customer_name if msg_record_orm.message_type == models.MessageTypeEnum.INBOUND \
                      else (customer_orm.business.representative_name or customer_orm.business.business_name),
            "is_hidden": msg_record_orm.is_hidden,
            "source": msg_record_orm.source,
        })

    stmt_ai_draft_engagements = (
        select(models.Engagement)
        .where(models.Engagement.customer_id == customer_id)
        .where(models.Engagement.business_id == current_business.id)
        .where(models.Engagement.status == models.MessageStatusEnum.PENDING_REVIEW)
        .where(models.Engagement.ai_response.isnot(None))
        .where(models.Engagement.is_hidden == False)
        .where(models.Engagement.source.in_(["ai_response_engagement", "system_ai_draft", "customer_sms_reply_engagement"]))
        .order_by(models.Engagement.created_at.asc())
    )
    result_ai_drafts = await db.execute(stmt_ai_draft_engagements)
    ai_draft_engagements_orm = result_ai_drafts.scalars().all()

    for draft_eng_orm in ai_draft_engagements_orm:
        temp_message_list.append({
            "id": f"eng-ai-{draft_eng_orm.id}",
            "text": draft_eng_orm.ai_response,
            "type": models.MessageTypeEnum.AI_DRAFT.value,
            "status": draft_eng_orm.status.value if draft_eng_orm.status else models.MessageStatusEnum.PENDING_REVIEW.value,
            "direction": "outbound",
            "timestamp": draft_eng_orm.created_at,
            "sender_name": customer_orm.business.representative_name or customer_orm.business.business_name,
            "is_hidden": draft_eng_orm.is_hidden,
            "source": draft_eng_orm.source or "system_ai_draft",
        })

    temp_message_list.sort(key=lambda m: m["timestamp"] or datetime.min.replace(tzinfo=dt_timezone.utc))

    formatted_messages: List[schemas.ConversationMessage] = []
    for msg_data in temp_message_list:
        localized_timestamp = msg_data["timestamp"].astimezone(business_tz) if msg_data["timestamp"] else get_utc_now().astimezone(business_tz)
        formatted_messages.append(schemas.ConversationMessage(
            id=str(msg_data["id"]),
            text=msg_data["text"],
            type=models.MessageTypeEnum(msg_data["type"]),
            status=models.MessageStatusEnum(msg_data["status"]) if msg_data["status"] else None,
            direction=msg_data["direction"],
            timestamp=localized_timestamp,
            sender_name=msg_data["sender_name"],
            is_hidden=msg_data["is_hidden"],
            source=msg_data.get("source")
        ))

    stmt_conversation = (
        select(models.Conversation)
        .where(models.Conversation.customer_id == customer_orm.id)
        .where(models.Conversation.business_id == current_business.id)
        .order_by(desc(models.Conversation.last_message_at))
        .limit(1)
    )
    result_conversation = await db.execute(stmt_conversation)
    conversation_orm = result_conversation.scalar_one_or_none()
    conv_id_for_response = str(conversation_orm.id) if conversation_orm else str(uuid.uuid4())
    
    stmt_latest_appt_req = (
        select(models.AppointmentRequest)
        .where(models.AppointmentRequest.customer_id == customer_id)
        .where(models.AppointmentRequest.business_id == current_business.id)
        .order_by(desc(models.AppointmentRequest.updated_at))
        .limit(1)
    )
    result_latest_appt_req = await db.execute(stmt_latest_appt_req)
    latest_appointment_request_orm = result_latest_appt_req.scalar_one_or_none()
    
    latest_appointment_request_read: Optional[schemas.AppointmentRequestRead] = None
    draft_reply_for_appointment_action: Optional[str] = None

    if latest_appointment_request_orm:
        latest_appointment_request_read = schemas.AppointmentRequestRead.model_validate(latest_appointment_request_orm)
        actionable_statuses_for_draft = [
            AppointmentRequestStatusEnum.PENDING_OWNER_ACTION,
            AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE,
            AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL,
        ]
        if latest_appointment_request_orm.status in actionable_statuses_for_draft:
            try:
                ai_service_instance = AppointmentAIService(db=None)
                draft_intent = schemas.AppointmentIntent.OWNER_ACTION_CONFIRM 
                if latest_appointment_request_orm.status == AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE:
                    draft_intent = schemas.AppointmentIntent.OWNER_ACTION_SUGGEST_RESCHEDULE
                
                draft_reply_for_appointment_action = await ai_service_instance.draft_appointment_related_sms(
                    business=current_business, 
                    customer_name=customer_orm.customer_name,
                    intent_type=draft_intent,
                    time_details=latest_appointment_request_orm.parsed_requested_time_text or \
                                 (latest_appointment_request_orm.parsed_requested_datetime_utc.strftime('%a, %b %d @ %I:%M %p') if latest_appointment_request_orm.parsed_requested_datetime_utc else "the requested time"),
                    original_customer_request=latest_appointment_request_orm.original_message_text
                )
            except Exception as e_ai_draft:
                logger.error(f"History: Error generating general AI draft: {e_ai_draft}", exc_info=True)
                draft_reply_for_appointment_action = "Could not generate AI suggestion."

    return schemas.ConversationResponseSchema(
        customer=customer_read_dto,
        messages=formatted_messages,
        conversation_id=conv_id_for_response,
        latest_appointment_request=latest_appointment_request_read,
        draft_reply_for_appointment=draft_reply_for_appointment_action
    )


@router.post("/customer/{customer_id}/reply", response_model=schemas.MessageRead)
async def send_reply_to_customer_conversation(
    customer_id: int,
    payload: schemas.InboxReplyPayload,
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    settings: Settings = Depends(get_settings)
):
    logger.info(
        f"Reply: Attempting for customer {customer_id} by business '{current_business.business_name}' (ID: {current_business.id})."
    )

    customer = await db.get(models.Customer, customer_id)
    if not customer or customer.business_id != current_business.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found for this business.")

    # MessageService uses AsyncSession, so it's fine with 'db' (which is AsyncSession here)
    message_service = MessageService(db=db)
    # AppointmentAIService does not rely on a db session for parsing/drafting in the methods used here
    appointment_ai_service = AppointmentAIService(db=None) 

    message_type_for_db = models.MessageTypeEnum.OUTBOUND
    should_create_appointment_request = False

    if payload.is_appointment_proposal:
        message_type_for_db = models.MessageTypeEnum.APPOINTMENT_PROPOSAL
        should_create_appointment_request = True
    else:
        # This part uses appointment_ai_service which is fine (no db session needed for this call)
        ai_parsed_owner_message = await appointment_ai_service.parse_appointment_sms(
            payload.message, business=current_business, customer=customer, is_owner_message=True
        )
        if ai_parsed_owner_message.intent == schemas.AppointmentIntent.OWNER_PROPOSAL:
            message_type_for_db = models.MessageTypeEnum.APPOINTMENT_PROPOSAL
            should_create_appointment_request = True

    try:
        # Message creation uses async session, this is fine
        message_orm_instance = await message_service.create_message(
            customer_id=customer_id, business_id=current_business.id, content=payload.message,
            message_type=message_type_for_db, status=models.MessageStatusEnum.PENDING_SEND,
            sender_type=models.SenderTypeEnum.BUSINESS, source="owner_manual_reply"
        )
        # Note: message_service.create_message should handle its own commit/flush logic.
        # If it returns the instance, it's usually after it's been added and flushed/refreshed.

        if should_create_appointment_request:
            # For AppointmentService operations that use its internal synchronous self.db
            sync_db_session_for_appt: Session = next(get_db())
            try:
                # Instantiate AppointmentService with the synchronous session
                appointment_service_sync_instance = AppointmentService(db=sync_db_session_for_appt)
                
                # Call the async method. Its helper methods (_check_availability_and_conflicts, 
                # _create_appointment_request_internal) will use the self.db 
                # (which is now sync_db_session_for_appt) correctly.
                await appointment_service_sync_instance.create_business_initiated_appointment_proposal(
                    business=current_business, 
                    customer=customer,
                    owner_message_text=payload.message, 
                    outbound_message_id=message_orm_instance.id
                )
                logger.info(f"Reply: Created AppointmentRequest for business proposal. Message ID: {message_orm_instance.id}")
                # Refresh using the async session if message_orm_instance is tied to it
                await db.refresh(message_orm_instance) 
            finally:
                sync_db_session_for_appt.close() # Ensure the synchronous session is closed

        can_send_sms = True
        if customer.sms_opt_in_status == OptInStatus.OPTED_OUT:
            can_send_sms = False
            logger.warning(f"Reply: SMS for Message ID {message_orm_instance.id} blocked, customer {customer.id} opted out.")
            message_orm_instance.status = models.MessageStatusEnum.FAILED
            message_orm_instance.message_metadata = {"failure_reason": "Customer opted out"}
        
        if can_send_sms and customer.phone and (current_business.twilio_number or current_business.messaging_service_sid):
            try:
                sync_db_for_twilio: Optional[Session] = None
                try:
                    sync_db_for_twilio = next(get_db()) 
                    twilio_service_instance = TwilioService(db=sync_db_for_twilio)
                    sms_sent_sid = await twilio_service_instance.send_sms(
                        to=customer.phone, message_body=payload.message,
                        business=current_business, customer=customer, is_direct_reply=True
                    )
                finally:
                    if sync_db_for_twilio:
                        sync_db_for_twilio.close()
                
                if sms_sent_sid:
                    message_orm_instance.twilio_message_sid = sms_sent_sid
                    message_orm_instance.status = models.MessageStatusEnum.SENT
                    message_orm_instance.sent_at = get_utc_now()
                else:
                    message_orm_instance.status = models.MessageStatusEnum.FAILED
                    message_orm_instance.message_metadata = {"failure_reason": "Twilio send returned no SID"}
            except HTTPException as e_http:
                message_orm_instance.status = models.MessageStatusEnum.FAILED
                message_orm_instance.message_metadata = {"failure_reason": f"Twilio HTTP Error: {e_http.detail}"}
                logger.error(f"Reply: HTTPException from Twilio: {e_http.detail}", exc_info=False)
            except Exception as e_sms:
                message_orm_instance.status = models.MessageStatusEnum.FAILED
                message_orm_instance.message_metadata = {"failure_reason": f"Unexpected SMS error: {str(e_sms)}"}
                logger.error(f"Reply: Error sending SMS: {e_sms}", exc_info=True)
        elif not can_send_sms:
            pass 
        else: 
            message_orm_instance.status = models.MessageStatusEnum.FAILED
            message_orm_instance.message_metadata = {"failure_reason": "Missing customer phone or Twilio config"}
        
        db.add(message_orm_instance)
        await db.commit() 
        await db.refresh(message_orm_instance)

        return schemas.MessageRead.model_validate(message_orm_instance)

    except HTTPException as e:
        await db.rollback()
        raise e
    except ValueError as ve:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        await db.rollback()
        logger.error(f"Reply: Unexpected error processing owner's reply for customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process message reply due to an internal error.")

schemas.ConversationResponseSchema.model_rebuild()
schemas.CustomerRead.model_rebuild()
schemas.AppointmentRequestRead.model_rebuild()