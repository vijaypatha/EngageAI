# backend/app/routes/twilio_routes.py

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession # For async routes
from sqlalchemy.orm import Session # Keep ONLY if TwilioService strictly requires sync session

from app.database import get_async_db, get_db # Provide both get_db and get_async_db
from app import models, schemas, auth # CORRECTLY IMPORT auth module
# REMOVE: from app.auth import get_current_user 
from app.config import Settings, get_settings
from app.services.twilio_service import TwilioService


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Twilio Operations"])


class AvailableNumber(schemas.BaseModel):
    phone_number: str
    friendly_name: str
    locality: Optional[str] = None
    region: Optional[str] = None

class AvailableNumbersResponse(schemas.BaseModel):
    numbers: List[AvailableNumber]


@router.get(
    "/numbers",
    response_model=AvailableNumbersResponse,
    # If this route needs authentication (e.g., only a logged-in business can search numbers for their context)
    # add: current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
)
async def get_available_numbers_route(
    area_code: Optional[str] = Query(
        None, min_length=3, max_length=3, regex="^[0-9]{3}$",
        description="3-digit US area code to search within."
    ),
    zip_code: Optional[str] = Query(
        None, min_length=5, max_length=5, regex="^[0-9]{5}$",
        description="5-digit US ZIP code to search near."
    ),
    # db_async: AsyncSession = Depends(get_async_db) # For async operations
    # TwilioService currently takes a sync Session. This is problematic in an async route.
):
    logger.info(f"Twilio Numbers: Request with area_code={area_code}, zip_code={zip_code}")

    if not area_code and not zip_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameters 'area_code' or 'zip_code' must be provided."
        )
    
    # --- Handling Synchronous TwilioService from Async Route ---
    # This is a known pain point. Ideally, TwilioService and its client calls
    # would be adapted for async (e.g., using run_in_threadpool for blocking I/O).
    # For now, to make it "work" to resolve the import error, we get a sync session.
    sync_db_session = None
    try:
        # Obtain a sync session for the TwilioService instantiation
        sync_db_session = next(get_db()) 
        twilio_service = TwilioService(db=sync_db_session) # TwilioService expects sync session

        from fastapi.concurrency import run_in_threadpool

        # Twilio client calls inside get_available_numbers are blocking.
        # The method twilio_service.get_available_numbers is async, but what it *does* matters.
        # If it directly calls the sync Twilio client, it should use asyncio.to_thread internally.
        # Assuming the method is correctly implemented to be awaitable from an async context.
        available_numbers_list = await twilio_service.get_available_numbers( # This was not awaited before, but service method is async
            country_code="US",
            area_code=area_code,
            postal_code=zip_code
        )
        
        formatted_numbers = [
             AvailableNumber(
                 phone_number=num.get("phone_number", "N/A"),
                 friendly_name=num.get("friendly_name", "N/A"),
                 locality=num.get("locality"),
                 region=num.get("region")
             ) for num in available_numbers_list if num and num.get("phone_number")
         ]
        logger.info(f"Twilio Numbers: Returning {len(formatted_numbers)} available numbers.")
        return AvailableNumbersResponse(numbers=formatted_numbers)
    except HTTPException as http_exc:
        if sync_db_session: sync_db_session.close() # Ensure close on handled error
        raise http_exc
    except Exception as e:
        logger.exception(f"Twilio Numbers: Error in /numbers route (area={area_code}, zip={zip_code}): {e}")
        if sync_db_session: sync_db_session.close() # Ensure close on unhandled error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available numbers."
        )
    finally:
        if sync_db_session:
            sync_db_session.close()


@router.post("/assign")
async def purchase_and_assign_number_route(
    data: schemas.TwilioNumberAssign,
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
):
    logger.info(
        f"Twilio Assign: Request for payload business_id={data.business_id}, phone_number={data.phone_number} "
        f"by authenticated business {current_business.id} ({current_business.business_name})"
    )

    if data.business_id != current_business.id:
        logger.warning(
            f"Twilio Assign AuthZ Error: Authenticated business ID {current_business.id} "
            f"does not match payload business_id {data.business_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to assign number to the specified business profile."
        )

    sync_db_session = None
    try:
        sync_db_session = next(get_db())
        twilio_service = TwilioService(db=sync_db_session)
        
        # Assuming purchase_and_assign_number_to_business is adapted for async execution
        result = await twilio_service.purchase_and_assign_number_to_business(
            business_id=current_business.id,
            phone_number=data.phone_number
        )
        
        logger.info(f"Twilio Assign: Successfully assigned {data.phone_number} to business {current_business.id}")
        return result
    except HTTPException as http_exc:
        if sync_db_session: sync_db_session.close()
        raise http_exc
    except Exception as e:
        logger.exception(f"Twilio Assign: Error assigning {data.phone_number} to business {current_business.id}: {e}")
        if sync_db_session: sync_db_session.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign number due to an internal error."
        )
    finally:
        if sync_db_session:
            sync_db_session.close()


@router.delete("/release")
async def release_assigned_number_route(
    business_id_query: int = Query(..., alias="business_id", description="The ID of the business whose number should be released."),
    current_business: models.BusinessProfile = Depends(auth.get_current_authenticated_business),
):
    logger.info(
        f"Twilio Release: Request for query business_id={business_id_query} "
        f"by authenticated business {current_business.id} ({current_business.business_name})"
    )

    if business_id_query != current_business.id:
        logger.warning(
            f"Twilio Release AuthZ Error: Authenticated business ID {current_business.id} "
            f"does not match query business_id {business_id_query}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to release number for the specified business."
        )
    
    sync_db_session = None
    try:
        sync_db_session = next(get_db())
        twilio_service = TwilioService(db=sync_db_session)

        # Assuming release_assigned_twilio_number is adapted for async execution
        result = await twilio_service.release_assigned_twilio_number(
            business_id=current_business.id
        )
        
        logger.info(f"Twilio Release: Successfully initiated release for Twilio number of business_id={current_business.id}")
        return result
    except HTTPException as http_exc:
        if sync_db_session: sync_db_session.close()
        raise http_exc
    except Exception as e:
        logger.exception(f"Twilio Release: Error releasing Twilio number for business_id={current_business.id}: {e}")
        if sync_db_session: sync_db_session.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to release number due to an internal error."
        )
    finally:
        if sync_db_session:
            sync_db_session.close()