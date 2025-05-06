# backend/app/routes/customer_routes.py

# --- Standard Imports ---
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload # Added joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, desc # Added func
from datetime import datetime
from typing import Optional, List
import logging

# --- Pydantic Imports ---
from pydantic import BaseModel, Field # Added BaseModel, Field

# --- App Specific Imports ---
from app.database import get_db
# Import all needed Models
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog, Tag, CustomerTag
# Import all needed Schemas (ensure Customer includes 'tags' list)
from app.schemas import Customer, CustomerCreate, CustomerUpdate, TagRead
from app.services.consent_service import ConsentService
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


# === Existing Customer CRUD Routes ===

# --- Route to create a new customer ---
@router.post("/", response_model=Customer)
async def create_customer( # Keep async if needed for consent_service call
    customer: CustomerCreate,
    db: Session = Depends(get_db),
    consent_service: ConsentService = Depends(get_consent_service)
):
    """
    Creates a new customer record and triggers the double opt-in SMS process.
    """
    # ... (Keep your full implementation for create_customer as provided before) ...
    logger.info(f"Received request to create customer: {customer.customer_name} ({customer.phone}) for business {customer.business_id}")
    existing_customer = db.query(CustomerModel).filter(
         CustomerModel.phone == customer.phone,
         CustomerModel.business_id == customer.business_id
    ).first()
    if existing_customer:
         logger.warning(f"Attempt to create duplicate customer phone {customer.phone} for business {customer.business_id}")
         raise HTTPException(
             status_code=status.HTTP_409_CONFLICT,
             detail="Customer with this phone number already exists for this business."
         )
    db_customer = CustomerModel(**customer.model_dump())
    if db_customer.opted_in is None:
        db_customer.opted_in = False
    db.add(db_customer)
    try:
        db.commit()
        db.refresh(db_customer)
        logger.info(f"Customer created successfully (ID: {db_customer.id}) for business {db_customer.business_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating customer {customer.phone} for business {customer.business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save customer record.")
    try:
        logger.info(f"Attempting to send double opt-in SMS to customer ID: {db_customer.id} (Phone: {db_customer.phone}) for Business ID: {db_customer.business_id}")
        optin_result = await consent_service.send_double_optin_sms(
            customer_id=db_customer.id,
            business_id=db_customer.business_id
        )
        if optin_result and optin_result.get("success"):
             logger.info(f"Successfully initiated double opt-in process for customer {db_customer.id}. Message SID: {optin_result.get('message_sid')}")
        else:
             error_msg = optin_result.get('message', 'Unknown reason') if isinstance(optin_result, dict) else 'Unknown error structure'
             logger.error(f"Failed to send double opt-in SMS for customer {db_customer.id}: {error_msg}")
    except Exception as e:
        logger.error(f"Unexpected error triggering double opt-in SMS for customer {db_customer.id}: {e}", exc_info=True)
    # --- Ensure tags are loaded if needed for response (usually empty for new customer) ---
    # Force load tags or rely on the fact they will be empty
    db.refresh(db_customer, attribute_names=['tags']) # Explicitly load if needed
    customer_response = Customer.from_orm(db_customer)
    # Ensure tags attribute exists, default to empty list if not loaded
    if not hasattr(customer_response, 'tags'):
        customer_response.tags = []
    return customer_response


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
@router.get("/by-business/{business_id}", response_model=List[Customer])
def get_customers_by_business(
    business_id: int,
    tags: Optional[str] = Query(None, description="Comma-separated list of tag names to filter by (lowercase)"), # Add tags query param
    db: Session = Depends(get_db)
):
    """
    Retrieves customers for a business, optionally filtered by tags. Includes tags and consent status.
    """
    logger.info(f"Fetching customers for business_id: {business_id}, tags: {tags}")

    # Base query: Select customers and efficiently load their tags
    query = db.query(CustomerModel).options(
        joinedload(CustomerModel.tags) # Eager load tags using the relationship
    ).filter(CustomerModel.business_id == business_id)

    # Apply tag filtering if tags query parameter is provided
    tag_names = []
    if tags:
        tag_names = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_names:
            logger.info(f"Filtering by tags: {tag_names}")
            # Filter customers associated with ALL specified tags
            query = query.join(CustomerModel.tags).filter(Tag.name.in_(tag_names))
            query = query.group_by(CustomerModel.id)
            query = query.having(func.count(Tag.id) == len(tag_names)) # Match *all* tags

    # Execute the query
    try:
        customers_orm = query.order_by(CustomerModel.customer_name).all() # Add ordering
    except Exception as e:
        logger.error(f"Database error fetching customers for business {business_id} with tags {tags}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error fetching customers.")

    if not customers_orm:
        logger.info(f"No customers found matching criteria for business_id: {business_id}, tags: {tags}")
        return []

    customers_response = []
    for customer_orm in customers_orm:
        # Get latest consent status
        latest_status, latest_updated = get_latest_consent_status(customer_orm.id, db)
        effective_opted_in = latest_status == "opted_in"

        # Convert ORM to Pydantic
        try:
            # Use from_orm which should include tags due to joinedload and schema definition
            customer_dto = Customer.from_orm(customer_orm)
            # Explicitly set consent fields based on log status
            customer_dto.latest_consent_status = latest_status
            customer_dto.latest_consent_updated = latest_updated
            customer_dto.opted_in = effective_opted_in
            # Ensure tags list exists if relationship didn't populate automatically
            if not hasattr(customer_dto, 'tags'):
                 customer_dto.tags = [TagRead.from_orm(tag) for tag in customer_orm.tags] if hasattr(customer_orm, 'tags') else []

            customers_response.append(customer_dto)
        except Exception as validation_error:
             logger.error(f"Pydantic validation/conversion failed for customer {customer_orm.id}: {validation_error}.", exc_info=True)
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