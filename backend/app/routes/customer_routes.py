# backend/app/routes/customer_routes.py

# --- Standard Imports ---
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload # Added joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, desc # Added func
from datetime import datetime
from typing import Optional, List
from app import schemas, models, auth # Make sure models is imported

import logging

# --- Pydantic Imports ---
from pydantic import BaseModel, Field # Added BaseModel, Field

# --- App Specific Imports ---
from app.database import get_db
# Import all needed Models
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog, Tag, CustomerTag, Message as MessageModel
# Import all needed Schemas (ensure Customer includes 'tags' list)
from app.schemas import (
    Customer, CustomerCreate, CustomerUpdate, TagRead,
    CustomerConversation, ConversationMessageForTimeline,
    CustomerSummarySchema # Import the new summary schema
)
from app.services.consent_service import ConsentService
from app.services import message_service # To get conversation history
# from ..auth import get_current_user # Keep commented if not used directly here

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["customers"] # Existing router setup
)

# --- Helper function to get consent status ---
# (Keep your existing helper function as provided before)
def get_latest_consent_status(customer_id: int, db: Session) -> tuple[Optional[str], Optional[datetime]]:
    """Get the latest consent status and timestamp for a customer."""
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at))
        .first()
    )
    if not latest_consent:
        return None, None
    return latest_consent.status, latest_consent.replied_at

# --- Helper function to validate consent status ---
# (Keep your existing helper function as provided before)
def validate_consent_status(customer: CustomerModel, status: Optional[str]) -> bool:
    """Validate that the customer's opted_in status matches their latest consent status."""
    if not status:
        return not customer.opted_in
    return (
        (status == "opted_in" and customer.opted_in) or
        (status == "opted_out" and not customer.opted_in) or
        (status in ["pending", "waiting"])
    )

# --- Dependency function to inject ConsentService ---
# (Keep your existing dependency function as provided before)
def get_consent_service(db: Session = Depends(get_db)) -> ConsentService:
    """Dependency injector for ConsentService."""
    return ConsentService(db)

@router.post("/", response_model=schemas.Customer, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: schemas.CustomerCreate, # customer_data contains business_id
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
    # Removed: current_business_schema: schemas.BusinessProfile = Depends(auth.get_current_user)
    # If you use get_consent_service dependency:
    # consent_service_dependency: ConsentService = Depends(get_consent_service)
):
    logger.info(f"Received request to create customer: {customer_data.customer_name} ({customer_data.phone}) for business {customer_data.business_id}")

    # --- MODIFICATION: Fetch BusinessProfile using business_id from payload ---
    business_profile = db.query(models.BusinessProfile).filter(models.BusinessProfile.id == customer_data.business_id).first()
    if not business_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {customer_data.business_id} not found."
        )
    # --- END MODIFICATION ---

    existing_customer = db.query(models.Customer).filter(
        models.Customer.phone == customer_data.phone,
        models.Customer.business_id == customer_data.business_id # Use business_id from payload
    ).first()

    if existing_customer:
        logger.warning(f"Customer with phone {customer_data.phone} already exists for business {customer_data.business_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this phone number already exists for this business."
        )

    # business_id from customer_data is used here implicitly by **customer_data.model_dump()
    # or explicitly if models.Customer requires it separately.
    # Assuming schemas.CustomerCreate includes business_id and models.Customer accepts it.
    db_customer_dict = customer_data.model_dump()
    # Ensure business_id from the payload is used if it's not already part of the model_dump for model creation
    if 'business_id' not in db_customer_dict:
         db_customer_dict['business_id'] = customer_data.business_id
    
    db_customer = models.Customer(**db_customer_dict)
    
    if not hasattr(db_customer, 'sms_opt_in_status') or db_customer.sms_opt_in_status is None:
        db_customer.sms_opt_in_status = models.OptInStatus.NOT_SET.value

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

    # --- Conditional Double Opt-In using fetched business_profile ---
    if business_profile.twilio_number and business_profile.messaging_service_sid:
        logger.info(f"Business {business_profile.id} is configured for SMS. Attempting to send double opt-in SMS to customer ID: {db_customer.id} (Phone: {db_customer.phone})")
        consent_service = ConsentService(db) # Instantiate service locally
        try:
            background_tasks.add_task(
                consent_service.send_double_optin_sms,
                customer_id=db_customer.id,
                business_id=business_profile.id # Use ID from fetched business_profile
            )
        except Exception as e:
            logger.error(f"Failed to schedule double opt-in SMS for customer {db_customer.id}: {e}", exc_info=True)
    else:
        logger.info(f"Business {business_profile.id} is NOT fully configured for SMS (missing twilio_number or messaging_service_sid). Skipping automatic double opt-in for customer {db_customer.id}.")
    
    return db_customer # FastAPI will convert models.Customer to schemas.Customer



# --- Route to get a list of all customers (paginated) ---
@router.get("/", response_model=List[Customer])
def get_customers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Retrieves a paginated list of all customers."""
    # Consider adding joinedload('tags') here if you need tags on the general list view
    customers_orm = db.query(CustomerModel).options(
        joinedload(CustomerModel.tags) # Eager load tags
        ).offset(skip).limit(limit).all()

    # Convert ORM models to Pydantic models, handling potential missing tags attribute
    response_list = []
    for customer_orm in customers_orm:
        customer_dto = Customer.from_orm(customer_orm)
        if not hasattr(customer_dto, 'tags'): # Ensure tags list exists
            customer_dto.tags = [TagRead.from_orm(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []
        response_list.append(customer_dto)
    return response_list


# --- Route to get a specific customer by ID ---
@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    """Retrieves a specific customer by their ID, including tags and consent status."""
    # Eager load tags when fetching the customer
    customer_orm = db.query(CustomerModel).options(
        joinedload(CustomerModel.tags) # Eager load tags
    ).filter(CustomerModel.id == customer_id).first()

    if not customer_orm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    latest_status, latest_updated = get_latest_consent_status(customer_id, db)
    effective_opted_in = latest_status == "opted_in"

    # Convert ORM to Pydantic - joinedload ensures tags are available
    try:
        customer_response = Customer.from_orm(customer_orm)
        # Overwrite/add consent status fields
        customer_response.latest_consent_status = latest_status
        customer_response.latest_consent_updated = latest_updated
        customer_response.opted_in = effective_opted_in # Ensure response reflects log
        # Ensure tags are correctly populated (should be handled by from_orm with relationship)
        if not hasattr(customer_response, 'tags'): # Safety check
             customer_response.tags = [TagRead.from_orm(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []

        return customer_response
    except Exception as e:
        logger.error(f"Error converting customer {customer_id} to Pydantic model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing customer data.")


# --- Route to update an existing customer ---
@router.put("/{customer_id}", response_model=Customer)
def update_customer(
    customer_id: int,
    customer: CustomerUpdate, # Note: This doesn't include tags, handled separately
    db: Session = Depends(get_db)
):
    """Updates an existing customer's core details (tags updated via POST /{id}/tags)."""
    # ... (Keep your existing implementation for update_customer) ...
    db_customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    update_data = customer.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    db_customer.updated_at = datetime.utcnow()
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
    # Convert to Pydantic, ensuring tags are included
    customer_response = Customer.from_orm(db_customer)
    if not hasattr(customer_response, 'tags'):
        customer_response.tags = [TagRead.from_orm(tag) for tag in db_customer.tags] if hasattr(db_customer, 'tags') else []
    return customer_response


# --- Route to delete a customer ---
@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    """
    Deletes a customer record. Ensure related records (like customer_tags) cascade delete.
    """
    # ... (Keep your existing implementation for delete_customer) ...
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    try:
        # DB level ON DELETE CASCADE on foreign keys in CustomerTag, ConsentLog etc.
        # should handle deletion of related records. Verify constraints.
        db.delete(customer)
        db.commit()
        logger.info(f"Customer {customer_id} deleted successfully.")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Database error deleting customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete customer: Check foreign key constraints or logs.")


# --- MODIFIED: Route to get customers by business ID (with tag filtering) ---
@router.get("/by-business/{business_id}", response_model=List[CustomerSummarySchema]) # Changed response_model
def get_customers_by_business(
    business_id: int,
    tags: Optional[str] = Query(None, description="Comma-separated list of tag names to filter by (lowercase)"), # Add tags query param
    db: Session = Depends(get_db)
):
    """
    Retrieves customers for a business, optionally filtered by tags. Includes tags and consent status.
    """
    logger.info(f"Fetching customers for business_id: {business_id}, tags: {tags}")

    # Subquery to get the latest replied_at for each customer relevant to the business
    latest_replied_at_sq = db.query(
        ConsentLog.customer_id,
        func.max(ConsentLog.replied_at).label("max_replied_at")
    ).filter(ConsentLog.business_id == business_id).group_by(ConsentLog.customer_id).subquery()

    # Subquery to get the consent status for that latest replied_at (or latest ID as tie-breaker)
    # Using a lateral join or a window function might be more robust if multiple logs share the exact same max_replied_at.
    # However, for simplicity and common case, joining on customer_id and max_replied_at.
    # To handle cases where replied_at might be null or to get truly the latest log, max(id) is safer.
    latest_consent_id_sq = db.query(
        ConsentLog.customer_id,
        func.max(ConsentLog.id).label("max_log_id")
    ).filter(ConsentLog.business_id == business_id).group_by(ConsentLog.customer_id).subquery()

    consent_details_sq = db.query(
        ConsentLog.customer_id.label("consent_customer_id"),
        ConsentLog.status.label("latest_status"),
        ConsentLog.replied_at.label("latest_replied_at")
    ).join(
        latest_consent_id_sq,
        ConsentLog.id == latest_consent_id_sq.c.max_log_id
    ).subquery()

    # Base query for customers
    query = db.query(
        CustomerModel,
        consent_details_sq.c.latest_status,
        consent_details_sq.c.latest_replied_at
    ).outerjoin(
        consent_details_sq, CustomerModel.id == consent_details_sq.c.consent_customer_id
    ).options(
        joinedload(CustomerModel.tags) # Eager load tags
    ).filter(CustomerModel.business_id == business_id)


    # Apply tag filtering if tags query parameter is provided
    tag_names = []
    if tags:
        tag_names = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_names:
            logger.info(f"Filtering by tags: {tag_names}")
            query = query.join(CustomerModel.tags).filter(Tag.name.in_(tag_names))
            query = query.group_by(CustomerModel.id, consent_details_sq.c.latest_status, consent_details_sq.c.latest_replied_at) # Need to group by selected scalar columns from outer join
            query = query.having(func.count(Tag.id.distinct()) == len(tag_names))


    try:
        customers_and_consent_data = query.order_by(CustomerModel.customer_name).all()
    except Exception as e:
        logger.error(f"Database error fetching customers for business {business_id} with tags {tags}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error fetching customers.")

    if not customers_and_consent_data:
        logger.info(f"No customers found matching criteria for business_id: {business_id}, tags: {tags}")
        return []

    customers_response = []
    for customer_orm, latest_status_val, latest_updated_val in customers_and_consent_data:
        effective_opted_in = latest_status_val == "opted_in" if latest_status_val else customer_orm.opted_in

        try:
            # Construct the CustomerSummarySchema
            # Most fields are directly from customer_orm and already loaded consent details
            customer_summary_data = {
                "id": customer_orm.id,
                "customer_name": customer_orm.customer_name,
                "phone": customer_orm.phone,
                "lifecycle_stage": customer_orm.lifecycle_stage,
                "opted_in": effective_opted_in,
                "latest_consent_status": latest_status_val,
                "latest_consent_updated": latest_updated_val,
                "tags": [TagRead.from_orm(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') and customer_orm.tags else [],
                "business_id": customer_orm.business_id, # Ensure this is part of CustomerSummarySchema
                # Excluded fields: pain_points, interaction_history, timezone, is_generating_roadmap, last_generation_attempt
            }
            customer_summary_dto = CustomerSummarySchema(**customer_summary_data)
            customers_response.append(customer_summary_dto)
        except Exception as validation_error:
             logger.error(f"Pydantic validation/conversion failed for customer {customer_orm.id} to CustomerSummarySchema: {validation_error}.", exc_info=True)
             # Skip this customer or handle error appropriately

    logger.info(f"Returning {len(customers_response)} customers for business_id: {business_id}")
    return customers_response


# === NEW Tag Association Logic ===

# --- Schema for Tag Association Request Body (Inline Definition) ---
class TagAssociationRequest(BaseModel):
    tag_ids: List[int] = Field(..., description="List of Tag IDs to associate with the customer.")

# --- NEW Route to Associate/Update Tags for a Customer ---
@router.post("/{customer_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def associate_tags_with_customer(
    customer_id: int,
    payload: TagAssociationRequest, # Use the schema defined above
    db: Session = Depends(get_db)
):
    """
    Sets the associated tags for a customer using Tag IDs. Replaces existing associations.
    Send empty list [] to remove all tags.
    """
    # --- 1. Fetch the Customer ---
    # Use joinedload to potentially pre-load existing tags if needed, though we overwrite anyway
    db_customer = db.query(CustomerModel).options(joinedload(CustomerModel.tags)).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    business_id = db_customer.business_id
    new_tag_ids = set(payload.tag_ids) # Use set for efficient lookup and uniqueness

    # --- 2. Verify Provided Tag IDs ---
    tags_to_associate = []
    if new_tag_ids: # Only query if IDs were provided
        tags_query = db.query(Tag).filter(
            Tag.id.in_(new_tag_ids)
        )
        tags_to_associate = tags_query.all()

        # Check if all requested tags were found
        found_ids = {tag.id for tag in tags_to_associate}
        missing_ids = new_tag_ids - found_ids
        if missing_ids:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tag IDs not found: {list(missing_ids)}"
             )

        # Check if all found tags belong to the *correct* business
        mismatched_tags = [tag.id for tag in tags_to_associate if tag.business_id != business_id]
        if mismatched_tags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, # Or 403 Forbidden? 400 seems appropriate for bad input data.
                detail=f"Tag IDs do not belong to business {business_id}: {mismatched_tags}"
            )
    # If new_tag_ids is empty, tags_to_associate remains []

    # --- 3. Update Associations in DB (Replace Strategy) ---
    try:
        # Create new list of CustomerTag objects for the ORM relationship assignment
        # SQLAlchemy handles the insert/delete diffing when assigning to the relationship collection
        db_customer.tags = tags_to_associate # Assign the list of Tag objects directly

        db.commit()
        logger.info(f"Successfully updated tags for customer {customer_id}. New tag IDs: {list(new_tag_ids)}")
        return None # Return None for 204 No Content

    except Exception as e: # Catch potential DB errors during commit
        db.rollback()
        logger.error(f"Error updating tag associations via relationship for customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update tag associations due to server error.")

# --- End of Tag Association Logic ---

@router.get("/{customer_id}/conversation", response_model=CustomerConversation)
async def get_customer_conversation_route(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve the full conversation history for a specific customer.
    """
    # Make sure message_service is correctly instantiated if it's a class-based service
    # If it's a module with functions, direct call is fine.
    # Assuming message_service module has a function get_full_conversation_for_customer
    # or if MessageService class is instantiated elsewhere or provided via dependency injection.

    # For this example, let's assume MessageService needs to be instantiated.
    msg_service = message_service.MessageService(db)
    messages_orm = msg_service.get_full_conversation_for_customer(customer_id=customer_id)

    if not messages_orm:
        logger.info(f"No messages found for customer_id: {customer_id} by service. Returning empty conversation.")
        # Check if customer exists to differentiate between no messages and no customer
        customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        return CustomerConversation(customer_id=customer_id, messages=[])

    conversation_messages = [ConversationMessageForTimeline.from_orm(msg) for msg in messages_orm]

    return CustomerConversation(customer_id=customer_id, messages=conversation_messages)