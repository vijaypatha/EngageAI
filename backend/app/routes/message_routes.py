# backend/app/routes/message_routes.py

import logging
import uuid # Keep for type hinting if needed
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select # No longer directly used here

from app.database import get_async_db
from app import models, schemas, auth
# from app.config import Settings, get_settings # Not used in this version
from app.services.message_service import MessageService # Import MessageService

logger = logging.getLogger(__name__)

router = APIRouter(
    # Prefix and tags are managed in main.py
)

# --- Dependency for MessageService ---
async def get_message_service(db: AsyncSession = Depends(get_async_db)) -> MessageService:
    """Dependency to get an instance of MessageService with an active AsyncSession."""
    return MessageService(db=db)
# --- End Dependency ---


@router.post("/", response_model=schemas.MessageRead, status_code=status.HTTP_201_CREATED)
async def create_message_route( # Renamed to avoid conflict with service method name
    message_data: schemas.MessageCreate,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    message_service: MessageService = Depends(get_message_service) # MODIFIED: Use explicit dependency
):
    logger.info(f"Message Create Route: Attempt by Business ID {current_business.id} for customer {message_data.customer_id}")

    if message_data.business_id != current_business.id:
        logger.warning(
            f"Message Create AuthZ Error: Auth Business ID {current_business.id} "
            f"does not match payload business_id {message_data.business_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create message for another business."
        )

    # Customer existence and association check can be done here for early failure,
    # or rely on the service. If done here, the db session can be obtained from message_service.db
    # For example:
    # customer = await message_service.db.get(models.Customer, message_data.customer_id)
    # if not customer or customer.business_id != current_business.id:
    #     logger.warning(f"Message Create Route: Customer {message_data.customer_id} not found or not part of business {current_business.id}")
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found for this business.")

    try:
        created_message = await message_service.create_message(
            customer_id=message_data.customer_id,
            business_id=message_data.business_id,
            content=message_data.content,
            message_type=message_data.message_type,
            status=message_data.status,
            conversation_id=message_data.conversation_id,
            parent_id=message_data.parent_id,
            scheduled_send_at=message_data.scheduled_send_at,
            sent_at=message_data.sent_at,
            is_hidden=message_data.is_hidden,
            message_metadata=message_data.message_metadata,
            twilio_message_sid=message_data.twilio_message_sid,
            sender_type=message_data.sender_type,
            source=message_data.source
        )
        logger.info(f"Message Create Route: Successfully created message ID {created_message.id} for Business ID {current_business.id}")
        return created_message
    except ValueError as ve:
        logger.error(f"Message Create Route: ValueError - {ve}", exc_info=False) # exc_info False for expected errors
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Message Create Route: Unexpected error - {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create message.")


@router.get("/", response_model=List[schemas.MessageRead])
async def list_messages_route( # Renamed
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=0, le=500),
    conversation_id: Optional[uuid.UUID] = Query(None, description="Filter by conversation UUID"),
    customer_id: Optional[int] = Query(None, description="Filter messages by customer ID"),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    message_service: MessageService = Depends(get_message_service) # MODIFIED: Use explicit dependency
):
    logger.info(f"Message List Route: Request by Business ID {current_business.id}, Filters: conversation_id={conversation_id}, customer_id={customer_id}")
    
    if customer_id is not None:
        # Perform a quick check if the customer belongs to the current business
        db_session_for_check = message_service.db # Get session from injected service
        customer = await db_session_for_check.get(models.Customer, customer_id)
        if not customer or customer.business_id != current_business.id:
            logger.warning(f"Message List Route: Attempt to filter by customer {customer_id} not belonging to business {current_business.id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid customer filter for this business.")

    messages = await message_service.list_messages_for_business(
        business_id=current_business.id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        skip=skip,
        limit=limit
    )
    
    logger.info(f"Message List Route: Found {len(messages)} messages for Business ID {current_business.id}")
    return messages

@router.get("/{message_id}", response_model=schemas.MessageRead)
async def get_message_route( # Renamed
    message_id: int,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    message_service: MessageService = Depends(get_message_service) # MODIFIED: Use explicit dependency
):
    logger.info(f"Message Get Route: Request for ID {message_id} by Business ID {current_business.id}")
    
    message = await message_service.get_message_by_id_for_business(message_id, current_business.id)
    if not message:
        logger.warning(f"Message Get Route: Message ID {message_id} not found for Business ID {current_business.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found or not authorized.")
        
    logger.info(f"Message Get Route: Successfully retrieved message ID {message.id}")
    return message

@router.put("/{message_id}", response_model=schemas.MessageRead)
async def update_message_route( # Renamed
    message_id: int,
    message_data: schemas.MessageUpdate,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    message_service: MessageService = Depends(get_message_service) # MODIFIED: Use explicit dependency
):
    logger.info(f"Message Update Route: Request for ID {message_id} by Business ID {current_business.id} with data: {message_data.model_dump(exclude_unset=True)}")
    
    try:
        updated_message = await message_service.update_message_content_schedule( # Changed to use the more specific service method
            message_id=message_id,
            business_id=current_business.id,
            message_data=message_data
        )
        if not updated_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found, not authorized, or no changes applied.")
        
        logger.info(f"Message Update Route: Successfully updated message ID {updated_message.id}")
        return updated_message
    except ValueError as ve:
        logger.warning(f"Message Update Route: ValueError for message ID {message_id} - {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Message Update Route: Error updating message ID {message_id} - {e}", exc_info=True)
        # Avoid re-raising generic Exception as HTTPException(500) if it's already an HTTPException
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update message.")


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_route( # Renamed
    message_id: int,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
    message_service: MessageService = Depends(get_message_service) # MODIFIED: Use explicit dependency
):
    logger.info(f"Message Delete Route: Request for ID {message_id} by Business ID {current_business.id}")
    
    try:
        deleted = await message_service.delete_message_by_id_logically(
            message_id=message_id,
            business_id=current_business.id
        )
        
        if not deleted:
            logger.warning(f"Message Delete Route: Message ID {message_id} not found or not authorized for deletion by Business ID {current_business.id}, or delete operation failed.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found or not authorized for deletion.")
            
        logger.info(f"Message Delete Route: Message ID {message_id} processed for deletion.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        logger.error(f"Message Delete Route: Error deleting message ID {message_id} - {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete message.")