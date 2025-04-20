from fastapi.responses import PlainTextResponse
from datetime import datetime
from app.models import ConsentLog, Customer, BusinessProfile
from sqlalchemy.orm import Session


def handle_opt_in_out(body: str, customer: Customer, business: BusinessProfile, db: Session):
    """
    Handle opt-in and opt-out SMS messages from the customer.
    Returns a PlainTextResponse if the message matches consent logic, else None.
    """
    normalized = (body or "").strip("!., ").lower()
    print(f"📨 Normalized body: '{normalized}'")
    print("🔄 Entering opt-in/out handling logic...")

    if normalized in ["yes", "yes!"]:
        print("📩 Processing opt-in attempt...")
        log = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).first()
        if log:
            log.status = "opted_in"
            log.replied_at = datetime.utcnow()
            print(f"🔁 Updating existing log ID={log.id}")
        else:
            db.add(ConsentLog(
                customer_id=customer.id,
                business_id=business.id,
                method="double_opt_in",
                phone_number=customer.phone,
                status="opted_in",
                replied_at=datetime.utcnow()
            ))
            print("➕ Creating new ConsentLog entry")
        
        # Update customer.opted_in to maintain single source of truth
        customer.opted_in = True
        customer.opted_in_at = datetime.utcnow()
        
        db.commit()
        print("✅ Opt-in saved. Skipping AI response.")
        return PlainTextResponse("Opt-in confirmed", status_code=200)

    elif normalized in ["stop", "unsubscribe", "no", "no!"]:
        print("📩 Processing opt-out attempt...")
        # No update to customer.opted_in directly — frontend should infer from latest ConsentLog.status
        log = db.query(ConsentLog).filter(ConsentLog.customer_id == customer.id).first()
        if log:
            log.status = "declined"
            log.replied_at = datetime.utcnow()
            print(f"🔁 Updating existing log ID={log.id}")
        else:
            db.add(ConsentLog(
                customer_id=customer.id,
                business_id=business.id,
                method="double_opt_in",
                phone_number=customer.phone,
                status="declined",
                replied_at=datetime.utcnow()
            ))
            print("➕ Creating new ConsentLog entry")
        db.commit()
        print("✅ Opt-out saved. Skipping AI response.")
        return PlainTextResponse("Opt-out confirmed", status_code=200)

    # Not a consent keyword — allow flow to continue
    return None