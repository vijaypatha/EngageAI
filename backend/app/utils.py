from datetime import datetime, timedelta, time
import pytz

def parse_sms_timing(sms_timing: str, customer_timezone_str: str) -> datetime:
    """
    Parses the SMS timing format "Day X, HH:MM AM/PM" and converts it into a UTC datetime.
    """
    try:
        # Split input format "Day X, HH:MM AM/PM"
        parts = sms_timing.split(", ")
        if len(parts) != 2:
            raise ValueError(f"Invalid sms_timing format: '{sms_timing}'. Expected 'Day X, HH:MM AM/PM'.")

        day_part, time_part = parts

        # Extract day offset
        try:
            days_offset = int(day_part.split(" ")[1])
        except (IndexError, ValueError):
            raise ValueError(f"Invalid day format in sms_timing: '{day_part}'. Expected 'Day X'.")

        # Extract scheduled time
        try:
            scheduled_time: time = datetime.strptime(time_part, "%I:%M %p").time()
        except ValueError:
            raise ValueError(f"Invalid time format in sms_timing: '{time_part}'. Expected 'HH:MM AM/PM'.")

        # Validate timezone
        try:
            customer_timezone = pytz.timezone(customer_timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid customer_timezone: '{customer_timezone_str}'.")

        # Get current date in customer's timezone
        today_customer_tz: datetime = datetime.now(customer_timezone)
        today_customer_tz_date = today_customer_tz.date()

        # Compute the scheduled datetime in the customer's timezone
        scheduled_datetime_customer_tz: datetime = customer_timezone.localize(
            datetime.combine(today_customer_tz_date, scheduled_time)
        )

        # Apply day offset
        scheduled_datetime_customer_tz += timedelta(days=days_offset)

        # Convert to UTC
        final_datetime_utc: datetime = scheduled_datetime_customer_tz.astimezone(pytz.utc)

        print(f"Parsed send time (Customer TZ): {scheduled_datetime_customer_tz}")
        print(f"Parsed send time (UTC): {final_datetime_utc}")

        return final_datetime_utc

    except Exception as e:
        raise ValueError(f"Error parsing SMS timing: {e}") from e
