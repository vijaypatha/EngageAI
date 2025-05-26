# backend/app/routes/appointment_routes.py

import logging
from pydantic import BaseModel 
from datetime import datetime 
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session # For synchronous service parts
from fastapi.concurrency import run_in_threadpool # For running sync code
from sqlalchemy import select # For new draft endpoint query
from sqlalchemy.orm import selectinload

from app.database import get_async_db, get_db
from app import schemas, models, auth
from app.config import Settings, get_settings
from app.services.appointment_service import AppointmentService
from app.services.appointment_ai_service import AppointmentAIService
from app.timezone_utils import get_utc_now

logger = logging.getLogger(__name__)

router = APIRouter(
    # Prefix and tags are managed in main.py
)

# Pydantic models for the AI slot suggestion response
class AiSuggestedSlotResponseItem(BaseModel):
    slot_utc: datetime
    status_message: str

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2

class AiSuggestedSlotListResponse(BaseModel):
    suggestions: List[AiSuggestedSlotResponseItem]

# --- Availability Routes (using sync service methods from async routes) ---
@router.post(
    "/availability/business/{business_id_in_path}",
    response_model=schemas.AppointmentAvailabilityRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Availability Slot"
)
async def create_availability_slot_route(
    business_id_in_path: int,
    availability_data: schemas.AppointmentAvailabilityCreate,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    sync_db: Session = Depends(get_db)
):
    if current_business.id != business_id_in_path:
        logger.warning(f"AuthZ Error: Business {current_business.id} trying to create availability for {business_id_in_path}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create availability for this business.")

    logger.info(
        f"Availability Create: For business {business_id_in_path} - Day: {availability_data.day_of_week}, "
        f"Start ISO: {availability_data.start_time_iso}, End ISO: {availability_data.end_time_iso}"
    )
    
    try:
        service = AppointmentService(db=sync_db)
        availability_orm = await run_in_threadpool(
            service.create_availability,
            business_id=business_id_in_path,
            availability_data=availability_data
        )
        return availability_orm
    except ValueError as ve:
        logger.warning(f"Validation error creating availability for business {business_id_in_path}: {ve}", exc_info=False) # exc_info=False for expected client errors
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating availability for business {business_id_in_path}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating availability slot.")

@router.get(
    "/availability/business/{business_id_in_path}",
    response_model=List[schemas.AppointmentAvailabilityRead],
    summary="Get Business Availability"
)
async def get_business_availability_route(
    business_id_in_path: int,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    sync_db: Session = Depends(get_db)
):
    if current_business.id != business_id_in_path: # Basic auth check
        logger.warning(f"AuthZ Error: Business {current_business.id} trying to get availability for {business_id_in_path}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")

    logger.info(f"Availability Get: Fetching for business {business_id_in_path}")
    try:
        service = AppointmentService(db=sync_db)
        availabilities_orm = await run_in_threadpool(
            service.get_availability_by_business,
            business_id=business_id_in_path
        )
        return availabilities_orm
    except Exception as e:
        logger.error(f"Error getting availability for business {business_id_in_path}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching availability.")

@router.put(
    "/availability/{availability_id}",
    response_model=schemas.AppointmentAvailabilityRead,
    summary="Update Availability Slot"
)
async def update_availability_slot_route(
    availability_id: int,
    availability_update_data: schemas.AppointmentAvailabilityUpdate,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    sync_db: Session = Depends(get_db)
):
    logger.info(f"Availability Update: Slot ID {availability_id} by Business ID {current_business.id}")
    try:
        service = AppointmentService(db=sync_db)
        
        slot_to_update = await run_in_threadpool(service.get_availability_by_id, availability_id=availability_id)
        if not slot_to_update:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability slot not found.")
        if slot_to_update.business_id != current_business.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this slot.")

        updated_availability_orm = await run_in_threadpool(
            service.update_availability,
            availability_id=availability_id,
            availability_data=availability_update_data
        )
        return updated_availability_orm
    except ValueError as ve:
        logger.warning(f"Validation error updating availability slot {availability_id}: {ve}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating availability slot {availability_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating availability slot.")

@router.delete(
    "/availability/{availability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Availability Slot"
)
async def delete_availability_slot_route(
    availability_id: int,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    sync_db: Session = Depends(get_db)
):
    logger.info(f"Availability Delete: Slot ID {availability_id} by Business ID {current_business.id}")
    try:
        service = AppointmentService(db=sync_db)
        slot_to_delete = await run_in_threadpool(service.get_availability_by_id, availability_id=availability_id)
        if not slot_to_delete:
            logger.warning(f"Availability slot {availability_id} not found for deletion attempt by Business {current_business.id}.")
            return Response(status_code=status.HTTP_204_NO_CONTENT) # Idempotent
        if slot_to_delete.business_id != current_business.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this slot.")

        deleted = await run_in_threadpool(service.delete_availability, availability_id=availability_id)
        if not deleted: # Should ideally not happen if found and authorized
            logger.error(f"Availability slot {availability_id} delete operation returned false unexpectedly.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete slot.")
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting availability slot {availability_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting availability slot.")


# --- Appointment Request Routes (Async) ---
@router.get(
    "/requests/business/{business_id_in_path}",
    response_model=List[schemas.AppointmentRequestRead],
    summary="List Appointment Requests for a Business",
)
async def list_appointment_requests(
    business_id_in_path: int,
    status_filter: Optional[List[schemas.AppointmentRequestStatusEnum]] = Query(None, alias="status"),
    customer_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
):
    if current_business.id != business_id_in_path:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    
    logger.info(f"Appt List: Business ID {current_business.id}, Filters: status={status_filter}, customer_id={customer_id}")
    
    # AppointmentService instantiated with None for db, as async methods take db session as param
    service_instance = AppointmentService(db=None)
    requests = await service_instance.get_appointment_requests_by_business(
        db=db, business_id=current_business.id, statuses=status_filter,
        customer_id=customer_id, limit=limit, offset=offset
    )
    return requests

@router.get(
    "/requests/business/{business_id_in_path}/pending",
    response_model=List[schemas.AppointmentRequestDashboardItem],
    summary="List Pending/Actionable Appointment Requests for Dashboard",
)
async def list_pending_appointment_requests_for_dashboard(
    business_id_in_path: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
):
    if current_business.id != business_id_in_path:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    
    logger.info(f"Dashboard Appt List: Pending for Business ID {current_business.id}")
    pending_statuses = [
        models.AppointmentRequestStatusEnum.PENDING_OWNER_ACTION,
        models.AppointmentRequestStatusEnum.BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY,
        models.AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL,
        models.AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE,
    ]
    
    service_instance = AppointmentService(db=None)
    appointment_requests_orm = await service_instance.get_appointment_requests_by_business(
        db=db, business_id=current_business.id, statuses=pending_statuses, limit=limit, offset=offset
    )

    dashboard_items: List[schemas.AppointmentRequestDashboardItem] = []
    for req_orm in appointment_requests_orm:
        display_time_text, requested_datetime_utc_iso = None, None
        if req_orm.parsed_requested_time_text:
            display_time_text = req_orm.parsed_requested_time_text
        elif req_orm.parsed_requested_datetime_utc:
            display_time_text = req_orm.parsed_requested_datetime_utc.strftime("%a, %b %d %I:%M %p UTC")
        elif req_orm.owner_suggested_time_text:
            display_time_text = req_orm.owner_suggested_time_text
        elif req_orm.owner_suggested_datetime_utc:
            display_time_text = req_orm.owner_suggested_datetime_utc.strftime("%a, %b %d %I:%M %p UTC")

        if req_orm.parsed_requested_datetime_utc:
            requested_datetime_utc_iso = req_orm.parsed_requested_datetime_utc.isoformat()
        elif req_orm.owner_suggested_datetime_utc:
            requested_datetime_utc_iso = req_orm.owner_suggested_datetime_utc.isoformat()
        
        customer_name = req_orm.customer.customer_name if req_orm.customer else None
        customer_phone = req_orm.customer.phone if req_orm.customer else None

        dashboard_items.append(schemas.AppointmentRequestDashboardItem(
            id=req_orm.id, customer_id=req_orm.customer_id, customer_name=customer_name, customer_phone=customer_phone,
            original_message_text=req_orm.original_message_text, parsed_requested_time_text=req_orm.parsed_requested_time_text,
            parsed_requested_datetime_utc=req_orm.parsed_requested_datetime_utc, status=req_orm.status, source=req_orm.source,
            confirmed_datetime_utc=req_orm.confirmed_datetime_utc, owner_suggested_time_text=req_orm.owner_suggested_time_text,
            owner_suggested_datetime_utc=req_orm.owner_suggested_datetime_utc, # This is datetime from model
            customer_reschedule_suggestion=req_orm.customer_reschedule_suggestion, details=req_orm.details,
            created_at=req_orm.created_at, updated_at=req_orm.updated_at,
            display_time_text=display_time_text, requested_datetime_utc_iso=requested_datetime_utc_iso
        ))
    logger.info(f"Dashboard Appt List: Found {len(dashboard_items)} items for Business ID {current_business.id}")
    return dashboard_items

@router.patch(
    "/requests/{request_id}/status",
    response_model=schemas.AppointmentRequestRead,
    summary="Update Appointment Request Status by Owner",
)
async def update_appointment_request_status_route(
    request_id: int,
    update_payload: schemas.AppointmentRequestStatusUpdateByOwner = Body(...),
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    settings: Settings = Depends(get_settings)
):
    logger.info(f"Appt Update Status: Req ID {request_id} by Biz ID {current_business.id} to status {update_payload.new_status}.")
    service_instance = AppointmentService(db=None)
    updated_request = await service_instance.update_appointment_request_status_by_owner(
        db=db, request_id=request_id, update_data=update_payload,
        business_id=current_business.id, settings=settings
    )
    if not updated_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment request not found or action not authorized.")
    logger.info(f"Appt Update Status: Req ID {request_id} status updated to {updated_request.status.value}.")
    return updated_request

@router.post(
    "/requests/{request_id}/draft_action_reply",
    response_model=schemas.AppointmentActionDraftResponse,
    summary="Get AI-drafted SMS for a specific appointment action",
    status_code=status.HTTP_200_OK
)
async def get_ai_draft_for_appointment_action_route( # Added _route suffix
    request_id: int,
    payload: schemas.AppointmentActionDraftRequest, # Payload contains action_type and context
    db: AsyncSession = Depends(get_async_db),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"Draft Action Reply: Req ID {request_id}, Action: {payload.action_type}, Biz ID: {current_business.id}")

    stmt = select(models.AppointmentRequest).where(
        models.AppointmentRequest.id == request_id,
        models.AppointmentRequest.business_id == current_business.id
    ).options(selectinload(models.AppointmentRequest.customer))
    result = await db.execute(stmt)
    appointment_request = result.scalar_one_or_none()

    if not appointment_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment request not found or not authorized.")
    if not appointment_request.customer: # Should be loaded
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Associated customer data missing.")

    ai_service = AppointmentAIService(db=None) # db=None as drafting method is stateless regarding db session

    # Context for the AI service method
    time_details_for_ai = appointment_request.parsed_requested_time_text or \
                          (appointment_request.parsed_requested_datetime_utc.strftime('%a, %b %d @ %I:%M %p') if appointment_request.parsed_requested_datetime_utc else "the appointment")
    
    owner_new_time_text_for_ai = payload.context.owner_proposed_new_time_text if payload.context else None
    owner_reason_for_action_for_ai = payload.context.owner_reason_for_action if payload.context else None

    try:
        draft_message = await ai_service.draft_appointment_related_sms(
            business=current_business,
            customer_name=appointment_request.customer.customer_name,
            intent_type=payload.action_type, # This should be one of OWNER_ACTION_...
            time_details=time_details_for_ai,
            original_customer_request=appointment_request.original_message_text,
            owner_reason_for_action=owner_reason_for_action_for_ai, # Changed from owner_reason_for_cancel
            owner_proposed_new_time_text=owner_new_time_text_for_ai # New param added to service method
        )
        return schemas.AppointmentActionDraftResponse(draft_message=draft_message)
    except Exception as e:
        logger.error(f"Error generating AI draft for appt action {payload.action_type} for req {request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate AI draft message.")
@router.get(
    "/requests/{request_id}/ai-slot-suggestions",
    response_model=AiSuggestedSlotListResponse,
    summary="Get AI Suggested Appointment Slots for a Specific Request",
    status_code=status.HTTP_200_OK
)
async def get_ai_suggested_slots_for_request_route(
    request_id: int,
    num_suggestions: Optional[int] = Query(2, ge=1, le=3, description="Number of suggestions to return"),
    # search_days_range: Optional[int] = Query(7, ge=1, le=14, description="How many days out to search"), # Already in service method default
    db_async: AsyncSession = Depends(get_async_db), # For fetching the AppointmentRequest
    sync_db: Session = Depends(get_db), # For the AppointmentService instance
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business)
):
    logger.info(f"ROUTE: Fetching AI slot suggestions for Req ID: {request_id}, Biz ID: {current_business.id}")

    # 1. Fetch the AppointmentRequest to ensure it exists and for context
    stmt = select(models.AppointmentRequest).where(
        models.AppointmentRequest.id == request_id,
        models.AppointmentRequest.business_id == current_business.id
    ).options(
        selectinload(models.AppointmentRequest.customer), # Eager load customer if needed by service
        selectinload(models.AppointmentRequest.business)  # Eager load business if needed by service
    )
    result = await db_async.execute(stmt)
    appointment_request_orm = result.scalar_one_or_none()

    if not appointment_request_orm:
        logger.warning(f"ROUTE: Appointment request {request_id} not found or not authorized for Business {current_business.id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment request not found or not authorized.")

    if not appointment_request_orm.business: # This should be current_business
         logger.error(f"ROUTE: Business object not loaded for appointment request {request_id}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error: Business data missing.")

    # The customer_request_text is the original message or a parsed version
    customer_request_text_for_service = appointment_request_orm.original_message_text or \
                                        appointment_request_orm.parsed_requested_time_text or \
                                        "customer requesting an appointment"


    # 2. Instantiate AppointmentService with the synchronous session
    service = AppointmentService(db=sync_db)

    try:
        # 3. Call the service method
        # get_ai_suggested_slots_for_request is async and internally calls sync self.db methods
        # If service method was purely sync, we'd use run_in_threadpool.
        # Since it's async but built on a sync self.db, direct await is fine if FastAPI/Starlette handles thread execution for sync IO within it.
        # To be absolutely safe if there's blocking IO in its sync parts:
        # suggested_slot_dicts = await run_in_threadpool(
        #     service.get_ai_suggested_slots_for_request, # This doesn't work as get_ai_suggested_slots_for_request is async
        # )
        # The AppointmentService is init with sync self.db. Its async method calls sync methods using self.db.
        # This is generally okay in FastAPI, as sync methods called from async routes are run in a threadpool.

        suggested_slot_dicts = await service.get_ai_suggested_slots_for_request(
            business=appointment_request_orm.business, # Pass the loaded business object
            customer_request_text=customer_request_text_for_service,
            customer=appointment_request_orm.customer, # Pass the loaded customer object
            num_suggestions=num_suggestions,
            # search_days_range can use service default or be passed from query param
            reference_datetime_utc=appointment_request_orm.parsed_requested_datetime_utc or get_utc_now(),
            original_request_status=appointment_request_orm.status,
            original_request_confirmed_utc=appointment_request_orm.confirmed_datetime_utc,
            original_request_parsed_utc=appointment_request_orm.parsed_requested_datetime_utc
        )

        # Convert list of dicts to list of Pydantic models for response
        response_suggestions = [
            AiSuggestedSlotResponseItem(slot_utc=item["slot_utc"], status_message=item["status_message"])
            for item in suggested_slot_dicts
        ]

        logger.info(f"ROUTE: Returning {len(response_suggestions)} AI slot suggestions for Req ID: {request_id}.")
        return AiSuggestedSlotListResponse(suggestions=response_suggestions)

    except Exception as e:
        logger.error(f"ROUTE: Error calling get_ai_suggested_slots_for_request for Req ID {request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get AI slot suggestions.")