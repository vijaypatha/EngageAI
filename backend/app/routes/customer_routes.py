# backend/app/routes/customer_routes.py

from fastapi import APIRouter, Depends, HTTPException, status # Ensure status is imported
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog # Ensure models are imported
from app.schemas import Customer, CustomerCreate, CustomerUpdate # Ensure schemas are imported
from app.services.consent_service import ConsentService # <<< IMPORT ConsentService
from datetime import datetime
from typing import Optional, List
# from ..auth import get_current_user # Commented out if not currently used here
import logging # Ensure logging is imported

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["customers"]
)

# --- Helper function to get consent status ---
def get_latest_consent_status(customer_id: int, db: Session) -> tuple[Optional[str], Optional[datetime]]:
    """Get the latest consent status and timestamp for a customer."""
    # Query the ConsentLog table, filter by customer_id, order by replied_at descending, get the first result
    latest_consent = (
        db.query(ConsentLog)
        .filter(ConsentLog.customer_id == customer_id)
        .order_by(desc(ConsentLog.replied_at)) # Order by replied_at to get the latest interaction
        .first()
    )
    
    if not latest_consent:
        # If no consent log exists, return None for both status and timestamp
        return None, None
        
    # Return the status and replied_at timestamp from the latest log entry
    return latest_consent.status, latest_consent.replied_at

# --- Helper function to validate consent status (kept for potential use) ---
def validate_consent_status(customer: CustomerModel, status: Optional[str]) -> bool:
    """Validate that the customer's opted_in status matches their latest consent status."""
    if not status:
        # If there's no consent status log, the customer should not be marked as opted_in
        return not customer.opted_in
        
    # Check if the customer's opted_in flag matches the latest consent status
    return (
        (status == "opted_in" and customer.opted_in) or
        (status == "opted_out" and not customer.opted_in) or
        # If status is pending or waiting, the opted_in flag doesn't strictly matter for validation here
        (status in ["pending", "waiting"]) 
    )

# --- Dependency function to inject ConsentService ---
def get_consent_service(db: Session = Depends(get_db)) -> ConsentService:
    """Dependency injector for ConsentService."""
    return ConsentService(db)

# --- Route to create a new customer ---
@router.post("/", response_model=Customer)
async def create_customer( # <<< Make the function async
    customer: CustomerCreate, # Input data validated by Pydantic schema
    db: Session = Depends(get_db), # Inject database session
    # Inject ConsentService dependency using the function defined above
    consent_service: ConsentService = Depends(get_consent_service) 
    # current_user: dict = Depends(get_current_user) # Optional: Add if user auth is needed
):
    """
    Creates a new customer record and triggers the double opt-in SMS process.
    """
    logger.info(f"Received request to create customer: {customer.customer_name} ({customer.phone}) for business {customer.business_id}")
    
    # Check if customer with the same phone already exists for this specific business
    existing_customer = db.query(CustomerModel).filter(
         CustomerModel.phone == customer.phone,
         CustomerModel.business_id == customer.business_id
    ).first()
    
    if existing_customer:
         logger.warning(f"Attempt to create duplicate customer phone {customer.phone} for business {customer.business_id}")
         # Return HTTP 409 Conflict if customer already exists
         raise HTTPException(
             status_code=status.HTTP_409_CONFLICT,
             detail="Customer with this phone number already exists for this business."
         )
         
    # Create a new CustomerModel instance from the input schema data
    db_customer = CustomerModel(**customer.model_dump())
    
    # Ensure opted_in status is explicitly set to False initially
    if db_customer.opted_in is None:
        db_customer.opted_in = False 
    # You could also default opted_in=False in the CustomerCreate schema or CustomerModel itself

    # Add the new customer instance to the session
    db.add(db_customer)
    
    try:
        # Commit the transaction to save the customer to the database
        db.commit()
        # Refresh the instance to get the database-assigned ID and default values
        db.refresh(db_customer)
        logger.info(f"Customer created successfully (ID: {db_customer.id}) for business {db_customer.business_id}")
    except Exception as e:
        # Rollback the transaction if commit fails
        db.rollback()
        logger.error(f"Database error creating customer {customer.phone} for business {customer.business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save customer record.")

    # --- Trigger Double Opt-in SMS AFTER successful customer creation ---
    try:
        logger.info(f"Attempting to send double opt-in SMS to customer ID: {db_customer.id} (Phone: {db_customer.phone}) for Business ID: {db_customer.business_id}")
        # Call the service method that sends the SMS AND creates the 'pending' ConsentLog entry
        optin_result = await consent_service.send_double_optin_sms( 
            customer_id=db_customer.id, 
            business_id=db_customer.business_id
        )
        # Log the outcome of the opt-in attempt
        if optin_result and optin_result.get("success"):
             logger.info(f"Successfully initiated double opt-in process for customer {db_customer.id}. Message SID: {optin_result.get('message_sid')}")
        else:
             # Log the failure but don't necessarily fail the whole customer creation request,
             # as the customer record itself was successfully created.
             error_msg = optin_result.get('message', 'Unknown reason') if isinstance(optin_result, dict) else 'Unknown error structure'
             logger.error(f"Failed to send double opt-in SMS for customer {db_customer.id}: {error_msg}")
             # Consider adding a status field to the Customer model to track opt-in initiation failure?
             
    except Exception as e:
        # Log any unexpected errors during the opt-in triggering process
        logger.error(f"Unexpected error triggering double opt-in SMS for customer {db_customer.id}: {e}", exc_info=True)
        # Do not raise HTTPException here, as the customer was already created.

    # Return the created customer data using the Pydantic model for serialization
    # The Customer schema now includes latest_consent_status, which will be None initially
    return Customer.from_orm(db_customer) 

# --- Route to get a list of all customers (paginated) ---
@router.get("/", response_model=List[Customer])
def get_customers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Retrieves a paginated list of all customers."""
    customers = db.query(CustomerModel).offset(skip).limit(limit).all()
    # Convert ORM models to Pydantic models for the response
    return [Customer.from_orm(customer) for customer in customers]

# --- Route to get a specific customer by ID ---
@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    """Retrieves a specific customer by their ID."""
    # Query the database for the customer
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        # Raise 404 if customer not found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    # Get latest consent status and timestamp from ConsentLog
    latest_status, latest_updated = get_latest_consent_status(customer_id, db)
    
    # --- Synchronization Logic (Optional but recommended) ---
    # If the customer's opted_in flag seems out of sync with the latest log, log a warning.
    # You could optionally force an update here, but be careful about unintended consequences.
    # Let's just log the warning for now. The get_customers_by_business logic already handles setting the response `opted_in` based on the log.
    is_consistent = validate_consent_status(customer, latest_status)
    if not is_consistent:
        logger.warning(f"Inconsistent consent status detected for customer {customer_id}. Customer.opted_in={customer.opted_in}, latest_consent_log_status='{latest_status}'. Fetch relies on log status.")
        # Example: Force update Customer.opted_in based on log (use with caution)
        # expected_opted_in = latest_status == "opted_in"
        # if customer.opted_in != expected_opted_in:
        #     logger.info(f"Attempting to correct Customer.opted_in for customer {customer_id} to {expected_opted_in}")
        #     customer.opted_in = expected_opted_in
        #     try:
        #         db.commit()
        #         db.refresh(customer)
        #     except Exception:
        #         db.rollback()
        #         logger.error(f"Failed to correct opted_in status for customer {customer_id}")
    
    # --- Populate response model ---
    # Convert the ORM model to the Pydantic response model.
    # We need to manually add the latest consent info fetched from the log.
    customer_response = Customer.from_orm(customer).model_dump() # Convert to dict first
    customer_response["latest_consent_status"] = latest_status
    customer_response["latest_consent_updated"] = latest_updated
    # Set the 'opted_in' field in the response based *only* on the latest log status for consistency
    customer_response["opted_in"] = latest_status == "opted_in" 
    
    # Validate the dictionary against the Pydantic model before returning
    return Customer(**customer_response)

# --- Route to update an existing customer ---
@router.put("/{customer_id}", response_model=Customer)
def update_customer(
    customer_id: int,
    customer: CustomerUpdate, # Input data validated by Pydantic schema
    db: Session = Depends(get_db)
    # current_user: dict = Depends(get_current_user) # Optional: Add auth if needed
):
    """Updates an existing customer's details."""
    # Fetch the existing customer record
    db_customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        # Raise 404 if customer not found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    # Update the customer object with fields present in the input data
    update_data = customer.model_dump(exclude_unset=True) # Get only fields that were provided
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    # Set the updated_at timestamp
    db_customer.updated_at = datetime.utcnow() 
    
    try:
        # Commit the changes to the database
        db.commit()
        # Refresh the instance to get updated data
        db.refresh(db_customer)
        logger.info(f"Customer {customer_id} updated successfully.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error updating customer {customer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update customer record.")
        
    # Return the updated customer data
    return Customer.from_orm(db_customer)

# --- Route to delete a customer ---
@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    """
    Deletes a customer record. 
    Note: This will fail if foreign key constraints exist (e.g., messages referencing this customer).
    Consider implementing cascading deletes or deleting related records first.
    """
    # Fetch the customer record
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        # Raise 404 if customer not found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    try:
        # Delete the customer record
        db.delete(customer)
        # Commit the transaction
        db.commit()
        logger.info(f"Customer {customer_id} deleted successfully.")
        # Return No Content success response
        return None # FastAPI handles 204 automatically when None is returned
    except Exception as e:
        db.rollback()
        logger.error(f"Database error deleting customer {customer_id}: {e}", exc_info=True)
        # Handle potential foreign key violations etc.
        # Re-raise as a 500 or potentially 409 Conflict if due to FK violation
        raise HTTPException(status_code=500, detail=f"Failed to delete customer: {e}")
    

# --- Route to get customers by business ID (including consent info) ---
@router.get("/by-business/{business_id}", response_model=List[Customer])
def get_customers_by_business(business_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a list of customers associated with a specific business ID,
    including their latest consent status and timestamp derived from ConsentLog.
    The 'opted_in' field in the response reflects the latest consent status.
    """
    logger.info(f"Fetching customers for business_id: {business_id}")

    # Query customers for the given business
    customers_orm = db.query(CustomerModel).filter(CustomerModel.business_id == business_id).all()

    if not customers_orm:
        logger.info(f"No customers found for business_id: {business_id}")
        return [] # Return empty list if no customers found

    customers_response = []
    for customer_orm in customers_orm:
        # Get latest consent status and timestamp using the helper function
        latest_status, latest_updated = get_latest_consent_status(customer_orm.id, db)

        # Determine the effective opted_in status based *only* on the log
        effective_opted_in = latest_status == "opted_in"

        # Create a dictionary from the ORM customer object
        # Manual construction to ensure all fields, including added consent info, are present
        customer_data = {
            "id": customer_orm.id,
            "customer_name": customer_orm.customer_name,
            "phone": customer_orm.phone,
            "lifecycle_stage": customer_orm.lifecycle_stage,
            "pain_points": customer_orm.pain_points,
            "interaction_history": customer_orm.interaction_history,
            "business_id": customer_orm.business_id,
            "timezone": customer_orm.timezone,
            "opted_in": effective_opted_in, # Use status derived from consent log
            "is_generating_roadmap": customer_orm.is_generating_roadmap,
            "last_generation_attempt": customer_orm.last_generation_attempt,
            "created_at": customer_orm.created_at,
            "updated_at": customer_orm.updated_at,
            # Add the fetched consent fields
            "latest_consent_status": latest_status,
            "latest_consent_updated": latest_updated
        }
        # Validate the dictionary against the Pydantic model and append
        try:
             validated_customer = Customer(**customer_data)
             customers_response.append(validated_customer)
        except Exception as validation_error:
             logger.error(f"Pydantic validation failed for customer {customer_orm.id} data: {validation_error}. Data: {customer_data}")
             # Optionally skip adding invalid data or handle differently


    logger.info(f"Returning {len(customers_response)} customers for business_id: {business_id}")
    # FastAPI will serialize the list of Pydantic Customer models correctly
    return customers_response