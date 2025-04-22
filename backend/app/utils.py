from datetime import datetime, timedelta, time
import pytz
import logging
from app.timezone_utils import (
    get_business_timezone,
    get_customer_timezone,
    convert_to_utc,
    convert_from_utc,
    format_datetime,
    is_business_hours,
    get_next_business_hour
)
from typing import Optional

logger = logging.getLogger(__name__)

def parse_sms_timing(sms_timing: str, business_timezone: str) -> datetime:
    """
    Parse SMS timing formats:
    - 'Day X, HH:MM AM/PM'
    - 'Immediate (New Client Welcome)'
    - Other special cases
    """
    logger.info(f"Parsing SMS timing: {sms_timing}")
    
    try:
        # Handle immediate case
        if sms_timing.startswith("Immediate"):
            return get_next_business_hour(datetime.now(), business_timezone)

        parts = sms_timing.split(", ")
        if len(parts) != 2:
            raise ValueError(f"Invalid timing format: '{sms_timing}'")

        day_part, time_part = parts

        # Extract day offset
        try:
            days_offset = int(day_part.split(" ")[1])
        except (IndexError, ValueError):
            raise ValueError(f"Invalid day format: '{day_part}'")

        # Extract time
        try:
            scheduled_time = datetime.strptime(time_part, "%I:%M %p").time()
        except ValueError:
            raise ValueError(f"Invalid time format: '{time_part}'")

        # Calculate final datetime
        tz = get_business_timezone(business_timezone)
        base_date = datetime.now(tz).date()
        target_date = base_date + timedelta(days=days_offset)
        local_dt = tz.localize(datetime.combine(target_date, scheduled_time))
        
        # Ensure the time is within business hours
        if not is_business_hours(local_dt, business_timezone):
            local_dt = get_next_business_hour(local_dt, business_timezone)
        
        logger.info(f"Parsed timing to: {local_dt}")
        return local_dt.astimezone(pytz.UTC)

    except Exception as e:
        logger.error(f"Error parsing timing '{sms_timing}': {str(e)}")
        raise

def get_formatted_timing(send_time: datetime, business_timezone: str, customer_timezone: Optional[str] = None) -> dict:
    """
    Format datetime into human-readable dictionary with both business and customer timezone info.
    """
    # Convert to business timezone
    business_tz = get_business_timezone(business_timezone)
    if send_time.tzinfo is None:
        send_time = pytz.UTC.localize(send_time)
    business_dt = send_time.astimezone(business_tz)
    
    # Calculate day offset from current business time
    now = datetime.now(business_tz)
    day_offset = (business_dt.date() - now.date()).days
    
    result = {
        "business_time": {
            "calendar_date": business_dt.strftime("%m/%d/%Y"),
            "time": business_dt.strftime("%I:%M %p"),
            "day_offset": max(0, day_offset),
            "display_date": business_dt.strftime("%A, %B %d"),
            "display_time": business_dt.strftime("%I:%M %p"),
            "timezone": business_timezone
        }
    }
    
    # Add customer timezone info if available
    if customer_timezone:
        customer_tz = get_customer_timezone(customer_timezone, business_timezone)
        customer_dt = send_time.astimezone(customer_tz)
        result["customer_time"] = {
            "calendar_date": customer_dt.strftime("%m/%d/%Y"),
            "time": customer_dt.strftime("%I:%M %p"),
            "display_date": customer_dt.strftime("%A, %B %d"),
            "display_time": customer_dt.strftime("%I:%M %p"),
            "timezone": customer_timezone
        }
    
    return result
