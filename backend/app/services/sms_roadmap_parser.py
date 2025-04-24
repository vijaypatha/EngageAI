# Parses the JSON response
# Stores each message with status = pending_review
# Converts smsTiming to UTC using your timezone parser

from app.models import RoadmapMessage, Message, Conversation
from datetime import datetime
from app.utils import parse_sms_timing, get_formatted_timing
import json
import pytz
import logging
import uuid

logger = logging.getLogger(__name__)

def save_roadmap_messages(roadmap_json_str, customer, db):
    """Parse and save roadmap messages to the database."""
    try:
        roadmap = json.loads(roadmap_json_str)
        customer_timezone_str = "America/Denver"  # TODO: Use customer.timezone
        logger.info(f"Processing roadmap for customer {customer.id}")

        # Sort messages by dayOffset
        roadmap.sort(key=lambda x: x["dayOffset"])

        # Get or create conversation
        conversation = db.query(Conversation).filter(
            Conversation.customer_id == customer.id,
            Conversation.business_id == customer.business_id,
            Conversation.status == 'active'
        ).first()
        
        if not conversation:
            conversation = Conversation(
                id=uuid.uuid4(),
                customer_id=customer.id,
                business_id=customer.business_id,
                started_at=datetime.now(pytz.UTC),
                last_message_at=datetime.now(pytz.UTC),
                status='active'
            )
            db.add(conversation)
            db.flush()

        for item in roadmap:
            try:
                sms_timing = item["smsTiming"]
                logger.info(f"Processing timing: {sms_timing}")
                
                # Parse send time
                send_time = parse_sms_timing(sms_timing, customer_timezone_str)
                
                # Format for display
                formatted_timing = get_formatted_timing(send_time, customer_timezone_str)
                
                # Create roadmap message
                roadmap_msg = RoadmapMessage(
                    customer_id=customer.id,
                    business_id=customer.business_id,
                    smsContent=item["smsContent"],
                    smsTiming=json.dumps(formatted_timing),
                    send_datetime_utc=send_time.astimezone(pytz.UTC),
                    status="pending_review",
                    relevance=item.get("relevance", ""),
                    success_indicator=item.get("successIndicator", ""),
                    no_response_plan=item.get("whatif_customer_does_not_respond", "")
                )
                db.add(roadmap_msg)
                db.flush()  # Get the ID

                # Create corresponding message
                message = Message(
                    conversation_id=conversation.id,
                    customer_id=customer.id,
                    business_id=customer.business_id,
                    content=item["smsContent"],
                    message_type='scheduled',
                    status="pending_review",
                    scheduled_time=send_time.astimezone(pytz.UTC),
                    metadata={
                        'source': 'roadmap',
                        'roadmap_id': roadmap_msg.id,
                        'timing': formatted_timing,
                        'relevance': item.get("relevance", ""),
                        'success_indicator': item.get("successIndicator", ""),
                        'no_response_plan': item.get("whatif_customer_does_not_respond", "")
                    }
                )
                db.add(message)
                
                # Link the message to the roadmap
                roadmap_msg.message_id = message.id

                logger.info(f"Created message for {formatted_timing['business_time']['display_date']} at {formatted_timing['business_time']['display_time']}")

            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                raise

        db.commit()
        logger.info("Successfully saved all roadmap messages")
        
    except Exception as e:
        logger.error(f"Error saving roadmap messages: {str(e)}")
        db.rollback()
        raise
