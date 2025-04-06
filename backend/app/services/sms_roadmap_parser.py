# Parses the JSON response
# Stores each message with status = pending_review
# Converts smsTiming to UTC using your timezone parser

from app.models import RoadmapMessage
from datetime import datetime
from app.utils import parse_sms_timing
import json
import pytz

def save_roadmap_messages(roadmap_json_str, customer, db):
    roadmap = json.loads(roadmap_json_str)
    customer_timezone_str = "America/Denver"

    for item in roadmap:
        sms_timing = item["smsTiming"]

        # Correctly convert to UTC
        send_time = parse_sms_timing(sms_timing, customer_timezone_str)

        # Extract day offset from "Day 3, 10:00 AM"
        day_offset = int(sms_timing.split(",")[0].strip().split(" ")[1])

        # Format smsTiming string for UI
        local_dt = send_time.astimezone(pytz.timezone(customer_timezone_str))
        human_date = local_dt.strftime("%A, %b %d")
        time_part = local_dt.strftime("%I:%M %p")
        formatted_timing = f"{human_date} (Day {day_offset}), {time_part}"

        # Create and store the SMS message
        sms = RoadmapMessage(
            customer_id=customer.id,
            business_id=customer.business_id,
            smsContent=item["smsContent"],
            smsTiming=f"Day {day_offset}, {time_part}",  # Display string
            send_datetime_utc=send_time,  # Used for scheduling + filtering
            status="pending_review",
        )

        print(f"[Parsed SMS] Will send on: {formatted_timing} (UTC: {send_time})")
        db.add(sms)

    db.commit()
