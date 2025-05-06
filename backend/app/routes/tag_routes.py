import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError # Import for handling unique constraint errors

from app.database import get_db
from app.models import Tag, CustomerTag, BusinessProfile # Import necessary models
from app.schemas import TagCreate, TagRead # Import necessary schemas
# from app.auth import get_current_user # Keep commented unless auth is strictly needed *now*

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Tags"]      # Group in Swagger UI
    # dependencies=[Depends(get_current_user)] # Protect all tag routes if needed
)

@router.post("/business/{business_id}/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag_for_business(
    business_id: int,
    tag: TagCreate, # Input uses TagCreate schema (which enforces lowercase via constr)
    db: Session = Depends(get_db)
):
    """
    Create a new tag for a specific business.
    Tag names are automatically converted to lowercase.
    """
    # Check if business exists
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with id {business_id} not found")

    # Check for duplicate tag name (already lowercase from schema validation)
    existing_tag = db.query(Tag).filter(
        Tag.business_id == business_id,
        Tag.name == tag.name # Check lowercase name
    ).first()

    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{tag.name}' already exists for this business."
        )

    db_tag = Tag(
        business_id=business_id,
        name=tag.name # Use the validated (lowercase) name
    )
    db.add(db_tag)
    try:
        db.commit()
        db.refresh(db_tag)
        logger.info(f"Tag '{db_tag.name}' (ID: {db_tag.id}) created for business {business_id}.")
        # Manually create the TagRead object if needed, or rely on FastAPI conversion
        return db_tag # FastAPI automatically converts using TagRead schema
    except IntegrityError: # Catch potential race conditions on unique constraint
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{tag.name}' already exists for this business (conflict)."
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating tag for business {business_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create tag due to server error."
        )

@router.get("/business/{business_id}/tags", response_model=List[TagRead])
def list_tags_for_business(
    business_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve all tags associated with a specific business, ordered by name.
    """
    # Check if business exists (optional, but good practice)
    business = db.query(BusinessProfile).filter(BusinessProfile.id == business_id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Business with id {business_id} not found")

    tags = db.query(Tag).filter(Tag.business_id == business_id).order_by(Tag.name).all()
    return tags

@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db)
    # current_user: BusinessProfile = Depends(get_current_user) # Add auth check here
):
    """
    Permanently delete a tag. Database cascade should handle removing associations
    from the customer_tags table. Frontend must provide confirmation.
    """
    db_tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not db_tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    # Authorization check: Ensure user deleting the tag owns the business
    # if current_user.id != db_tag.business_id:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this tag")

    try:
        # The 'ondelete="CASCADE"' in the CustomerTag model's ForeignKey
        # definition should instruct the database to automatically delete
        # corresponding rows in customer_tags when a tag is deleted.
        # The ORM cascade="all, delete-orphan" on BusinessProfile.tags
        # handles ORM-level cleanup if a business is deleted.
        tag_name = db_tag.name # Get name for logging before deletion
        db.delete(db_tag)
        db.commit()
        logger.info(f"Tag '{tag_name}' (ID: {tag_id}) deleted permanently.")
        return None # Return None explicitly for 204 No Content
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting tag ID {tag_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete tag due to server error."
        )