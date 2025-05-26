# backend/app/utils.py
from datetime import datetime, time, timedelta 
import logging
from typing import Optional, Dict, Any
import pytz

# Import specific functions from timezone_utils needed by this module's functions
from app.timezone_utils import (
    get_business_timezone,
    is_business_hours,
    get_next_business_hour,
    # Removed get_utc_now, convert_to_utc from here
)

logger = logging.getLogger(__name__)

def parse_time_string(time_str: str) -> Optional[time]:
    if not isinstance(time_str, str):
        logger.warning(f"parse_time_string received non-string input: {time_str}")
        return None
    try:
        return datetime.strptime(time_str, '%H:%M:%S').time()
    except ValueError:
        try:
            return datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            logger.error(f"Invalid time format for string: '{time_str}'. Expected HH:MM or HH:MM:SS.")
            return None

def parse_sms_timing(sms_timing: str, business_timezone_str: str) -> datetime:
    logger.info(f"Parsing SMS timing: '{sms_timing}' for timezone: {business_timezone_str}")
    business_tz = get_business_timezone(business_timezone_str)

    try:
        if sms_timing.lower().startswith("immediate"):
            now_in_business_tz = datetime.now(business_tz)
            return get_next_business_hour(now_in_business_tz, business_timezone_str)

        parts = sms_timing.split(", ")
        if len(parts) != 2:
            raise ValueError(f"Invalid timing format (expected 'Day X, HH:MM AM/PM'): '{sms_timing}'")
        day_part, time_part = parts

        days_offset = 0
        if day_part.lower().startswith("day "):
            try:
                days_offset = int(day_part.split(" ")[1])
            except (IndexError, ValueError):
                raise ValueError(f"Invalid day format in '{day_part}'")
        else:
            raise ValueError(f"Unsupported day format: '{day_part}'")

        parsed_time_obj = datetime.strptime(time_part, "%I:%M %p").time()
        base_date_local = datetime.now(business_tz).date()
        target_date_local = base_date_local + timedelta(days=days_offset)
        
        local_dt_naive = datetime.combine(target_date_local, parsed_time_obj)
        local_dt_aware = business_tz.localize(local_dt_naive, is_dst=None)
        
        if not is_business_hours(local_dt_aware, business_timezone_str):
            return get_next_business_hour(local_dt_aware, business_timezone_str)
        
        return local_dt_aware.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Error parsing SMS timing '{sms_timing}': {str(e)}", exc_info=True)
        raise ValueError(f"Could not parse SMS timing '{sms_timing}': {e}")

def get_formatted_timing(
    send_time_utc: datetime, 
    business_timezone_str: str, 
    customer_timezone_str: Optional[str] = None
) -> Dict[str, Any]:
    from app.timezone_utils import convert_from_utc, get_customer_timezone # Local import

    if send_time_utc.tzinfo is None or send_time_utc.tzinfo.utcoffset(send_time_utc) is None:
        send_time_utc = pytz.utc.localize(send_time_utc)
    else:
        send_time_utc = send_time_utc.astimezone(pytz.utc)

    business_dt = convert_from_utc(send_time_utc, business_timezone_str)
    now_in_business_tz = datetime.now(get_business_timezone(business_timezone_str))
    day_offset = (business_dt.date() - now_in_business_tz.date()).days
    
    result = {
        "business_time": {
            "calendar_date": business_dt.strftime("%m/%d/%Y"),
            "time": business_dt.strftime("%I:%M %p"),
            "day_offset": max(0, day_offset),
            "display_date": business_dt.strftime("%A, %B %d"),
            "display_time": business_dt.strftime("%I:%M %p %Z"),
            "timezone_str": business_timezone_str
        }
    }
    if customer_timezone_str:
        customer_dt = convert_from_utc(send_time_utc, customer_timezone_str)
        result["customer_time"] = {
            "calendar_date": customer_dt.strftime("%m/%d/%Y"),
            "time": customer_dt.strftime("%I:%M %p"),
            "display_date": customer_dt.strftime("%A, %B %d"),
            "display_time": customer_dt.strftime("%I:%M %p %Z"),
            "timezone_str": customer_timezone_str
        }
    return result