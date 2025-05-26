# backend/app/timezone_utils.py
from datetime import datetime, timedelta, timezone, date, time
from typing import Optional, Union, Tuple # Ensured Tuple is imported
import pytz
import logging

logger = logging.getLogger(__name__)

def get_utc_now() -> datetime:
    """Returns the current datetime object, timezone-aware, in UTC."""
    return datetime.now(timezone.utc)

def get_business_timezone(business_timezone_str: Optional[str]) -> pytz.BaseTzInfo:
    if not business_timezone_str:
        logger.debug("Business timezone string is None or empty, falling back to UTC.")
        return pytz.utc
    try:
        return pytz.timezone(business_timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"Invalid timezone '{business_timezone_str}' provided, falling back to UTC")
        return pytz.utc

def get_customer_timezone(customer_timezone_str: Optional[str], business_timezone_str: str) -> pytz.BaseTzInfo:
    if customer_timezone_str:
        try:
            return pytz.timezone(customer_timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warning(f"Invalid customer timezone '{customer_timezone_str}', falling back to business timezone")
    return get_business_timezone(business_timezone_str)

def convert_to_utc(dt: datetime, source_timezone_str: str) -> datetime:
    source_tz = get_business_timezone(source_timezone_str)
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        aware_dt = source_tz.localize(dt, is_dst=None)
    else:
        aware_dt = dt.astimezone(source_tz)
    return aware_dt.astimezone(pytz.utc)

def convert_from_utc(utc_dt: datetime, target_timezone_str: str) -> datetime:
    target_tz = get_business_timezone(target_timezone_str)
    if utc_dt.tzinfo is None or utc_dt.tzinfo.utcoffset(utc_dt) is None:
        utc_dt = pytz.utc.localize(utc_dt)
    return utc_dt.astimezone(target_tz)

def format_datetime_in_timezone(
    dt: datetime,
    target_timezone_str: str,
    format_str: str = "%Y-%m-%d %I:%M %p %Z"
) -> str:
    dt_utc = dt
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt_utc = pytz.utc.localize(dt)
    elif dt_utc.tzinfo != pytz.utc: # Ensure it's actually UTC before converting
        dt_utc = dt.astimezone(pytz.utc)
    
    local_tz = get_business_timezone(target_timezone_str)
    local_dt = dt_utc.astimezone(local_tz)
    return local_dt.strftime(format_str)

def get_current_time_in_timezone(timezone_str: str) -> datetime:
    tz = get_business_timezone(timezone_str)
    return datetime.now(tz)

def is_business_hours(
    dt_to_check: datetime, 
    business_timezone_str: str,
    business_hours_start: time = time(9, 0),
    business_hours_end: time = time(17, 0)
) -> bool:
    local_dt = convert_from_utc(dt_to_check, business_timezone_str) if dt_to_check.tzinfo else get_business_timezone(business_timezone_str).localize(dt_to_check, is_dst=None)

    if local_dt.weekday() >= 5:
        return False
    return business_hours_start <= local_dt.time() < business_hours_end

def get_next_business_hour(
    dt_from: datetime, 
    business_timezone_str: str,
    business_hours_start: time = time(9, 0),
    business_hours_end: time = time(17, 0)
) -> datetime:
    local_dt = convert_from_utc(dt_from, business_timezone_str) if dt_from.tzinfo else get_business_timezone(business_timezone_str).localize(dt_from, is_dst=None)
    business_tz = local_dt.tzinfo

    # Ensure business_tz is not None, fallback if necessary (though get_business_timezone should handle it)
    if business_tz is None:
        business_tz = get_business_timezone(business_timezone_str)
        local_dt = local_dt.replace(tzinfo=business_tz)


    start_datetime_today = business_tz.localize(datetime.combine(local_dt.date(), business_hours_start), is_dst=None) # type: ignore
    
    if local_dt.weekday() >= 5 or local_dt.time() >= business_hours_end: 
        local_dt += timedelta(days=1)
        local_dt = local_dt.replace(hour=business_hours_start.hour, minute=business_hours_start.minute, second=0, microsecond=0)
        while local_dt.weekday() >= 5: 
            local_dt += timedelta(days=1)
            local_dt = local_dt.replace(hour=business_hours_start.hour, minute=business_hours_start.minute, second=0, microsecond=0) # reset time for new day
    elif local_dt.time() < business_hours_start: 
        local_dt = local_dt.replace(hour=business_hours_start.hour, minute=business_hours_start.minute, second=0, microsecond=0)
    
    return local_dt.astimezone(pytz.utc)

def get_business_today_utc_boundaries(
    business_timezone_str: str, 
    reference_date_in_business_tz: Optional[datetime] = None # This should be a naive date or an aware date in business_tz
) -> Tuple[datetime, datetime]:
    business_tz = get_business_timezone(business_timezone_str)
    
    if reference_date_in_business_tz:
        ref_dt_local = reference_date_in_business_tz.astimezone(business_tz) if reference_date_in_business_tz.tzinfo else business_tz.localize(reference_date_in_business_tz, is_dst=None)
    else:
        ref_dt_local = datetime.now(business_tz)

    start_of_day_local = ref_dt_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Ensure start_of_day_local is aware if it became naive after replace
    if start_of_day_local.tzinfo is None:
        start_of_day_local = business_tz.localize(start_of_day_local, is_dst=None)

    end_of_day_local = start_of_day_local + timedelta(days=1) # This is start of next day

    return start_of_day_local.astimezone(pytz.utc), end_of_day_local.astimezone(pytz.utc)

def get_day_of_week_from_datetime(dt_object: datetime, business_timezone_str: str) -> str:
    dt_in_business_tz = convert_from_utc(dt_object, business_timezone_str) if dt_object.tzinfo else get_business_timezone(business_timezone_str).localize(dt_object, is_dst=None).astimezone(get_business_timezone(business_timezone_str))
    return dt_in_business_tz.strftime('%A').lower()

def convert_naive_datetime_to_utc(naive_dt: datetime, source_timezone_str: str) -> datetime:
    if naive_dt.tzinfo is not None: # If somehow already aware
        return naive_dt.astimezone(pytz.utc)
    source_tz = get_business_timezone(source_timezone_str)
    aware_dt = source_tz.localize(naive_dt, is_dst=None) # is_dst=None for safety during DST transitions
    return aware_dt.astimezone(pytz.utc)

def get_business_timezone_and_current_time(business_timezone_str: str) -> Tuple[pytz.BaseTzInfo, datetime]:
    business_tz = get_business_timezone(business_timezone_str)
    current_time_in_business_tz = datetime.now(business_tz)
    return business_tz, current_time_in_business_tz

def convert_naive_time_to_aware_dt_business_tz(
    naive_time: time, 
    business_timezone_str: str, 
    target_date_local: Optional[date] = None # Date in business's local timezone
) -> datetime:
    business_tz = get_business_timezone(business_timezone_str)
    if target_date_local is None:
        target_date_local = datetime.now(business_tz).date()
    
    naive_datetime = datetime.combine(target_date_local, naive_time)
    return business_tz.localize(naive_datetime, is_dst=None)