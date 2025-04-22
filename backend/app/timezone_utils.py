from datetime import datetime
import pytz
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

def get_business_timezone(business_timezone: str) -> pytz.BaseTzInfo:
    """
    Get a timezone object for a business, with fallback to UTC if invalid.
    """
    try:
        return pytz.timezone(business_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"Invalid timezone '{business_timezone}' provided, falling back to UTC")
        return pytz.UTC

def get_customer_timezone(customer_timezone: Optional[str], business_timezone: str) -> pytz.BaseTzInfo:
    """
    Get a timezone object for a customer, falling back to business timezone if not set.
    """
    if customer_timezone:
        try:
            return pytz.timezone(customer_timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warning(f"Invalid customer timezone '{customer_timezone}', falling back to business timezone")
    
    return get_business_timezone(business_timezone)

def convert_to_utc(dt: datetime, timezone_str: str) -> datetime:
    """
    Convert a datetime from a given timezone to UTC.
    """
    tz = get_business_timezone(timezone_str)
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.UTC)

def convert_from_utc(dt: datetime, timezone_str: str) -> datetime:
    """
    Convert a UTC datetime to a given timezone.
    """
    tz = get_business_timezone(timezone_str)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(tz)

def format_datetime(dt: datetime, timezone_str: str, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """
    Format a datetime in a specific timezone.
    """
    tz = get_business_timezone(timezone_str)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(tz)
    return local_dt.strftime(format_str)

def get_current_time(timezone_str: str) -> datetime:
    """
    Get current time in a specific timezone.
    """
    tz = get_business_timezone(timezone_str)
    return datetime.now(tz)

def is_business_hours(dt: datetime, business_timezone: str, 
                     business_hours_start: int = 9,  # 9 AM
                     business_hours_end: int = 17) -> bool:  # 5 PM
    """
    Check if a given datetime falls within business hours.
    """
    tz = get_business_timezone(business_timezone)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(tz)
    
    # Check if it's a weekday
    if local_dt.weekday() >= 5:  # 5 is Saturday, 6 is Sunday
        return False
    
    # Check if it's within business hours
    hour = local_dt.hour
    return business_hours_start <= hour < business_hours_end

def get_next_business_hour(dt: datetime, business_timezone: str,
                          business_hours_start: int = 9,
                          business_hours_end: int = 17) -> datetime:
    """
    Get the next business hour for a given datetime.
    """
    tz = get_business_timezone(business_timezone)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    local_dt = dt.astimezone(tz)
    
    # If it's a weekend, move to next Monday
    if local_dt.weekday() >= 5:
        days_until_monday = 7 - local_dt.weekday()
        local_dt = local_dt + datetime.timedelta(days=days_until_monday)
        local_dt = local_dt.replace(hour=business_hours_start, minute=0, second=0, microsecond=0)
        return local_dt.astimezone(pytz.UTC)
    
    # If it's before business hours, move to start of business hours
    if local_dt.hour < business_hours_start:
        local_dt = local_dt.replace(hour=business_hours_start, minute=0, second=0, microsecond=0)
        return local_dt.astimezone(pytz.UTC)
    
    # If it's after business hours, move to next day's start of business hours
    if local_dt.hour >= business_hours_end:
        local_dt = local_dt + datetime.timedelta(days=1)
        local_dt = local_dt.replace(hour=business_hours_start, minute=0, second=0, microsecond=0)
        return local_dt.astimezone(pytz.UTC)
    
    return dt 