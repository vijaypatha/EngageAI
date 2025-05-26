# backend/app/services/appointment_service.py
import logging
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum as PythonEnum

from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import desc, func, case, and_, String, select as sql_select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
import pytz
from datetime import datetime, time, timedelta, date, timezone as dt_timezone

from app import models, schemas
from app.database import get_db
from app.models import (
    AppointmentAvailability,
    AppointmentRequest as AppointmentRequestModel,
    AppointmentRequestStatusEnum,
    AppointmentRequestSourceEnum,
    BusinessProfile as BusinessProfileModel,
    Customer as CustomerModel,
    Message as MessageModel,
    MessageTypeEnum,
    MessageStatusEnum,
    SenderTypeEnum,
    OptInStatus,
)
from app.schemas import (
    AppointmentAvailabilityCreate,
    AppointmentAvailabilityUpdate,
    AppointmentRequestCreateInternal,
    AppointmentAIResponse,
    AppointmentIntent as AppointmentIntentSchema,
    AppointmentRequestStatusUpdateByOwner,
)
from app.services.appointment_ai_service import AppointmentAIService
from app.services.twilio_service import TwilioService
from app.celery_tasks import schedule_appointment_reminder_task, schedule_appointment_thank_you_task
from app.timezone_utils import (
    get_utc_now,
    get_business_timezone,
)
from app.config import Settings

logger = logging.getLogger(__name__)

DAY_OF_WEEK_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}
ARBITRARY_EPOCH_DATE_MONDAY = date(1970, 1, 5)

def get_arbitrary_date_for_day(day_of_week_str: str) -> date:
    day_offset = DAY_OF_WEEK_MAP.get(day_of_week_str.lower(), 0)
    return ARBITRARY_EPOCH_DATE_MONDAY + timedelta(days=day_offset)


class AppointmentService:
    def __init__(self, db: Session):
        self.db = db
        self.appointment_ai_service = AppointmentAIService(db=db)

    def _parse_and_convert_availability_time(
        self,
        datetime_iso_str: str,
        day_of_week_str: str,
        business_timezone_str: str
    ) -> datetime:
        try:
            local_dt_obj = datetime.fromisoformat(datetime_iso_str.replace('Z', '+00:00'))
        except ValueError as e:
            logger.error(f"Invalid ISO format for availability time string: {datetime_iso_str}. Error: {e}")
            raise ValueError(f"Invalid ISO format for availability time string: {datetime_iso_str}.")

        arbitrary_date = get_arbitrary_date_for_day(day_of_week_str)
        business_tz = get_business_timezone(business_timezone_str)

        if local_dt_obj.tzinfo is None:
            local_dt_obj = business_tz.localize(local_dt_obj)
        else:
            local_dt_obj = local_dt_obj.astimezone(business_tz)

        time_component = local_dt_obj.time()
        effective_local_dt = datetime.combine(arbitrary_date, time_component, tzinfo=business_tz)
        return effective_local_dt.astimezone(dt_timezone.utc)

    def create_availability(self, business_id: int, availability_data: schemas.AppointmentAvailabilityCreate) -> models.AppointmentAvailability:
        logger.info(f"SERVICE: Creating availability for business_id: {business_id}, data: {availability_data.model_dump(by_alias=True)}")
        business = self.db.query(BusinessProfileModel).filter(BusinessProfileModel.id == business_id).first()
        if not business:
            raise ValueError(f"Business with id {business_id} not found.")

        business_tz_str = business.timezone
        start_time_utc = self._parse_and_convert_availability_time(availability_data.start_time_iso, availability_data.day_of_week, business_tz_str)
        end_time_utc = self._parse_and_convert_availability_time(availability_data.end_time_iso, availability_data.day_of_week, business_tz_str)

        if start_time_utc >= end_time_utc:
            raise ValueError("Start time must be before end time.")

        db_availability = models.AppointmentAvailability(
            **availability_data.model_dump(exclude={"start_time_iso", "end_time_iso"}),
            start_time=start_time_utc,
            end_time=end_time_utc,
            business_id=business_id,
            created_at=get_utc_now(),
            updated_at=get_utc_now()
        )
        self.db.add(db_availability)
        self.db.commit()
        self.db.refresh(db_availability)
        return db_availability

    def _check_availability_and_conflicts(
        self, business: BusinessProfileModel, requested_datetime_utc: datetime,
        appointment_request_id_to_exclude: Optional[int] = None
    ) -> Tuple[bool, str, Optional[models.AppointmentAvailability]]:
        duration_minutes = business.default_appointment_duration_minutes
        logger.info(f"SERVICE (sync _check_availability): Business ID: {business.id}, ReqDateTimeUTC: {requested_datetime_utc.isoformat()}, ExcludeReqID: {appointment_request_id_to_exclude}, Duration: {duration_minutes}m")

        business_tz = get_business_timezone(business.timezone)
        requested_dt_local = requested_datetime_utc.astimezone(business_tz)

        day_of_week_str_for_requested_dt = requested_dt_local.strftime('%A')
        arbitrary_date_for_requested_dt = get_arbitrary_date_for_day(day_of_week_str_for_requested_dt)

        requested_time_component_utc = requested_datetime_utc.time()
        comparable_request_start_utc = datetime.combine(arbitrary_date_for_requested_dt, requested_time_component_utc, tzinfo=dt_timezone.utc)
        comparable_request_end_utc = comparable_request_start_utc + timedelta(minutes=duration_minutes)

        active_rules_for_day = self.db.query(models.AppointmentAvailability).filter(
            models.AppointmentAvailability.business_id == business.id,
            func.lower(models.AppointmentAvailability.day_of_week) == day_of_week_str_for_requested_dt.lower(),
            models.AppointmentAvailability.is_active == True
        ).all()

        availability_rule_matched = None
        is_flexible_coordinator_style_for_day = False
        if not active_rules_for_day:
            is_flexible_coordinator_style_for_day = True
        else:
            for rule in active_rules_for_day:
                if rule.start_time <= comparable_request_start_utc and comparable_request_end_utc <= rule.end_time:
                    availability_rule_matched = rule
                    break
            if not availability_rule_matched:
                return False, f"Requested time {requested_dt_local.strftime('%I:%M %p')} on {day_of_week_str_for_requested_dt.title()} is outside defined available hours or slot duration exceeds rule.", None

        slot_start_utc = requested_datetime_utc
        slot_end_utc = slot_start_utc + timedelta(minutes=duration_minutes)

        conflict_query = self.db.query(AppointmentRequestModel.id).filter(
            AppointmentRequestModel.business_id == business.id,
            AppointmentRequestModel.status.in_([
                AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER,
                AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL
            ]),
            AppointmentRequestModel.confirmed_datetime_utc.isnot(None),
            AppointmentRequestModel.confirmed_datetime_utc < slot_end_utc,
            (AppointmentRequestModel.confirmed_datetime_utc + timedelta(minutes=business.default_appointment_duration_minutes)) > slot_start_utc
        )

        if appointment_request_id_to_exclude:
            conflict_query = conflict_query.filter(AppointmentRequestModel.id != appointment_request_id_to_exclude)

        conflicting_appointment = conflict_query.first()
        if conflicting_appointment:
            return False, f"Requested time slot {requested_dt_local.strftime('%I:%M %p')} on {day_of_week_str_for_requested_dt.title()} is already booked.", availability_rule_matched

        return True, "Slot is available." if not is_flexible_coordinator_style_for_day else "Slot appears open (Flexible Coordinator style, owner to confirm).", availability_rule_matched

    def _create_appointment_request_internal(self, appointment_data: schemas.AppointmentRequestCreateInternal) -> AppointmentRequestModel:
        db_req = AppointmentRequestModel(**appointment_data.model_dump())
        db_req.created_at = get_utc_now()
        db_req.updated_at = get_utc_now()
        self.db.add(db_req)
        self.db.commit()
        self.db.refresh(db_req)
        logger.debug(f"SERVICE (sync _create_internal): ID: {db_req.id}, Status: {db_req.status.value if db_req.status else 'N/A'}")
        return db_req

    async def get_ai_suggested_slots_for_request(
        self, business: BusinessProfileModel, customer_request_text: Optional[str],
        customer: Optional[CustomerModel] = None, num_suggestions: int = 2, search_days_range: int = 7,
        reference_datetime_utc: Optional[datetime] = None, original_request_status: Optional[AppointmentRequestStatusEnum] = None,
        original_request_confirmed_utc: Optional[datetime] = None, original_request_parsed_utc: Optional[datetime] = None,
        existing_confirmed_utc: Optional[datetime] = None,
        existing_confirmed_message_prefix: Optional[str] = "Customer confirmed this time. Slot status:"
    ) -> List[Dict[str, Any]]:
        logger.info(f"SERVICE (async get_ai_suggested_slots): Business ID: {business.id}, CustReq: '{customer_request_text}', NumSuggest: {num_suggestions}, ExistingConfirmedUTC: {existing_confirmed_utc}")
        suggested_slots: List[Dict[str, Any]] = []
        business_tz = get_business_timezone(business.timezone)
        current_moment_utc = get_utc_now()

        if existing_confirmed_utc and existing_confirmed_utc > current_moment_utc:
            is_available, status_message, _ = await run_in_threadpool(
                self._check_availability_and_conflicts, business, existing_confirmed_utc
            )
            slot_status_message_combined = f"{existing_confirmed_message_prefix} {status_message}"
            suggested_slots.append({"slot_utc": existing_confirmed_utc, "status_message": slot_status_message_combined})
            logger.info(f"Added existing confirmed slot for Business ID {business.id}: {existing_confirmed_utc}, Status: {slot_status_message_combined}")
            if len(suggested_slots) >= num_suggestions:
                return suggested_slots

        effective_ref_utc = original_request_parsed_utc or reference_datetime_utc or current_moment_utc
        start_search_dt_local: datetime
        business_day_start_hour = getattr(business, 'default_business_day_start_hour', 9)
        business_day_end_hour = getattr(business, 'default_business_day_end_hour', 17)
        time_slot_increment_minutes = business.default_appointment_duration_minutes

        if original_request_status == AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL and original_request_confirmed_utc:
            next_day_date_local = (original_request_confirmed_utc.astimezone(business_tz) + timedelta(days=1)).date()
            start_search_dt_local_naive = datetime.combine(next_day_date_local, time(business_day_start_hour, 0))
            start_search_dt_local = business_tz.localize(start_search_dt_local_naive, is_dst=None)
        elif customer_request_text:
            initial_parsed_target_utc = await self.appointment_ai_service.parse_owner_manual_time_suggestion(
                owner_text_suggestion=customer_request_text, business=business,
                customer_original_request_text=customer_request_text, reference_datetime_utc=effective_ref_utc
            )
            current_ref_dt_local_for_decision = effective_ref_utc.astimezone(business_tz)
            if initial_parsed_target_utc and initial_parsed_target_utc > effective_ref_utc:
                start_search_dt_local = initial_parsed_target_utc.astimezone(business_tz)
            else:
                if initial_parsed_target_utc:
                     logger.warning(f"SERVICE: AI parsed '{customer_request_text}' to {initial_parsed_target_utc.isoformat()}, not after ref_utc {effective_ref_utc.isoformat()}. Finding next available.")
                start_search_dt_local = current_ref_dt_local_for_decision
                if start_search_dt_local < current_moment_utc.astimezone(business_tz):
                    start_search_dt_local = current_moment_utc.astimezone(business_tz)

                start_search_dt_local = (start_search_dt_local + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                if start_search_dt_local.time() >= time(business_day_end_hour, 0) or start_search_dt_local.hour < business_day_start_hour :
                     next_day_date_local = (start_search_dt_local.date() + timedelta(days=1))
                     start_search_dt_local_naive = datetime.combine(next_day_date_local, time(business_day_start_hour, 0))
                     start_search_dt_local = business_tz.localize(start_search_dt_local_naive, is_dst=None)
        else:
             start_search_dt_local = effective_ref_utc.astimezone(business_tz)
             if start_search_dt_local < current_moment_utc.astimezone(business_tz): start_search_dt_local = current_moment_utc.astimezone(business_tz)
             start_search_dt_local = (start_search_dt_local + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
             if start_search_dt_local.time() >= time(business_day_end_hour, 0) or start_search_dt_local.hour < business_day_start_hour :
                next_day_date_local = (start_search_dt_local.date() + timedelta(days=1))
                start_search_dt_local_naive = datetime.combine(next_day_date_local, time(business_day_start_hour, 0))
                start_search_dt_local = business_tz.localize(start_search_dt_local_naive, is_dst=None)

        current_search_day_loop_start_local = start_search_dt_local
        for day_offset in range(search_days_range):
            if len(suggested_slots) >= num_suggestions: break
            current_search_date_local = (current_search_day_loop_start_local.date() + timedelta(days=day_offset))

            current_potential_time_local_val = time(business_day_start_hour, 0)
            if day_offset == 0 and current_search_day_loop_start_local.date() == current_search_date_local:
                if current_search_day_loop_start_local.time() > current_potential_time_local_val:
                    current_potential_time_local_val = current_search_day_loop_start_local.time()
                    if time_slot_increment_minutes > 0 and current_potential_time_local_val.minute % time_slot_increment_minutes != 0:
                        current_hour = current_potential_time_local_val.hour
                        current_minute = current_potential_time_local_val.minute
                        
                        slots_passed = current_minute // time_slot_increment_minutes
                        next_slot_minute_offset = (slots_passed + 1) * time_slot_increment_minutes
                        
                        new_minute = next_slot_minute_offset % 60
                        hour_increment = next_slot_minute_offset // 60
                        new_hour = (current_hour + hour_increment)
                        
                        if new_hour >= 24 : 
                            continue 

                        current_potential_time_local_val = time(new_hour, new_minute, 0, 0)

                        if current_potential_time_local_val >= time(business_day_end_hour, 0):
                             continue


            while current_potential_time_local_val < time(business_day_end_hour, 0):
                if len(suggested_slots) >= num_suggestions: break
                potential_slot_local_dt_naive = datetime.combine(current_search_date_local, current_potential_time_local_val)
                try:
                    potential_slot_aware_local_dt = business_tz.localize(potential_slot_local_dt_naive, is_dst=None)
                except pytz.exceptions.AmbiguousTimeError:
                    potential_slot_aware_local_dt = business_tz.localize(potential_slot_local_dt_naive, is_dst=True)
                except pytz.exceptions.NonExistentTimeError:
                     logger.debug(f"Skipping non-existent time {potential_slot_local_dt_naive.isoformat()} in timezone {business_tz.zone}")
                     current_potential_time_local_val = (datetime.combine(date.min, current_potential_time_local_val) + timedelta(minutes=time_slot_increment_minutes)).time(); continue

                potential_slot_utc = potential_slot_aware_local_dt.astimezone(dt_timezone.utc)

                if existing_confirmed_utc and potential_slot_utc == existing_confirmed_utc:
                    current_potential_time_local_val = (datetime.combine(date.min, current_potential_time_local_val) + timedelta(minutes=time_slot_increment_minutes)).time(); continue

                if potential_slot_utc <= get_utc_now() + timedelta(minutes=5):
                    current_potential_time_local_val = (datetime.combine(date.min, current_potential_time_local_val) + timedelta(minutes=time_slot_increment_minutes)).time(); continue

                is_available, status_message, _ = await run_in_threadpool(
                    self._check_availability_and_conflicts, business, potential_slot_utc
                )
                if is_available:
                    suggested_slots.append({"slot_utc": potential_slot_utc, "status_message": status_message })
                    if len(suggested_slots) >= num_suggestions: break
                current_potential_time_local_val = (datetime.combine(date.min, current_potential_time_local_val) + timedelta(minutes=time_slot_increment_minutes)).time()
            if len(suggested_slots) >= num_suggestions: break
        return suggested_slots

    async def create_request_from_sms_intent(
        self, business: BusinessProfileModel, customer: CustomerModel,
        sms_body: str, inbound_message_id: int,
        inbound_message_created_at: Optional[datetime] = None
    ) -> Optional[AppointmentRequestModel]:
        logger.info(f"SERVICE (create_request_from_sms_intent): BizID {business.id}, CustID {customer.id}, SMS: '{sms_body}'")

        last_business_message_text: Optional[str] = None
        if self.db:
            def _get_last_business_message_sync() -> Optional[str]:
                query_stmt = self.db.query(MessageModel.content) \
                    .filter(
                        MessageModel.business_id == business.id,
                        MessageModel.customer_id == customer.id,
                        MessageModel.sender_type == SenderTypeEnum.BUSINESS
                    )
                if inbound_message_created_at:
                     query_stmt = query_stmt.filter(MessageModel.created_at < inbound_message_created_at)
                else:
                    logger.warning("inbound_message_created_at not provided for create_request_from_sms_intent. Last business message context might be imprecise if message IDs are not strictly ordered by time.")
                    if isinstance(inbound_message_id, int):
                         query_stmt = query_stmt.filter(MessageModel.id < inbound_message_id) # type: ignore

                last_msg_content_tuple = query_stmt.order_by(desc(MessageModel.created_at)).first()
                return last_msg_content_tuple[0] if last_msg_content_tuple else None

            last_business_message_text = await run_in_threadpool(_get_last_business_message_sync)
            if last_business_message_text:
                logger.info(f"Context for AI in create_request_from_sms_intent: Last business message was: '{last_business_message_text[:100]}...'")

        ai_response: schemas.AppointmentAIResponse = await self.appointment_ai_service.parse_appointment_sms(
            sms_body, business, customer,
            last_business_message_text=last_business_message_text
        )

        ai_intent_val = ai_response.intent.value if isinstance(ai_response.intent, PythonEnum) else str(ai_response.intent)
        logger.info(f"AI Response in create_request_from_sms_intent: Intent='{ai_intent_val}', RequiresClarification='{ai_response.requires_clarification}', Details='{ai_response.parsed_intent_details}'")

        if ai_response.intent not in [
            AppointmentIntentSchema.REQUEST_APPOINTMENT,
            AppointmentIntentSchema.CONFIRMATION,
            AppointmentIntentSchema.RESCHEDULE
        ] or ai_response.intent == AppointmentIntentSchema.ERROR_PARSING:
            if ai_response.intent == AppointmentIntentSchema.NOT_APPOINTMENT or \
               (ai_response.intent == AppointmentIntentSchema.CONFIRMATION and not ai_response.datetime_preferences and not ai_response.requires_clarification):
                     logger.info(f"Non-actionable AI intent '{ai_intent_val}' for creating request. No request created.")
                     return None

        parsed_time_utc: Optional[datetime] = None
        parsed_time_text: str = sms_body

        current_status = AppointmentRequestStatusEnum.PENDING_OWNER_ACTION
        ai_suggested_reply_for_request: Optional[str] = None
        confirmed_datetime_for_request: Optional[datetime] = None
        details_for_request_parts: List[str] = [f"AI Intent: {ai_intent_val}. Confidence: {ai_response.confidence_score or 'N/A'}."]
        if ai_response.parsed_intent_details:
            details_for_request_parts.append(f"AI Details: {ai_response.parsed_intent_details}.")

        if ai_response.datetime_preferences and ai_response.datetime_preferences[0].start_time:
            pref = ai_response.datetime_preferences[0]
            parsed_time_utc = pref.start_time
            parsed_time_text = pref.datetime_str or \
                               (f"AI parsed: {pref.start_time.astimezone(get_business_timezone(business.timezone)).strftime('%a, %b %d %I:%M %p %Z')}"
                                if parsed_time_utc else "Time TBD")
            details_for_request_parts.append(f"Parsed Time: {parsed_time_text} (UTC: {parsed_time_utc.isoformat() if parsed_time_utc else 'N/A'}).")

            if ai_response.intent == AppointmentIntentSchema.CONFIRMATION and not ai_response.requires_clarification:
                current_status = AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL
                confirmed_datetime_for_request = parsed_time_utc
                logger.info(f"Contextual confirmation by AI for {parsed_time_text}. Status: CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL.")
            else:
                if parsed_time_utc:
                    is_available, availability_msg, _ = await run_in_threadpool(self._check_availability_and_conflicts, business, parsed_time_utc)
                    details_for_request_parts.append(f"Availability: {availability_msg}.")
                    if not is_available:
                        ai_suggested_reply_for_request = ai_response.clarification_question or f"The time {parsed_time_text} is not available. {availability_msg}"
                    elif ai_response.requires_clarification:
                        ai_suggested_reply_for_request = ai_response.clarification_question
                elif ai_response.requires_clarification:
                    ai_suggested_reply_for_request = ai_response.clarification_question

        elif ai_response.requires_clarification:
            ai_suggested_reply_for_request = ai_response.clarification_question
            details_for_request_parts.append("AI requires clarification.")

        if ai_response.failure_reason:
            details_for_request_parts.append(f"AI Failure: {ai_response.failure_reason}.")

        final_details = " ".join(details_for_request_parts)
        
        create_req_condition = (
            current_status != AppointmentRequestStatusEnum.PENDING_OWNER_ACTION or \
            parsed_time_utc is not None or \
            ai_suggested_reply_for_request is not None or \
            ai_response.intent in [
                AppointmentIntentSchema.REQUEST_APPOINTMENT,
                AppointmentIntentSchema.AMBIGUOUS_APPOINTMENT_RELATED,
                AppointmentIntentSchema.QUERY_AVAILABILITY,
                AppointmentIntentSchema.CONFIRMATION
            ]
        )
        if not create_req_condition:
            logger.info(f"No actionable data/reason for appointment request from SMS intent '{ai_intent_val}'. No request created.")
            return None

        req_data = schemas.AppointmentRequestCreateInternal(
            business_id=business.id, customer_id=customer.id,
            customer_initiated_message_id=inbound_message_id, original_message_text=sms_body,
            parsed_requested_time_text=parsed_time_text,
            parsed_requested_datetime_utc=parsed_time_utc,
            confirmed_datetime_utc=confirmed_datetime_for_request,
            status=current_status,
            source=AppointmentRequestSourceEnum.CUSTOMER_INITIATED,
            ai_suggested_reply=ai_suggested_reply_for_request,
            details=final_details.strip()
        )
        logger.info(f"Creating AppointmentRequest with data: Status={req_data.status}, ParsedUTC={req_data.parsed_requested_datetime_utc}, ConfirmedUTC={req_data.confirmed_datetime_utc}, AISuggestedReply='{req_data.ai_suggested_reply}'")
        return await run_in_threadpool(self._create_appointment_request_internal, req_data)

    async def create_business_initiated_appointment_proposal(
        self,
        business: BusinessProfileModel,
        customer: CustomerModel,
        owner_message_text: str,
        outbound_message_id: int,
        proposed_datetime_utc: Optional[datetime] = None,
        appointment_notes: Optional[str] = None
    ) -> AppointmentRequestModel:
        logger.info(f"SERVICE (create_biz_proposal): Biz ID: {business.id}, Cust ID: {customer.id}, Proposed UTC: {proposed_datetime_utc}, Notes: '{appointment_notes}'")
        parsed_time_utc: Optional[datetime] = None
        parsed_time_text: str = owner_message_text
        ai_intent_val: str = AppointmentIntentSchema.OWNER_PROPOSAL.value

        if proposed_datetime_utc:
            parsed_time_utc = proposed_datetime_utc
            if parsed_time_utc.tzinfo is None or parsed_time_utc.tzinfo.utcoffset(parsed_time_utc) is None:
                parsed_time_utc = pytz.utc.localize(parsed_time_utc)
            else:
                parsed_time_utc = parsed_time_utc.astimezone(pytz.utc)

            business_tz_obj = get_business_timezone(business.timezone)
            proposed_time_local = parsed_time_utc.astimezone(business_tz_obj)
            parsed_time_text = f"Proposal for: {proposed_time_local.strftime('%a, %b %d, %I:%M %p %Z')}"
        else:
            ai_response: schemas.AppointmentAIResponse = await self.appointment_ai_service.parse_appointment_sms(
                owner_message_text,
                business,
                customer,
                is_owner_message=True
            )
            ai_intent_val = ai_response.intent.value if isinstance(ai_response.intent, PythonEnum) else str(ai_response.intent)
            if ai_response.datetime_preferences and ai_response.datetime_preferences[0].start_time:
                pref = ai_response.datetime_preferences[0]
                parsed_time_utc = pref.start_time
                business_tz_obj = get_business_timezone(business.timezone)
                parsed_time_text = pref.datetime_str or \
                                   (f"AI parsed proposal: {pref.start_time.astimezone(business_tz_obj).strftime('%a, %b %d %I:%M %p %Z')}"
                                    if parsed_time_utc else "Time TBD")

        conflict_details = "Time not specified or parsed."
        if parsed_time_utc:
            is_avail, conflict_msg_detail, _ = await run_in_threadpool(self._check_availability_and_conflicts, business, parsed_time_utc)
            conflict_details = f"Proposed time '{parsed_time_text}' " + (f"is available." if is_avail else f"is unavailable/conflicting: {conflict_msg_detail}")

        base_details_parts: List[str] = ["Business proposal."]
        if proposed_datetime_utc:
            base_details_parts.append(f"Time directly set to '{parsed_time_text}'.")
        else:
            base_details_parts.append(f"AI Parsed Intent: {ai_intent_val} (Parsed Text: '{parsed_time_text}').")
        if appointment_notes:
            base_details_parts.append(f"Notes: {appointment_notes}.")
        final_details = " ".join(base_details_parts).strip() + f" Availability check: {conflict_details}"

        req_data = schemas.AppointmentRequestCreateInternal(
            business_id=business.id,
            customer_id=customer.id,
            business_proposal_message_id=outbound_message_id,
            original_message_text=owner_message_text,
            parsed_requested_time_text=parsed_time_text,
            parsed_requested_datetime_utc=parsed_time_utc,
            status=AppointmentRequestStatusEnum.BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY,
            source=AppointmentRequestSourceEnum.BUSINESS_INITIATED,
            details=final_details
        )
        return await run_in_threadpool(self._create_appointment_request_internal, req_data)

    async def handle_customer_reply_to_proposal(
        self, existing_request: AppointmentRequestModel, sms_body: str,
        inbound_message_id: int,
        business: BusinessProfileModel, customer: CustomerModel
    ) -> Optional[AppointmentRequestModel]:
        if existing_request.status != AppointmentRequestStatusEnum.BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY:
            return None

        last_business_message_text_for_ai = existing_request.original_message_text

        ai_response: schemas.AppointmentAIResponse = await self.appointment_ai_service.parse_appointment_sms(
            sms_body, business, customer,
            last_business_message_text=last_business_message_text_for_ai
        )
        detected_intent_enum: AppointmentIntentSchema = ai_response.intent # type: ignore

        normalized_sms_body = sms_body.lower().strip().translate(str.maketrans('', '', '?!.'))
        simple_affirmatives = ["yes", "yep", "yeah", "ok", "okay", "sounds good", "perfect", "confirmed", "confirm", "deal", "fine", "sure", "great", "y", "i'll be there"]

        is_simple_affirmative = any(phrase == normalized_sms_body for phrase in simple_affirmatives) or \
                                any(normalized_sms_body.startswith(phrase + " ") for phrase in simple_affirmatives)

        original_proposal_time_utc = existing_request.parsed_requested_datetime_utc
        ai_parsed_time_utc: Optional[datetime] = None
        if ai_response.datetime_preferences and ai_response.datetime_preferences[0].start_time:
            ai_parsed_time_utc = ai_response.datetime_preferences[0].start_time

        effective_intent = detected_intent_enum
        if is_simple_affirmative and detected_intent_enum != AppointmentIntentSchema.CONFIRMATION:
            logger.info(f"Simple affirmative '{sms_body}' detected. Tentatively setting intent to CONFIRMATION for proposal reply.")
            effective_intent = AppointmentIntentSchema.CONFIRMATION
        
        if detected_intent_enum == AppointmentIntentSchema.CONFIRMATION and \
           not ai_response.requires_clarification and \
           ai_parsed_time_utc and original_proposal_time_utc and \
           ai_parsed_time_utc.replace(second=0, microsecond=0) == original_proposal_time_utc.replace(second=0, microsecond=0):
            logger.info("AI contextually confirmed customer's reply for the original proposed time.")
            effective_intent = AppointmentIntentSchema.CONFIRMATION

        update_dict: Dict[str, Any] = {
            "customer_reply_to_proposal_message_id": inbound_message_id,
            "updated_at": get_utc_now()
        }
        current_details: str = (existing_request.details or "").strip()
        
        ai_intent_display_val = effective_intent.value if isinstance(effective_intent, PythonEnum) else str(effective_intent)
        ai_log_details_parts: List[str] = [f"Cust. SMS: '{sms_body}'. Effective AI Intent: {ai_intent_display_val}."]
        if ai_response.parsed_intent_details: ai_log_details_parts.append(f"{ai_response.parsed_intent_details}")
        if ai_response.requires_clarification and ai_response.clarification_question: ai_log_details_parts.append(f"AI Clarification: {ai_response.clarification_question}")
        
        details_update_parts: List[str] = [" ".join(ai_log_details_parts)]
        
        new_status: AppointmentRequestStatusEnum = existing_request.status
        old_status: AppointmentRequestStatusEnum = existing_request.status

        if effective_intent == AppointmentIntentSchema.CONFIRMATION:
            if ai_parsed_time_utc and original_proposal_time_utc and \
               ai_parsed_time_utc.replace(second=0, microsecond=0) != original_proposal_time_utc.replace(second=0, microsecond=0):
                logger.warning(f"Customer replied affirmatively but AI parsed a new time ({ai_parsed_time_utc}) different from proposal ({original_proposal_time_utc}). Switching to RESCHEDULE.")
                effective_intent = AppointmentIntentSchema.RESCHEDULE
                update_dict["parsed_requested_datetime_utc"] = ai_parsed_time_utc
                update_dict["parsed_requested_time_text"] = ai_response.datetime_preferences[0].datetime_str or f"Reschedule to {ai_parsed_time_utc.isoformat()}"
                update_dict["confirmed_datetime_utc"] = None
            elif not ai_parsed_time_utc and not original_proposal_time_utc and is_simple_affirmative:
                new_status = AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL
                details_update_parts.append("Cust. confirmed generally (orig. proposal had no specific UTC). Owner to finalize.")
            elif original_proposal_time_utc :
                time_text = existing_request.parsed_requested_time_text or original_proposal_time_utc.strftime('%a, %b %d %I:%M %p')
                is_avail, conflict_msg, _ = await run_in_threadpool(self._check_availability_and_conflicts, business, original_proposal_time_utc, existing_request.id)
                if is_avail:
                    new_status = AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL
                    details_update_parts.append(f"Confirmed for {time_text}. Slot OK. Pending owner approval.")
                    update_dict["confirmed_datetime_utc"] = original_proposal_time_utc
                else:
                    new_status = AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE
                    details_update_parts.append(f"Customer tried to confirm {time_text}, but slot now has conflict: {conflict_msg}. Marked as reschedule.")
                    update_dict["customer_reschedule_suggestion"] = (existing_request.customer_reschedule_suggestion or "") + f" Conflict for proposed {time_text}: {conflict_msg}"
                    update_dict["confirmed_datetime_utc"] = None
            elif ai_response.requires_clarification:
                new_status = AppointmentRequestStatusEnum.CUSTOMER_REPLIED_NEEDS_REVIEW
                details_update_parts.append(f"Reply seems confirmatory but AI needs clarification: {ai_response.clarification_question}")
                update_dict["ai_suggested_reply"] = ai_response.clarification_question

        if effective_intent == AppointmentIntentSchema.RESCHEDULE:
            new_status = AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE
            pref_text = "no specific time in reschedule"
            if "parsed_requested_datetime_utc" in update_dict and "parsed_requested_time_text" in update_dict:
                pref_text = update_dict["parsed_requested_time_text"]
            elif ai_parsed_time_utc:
                update_dict["parsed_requested_datetime_utc"] = ai_parsed_time_utc
                update_dict["parsed_requested_time_text"] = ai_response.datetime_preferences[0].datetime_str or f"Reschedule to {ai_parsed_time_utc.isoformat()}"
                update_dict["confirmed_datetime_utc"] = None
                pref_text = update_dict["parsed_requested_time_text"]
            elif ai_response.datetime_preferences and ai_response.datetime_preferences[0].datetime_str:
                pref_text = ai_response.datetime_preferences[0].datetime_str
                update_dict["parsed_requested_time_text"] = pref_text
                update_dict["confirmed_datetime_utc"] = None
            
            details_update_parts.append(f"Cust. requested reschedule. Suggestion: {pref_text}.")
            update_dict["customer_reschedule_suggestion"] = (existing_request.customer_reschedule_suggestion or "") + f" Cust. reschedule suggestion: {pref_text}."

        elif effective_intent == AppointmentIntentSchema.CANCELLATION:
            new_status = AppointmentRequestStatusEnum.CUSTOMER_DECLINED_PROPOSAL
            details_update_parts.append("Cust. declined/cancelled proposal.")

        elif new_status == old_status:
            new_status = AppointmentRequestStatusEnum.CUSTOMER_REPLIED_NEEDS_REVIEW
            details_update_parts.append(f"Cust. reply needs owner review.")
            if ai_response.requires_clarification and ai_response.clarification_question:
                update_dict["ai_suggested_reply"] = ai_response.clarification_question
            elif not ai_response.requires_clarification and not ai_parsed_time_utc:
                 details_update_parts.append("Reply is non-specific, for owner review.")

        if new_status != old_status:
            update_dict["status"] = new_status
        
        update_dict["details"] = (current_details + "\n" + " ".join(details_update_parts)).strip()

        def _update_commit_refresh_sync(req_id: int, updates_dict: Dict[str, Any]) -> Optional[AppointmentRequestModel]:
            req = self.db.query(AppointmentRequestModel).filter(AppointmentRequestModel.id == req_id).first()
            if not req: return None
            for key, value in updates_dict.items():
                setattr(req, key, value)
            self.db.commit()
            self.db.refresh(req)
            return req

        updated_request = await run_in_threadpool(_update_commit_refresh_sync, existing_request.id, update_dict) # type: ignore
        new_status_val = updated_request.status.value if updated_request and updated_request.status and isinstance(updated_request.status, PythonEnum) else str(updated_request.status if updated_request else None)
        old_status_val = old_status.value if isinstance(old_status, PythonEnum) else str(old_status)
        logger.info(f"SERVICE (handle_customer_reply): Req {updated_request.id if updated_request else 'N/A'}. Old Status: {old_status_val}, New status: {new_status_val}. Details: {update_dict.get('details')}")
        return updated_request

    async def get_appointment_requests_by_business(
        self, db: AsyncSession, business_id: int,
        statuses: Optional[List[AppointmentRequestStatusEnum]] = None, customer_id: Optional[int] = None,
        limit: int = 100, offset: int = 0
    ) -> List[AppointmentRequestModel]:
        stmt = (
            sql_select(AppointmentRequestModel).where(AppointmentRequestModel.business_id == business_id)
            .order_by(desc(AppointmentRequestModel.updated_at)).limit(limit).offset(offset)
            .options(
                selectinload(AppointmentRequestModel.customer).options(
                    selectinload(CustomerModel.business),
                    selectinload(CustomerModel.tags)
                ),
                selectinload(AppointmentRequestModel.business),
                selectinload(AppointmentRequestModel.customer_initiated_message_ref),
                selectinload(AppointmentRequestModel.business_proposal_message_ref),
                selectinload(AppointmentRequestModel.customer_reply_to_proposal_message_ref)
            )
        )
        if statuses:
            stmt = stmt.where(AppointmentRequestModel.status.in_(statuses))
        if customer_id:
            stmt = stmt.where(AppointmentRequestModel.customer_id == customer_id)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_appointment_request_status_by_owner(
        self,
        db: AsyncSession,
        request_id: int,
        update_data: schemas.AppointmentRequestStatusUpdateByOwner,
        business_id: int,
        settings: Settings
    ) -> Optional[models.AppointmentRequest]:
        logger.info(
            f"SERVICE (update_status_by_owner): Req ID: {request_id}, Biz ID: {business_id}, "
            f"Incoming New Status Type: {type(update_data.new_status)}, Value: '{update_data.new_status}'"
        )

        stmt = (
            sql_select(AppointmentRequestModel)
            .where(AppointmentRequestModel.id == request_id, AppointmentRequestModel.business_id == business_id)
            .options(
                selectinload(AppointmentRequestModel.customer).options(selectinload(CustomerModel.tags)),
                selectinload(AppointmentRequestModel.business),
                selectinload(AppointmentRequestModel.customer_initiated_message_ref),
                selectinload(AppointmentRequestModel.business_proposal_message_ref),
                selectinload(AppointmentRequestModel.customer_reply_to_proposal_message_ref)
            )
        )
        result = await db.execute(stmt)
        appointment_request: Optional[AppointmentRequestModel] = result.scalar_one_or_none()

        if not appointment_request:
            return None
        if not appointment_request.customer:
            logger.error(f"Customer not loaded for AppointmentRequest ID: {request_id}")
            raise ValueError("Customer not loaded for appointment request status update.")
        if not appointment_request.business:
            logger.error(f"Business not loaded for AppointmentRequest ID: {request_id}")
            raise ValueError("Business not loaded for appointment request status update.")

        original_status_enum: AppointmentRequestStatusEnum = appointment_request.status

        new_status_enum: AppointmentRequestStatusEnum
        if isinstance(update_data.new_status, AppointmentRequestStatusEnum):
            new_status_enum = update_data.new_status
        elif isinstance(update_data.new_status, str):
            logger.warning(
                f"new_status for Req ID {request_id} received as string: '{update_data.new_status}'. "
                f"Attempting conversion. Verify Pydantic schema 'AppointmentRequestStatusUpdateByOwner' has 'new_status: AppointmentRequestStatusEnum'."
            )
            try:
                new_status_enum = AppointmentRequestStatusEnum(update_data.new_status)
            except ValueError:
                logger.error(
                    f"Invalid string value for new_status: '{update_data.new_status}' "
                    f"cannot be converted to AppointmentRequestStatusEnum for Req ID {request_id}."
                )
                raise HTTPException(status_code=400, detail=f"Invalid status value provided: {update_data.new_status}")
        else:
            logger.error(
                f"Unexpected type for new_status: {type(update_data.new_status)} for Req ID {request_id}. "
                f"Value: {update_data.new_status}"
            )
            raise HTTPException(status_code=400, detail="Invalid type for new_status. Expected a valid status string or AppointmentRequestStatusEnum.")

        appointment_request.status = new_status_enum
        appointment_request.updated_at = get_utc_now()

        current_details: str = (appointment_request.details or "").strip()
        
        original_status_value: str = original_status_enum.value if isinstance(original_status_enum, PythonEnum) else str(original_status_enum)
        new_status_value: str = new_status_enum.value

        action_detail_parts: List[str] = [
            f"Owner action: Status changed from {original_status_value} to {new_status_value}."
        ]

        if hasattr(update_data, 'owner_notes') and update_data.owner_notes:
            action_detail_parts.append(f"Owner notes: {update_data.owner_notes}.")

        if new_status_enum == AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER:
            if hasattr(update_data, 'confirmed_datetime_utc') and update_data.confirmed_datetime_utc:
                appointment_request.confirmed_datetime_utc = update_data.confirmed_datetime_utc
                appointment_request.parsed_requested_datetime_utc = update_data.confirmed_datetime_utc
                business_tz = get_business_timezone(appointment_request.business.timezone)
                confirmed_local_str = update_data.confirmed_datetime_utc.astimezone(business_tz).strftime('%a, %b %d, %I:%M %p %Z')
                appointment_request.parsed_requested_time_text = f"Confirmed for {confirmed_local_str}"
                action_detail_parts.append(f"Appointment confirmed by owner for {confirmed_local_str}.")
                if appointment_request.id is not None:
                    schedule_appointment_reminder_task.delay(appointment_request.id)
                    schedule_appointment_thank_you_task.delay(appointment_request.id)
            else:
                action_detail_parts.append("Owner confirmed but no specific time was provided in update_data.")
        
        elif new_status_enum == AppointmentRequestStatusEnum.CANCELLED_BY_OWNER:
            cancellation_reason_val = getattr(update_data, 'cancellation_reason', None) or 'Not specified'
            action_detail_parts.append(f"Cancelled by owner. Reason: {cancellation_reason_val}.")
            appointment_request.cancellation_reason = getattr(update_data, 'cancellation_reason', None)
        
        elif new_status_enum == AppointmentRequestStatusEnum.OWNER_SUGGESTED_RESCHEDULE:
            if hasattr(update_data, 'owner_suggested_datetime_utc') and update_data.owner_suggested_datetime_utc:
                appointment_request.owner_suggested_datetime_utc = update_data.owner_suggested_datetime_utc
                business_tz = get_business_timezone(appointment_request.business.timezone)
                suggested_local_str = update_data.owner_suggested_datetime_utc.astimezone(business_tz).strftime('%a, %b %d, %I:%M %p %Z')
                action_detail_parts.append(f"Owner suggested reschedule to {suggested_local_str}.")
            else:
                action_detail_parts.append("Owner suggested reschedule but no specific time provided in update_data.")

        appointment_request.details = (current_details + "\n" + " ".join(action_detail_parts)).strip()
        await db.flush()

        send_sms = getattr(update_data, 'send_sms_to_customer', False)
        sms_body_content = getattr(update_data, 'sms_message_body', None)

        if send_sms and sms_body_content and \
           appointment_request.customer.phone and appointment_request.business and \
           (appointment_request.business.twilio_number or appointment_request.business.messaging_service_sid) and \
           appointment_request.customer.sms_opt_in_status != OptInStatus.OPTED_OUT:

            conv_id: Optional[str] = None
            related_message_refs = [
                appointment_request.customer_initiated_message_ref,
                appointment_request.business_proposal_message_ref,
                appointment_request.customer_reply_to_proposal_message_ref
            ]
            for msg_ref in related_message_refs:
                if msg_ref and msg_ref.conversation_id:
                    conv_id = str(msg_ref.conversation_id)
                    break
            
            new_msg = MessageModel( # Ensure MessageModel constructor matches fields in your models.py
                customer_id=appointment_request.customer_id,
                business_id=business_id,
                content=sms_body_content,
                sender_type=SenderTypeEnum.BUSINESS,
                message_type=MessageTypeEnum.OUTBOUND,
                status=MessageStatusEnum.PENDING_SEND,
                conversation_id=conv_id,
                source="owner_appointment_action_sms",
                created_at=get_utc_now(),
                updated_at=get_utc_now()
                # Removed 'related_appointment_request_id' or 'appointment_request_id'
                # as it's not directly on MessageModel per your models.py
            )
            # If you need to link this message to the appointment request,
            # you might need to add a field to MessageModel or handle linking differently.
            logger.warning(
                f"Outbound SMS for AppointmentRequest ID {appointment_request.id} created. "
                f"Note: MessageModel (as per provided models.py) does not have a direct FK to AppointmentRequest "
                f"like 'appointment_request_id' for this specific message."
            )
            db.add(new_msg)
            await db.flush()

            try:
                # Initialize TwilioService with the current async db session
                # Note: Your TwilioService.send_sms is already async and uses run_in_threadpool internally for blocking calls.
                twilio_svc = TwilioService(db=db) 
                
                sid: Optional[str] = await twilio_svc.send_sms(
                    to=appointment_request.customer.phone,
                    message_body=sms_body_content,
                    business=appointment_request.business,
                    customer=appointment_request.customer,
                    is_direct_reply=True
                )
                if sid:
                    new_msg.twilio_message_sid = sid
                    new_msg.status = MessageStatusEnum.SENT
                    new_msg.sent_at = get_utc_now()
                else:
                    new_msg.status = MessageStatusEnum.FAILED
                    new_msg.message_metadata = {"failure_reason": "Twilio service did not return SID"}
            except Exception as e:
                logger.error(f"Error sending SMS via TwilioService for Req ID {request_id}: {e}", exc_info=True)
                new_msg.status = MessageStatusEnum.FAILED
                new_msg.message_metadata = {"failure_reason": str(e)}
            
            await db.flush()

        await db.commit()
        await db.refresh(appointment_request)
        return appointment_request