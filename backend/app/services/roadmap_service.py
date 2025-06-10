# Helps business owners plan and automate their customer communication strategy
# Business owners can create personalized message sequences that automatically send at the right time to nurture customer relationships
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import RoadmapMessage, Customer, BusinessProfile
from app.schemas import RoadmapGenerate, RoadmapMessageResponse

import logging

logger = logging.getLogger(__name__)


class RoadmapService:
    """Service for managing automated message sequences and customer communication roadmaps."""

    def __init__(self, db: Session) -> None:
        """Initialize the roadmap service.

        Args:
            db: Database session for database operations
        """
        self.db = db

    async def generate_roadmap(
        self,
        data: RoadmapGenerate
    ) -> List[RoadmapMessage]:
        """Generate a sequence of scheduled messages for a customer.

        Args:
            data: Contains customer_id, business_id and context for roadmap generation

        Returns:
            List of created roadmap messages

        Raises:
            HTTPException: If customer or business not found, or if roadmap generation fails
        """
        try:
            # Verify customer and business exist
            customer = self.db.query(Customer).filter(
                Customer.id == data.customer_id
            ).first()
            
            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Customer not found"
                )
            
            business = self.db.query(BusinessProfile).filter(
                BusinessProfile.id == data.business_id
            ).first()
            
            if not business:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business not found"
                )
            
            # Generate roadmap messages
            roadmap_messages = [
                RoadmapMessage(
                    customer_id=data.customer_id,
                    business_id=data.business_id,
                    smsContent="Welcome message",
                    send_datetime_utc=datetime.utcnow(),
                    status="pending"
                ),
                RoadmapMessage(
                    customer_id=data.customer_id,
                    business_id=data.business_id,
                    smsContent="Follow-up message",
                    send_datetime_utc=datetime.utcnow(),
                    status="pending"
                )
            ]
            
            # Save roadmap messages
            for msg in roadmap_messages:
                self.db.add(msg)
            
            self.db.commit()
            
            return roadmap_messages
            
        except Exception as e:
            logger.error(f"Error generating roadmap: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate roadmap"
            )
    
    async def get_roadmap(
        self,
        customer_id: int,
        business_id: int
    ) -> List[RoadmapMessage]:
        """Retrieve all scheduled messages for a specific customer.

        Args:
            customer_id: ID of the customer
            business_id: ID of the business

        Returns:
            List of roadmap messages ordered by scheduled time

        Raises:
            HTTPException: If retrieval fails
        """
        try:
            roadmap = self.db.query(RoadmapMessage).filter(
                RoadmapMessage.customer_id == customer_id,
                RoadmapMessage.business_id == business_id
            ).order_by(RoadmapMessage.send_datetime_utc.asc()).all()
            
            return roadmap
            
        except Exception as e:
            logger.error(f"Error getting roadmap: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get roadmap"
            )
    
    async def update_roadmap_status(
        self,
        roadmap_id: int,
        status: str
    ) -> RoadmapMessage:
        """Update the status of a specific roadmap message.

        Args:
            roadmap_id: ID of the roadmap message to update
            status: New status to set

        Returns:
            Updated roadmap message

        Raises:
            HTTPException: If message not found or update fails
        """
        try:
            roadmap = self.db.query(RoadmapMessage).filter(
                RoadmapMessage.id == roadmap_id
            ).first()
            
            if not roadmap:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Roadmap message not found"
                )
            
            roadmap.status = status
            self.db.commit()
            self.db.refresh(roadmap)
            
            return roadmap
            
        except Exception as e:
            logger.error(f"Error updating roadmap status: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update roadmap status"
            ) 