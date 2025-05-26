# backend/app/celery_tasks.py
# CONSOLIDATED DEBUGGING VERSION - Resolves ImportError

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, Optional, Union, Tuple, Any, Coroutine

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.future import select

from app.celery_app import celery_app as celery
from app.database import AsyncSessionLocal, SessionLocal
from app.models import (
    BusinessProfile, Customer, Message, Engagement, AppointmentRequest,
    MessageTypeEnum, MessageStatusEnum, SenderTypeEnum, OptInStatus,
    AppointmentRequestStatusEnum
)
from app.services.twilio_service import TwilioService # Assuming these are adaptable
from app.services.appointment_ai_service import AppointmentAIService # Assuming these are adaptable

# Placeholder for async conversation ID service function from message_service
async def get_conversation_id_from_service_async(db: AsyncSession, business_id: int, customer_id: int) -> str:
    logger.warning(f"get_conversation_id_from_service_async is using placeholder new UUID generation for B:{business_id}/C:{customer_id}")
    await asyncio.sleep(0) # Simulate async work
    return str(uuid.uuid4())

from app.timezone_utils import convert_from_utc, get_business_timezone

logger = logging.getLogger(__name__)

# --- Debugging: Helper to check for coroutines ---
def check_for_coroutines(data, path=""): # Included from previous debugging steps
    if isinstance(data, dict):
        for k, v in data.items(): check_for_coroutines(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, item in enumerate(data): check_for_coroutines(item, f"{path}[{i}]")
    elif asyncio.iscoroutine(data):
        print(f"!!! COROUTINE CHECKER FOUND COROUTINE at path: {path} - Value: {data} !!!")
        logger.error(f"FOUND COROUTINE at path: {path} - Value: {data}")

def get_log_prefix(task_name: str, id_value: Union[int, str]) -> str:
    return f"[CELERY_TASK {task_name}(ID:{id_value})]"

# --- ULTRA-MINIMAL ASYNC DECORATOR (for process_scheduled_message_task only) ---
def ultra_minimal_async_debug_decorator(func):
    async def wrapper(*args, **kwargs):
        task_instance_name = func.__name__; task_req_id = "unknown_req_id"; original_message_id_arg = "unknown_msg_id"
        if args:
            if hasattr(args[0], 'request') and hasattr(args[0].request, 'id'):
                task_instance_name = args[0].name; task_req_id = args[0].request.id
            if len(args) > 1: original_message_id_arg = args[1]
        print(f"[PRINT_ULTRA_MINIMAL_DECO] ASYNC WRAPPER ENTERED for {task_instance_name}[{task_req_id}]. Original MsgID Arg: {original_message_id_arg}")
        logger.info(f"[LOG_ULTRA_MINIMAL_DECO] ASYNC WRAPPER ENTERED for {task_instance_name}[{task_req_id}]. Original MsgID Arg: {original_message_id_arg}")
        new_args = []
        if args: new_args.append(args[0]); new_args.append(None); new_args.extend(args[1:])
        final_result_for_celery = None
        try:
            print(f"[PRINT_ULTRA_MINIMAL_DECO] About to call {func.__name__} with {len(new_args)} effective args (self, db=None, ...)")
            logger.info(f"[LOG_ULTRA_MINIMAL_DECO] About to call {func.__name__} with {new_args[:3]}...")
            result_from_func = await func(*new_args, **kwargs)
            print(f"[PRINT_ULTRA_MINIMAL_DECO] {func.__name__} returned. Result: {str(result_from_func)[:100]}")
            logger.info(f"[LOG_ULTRA_MINIMAL_DECO] {func.__name__} returned. Result: {str(result_from_func)[:100]}")
            final_result_for_celery = result_from_func
            return result_from_func
        except Exception as e:
            print(f"[PRINT_ULTRA_MINIMAL_DECO] EXCEPTION in async wrapper: {type(e).__name__} - {str(e)}")
            logger.error(f"[LOG_ULTRA_MINIMAL_DECO] EXCEPTION in async wrapper: {type(e).__name__} - {str(e)}", exc_info=True)
            final_result_for_celery = e; raise
        finally:
            print(f"[PRINT_ULTRA_MINIMAL_DECO] Async wrapper FINALLY for {task_instance_name}[{task_req_id}]. Final obj: {type(final_result_for_celery)}")
            logger.info(f"[LOG_ULTRA_MINIMAL_DECO] Async wrapper FINALLY for {task_instance_name}[{task_req_id}].")
    return wrapper

# --- REGULAR VERBOSE handle_db_session DECORATOR (for all other tasks) ---
def handle_db_session(func):
    original_func_is_async = asyncio.iscoroutinefunction(func)
    is_bound_method = False
    try:
        if func.__code__.co_argcount > 0 and func.__code__.co_varnames[0] == 'self': is_bound_method = True
    except AttributeError: pass

    if original_func_is_async:
        async def wrapper(*args, **kwargs):
            task_instance_name = func.__name__; task_request_id = "unknown_req_id"
            if is_bound_method and args and hasattr(args[0], 'request') and hasattr(args[0].request, 'id'):
                task_instance_name = args[0].name; task_request_id = args[0].request.id
            log_point = f"handle_db_session_async_REGULAR_WRAPPER for {task_instance_name}[{task_request_id}]" # Changed log_point name
            print(f"{log_point}: [PRINT_DEBUG] ENTERED async wrapper. is_bound_method: {is_bound_method}")
            logger.info(f"{log_point}: ENTERED async wrapper. Args: {args[:2]}...")
            session_instance: Optional[AsyncSession] = None
            try:
                logger.info(f"{log_point}: Creating AsyncSessionLocal instance..."); session_instance = AsyncSessionLocal()
                logger.info(f"{log_point}: AsyncSessionLocal instance CREATED: {type(session_instance)}")
                func_args_list = list(args)
                if is_bound_method: func_args_list.insert(1, session_instance)
                else: func_args_list.insert(0, session_instance)
                logger.info(f"{log_point}: Calling await func {func.__name__}..."); result = await func(*func_args_list, **kwargs)
                logger.info(f"{log_point}: Func call returned. Result type: {type(result)}. Checking for coroutines..."); check_for_coroutines(result, f"{task_instance_name}_result")
                if session_instance: await session_instance.commit(); logger.info(f"{log_point}: Session committed.")
                return result
            except Exception as e:
                logger.error(f"{log_point}: EXCEPTION CAUGHT: {type(e).__name__} - {str(e)}", exc_info=True); check_for_coroutines(e, f"{task_instance_name}_exception_object")
                if session_instance: await session_instance.rollback(); logger.info(f"{log_point}: Session rolled back.")
                raise
            finally:
                if session_instance: await session_instance.close(); logger.info(f"{log_point}: Session closed.")
        return wrapper
    else: # Synchronous function
        def wrapper(*args, **kwargs):
            task_instance_name = func.__name__; task_request_id = "unknown_req_id"
            if is_bound_method and args and hasattr(args[0], 'request') and hasattr(args[0].request, 'id'):
                task_instance_name = args[0].name; task_request_id = args[0].request.id
            log_point = f"handle_db_session_sync_REGULAR_WRAPPER for {task_instance_name}[{task_request_id}]" # Changed log_point name
            print(f"{log_point}: [PRINT_DEBUG] ENTERED sync wrapper.")
            logger.info(f"{log_point}: ENTERED sync wrapper.")
            session_instance: Optional[SyncSession] = None
            try:
                session_instance = SessionLocal(); logger.info(f"{log_point}: SyncSessionLocal instance CREATED: {type(session_instance)}")
                func_args_list = list(args)
                if is_bound_method: func_args_list.insert(1, session_instance)
                else: func_args_list.insert(0, session_instance)
                result = func(*func_args_list, **kwargs); logger.info(f"{log_point}: Sync func call returned."); check_for_coroutines(result, f"{task_instance_name}_sync_task_result")
                if session_instance: session_instance.commit(); logger.info(f"{log_point}: Sync session committed.")
                return result
            except Exception as e:
                logger.error(f"{log_point}: SYNC EXCEPTION CAUGHT: {type(e).__name__} - {str(e)}", exc_info=True); check_for_coroutines(e, f"{task_instance_name}_sync_exception_object")
                if session_instance: session_instance.rollback(); logger.info(f"{log_point}: Sync session rolled back.")
                raise
            finally:
                if session_instance: session_instance.close(); logger.info(f"{log_point}: Sync session closed.")
        return wrapper

# --- ASYNC HELPER FUNCTIONS (These are shared and need to be fully defined) ---
async def update_engagement_status_async(
    db: AsyncSession, message: Message, new_status: MessageStatusEnum, log_prefix: str
) -> None:
    if message.message_metadata and message.message_metadata.get('source') == 'manual_reply_inbox':
        stmt = select(Engagement).filter(Engagement.message_id == message.id)
        result = await db.execute(stmt)
        engagement: Optional[Engagement] = result.scalars().first()
        if engagement:
            engagement.status = new_status
            if new_status == MessageStatusEnum.SENT: engagement.sent_at = message.sent_at
            db.add(engagement)
            logger.info(f"{log_prefix} Updated engagement (ID: {engagement.id}) status to {new_status.value}")
        else: logger.warning(f"{log_prefix} Could not find related engagement for message_id {message.id}")

async def create_scheduled_message_async(
    db: AsyncSession, conversation_id: uuid.UUID, customer_id: int, business_id: int,
    content: str, message_type: MessageTypeEnum, scheduled_time: datetime,
    metadata: Dict[str, Any], log_prefix: str
) -> Message:
    message = Message(
        conversation_id=conversation_id, customer_id=customer_id, business_id=business_id, content=content,
        message_type=message_type, status=MessageStatusEnum.SCHEDULED, scheduled_send_at=scheduled_time,
        message_metadata=metadata, sender_type=SenderTypeEnum.SYSTEM, created_at=datetime.now(dt_timezone.utc),
        updated_at=datetime.now(dt_timezone.utc)
    )
    db.add(message); await db.flush([message])
    logger.info(f"{log_prefix} Created scheduled message (ID: {message.id})")
    return message

async def handle_customer_error_async(db: AsyncSession, message: Message, log_prefix: str) -> Dict[str, Any]:
    err_msg = "Customer or phone not found"; logger.error(f"{log_prefix} {err_msg}")
    message.status = MessageStatusEnum.FAILED; message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': err_msg}
    db.add(message); await update_engagement_status_async(db, message, MessageStatusEnum.FAILED, log_prefix)
    return {"success": False, "error": err_msg, "status": MessageStatusEnum.FAILED.value}

async def handle_opt_out_async(db: AsyncSession, message: Message, log_prefix: str) -> Dict[str, Any]:
    err_msg = "Customer opted out"; logger.warning(f"{log_prefix} {err_msg}. Skipping send.")
    message.status = MessageStatusEnum.FAILED; message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': err_msg}
    db.add(message); await update_engagement_status_async(db, message, MessageStatusEnum.FAILED, log_prefix)
    return {"success": False, "error": err_msg, "status": MessageStatusEnum.FAILED.value}

async def handle_business_error_async(db: AsyncSession, message: Message, log_prefix: str) -> Dict[str, Any]:
    err_msg = "Business not found"; logger.error(f"{log_prefix} {err_msg}")
    message.status = MessageStatusEnum.FAILED; message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': err_msg}
    db.add(message) # No engagement update mentioned in original, aligns with that
    return {"success": False, "error": err_msg, "status": MessageStatusEnum.FAILED.value}

async def handle_send_error_async(db: AsyncSession, message: Message, error: Exception, log_prefix: str) -> Dict[str, Any]:
    err_msg = f"Send error: {str(error)}"; logger.error(f"{log_prefix} {err_msg}", exc_info=not isinstance(error, HTTPException))
    message.status = MessageStatusEnum.FAILED; message.message_metadata = {**(message.message_metadata or {}), 'failure_reason': f"Send Error: {str(error)}"}
    db.add(message); await update_engagement_status_async(db, message, MessageStatusEnum.FAILED, log_prefix)
    return {"success": False, "error": err_msg, "status": MessageStatusEnum.FAILED.value}

# This is the full logic for sending, if the simplified task is later restored
async def send_message_via_twilio_full_logic_async(
    db: AsyncSession, message: Message, customer: Customer, business: BusinessProfile, log_prefix: str
) -> Dict[str, Any]:
    try:
        twilio_service = TwilioService(db=db) # Assumes TwilioService is async ready or db is optional/unused by its send_sms
        message_sid = await twilio_service.send_sms( # Assumes send_sms is async
            to=customer.phone, message_body=message.content, business=business, customer=customer,
            is_direct_reply=message.message_metadata.get('source') == 'manual_reply_inbox'
        )
        message.status = MessageStatusEnum.SENT; message.sent_at = datetime.now(dt_timezone.utc)
        message.message_metadata = {**(message.message_metadata or {}), 'twilio_sid': message_sid}; db.add(message)
        await update_engagement_status_async(db, message, MessageStatusEnum.SENT, log_prefix)
        return {"success": True, "message_sid": message_sid, "status": MessageStatusEnum.SENT.value}
    except HTTPException as http_exc: return await handle_send_error_async(db, message, http_exc, log_prefix)
    except Exception as e: return await handle_send_error_async(db, message, e, log_prefix)

# --- CELERY TASKS ---
@celery.task(name='ping')
@handle_db_session # Uses the regular verbose handle_db_session
def ping(db: SyncSession) -> str:
    logger.info(f"Celery ping task executed (db session type: {type(db)}).")
    return "pong"

# --- ULTRA-MINIMAL process_scheduled_message_task (for targeted debugging) ---
@celery.task(name='process_scheduled_message', bind=True, max_retries=3, default_retry_delay=60)
@ultra_minimal_async_debug_decorator # Apply the NEW ultra-minimal decorator
async def process_scheduled_message_task(self, db: Optional[AsyncSession], message_id: int) -> Dict[str, Any]:
    task_id_for_log = getattr(getattr(self, 'request', None), 'id', "unknown_task_id")
    print(f"[PRINT_ULTRA_MINIMAL_TASK] TASK {task_id_for_log} ENTERED. MsgID: {message_id}. DB is None: {db is None}")
    logger.info(f"[LOG_ULTRA_MINIMAL_TASK] TASK {task_id_for_log} EXECUTION STARTING. MsgID: {message_id}. DB is None: {db is None}")
    final_task_return = {}
    try:
        if db is not None: # This case should not happen with ultra_minimal_async_debug_decorator
            print(f"[PRINT_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: DB object received: {type(db)}")
            logger.warning(f"[LOG_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: DB object received: {type(db)}")
        await asyncio.sleep(0.01)
        print(f"[PRINT_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: About to return success.")
        logger.info(f"[LOG_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: About to return success.")
        final_task_return = {"success": True, "status": "ultra_minimal_debug_complete_v4", "message_id": message_id, "task_id": task_id_for_log}
        return final_task_return
    except Exception as e:
        print(f"[PRINT_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: EXCEPTION caught: {type(e).__name__} - {str(e)}")
        logger.error(f"[LOG_ULTRA_MINIMAL_TASK] TASK {task_id_for_log}: EXCEPTION caught: {type(e).__name__} - {str(e)}", exc_info=True)
        final_task_return = e; raise
    finally:
        print(f"[PRINT_ULTRA_MINIMAL_TASK] TASK {task_id_for_log} FINALLY block. Object being handled: {type(final_task_return)}")
        logger.info(f"[LOG_ULTRA_MINIMAL_TASK] TASK {task_id_for_log} FINALLY block.")

# --- Appointment Related Tasks & Helpers (Restored and using regular handle_db_session) ---
async def validate_appointment_request_async(
    db: AsyncSession, appointment_request_id: int, log_prefix: str
) -> Tuple[Optional[AppointmentRequest], Optional[Customer], Optional[BusinessProfile]]:
    appt_req_stmt = select(AppointmentRequest).filter(AppointmentRequest.id == appointment_request_id)
    appt_req: Optional[AppointmentRequest] = (await db.execute(appt_req_stmt)).scalars().first()
    if not appt_req: logger.error(f"{log_prefix} AppointmentRequest not found."); return None, None, None
    if appt_req.status != AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER:
        logger.warning(f"{log_prefix} ApptReq status {appt_req.status}, not CONFIRMED."); return None, None, None
    if not appt_req.confirmed_datetime_utc: logger.error(f"{log_prefix} Confirmed datetime missing."); return None, None, None
    cust_stmt = select(Customer).filter(Customer.id == appt_req.customer_id)
    customer: Optional[Customer] = (await db.execute(cust_stmt)).scalars().first()
    biz_stmt = select(BusinessProfile).filter(BusinessProfile.id == appt_req.business_id)
    business: Optional[BusinessProfile] = (await db.execute(biz_stmt)).scalars().first()
    if not customer or not customer.phone: logger.error(f"{log_prefix} Customer/phone missing."); return None, None, None
    if not business: logger.error(f"{log_prefix} Business profile missing."); return None, None, None
    return appt_req, customer, business

async def generate_message_content_async(
    db: AsyncSession, business: BusinessProfile, customer: Customer, appt_req: AppointmentRequest,
    intent_type: str, log_prefix: str
) -> str:
    ai_service = AppointmentAIService(db=db)
    customer_name = customer.customer_name or "there"; business_name = business.representative_name or business.business_name
    content = await ai_service.draft_appointment_related_sms(
        business=business, customer_name=customer_name, intent_type=intent_type,
        time_details=appt_req.parsed_requested_time_text or appt_req.confirmed_datetime_utc.strftime("%A, %B %d at %I:%M %p"),
        original_customer_request=appt_req.original_message_text
    )
    signature = f" - {business_name}"
    if not content.strip().endswith(signature.strip()): content = content.strip() + signature
    logger.info(f"{log_prefix} Generated content for {intent_type}: '{content[:50]}...'")
    return content

async def get_or_create_conversation_id_async(
    db: AsyncSession, appt_req: AppointmentRequest, business: BusinessProfile, customer: Customer, log_prefix: str
) -> uuid.UUID:
    if appt_req.customer_initiated_message_id:
        res = await db.execute(select(Message.conversation_id).filter(Message.id == appt_req.customer_initiated_message_id))
        conv_uuid: Optional[uuid.UUID] = res.scalars().first()
        if conv_uuid: logger.info(f"{log_prefix} Found conv_id {conv_uuid}"); return conv_uuid
        else: logger.warning(f"{log_prefix} msg_id {appt_req.customer_initiated_message_id} no conv_id.")
    new_conv_id_str = await get_conversation_id_from_service_async(db, business.id, customer.id) # Uses placeholder
    logger.info(f"{log_prefix} Generated new conv_id {new_conv_id_str} via service.")
    return uuid.UUID(new_conv_id_str)

async def schedule_appointment_message_logic(
    db: AsyncSession, appointment_request_id: int, message_purpose: str,
    message_type_enum: MessageTypeEnum, time_calculator, intent_type_for_ai: str
) -> Dict[str, Union[bool, str]]:
    log_prefix = get_log_prefix(f"schedule_appt_{message_purpose}", appointment_request_id)
    logger.info(f"{log_prefix} Starting to schedule {message_purpose} message.")
    try:
        appt_req, customer, business = await validate_appointment_request_async(db, appointment_request_id, log_prefix)
        if not all([appt_req, customer, business]): return {"success": False, "error": "Invalid appt req or missing data."}
        confirmed_dt_utc = appt_req.confirmed_datetime_utc
        if confirmed_dt_utc.tzinfo is None: confirmed_dt_utc = confirmed_dt_utc.replace(tzinfo=dt_timezone.utc)
        scheduled_time_utc = time_calculator(confirmed_dt_utc)
        if scheduled_time_utc <= datetime.now(dt_timezone.utc):
            return {"success": False, "error": f"{message_purpose.capitalize()} time is in the past"}
        content = await generate_message_content_async(db, business, customer, appt_req, intent_type_for_ai, log_prefix)
        conversation_id = await get_or_create_conversation_id_async(db, appt_req, business, customer, log_prefix)
        message = await create_scheduled_message_async(
            db=db, conversation_id=conversation_id, customer_id=customer.id, business_id=business.id, content=content,
            message_type=message_type_enum, scheduled_time=scheduled_time_utc,
            metadata={'source': f'appointment_{message_purpose}', 'appointment_request_id': appt_req.id}, log_prefix=log_prefix
        )
        process_scheduled_message_task.apply_async(args=[message.id], eta=scheduled_time_utc) # Uses the debugged task
        logger.info(f"{log_prefix} Scheduled Celery task for Msg ID {message.id} at {scheduled_time_utc}.")
        return {"success": True, "message": f"{message_purpose.capitalize()} MsgID {message.id} for ApptReq {appointment_request_id} scheduled for {scheduled_time_utc}"}
    except Exception as e:
        logger.error(f"{log_prefix} Error scheduling {message_purpose} message: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@celery.task(name='schedule_appointment_reminder', bind=True, max_retries=3, default_retry_delay=300)
@handle_db_session # Uses regular verbose handle_db_session
async def schedule_appointment_reminder_task(self, db: AsyncSession, appointment_request_id: int) -> Dict[str, Union[bool, str]]:
    log_prefix = get_log_prefix('schedule_appt_reminder_task', appointment_request_id)
    try:
        return await schedule_appointment_message_logic(
            db, appointment_request_id, message_purpose="reminder",
            message_type_enum=MessageTypeEnum.APPOINTMENT_REMINDER,
            time_calculator=lambda dt: dt - timedelta(hours=24), intent_type_for_ai="appointment_reminder"
        )
    except Exception as e: logger.error(f"{log_prefix} Outer task error: {str(e)}", exc_info=True); raise

@celery.task(name='schedule_appointment_thank_you', bind=True, max_retries=3, default_retry_delay=300)
@handle_db_session # Uses regular verbose handle_db_session
async def schedule_appointment_thank_you_task(self, db: AsyncSession, appointment_request_id: int) -> Dict[str, Union[bool, str]]:
    log_prefix = get_log_prefix('schedule_appt_thank_you_task', appointment_request_id)
    try:
        return await schedule_appointment_message_logic(
            db, appointment_request_id, message_purpose="thank_you",
            message_type_enum=MessageTypeEnum.APPOINTMENT_THANK_YOU,
            time_calculator=lambda dt: dt + timedelta(hours=1), intent_type_for_ai="appointment_thank_you"
        )
    except Exception as e: logger.error(f"{log_prefix} Outer task error: {str(e)}", exc_info=True); raise