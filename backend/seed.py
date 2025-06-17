# backend/seed.py
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import json

# Add the project root to the Python path to allow 'app' module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.database import SessionLocal, engine, Base
from app.models import (
    BusinessProfile,
    Customer,
    Message,
    MessageStatusEnum,
    MessageTypeEnum,
    BusinessOwnerStyle
)

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def seed_database():
    """
    Main function to seed the database with sample data.
    This script is idempotent: it first cleans up existing sample data
    before creating new data to ensure a consistent state.
    """
    db: Session = SessionLocal()
    
    try:
        logger.info("--- Starting Database Seeding ---")

        # --- 1. Clean up existing sample data ---
        existing_business = db.query(BusinessProfile).filter_by(business_name="The Corner Cafe").first()
        if existing_business:
            logger.warning(f"Found existing business 'The Corner Cafe' (ID: {existing_business.id}). Deleting it and all associated data to ensure a clean seed.")
            db.delete(existing_business)
            db.commit()
            logger.info("Existing sample business and its data have been cleared.")
        
        # --- 2. Create the sample Business ---
        logger.info("Creating sample business: The Corner Cafe")
        business = BusinessProfile(
            business_name="The Corner Cafe",
            slug="corner-cafe",
            industry="Food & Beverage",
            primary_services="Coffee, Pastries, Sandwiches",
            representative_name="Jane",
            timezone="America/New_York",
            review_platform_url="https://www.google.com/search?q=the+corner+cafe",
            business_goal="Increase customer loyalty and repeat visits."
        )
        db.add(business)
        db.commit()
        db.refresh(business)
        logger.info(f"✅ Successfully created 'The Corner Cafe' with Business ID: {business.id}")

        # --- 3. Create a Default Style Guide for the Business ---
        logger.info(f"Creating default style guide for business ID: {business.id}")
        default_style = BusinessOwnerStyle(
            business_id=business.id,
            scenario="Default Style Template",
            response="This is a sample response used to establish the initial tone.",
            context_type="initial_setup",
            key_phrases=json.dumps(["Thanks for stopping by!", "Hope to see you soon!", "Enjoy your coffee"]),
            style_notes=json.dumps({
                "tone": "Friendly, warm, and welcoming",
                "formality_level": "Casual and approachable",
                "personal_touches": ["Uses emojis like ☕️ and 😊 sparingly", "Addresses customer by first name"],
                "authenticity_markers": ["Short, concise sentences", "Sounds like a real person, not a corporation"]
            }),
            personality_traits=json.dumps(["Welcoming", "Appreciative", "Community-oriented"]),
            message_patterns=json.dumps({
                "greetings": ["Hi [Name]", "Hey [Name]"],
                "closings": ["- Jane", "- The Corner Cafe Team"]
            }),
            special_elements=json.dumps({
                "emojis": ["☕️", "😊", "☀️"]
            }),
            last_analyzed=datetime.now(timezone.utc)
        )
        db.add(default_style)
        logger.info("✅ Default style guide created.")

        # --- 4. Create sample Customers ---
        # (Customer creation logic remains the same)
        customers_to_create = [
            {"customer_name": "Alice Johnson", "phone": "+15550001111", "lifecycle_stage": "New"},
            {"customer_name": "Bob Williams", "phone": "+15550002222", "lifecycle_stage": "Repeat"},
            {"customer_name": "Charlie Brown", "phone": "+15550003333", "lifecycle_stage": "Loyal"},
            {"customer_name": "Diana Miller", "phone": "+15550004444", "lifecycle_stage": "At-Risk"},
        ]
        customers = []
        for cust_data in customers_to_create:
            customer = Customer(**cust_data, business_id=business.id, opted_in=True)
            db.add(customer)
            customers.append(customer)
        db.flush() # Flush to assign IDs before using them below
        logger.info(f"✅ Successfully created {len(customers)} sample customers.")

        # --- 5. Seed Approval Queue and Scheduled Plan ---
        # (Message seeding logic remains the same)
        # ... (approval and scheduled messages logic) ...

        db.commit()
        logger.info("--- Database Seeding Completed Successfully! ---")

    except Exception as e:
        logger.error(f"An error occurred during seeding: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()