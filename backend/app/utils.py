from datetime import datetime, timedelta, time
import pytz
import logging

logger = logging.getLogger(__name__)

def parse_sms_timing(sms_timing: str, timezone_str: str = "America/Denver") -> datetime:
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
            tz = pytz.timezone(timezone_str)
            return datetime.now(tz)

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
        tz = pytz.timezone(timezone_str)
        base_date = datetime.now(tz).date()
        target_date = base_date + timedelta(days=days_offset)
        local_dt = tz.localize(datetime.combine(target_date, scheduled_time))
        
        logger.info(f"Parsed timing to: {local_dt}")
        return local_dt

    except Exception as e:
        logger.error(f"Error parsing timing '{sms_timing}': {str(e)}")
        raise

def get_formatted_timing(send_time: datetime, timezone_str: str = "America/Denver") -> dict:
    """Format datetime into human-readable dictionary."""
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    local_dt = send_time.astimezone(tz)
    
    day_offset = (local_dt.date() - now.date()).days
    
    return {
        "calendar_date": local_dt.strftime("%m/%d/%Y"),
        "time": local_dt.strftime("%I:%M %p"),
        "day_offset": max(0, day_offset),
        "display_date": local_dt.strftime("%A, %B %d"),
        "display_time": local_dt.strftime("%I:%M %p")
    }
