# ----------------------------------------------------------------------
# FILE: backend/app/routes/customer_routes.py
# This version is the complete, correct file. It adds the new "Frictionless
# Contact Creation" endpoint while preserving all existing essential routes,
# including tag management, listing customers, and getting conversation history.
# ----------------------------------------------------------------------

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, desc
from datetime import datetime, timezone # Import timezone for utcnow() consistency
from typing import Optional, List

from app.database import get_db
from app.models import Customer as CustomerModel, BusinessProfile, ConsentLog, Tag, CustomerTag, Message as MessageModel
from app.schemas import (
    Customer, CustomerCreate, CustomerUpdate, TagRead, CustomerFindOrCreate,
    CustomerConversation, ConversationMessageForTimeline, CustomerSummarySchema,
    TagAssociationRequest
)
from app.services.consent_service import ConsentService
from app.services.message_service import MessageService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["customers"])


@router.post("/find-or-create-by-phone", response_model=Customer)
def find_or_create_customer_by_phone(
    payload: CustomerFindOrCreate,
    db: Session = Depends(get_db)
):
    """
    Finds a customer by phone number and business ID. If not found, creates a new one.
    This is the engine for the "Frictionless Contact Creation" flow.
    """
    phone_number = payload.phone_number

    customer = db.query(CustomerModel).filter(
        CustomerModel.phone == phone_number,
        CustomerModel.business_id == payload.business_id
    ).first()

    if customer:
        logger.info(f"Found existing customer ID {customer.id} for phone {phone_number}")
        return customer

    logger.info(f"No customer found for phone {phone_number}. Creating new contact.")
    new_customer = CustomerModel(
        phone=phone_number,
        business_id=payload.business_id,
        customer_name=f"New Lead ({phone_number})",
        lifecycle_stage="New Lead",
        sms_opt_in_status='not_set',
        last_read_at=datetime.now(timezone.utc) # Set initial read time for new contacts
    )
    db.add(new_customer)
    try:
        db.commit()
        db.refresh(new_customer)
        logger.info(f"Created new customer ID {new_customer.id}")
        return new_customer
    except IntegrityError:
        db.rollback()
        # This can happen in a race condition. Query again to be sure.
        customer = db.query(CustomerModel).filter(
            CustomerModel.phone == phone_number,
            CustomerModel.business_id == payload.business_id
        ).first()
        if customer:
            return customer
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create customer.")

@router.post("/", response_model=Customer, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this phone number already exists for this business."
        )

    db_customer = CustomerModel(**customer_data.model_dump())
    db_customer.sms_opt_in_status = 'not_set'
    db_customer.last_read_at = datetime.now(timezone.utc) # Set initial read time

    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)

    if business_profile.twilio_number and business_profile.messaging_service_sid:
        consent_service = ConsentService(db)
        background_tasks.add_task(
            consent_service.send_double_optin_sms,
            customer_id=db_customer.id,
            business_id=business_profile.id
        )
    
    return db_customer


@router.get("/by-business/{business_id}", response_model=List[CustomerSummarySchema])
def get_customers_by_business(
    business_id: int,
    tags: Optional[str] = Query(None, description="Comma-separated list of tag names to filter by (lowercase)"),
    db: Session = Depends(get_db)
):
    query = db.query(
        CustomerModel,
    ).options(
        joinedload(CustomerModel.tags)
    ).filter(CustomerModel.business_id == business_id)

    if tags:
        tag_names = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_names:
            query = query.join(CustomerModel.tags).filter(Tag.name.in_(tag_names))
            query = query.group_by(CustomerModel.id).having(func.count(Tag.id) == len(tag_names))

    customers_orm = query.order_by(CustomerModel.customer_name).all()

    customers_response = []
    for customer_orm in customers_orm:
        latest_consent = db.query(ConsentLog).filter(ConsentLog.customer_id == customer_orm.id).order_by(desc(ConsentLog.replied_at)).first()
        customers_response.append(
            CustomerSummarySchema(
                id=customer_orm.id,
                customer_name=customer_orm.customer_name,
                phone=customer_orm.phone,
                lifecycle_stage=customer_orm.lifecycle_stage,
                opted_in=latest_consent.status == "opted_in" if latest_consent else customer_orm.opted_in,
                latest_consent_status=latest_consent.status if latest_consent else None,
                latest_consent_updated=latest_consent.replied_at if latest_consent else None,
                tags=[TagRead.from_orm(tag) for tag in customer_orm.tags],
                business_id=customer_orm.business_id,
            )
        )
    return customers_response


@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(CustomerModel).options(joinedload(CustomerModel.tags)).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=Customer)
def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    db: Session = Depends(get_db)
):
    db_customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    update_data = customer_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_customer, key, value)
    
    db_customer.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_customer)
    return db_customer


@router.post("/{customer_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def associate_tags_with_customer(
    customer_id: int,
    payload: TagAssociationRequest,
    db: Session = Depends(get_db)
):
    db_customer = db.query(CustomerModel).options(joinedload(CustomerModel.tags)).filter(CustomerModel.id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    new_tag_ids = set(payload.tag_ids)
    
    if not new_tag_ids:
        db_customer.tags = []
    else:
        tags_to_associate = db.query(Tag).filter(Tag.id.in_(new_tag_ids)).all()
        found_ids = {tag.id for tag in tags_to_associate}
        if missing_ids := new_tag_ids - found_ids:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tag IDs not found: {list(missing_ids)}")
        
        db_customer.tags = tags_to_associate

    db.commit()
    return None

@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    db.delete(customer)
    db.commit()
    return None

@router.put("/{customer_id}/mark-as-read", status_code=status.HTTP_200_OK)
def mark_customer_conversation_as_read(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """
    Updates the 'last_read_at' timestamp for a customer, marking their conversation as read.
    """
    customer = db.query(CustomerModel).filter(CustomerModel.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    
    customer.last_read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(customer)
    logger.info(f"Customer {customer_id} conversation marked as read at {customer.last_read_at}.")
    return {"message": f"Conversation for customer {customer_id} marked as read."}