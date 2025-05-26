# File: backend/app/services/instant_nudge_service.py
# Provides AI-powered SMS generation and handling logic for the Instant Nudge feature.
# Includes generation of personalized messages and logic to send or schedule them.

# --- Standard Imports ---
import logging
import json
import uuid
# import traceback # Not used
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

# --- Pydantic and SQLAlchemy Imports ---
from sqlalchemy.orm import Session 
from sqlalchemy.ext.asyncio import AsyncSession 
from sqlalchemy import select
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool # ADDED
import pytz
import openai

# --- App Specific Imports ---
from app.models import (
    BusinessProfile,
    Message,
    # Engagement, # Not used in this version of the file
    Customer,
    # Conversation, # Not used in this version of the file
    MessageTypeEnum,
    OptInStatus,
    MessageStatusEnum
) #
from app.celery_tasks import process_scheduled_message_task
from app.services.style_service import get_style_guide 
from app.services.twilio_service import TwilioService
from app.services.appointment_service import AppointmentService
from app.schemas import InstantNudgeSendPayload 
from app.services.message_service import get_conversation_id 
from app.database import get_db # For obtaining sync session

logger = logging.getLogger(__name__)

async def generate_instant_nudge(topic: str, business_id: int, db: AsyncSession) -> Dict[str, Any]: # MODIFIED: db to AsyncSession
    """Generate a message that perfectly matches the business owner's style"""
    
    business_stmt = select(BusinessProfile).filter(BusinessProfile.id == business_id)
    business_result = await db.execute(business_stmt) # MODIFIED: await
    business = business_result.scalar_one_or_none()

    if not business:
        raise ValueError(f"Business not found for ID: {business_id}")

    style_guide_data = await get_style_guide(business_id, db) # Assuming get_style_guide is async

    style_elements = {
        'phrases': '\n'.join(style_guide_data.get('key_phrases', [])),
        'patterns': '\n'.join(style_guide_data.get('message_patterns', {}).get('patterns', [])),
        'personality': '\n'.join(style_guide_data.get('personality_traits', [])),
        'special': json.dumps(style_guide_data.get('special_elements', {}), indent=2),
        'style_notes': json.dumps(style_guide_data.get('style_notes', {}), indent=2)
    }

    prompt = f"""
    You are {business.representative_name or 'the owner'} from {business.business_name}.
    Write a short, friendly SMS message (under 160 chars) about: '{topic}'
    Use the placeholder {{{{customer_name}}}} where the customer's name should go.

    YOUR UNIQUE VOICE:
    Common Phrases You Use:
    {style_elements['phrases']}
    How You Structure Messages:
    {style_elements['patterns']}
    Your Personality Traits:
    {style_elements['personality']}
    Your Special Elements:
    {style_elements['special']}
    Your Style Notes:
    {style_elements['style_notes']}

    CRITICAL RULES:
    1. Write EXACTLY as if you are this person, matching their unique style.
    2. Use their exact communication patterns and phrases naturally.
    3. Keep message under 160 characters.
    4. MUST include the placeholder {{{{customer_name}}}}.
    5. End appropriately (e.g., with representative name if available).

    Write your message:
    """

    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # MODIFIED: Run synchronous OpenAI call in a thread pool
        response = await run_in_threadpool(
            client.chat.completions.create, # Pass the callable
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at matching exact communication styles for SMS."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        message_content = response.choices[0].message.content.strip()

        if "{{customer_name}}" not in message_content:
             logger.warning("Generated message missing {{customer_name}} placeholder. Attempting to add it.")
             message_content = f"Hi {{{{customer_name}}}}, {message_content}"

        return {"message": message_content}

    except Exception as e:
        logger.error(f"OpenAI API call failed during nudge generation: {e}", exc_info=True)
        raise Exception(f"AI message generation failed: {e}")


async def handle_instant_nudge_batch(
    db: AsyncSession,  # MODIFIED: Changed from Session to AsyncSession
    payload: InstantNudgeSendPayload,
    business: BusinessProfile,
) -> Dict[str, Any]:
    business_id_for_logging = business.id

    if not payload.customer_ids:
        logger.warning("handle_instant_nudge_batch called with empty customer_ids list.")
        return {"processed_message_ids": [], "sent_count": 0, "scheduled_count": 0, "failed_count": 0, "appointment_proposals_created": 0}

    processed_message_ids = []
    sent_count = 0
    scheduled_count = 0
    failed_count = 0
    appointment_proposals_created = 0

    now_utc = datetime.now(timezone.utc)
    is_scheduling = False
    scheduled_time_utc: Optional[datetime] = None

    if payload.send_datetime_utc: # Validator in schema ensures this is UTC if present
        if payload.send_datetime_utc > (now_utc - timedelta(minutes=1)): # Check if it's effectively in the future
            is_scheduling = True
            scheduled_time_utc = payload.send_datetime_utc
            logger.info(f"Batch will be scheduled for {scheduled_time_utc.isoformat()} UTC.")
        else:
            logger.info(f"Scheduled time {payload.send_datetime_utc.isoformat()} is in the past. Sending immediately.")

    # CORRECTED: Logic for message_type_to_set
    if payload.is_appointment_proposal:
        message_type_to_set = MessageTypeEnum.APPOINTMENT_PROPOSAL
    elif is_scheduling:
        message_type_to_set = MessageTypeEnum.SCHEDULED_MESSAGE
    else:
        message_type_to_set = MessageTypeEnum.OUTBOUND # Use the existing OUTBOUND member

    for customer_id in payload.customer_ids:
        message_record_id: Optional[int] = None
        customer: Optional[Customer] = None
        try:
            stmt_customer = select(Customer).filter(Customer.id == customer_id, Customer.business_id == business_id_for_logging)
            result_customer = await db.execute(stmt_customer) # MODIFIED: await
            customer = result_customer.scalar_one_or_none()

            if not customer:
                logger.warning(f"Skipping unknown customer_id={customer_id} for business_id={business_id_for_logging} in batch.")
                failed_count += 1
                continue
            
            if customer.sms_opt_in_status != OptInStatus.OPTED_IN: #
                logger.info(f"Skipping customer_id={customer_id} (Name: {customer.customer_name}) due to consent status: {customer.sms_opt_in_status.value}.")
                failed_count += 1
                continue
            if not customer.phone:
                logger.warning(f"Skipping customer_id={customer_id} (Name: {customer.customer_name}) due to missing phone number.")
                failed_count += 1
                continue

            personalized_message = payload.message.replace("{{customer_name}}", customer.customer_name or "there")
            
            conversation_id_str = await get_conversation_id(db, business_id_for_logging, customer.id) # Assumes get_conversation_id is async

            message_status_enum = MessageStatusEnum.SCHEDULED if is_scheduling else MessageStatusEnum.PENDING_SEND #

            message_obj = Message(
                conversation_id=uuid.UUID(conversation_id_str) if conversation_id_str else None,
                customer_id=customer.id,
                business_id=business_id_for_logging,
                content=personalized_message,
                sender_type="business", 
                message_type=message_type_to_set,
                status=message_status_enum,
                created_at=now_utc,
                updated_at=now_utc,
                scheduled_send_at=scheduled_time_utc if is_scheduling else None,
                message_metadata={
                    'source': 'instant_nudge',
                    'is_appointment_proposal': payload.is_appointment_proposal,
                    'nudge_payload_business_id': payload.business_id 
                }
            )
            db.add(message_obj)
            await db.flush() # MODIFIED: await
            message_record_id = message_obj.id

            if payload.is_appointment_proposal:
                if not payload.proposed_datetime_utc:
                     logger.error(f"CRITICAL: Appointment proposal for cust {customer_id} missing proposed_datetime_utc (should be caught by schema validator).")
                     failed_count += 1
                     # Consider how to handle message_obj if AP creation fails. Mark message as failed?
                else:
                    sync_session_for_appt_svc: Optional[Session] = None
                    try:
                        sync_session_for_appt_svc = next(get_db())
                        appointment_service = AppointmentService(db=sync_session_for_appt_svc)
                        
                        # create_business_initiated_appointment_proposal is async but calls sync internal methods.
                        # It should internally use run_in_threadpool for its sync DB calls.
                        # If create_business_initiated_appointment_proposal itself is not refactored to use run_in_threadpool for its internal sync calls,
                        # then this call itself needs to be wrapped.
                        await appointment_service.create_business_initiated_appointment_proposal(
                            db_async_for_refresh=db, 
                            business=business, 
                            customer=customer,
                            owner_message_text=personalized_message,
                            outbound_message_id=message_obj.id,
                            proposed_datetime_utc=payload.proposed_datetime_utc,
                            appointment_notes=payload.appointment_notes,
                        )
                        appointment_proposals_created += 1
                        logger.info(f"Successfully created AppointmentRequest linked to Message ID {message_obj.id} for customer {customer_id}.")
                    except Exception as ar_exc:
                        logger.error(f"Failed to create AppointmentRequest for Message ID {message_obj.id} (Customer {customer_id}): {ar_exc}. Message send/schedule will still proceed.", exc_info=True)
                    finally:
                        if sync_session_for_appt_svc:
                            sync_session_for_appt_svc.close()


            if is_scheduling and scheduled_time_utc:
                process_scheduled_message_task.apply_async(args=[message_obj.id], eta=scheduled_time_utc)
                processed_message_ids.append(message_obj.id)
                scheduled_count += 1
                logger.info(f"✅ Successfully scheduled Message ID {message_obj.id} for customer {customer_id} at {scheduled_time_utc.isoformat()} UTC.")
            else: 
                sync_db_for_twilio: Optional[Session] = None
                message_sid: Optional[str] = None
                try:
                    sync_db_for_twilio = next(get_db())
                    twilio_service_instance = TwilioService(db=sync_db_for_twilio)
                    
                    # Assuming twilio_service_instance.send_sms is async due to await,
                    # but TwilioService itself might be initialized with a sync session.
                    # If send_sms is blocking, it should be in run_in_threadpool.
                    message_sid = await twilio_service_instance.send_sms(
                        to=customer.phone, 
                        message_body=personalized_message,
                        business=business, 
                        customer=customer,
                        is_direct_reply=True 
                    )
                    
                    if message_sid:
                        message_obj.status = MessageStatusEnum.SENT #
                        message_obj.twilio_message_sid = message_sid
                        message_obj.sent_at = datetime.now(timezone.utc)
                        sent_count += 1
                        logger.info(f"✅ Successfully sent immediate SMS for Message ID {message_obj.id} (Customer {customer_id}). SID: {message_sid}")
                    else: 
                        message_obj.status = MessageStatusEnum.FAILED #
                        if isinstance(message_obj.message_metadata, dict):
                             message_obj.message_metadata['failure_reason'] = "Twilio did not return a Message SID."
                        failed_count += 1
                        logger.error(f"❌ Failed to send immediate SMS for Message ID {message_obj.id} (Customer {customer_id}): No SID returned.")
                    
                except HTTPException as http_send_err:
                    message_obj.status = MessageStatusEnum.FAILED #
                    if isinstance(message_obj.message_metadata, dict):
                        message_obj.message_metadata['failure_reason'] = f"Twilio HTTP Error: {http_send_err.detail}"
                    failed_count += 1
                    logger.error(f"❌ HTTP error sending immediate SMS for Message ID {message_record_id or 'N/A'} (Customer {customer_id if customer else 'N/A'}): {http_send_err.status_code} - {http_send_err.detail}")
                except Exception as send_err:
                     message_obj.status = MessageStatusEnum.FAILED #
                     if isinstance(message_obj.message_metadata, dict):
                        message_obj.message_metadata['failure_reason'] = f"General send error: {str(send_err)}"
                     failed_count += 1
                     logger.error(f"❌ Failed to send immediate SMS for Message ID {message_record_id or 'N/A'} (Customer {customer_id if customer else 'N/A'}): {send_err}", exc_info=True)
                finally:
                    if sync_db_for_twilio:
                        sync_db_for_twilio.close()
                
                db.add(message_obj) # Ensure updated message_obj is part of the session
                processed_message_ids.append(message_obj.id)

        except Exception as per_customer_err:
             failed_count += 1
             logger.error(f"❌ Unexpected error processing customer_id={customer_id} in batch: {per_customer_err}", exc_info=True)
    
    try:
        await db.commit() # MODIFIED: await
    except Exception as commit_err:
        logger.error(f"Critical error during final commit in handle_instant_nudge_batch for Business ID {business_id_for_logging}: {commit_err}", exc_info=True)
        try:
            await db.rollback() # MODIFIED: await
        except Exception as rb_err:
            logger.error(f"Failed to rollback after commit error: {rb_err}", exc_info=True)
        return { 
            "message": f"Batch processing failed during final commit. Error: {commit_err}",
            "processed_message_ids": [], "sent_count": 0, "scheduled_count": 0, 
            "failed_count": len(payload.customer_ids), "appointment_proposals_created": 0 
        }

    logger.info(f"Batch processing summary for business {business_id_for_logging}: Sent={sent_count}, Scheduled={scheduled_count}, Failed/Skipped={failed_count}, Appointment Proposals Created={appointment_proposals_created}")
    return {
        "message": f"Batch processing summary: Sent={sent_count}, Scheduled={scheduled_count}, Failed/Skipped={failed_count}, Appointment Proposals Created={appointment_proposals_created}",
        "processed_message_ids": processed_message_ids,
        "sent_count": sent_count,
        "scheduled_count": scheduled_count,
        "failed_count": failed_count,
        "appointment_proposals_created": appointment_proposals_created
    }