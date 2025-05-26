# backend/app/routes/customer_routes.py

# --- Standard Imports ---
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, desc
from datetime import datetime, timezone # Ensure timezone is imported for utcnow()
from typing import Optional, List

# --- App Specific Imports ---
from app.database import get_db
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog, Tag, CustomerTag, OptInStatus # Added OptInStatus
from app.schemas import (
    CustomerRead, # CHANGED: Import CustomerRead instead of Customer
    CustomerCreate,
    CustomerUpdate,
    TagRead
)
from app.services.consent_service import ConsentService
from app import models # To access models.OptInStatus if needed directly

import logging

# --- Pydantic Imports ---
from pydantic import BaseModel, Field # Keep if used, e.g., for inline schemas

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["customers"]
)

# --- Helper function to get consent status ---
def get_latest_consent_status(customer_id: int, db: Session) -> tuple[Optional[str], Optional[datetime]]:
    """Get the latest consent status and timestamp for a customer."""
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at), desc(ConsentLog.created_at)) # Prioritize replied_at
        .first()
    )
    if not latest_consent:
        # Check original sms_opt_in_status from customer table if no log
        customer = db.query(CustomerModel.sms_opt_in_status, CustomerModel.updated_at).filter(CustomerModel.id == customer_id).first()
        if customer:
            return customer.sms_opt_in_status.value if customer.sms_opt_in_status else None, customer.updated_at
        return None, None
    return latest_consent.status.value if latest_consent.status else None, latest_consent.replied_at or latest_consent.created_at


@router.post("/", response_model=CustomerRead, status_code=status.HTTP_201_CREATED) # CHANGED
async def create_customer(
    customer_data: CustomerCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    logger.info(f"Received request to create customer: {customer_data.customer_name} ({customer_data.phone}) for business {customer_data.business_id}")

    business_profile = db.query(BusinessProfile).filter(BusinessProfile.id == customer_data.business_id).first()
    if not business_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {customer_data.business_id} not found."
        )

    existing_customer = db.query(CustomerModel).filter(
        CustomerModel.phone == customer_data.phone,
        CustomerModel.business_id == customer_data.business_id
    ).first()

    if existing_customer:
        logger.warning(f"Customer with phone {customer_data.phone} already exists for business {customer_data.business_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this phone number already exists for this business."
        )
    
    db_customer_dict = customer_data.model_dump()
    # Ensure sms_opt_in_status from schema is used if provided, otherwise model's default applies.
    # The model OptInStatus.NOT_SET should be the default if not in customer_data.
    # If customer_data.sms_opt_in_status is already an enum from schema, it's fine.
    # If it's a string, SQLAlchemy model will handle conversion if SAEnum is configured.
    db_customer = CustomerModel(**db_customer_dict)
    
    # If sms_opt_in_status is not set by payload, ensure model default (NOT_SET) is applied.
    # This is usually handled by SQLAlchemy model default, but explicit check if needed:
    if db_customer.sms_opt_in_status is None:
         db_customer.sms_opt_in_status = OptInStatus.NOT_SET


    db.add(db_customer)
    try:
        db.commit()
        db.refresh(db_customer)
        logger.info(f"Customer created successfully (ID: {db_customer.id}) for business {db_customer.business_id}")
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating customer for business {db_customer.business_id}: {e}", exc_info=True)
        if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A customer with this phone number might already exist or another unique field conflicts.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save customer due to a database issue.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating customer {customer_data.phone} for business {db_customer.business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save customer record.")

    if business_profile.twilio_number and (business_profile.messaging_service_sid or business_profile.twilio_sid): # Check for SID too
        logger.info(f"Business {business_profile.id} is configured for SMS. Attempting to send double opt-in SMS to customer ID: {db_customer.id} (Phone: {db_customer.phone})")
        consent_service = ConsentService(db)
        try:
            background_tasks.add_task(
                consent_service.send_double_optin_sms,
                customer_id=db_customer.id,
                business_id=business_profile.id
            )
            logger.info(f"Double opt-in SMS task scheduled for customer {db_customer.id}.")
        except Exception as e:
            logger.error(f"Failed to schedule double opt-in SMS for customer {db_customer.id}: {e}", exc_info=True)
    else:
        logger.info(f"Business {business_profile.id} is NOT fully configured for SMS. Skipping automatic double opt-in for customer {db_customer.id}.")
    
    # For Pydantic v2, direct return is fine if CustomerRead.Config.from_attributes = True
    # For Pydantic v1, it was schemas.Customer.from_orm(db_customer)
    return db_customer


@router.get("/", response_model=List[CustomerRead]) # CHANGED
def get_customers(
    business_id: int, # Assuming customers are always fetched per business
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Retrieves a paginated list of all customers for a given business."""
    customers_orm = db.query(CustomerModel).filter(CustomerModel.business_id == business_id).options(
        joinedload(CustomerModel.tags)
    ).order_by(CustomerModel.customer_name, CustomerModel.id).offset(skip).limit(limit).all() # Added ordering

    response_list = []
    for customer_orm in customers_orm:
        latest_status, latest_updated = get_latest_consent_status(customer_orm.id, db)
        # For Pydantic v2, direct conversion is fine
        customer_dto = CustomerRead.model_validate(customer_orm) # Pydantic v2 way
        # For Pydantic v1: customer_dto = CustomerRead.from_orm(customer_orm)
        
        customer_dto.latest_consent_status = latest_status
        customer_dto.latest_consent_updated = latest_updated
        customer_dto.opted_in = (latest_status == OptInStatus.OPTED_IN.value) # Ensure it's boolean based on status

        # Tags should be handled by model_validate/from_orm if schema is correct
        # If tags are not automatically populated in CustomerRead from customer_orm.tags:
        if customer_dto.tags is None or not isinstance(customer_dto.tags, list): # Check if conversion happened
             customer_dto.tags = [TagRead.model_validate(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []

        response_list.append(customer_dto)
    return response_list


@router.get("/{customer_id}", response_model=CustomerRead) # CHANGED
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    """Retrieves a specific customer by their ID, including tags and consent status."""
    customer_orm = db.query(CustomerModel).options(
        joinedload(CustomerModel.tags)
    ).filter(CustomerModel.id == customer_id).first()

    if not customer_orm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    latest_status, latest_updated = get_latest_consent_status(customer_id, db)
    
    # For Pydantic v2
    customer_response = CustomerRead.model_validate(customer_orm)
    # For Pydantic v1: customer_response = CustomerRead.from_orm(customer_orm)
    
    customer_response.latest_consent_status = latest_status
    customer_response.latest_consent_updated = latest_updated
    customer_response.opted_in = (latest_status == OptInStatus.OPTED_IN.value)
    
    if customer_response.tags is None or not isinstance(customer_response.tags, list):
        customer_response.tags = [TagRead.model_validate(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []
        
    return customer_response


@router.put("/{customer_id}", response_model=CustomerRead) # CHANGED
def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate, # Use CustomerUpdate schema
    db: Session = Depends(get_db)
):
    db_customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    update_data = customer_data.model_dump(exclude_unset=True)
    logger.info(f"Updating customer {customer_id} with data: {update_data}")

    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    # Ensure updated_at is set
    db_customer.updated_at = datetime.now(timezone.utc) 

    try:
        db.commit()
        db.refresh(db_customer)
        # Explicitly load tags after update for the response
        db.refresh(db_customer, attribute_names=['tags']) 
        logger.info(f"Customer {customer_id} updated successfully.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update customer record.")

    # Convert to Pydantic, ensuring tags are included and consent status is fresh
    latest_status, latest_updated = get_latest_consent_status(db_customer.id, db)
    # Pydantic v2
    customer_response = CustomerRead.model_validate(db_customer)
    # Pydantic v1: customer_response = CustomerRead.from_orm(db_customer)

    customer_response.latest_consent_status = latest_status
    customer_response.latest_consent_updated = latest_updated
    customer_response.opted_in = (latest_status == OptInStatus.OPTED_IN.value)

    if customer_response.tags is None or not isinstance(customer_response.tags, list):
        customer_response.tags = [TagRead.model_validate(tag) for tag in db_customer.tags] if hasattr(db_customer, 'tags') else []

    return customer_response


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    try:
        db.delete(customer)
        db.commit()
        logger.info(f"Customer {customer_id} deleted successfully.")
        return Response(status_code=status.HTTP_204_NO_CONTENT) # Explicit Response for 204
    except Exception as e:
        db.rollback()
        logger.error(f"Database error deleting customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete customer: Check foreign key constraints or logs.")


@router.get("/by-business/{business_id}", response_model=List[CustomerRead]) # CHANGED
def get_customers_by_business(
    business_id: int,
    tags: Optional[str] = Query(None, description="Comma-separated list of tag names to filter by (lowercase)"),
    db: Session = Depends(get_db)
):
    logger.info(f"Fetching customers for business_id: {business_id}, tags: {tags}")
    query = db.query(CustomerModel).options(
        joinedload(CustomerModel.tags)
    ).filter(CustomerModel.business_id == business_id)

    tag_names = []
    if tags:
        tag_names = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_names:
            logger.info(f"Filtering by tags: {tag_names}")
            query = query.join(CustomerModel.tags).filter(Tag.name.in_(tag_names))
            query = query.group_by(CustomerModel.id).having(func.count(Tag.id) == len(tag_names))

    try:
        customers_orm = query.order_by(CustomerModel.customer_name, CustomerModel.id).all()
    except Exception as e:
        logger.error(f"Database error fetching customers for business {business_id} with tags {tags}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error fetching customers.")

    if not customers_orm:
        logger.info(f"No customers found matching criteria for business_id: {business_id}, tags: {tags}")
        return []

    customers_response = []
    for customer_orm in customers_orm:
        latest_status, latest_updated = get_latest_consent_status(customer_orm.id, db)
        
        # Pydantic v2
        customer_dto = CustomerRead.model_validate(customer_orm)
        # Pydantic v1: customer_dto = CustomerRead.from_orm(customer_orm)
        
        customer_dto.latest_consent_status = latest_status
        customer_dto.latest_consent_updated = latest_updated
        customer_dto.opted_in = (latest_status == OptInStatus.OPTED_IN.value)
        
        if customer_dto.tags is None or not isinstance(customer_dto.tags, list):
            customer_dto.tags = [TagRead.model_validate(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []
        
        customers_response.append(customer_dto)

    logger.info(f"Returning {len(customers_response)} customers for business_id: {business_id}")
    return customers_response


class TagAssociationRequest(BaseModel):
    tag_ids: List[int] = Field(..., description="List of Tag IDs to associate with the customer.")

@router.post("/{customer_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def associate_tags_with_customer(
    customer_id: int,
    payload: TagAssociationRequest,
    db: Session = Depends(get_db)
):
    db_customer = db.query(CustomerModel).options(joinedload(CustomerModel.tags)).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    business_id = db_customer.business_id
    new_tag_ids = set(payload.tag_ids)

    tags_to_associate = []
    if new_tag_ids:
        tags_query = db.query(Tag).filter(Tag.id.in_(new_tag_ids))
        tags_to_associate = tags_query.all()

        found_ids = {tag.id for tag in tags_to_associate}
        missing_ids = new_tag_ids - found_ids
        if missing_ids:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tag IDs not found: {list(missing_ids)}"
             )

        mismatched_tags = [tag.id for tag in tags_to_associate if tag.business_id != business_id]
        if mismatched_tags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tag IDs do not belong to business {business_id}: {mismatched_tags}"
            )
    try:
        db_customer.tags = tags_to_associate
        db.commit()
        logger.info(f"Successfully updated tags for customer {customer_id}. New tag IDs: {list(new_tag_ids)}")
        return Response(status_code=status.HTTP_204_NO_CONTENT) # Explicit Response for 204

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating tag associations for customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update tag associations.")