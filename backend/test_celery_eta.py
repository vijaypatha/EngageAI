# File: backend/test_celery_eta.py
import os
from app.celery_app import celery_app, ping # Import your configured app and simple ping task
from datetime import datetime, timedelta, timezone
import time

print(f"[{datetime.now()}] Attempting to schedule a ping task...")

# Schedule for 45 seconds in the future to give time to observe
schedule_time_utc = datetime.now(timezone.utc) + timedelta(seconds=45)
print(f"[{datetime.now()}] Task target ETA (UTC): {schedule_time_utc.isoformat()}")
print(f"[{datetime.now()}] Task target ETA (Local): {schedule_time_utc.astimezone().isoformat()}")


try:
    # Use apply_async with eta
    result = ping.apply_async(eta=schedule_time_utc)
    print(f"[{datetime.now()}] Successfully sent task {result.id} to broker for ETA.")
    print("-" * 30)
    print("NOW: Check your running LOCAL Celery worker terminal.")
    print(f"EXPECTED: Worker should execute ping around {schedule_time_utc.astimezone().isoformat()}")
    print("-" * 30)

except Exception as e:
    print(f"[{datetime.now()}] Error sending task to broker: {e}")

# Keep script alive briefly to ensure message is sent if broker connection is slow
# time.sleep(5) # Optional: uncomment if you suspect send issues
print(f"[{datetime.now()}] Test script finished.")