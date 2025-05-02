from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BusinessProfile
from app.schemas import TwilioNumberAssign
from app.services.twilio_service import TwilioService
from app.auth import get_current_user
import logging  # Add this import

# Create logger
logger = logging.getLogger(__name__)  # Add this line

router = APIRouter(tags=["twilio"])


# Add these imports at the top if they aren't already there
from typing import Optional, List
from pydantic import BaseModel
from fastapi import Query, status # Make sure Query and status are imported

# --- Add Pydantic Models for Response (Recommended) ---
class AvailableNumber(BaseModel):
    phone_number: str
    friendly_name: str
    # Add other fields like locality, region if your service returns them

class AvailableNumbersResponse(BaseModel):
    numbers: List[AvailableNumber]


# -----------------------------------------------
# Twilio Phone Number Search Route
# -----------------------------------------------
@router.get(
    "/numbers",
    response_model=AvailableNumbersResponse
)
async def get_available_numbers(
    area_code: Optional[str] = Query(
        None, min_length=3, max_length=3, regex="^[0-9]{3}$",
        description="3-digit US area code to search within."
    ),
    zip_code: Optional[str] = Query(
        None, min_length=5, max_length=5, regex="^[0-9]{5}$",
        description="5-digit US ZIP code to search near."
    ),
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)
):
    """
    Searches for available Twilio phone numbers based on area code OR zip code.
    """
    logger.info(f"Received request to /numbers with area_code={area_code}, zip_code={zip_code}")

    if not area_code and not zip_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameters 'area_code' or 'zip_code' must be provided."
        )

    # Only log the parameters passed from the frontend
    logger.info(f"Route received search request: area_code={area_code}, zip_code={zip_code}")

    try:
        twilio_service = TwilioService(db)

        # --- FIX: Call the updated service method, passing BOTH params ---
        # The service will decide which one to use based on its internal logic
        available_numbers_list = await twilio_service.get_available_numbers(
            area_code=area_code,
            postal_code=zip_code # Pass zip_code value to postal_code param
        )

        # Format response (using .get for safety on potentially missing keys)
        formatted_numbers = [
             AvailableNumber(
                 phone_number=num.get("phone_number", "N/A"), # Provide default on missing key
                 friendly_name=num.get("friendly_name", "N/A")
             ) for num in available_numbers_list if num and num.get("phone_number") # Ensure num and phone_number exist
         ]

        logger.info(f"Route returning {len(formatted_numbers)} available numbers.")
        return AvailableNumbersResponse(numbers=formatted_numbers)

    except HTTPException as http_exc:
        raise http_exc # Re-raise errors from service/validation
    except Exception as e:
        logger.exception(f"Error in /numbers route (area={area_code}, zip={zip_code}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available numbers."
        )


# -----------------------------------------------
# Twilio Number Assignment Route
# -----------------------------------------------
@router.post("/assign")
async def purchase_and_assign_number(
    data: TwilioNumberAssign,
    db: Session = Depends(get_db)
    # current_user = Depends(get_current_user) # Still commented out
):
    logger.info(f"Received request to /assign with business_id={data.business_id}, phone_number={data.phone_number}")
    try:
        # Business lookup is fine
        business = db.query(BusinessProfile).filter(
            BusinessProfile.id == data.business_id
        ).first()

        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )

        # --- FIX: Pass 'db' when creating the service ---
        twilio_service = TwilioService(db)

        # --- FIX: Call the correct service method with correct arguments ---
        # Your service has 'purchase_and_assign_number_to_business(business_id, phone_number)'
        result = await twilio_service.purchase_and_assign_number_to_business(
            business_id=data.business_id,  # Pass the ID
            phone_number=data.phone_number # Pass the number
        )

        # The service method already updates the DB and returns a dict
        logger.info(f"Successfully assigned number {data.phone_number} to business {data.business_id}")
        return result

    except HTTPException as http_exc:
        raise http_exc # Re-raise validation/not found errors
    except Exception as e:
        logger.exception(f"Error assigning Twilio number {data.phone_number} to business {data.business_id}: {e}") # Use logger.exception
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Use 500
            detail="Failed to assign number due to an internal error." # Generic message
        )


# -----------------------------------------------
# Twilio Number Release Route
# -----------------------------------------------
@router.delete("/release")
async def release_assigned_number(
    business_id: int = Query(..., description="The ID of the business whose number should be released."),
    db: Session = Depends(get_db)
):
    """
    Releases the assigned Twilio number for the given business.
    This should be triggered when a business cancels or is offboarded.
    """
    logger.info(f"Received request to /release with business_id={business_id}")
    try:
        twilio_service = TwilioService(db)
        result = await twilio_service.release_assigned_twilio_number(business_id)
        logger.info(f"Successfully released Twilio number for business_id={business_id}")
        return result
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Error releasing Twilio number for business_id={business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to release number due to an internal error."
        )