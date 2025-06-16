# backend/seed.py
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

# --- FIX: Add the project root to the Python path ---
# This ensures that the 'app' module can be found when running the script directly.
# It calculates the path to the 'backend' directory and then goes one level up to the project root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal, engine, Base
from app.models import (
    BusinessProfile,
    Customer,
    Message,
    MessageStatusEnum,
    MessageTypeEnum,
)

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_database():
    """
    Main function to seed the database with sample data for the Autopilot feature.
    """
    db: Session = SessionLocal()
    
    try:
        logger.info("--- Starting Database Seeding ---")

        # --- 1. Create a sample Business ---
        business = db.query(BusinessProfile).filter_by(business_name="The Corner Cafe").first()
        if not business:
            logger.info("Creating sample business: The Corner Cafe")
            business = BusinessProfile(
                business_name="The Corner Cafe",
                slug="corner-cafe",
                industry="Food & Beverage",
                primary_services="Coffee, Pastries, Sandwiches",
                representative_name="Jane Doe",
                timezone="America/New_York",
                review_platform_url="https://www.google.com/search?q=the+corner+cafe",
                business_goal="Increase customer loyalty and repeat visits."
            )
            db.add(business)
            db.flush()
        else:
            logger.info("Sample business 'The Corner Cafe' already exists.")

        # --- 2. Create sample Customers ---
        customers_to_create = [
            {"customer_name": "Alice Johnson", "phone": "+15550001111", "lifecycle_stage": "New"},
            {"customer_name": "Bob Williams", "phone": "+15550002222", "lifecycle_stage": "Repeat"},
            {"customer_name": "Charlie Brown", "phone": "+15550003333", "lifecycle_stage": "Loyal"},
            {"customer_name": "Diana Miller", "phone": "+15550004444", "lifecycle_stage": "At-Risk"},
        ]
        
        customers = []
        for cust_data in customers_to_create:
            customer = db.query(Customer).filter_by(phone=cust_data["phone"], business_id=business.id).first()
            if not customer:
                logger.info(f"Creating sample customer: {cust_data['customer_name']}")
                customer = Customer(**cust_data, business_id=business.id, opted_in=True)
                db.add(customer)
                db.flush()
            else:
                logger.info(f"Sample customer '{cust_data['customer_name']}' already exists.")
            customers.append(customer)

        # --- 3. Seed the Approval Queue ---
        approval_messages_to_create = [
            {
                "customer_id": customers[0].id,
                "content": "Hi Alice, thanks for your recent visit! As a valued customer, we'd love to offer you a free coffee on your next order.",
                "message_metadata": {"source": "copilot_growth_campaign", "campaign_type": "Loyalty Offer"}
            },
            {
                "customer_id": customers[1].id,
                "content": "Hey Bob, it was great to see you again! We're always looking to improve. Would you mind sharing your feedback?",
                "message_metadata": {"source": "copilot_growth_campaign", "campaign_type": "Feedback Request"}
            },
            {
                "customer_id": customers[3].id,
                "content": "Hi Diana, we miss you at The Corner Cafe! Here's a 15% off coupon for your next visit: WELCOMEBACK15",
                "message_metadata": {"source": "copilot_growth_campaign", "campaign_type": "Re-Engagement Campaign"}
            },
        ]

        logger.info("Seeding messages for the Approval Queue...")
        for msg_data in approval_messages_to_create:
            existing_msg = db.query(Message).filter_by(
                customer_id=msg_data["customer_id"],
                status=MessageStatusEnum.PENDING_APPROVAL,
                content=msg_data["content"]
            ).first()

            if not existing_msg:
                message = Message(
                    business_id=business.id,
                    status=MessageStatusEnum.PENDING_APPROVAL,
                    message_type=MessageTypeEnum.OUTBOUND,
                    **msg_data
                )
                db.add(message)
                logger.info(f"  -> Added message for {db.query(Customer.customer_name).filter_by(id=msg_data['customer_id']).scalar()} to the queue.")
            else:
                logger.info(f"  -> Skipping duplicate pending message for customer ID {msg_data['customer_id']}.")

        # --- 4. Seed the Scheduled Flight Plan ---
        scheduled_messages_to_create = [
            {
                "customer_id": customers[2].id,
                "content": "Hi Charlie, just a friendly reminder about your pickup tomorrow at 10 AM.",
                "scheduled_time": datetime.now(timezone.utc) + timedelta(hours=18)
            },
            {
                "customer_id": customers[0].id,
                "content": "Hey Alice! Don't forget our weekly coffee tasting event this Friday. Hope to see you there!",
                "scheduled_time": datetime.now(timezone.utc) + timedelta(days=3, hours=4)
            }
        ]
        
        logger.info("Seeding messages for the Scheduled Flight Plan...")
        for msg_data in scheduled_messages_to_create:
             existing_msg = db.query(Message).filter_by(
                customer_id=msg_data["customer_id"],
                status=MessageStatusEnum.SCHEDULED,
                content=msg_data["content"]
            ).first()
             if not existing_msg:
                message = Message(
                    business_id=business.id,
                    status=MessageStatusEnum.SCHEDULED,
                    message_type=MessageTypeEnum.SCHEDULED,
                    **msg_data
                )
                db.add(message)
                logger.info(f"  -> Added scheduled message for {db.query(Customer.customer_name).filter_by(id=msg_data['customer_id']).scalar()}.")
             else:
                logger.info(f"  -> Skipping duplicate scheduled message for customer ID {msg_data['customer_id']}.")

        db.commit()
        logger.info("--- Database Seeding Completed Successfully! ---")

    except Exception as e:
        logger.error(f"An error occurred during seeding: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()