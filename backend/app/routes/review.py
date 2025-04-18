print("✅ review.py loaded")

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RoadmapMessage, ScheduledSMS, Customer, Engagement
from datetime import datetime, timezone
from sqlalchemy import and_
from app.celery_tasks import schedule_sms_task


router = APIRouter()

@router.get("/engagement-plan/{customer_id}")
def get_engagement_plan(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now_utc = datetime.now(timezone.utc)

    roadmap_messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status != "deleted"
        )
    ).all()

    scheduled_sms = db.query(ScheduledSMS).filter(
        and_(
            ScheduledSMS.customer_id == customer_id,
            ScheduledSMS.send_time != None,
            ScheduledSMS.send_time >= now_utc
        )
    ).all()

    roadmap_data = [
        {
            "id": msg.id,
            "smsContent": msg.smsContent,
            "smsTiming": msg.smsTiming,
            "status": msg.status,
            "relevance": getattr(msg, "relevance", None),
            "successIndicator": getattr(msg, "successIndicator", None),
            "send_datetime_utc": msg.send_datetime_utc.isoformat() if msg.send_datetime_utc else None,
        }
        for msg in roadmap_messages
    ]

    scheduled_data = [
        {
            "id": sms.id,
            "smsContent": sms.message,
            "smsTiming": sms.send_time.strftime("Scheduled: %b %d, %I:%M %p"),
            "status": sms.status,
            "send_datetime_utc": sms.send_time.isoformat() if sms.send_time else None,
        }
        for sms in scheduled_sms
    ]

    return {"engagements": roadmap_data + scheduled_data}

@router.put("/{roadmap_id}/approve")
def schedule_message(roadmap_id: int, db: Session = Depends(get_db)):
    msg = db.query(RoadmapMessage).filter(RoadmapMessage.id == roadmap_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Roadmap message not found")

    if not msg.send_datetime_utc:
        raise HTTPException(status_code=400, detail="Missing send time for roadmap message")

    if msg.status == "scheduled":
        return {"status": "already scheduled"}

    existing_sms = db.query(ScheduledSMS).filter(
        ScheduledSMS.customer_id == msg.customer_id,
        ScheduledSMS.business_id == msg.business_id,
        ScheduledSMS.message == msg.smsContent,
        ScheduledSMS.send_time == msg.send_datetime_utc
    ).first()

    if not existing_sms:
        scheduled = ScheduledSMS(
            customer_id=msg.customer_id,
            business_id=msg.business_id,
            message=msg.smsContent,
            send_time=msg.send_datetime_utc,
            status="scheduled",
            roadmap_id=msg.id  # <-- link the originating roadmap message
        )
        db.add(scheduled)
        db.flush()
        print(f"📤 Scheduling SMS via Celery: ScheduledSMS id={scheduled.id}, ETA={msg.send_datetime_utc}")
        schedule_sms_task.apply_async(args=[scheduled.id], eta=msg.send_datetime_utc)
        msg.status = "scheduled"
        db.commit()

        return {
            "status": "scheduled",
            "scheduled_sms_id": scheduled.id,
            "scheduled_sms": {
                "id": scheduled.id,
                "customer_name": db.query(Customer).get(msg.customer_id).customer_name,
                "smsContent": scheduled.message,
                "send_datetime_utc": scheduled.send_time,
                "status": scheduled.status,
                "source": "scheduled"
            }
        }

    msg.status = "scheduled"
    db.commit()
    return {"status": "already scheduled"}

@router.put("/{roadmap_id}/schedule")
def schedule_message_alias(roadmap_id: int, db: Session = Depends(get_db)):
    """Alias for /approve to support consistent frontend naming."""
    return schedule_message(roadmap_id, db)

@router.put("/{roadmap_id}/reject")
def reject_message(roadmap_id: int, db: Session = Depends(get_db)):
    msg = db.query(RoadmapMessage).filter(RoadmapMessage.id == roadmap_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Roadmap message not found")
    msg.status = "rejected"
    db.commit()
    return {"status": "rejected"}

@router.post("/approve-all/{customer_id}")
def approve_all(customer_id: int, db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)
    messages = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id == customer_id,
            RoadmapMessage.send_datetime_utc != None,
            RoadmapMessage.send_datetime_utc >= now_utc,
            RoadmapMessage.status == "pending_review"
        )
    ).all()

    new_scheduled_count = 0

    for msg in messages:
        msg.status = "scheduled"
        exists = db.query(ScheduledSMS).filter(
            ScheduledSMS.customer_id == msg.customer_id,
            ScheduledSMS.business_id == msg.business_id,
            ScheduledSMS.message == msg.smsContent,
            ScheduledSMS.send_time == msg.send_datetime_utc
        ).first()

        if not exists:
            scheduled = ScheduledSMS(
                customer_id=msg.customer_id,
                business_id=msg.business_id,
                message=msg.smsContent,
                send_time=msg.send_datetime_utc,
                status="scheduled"
            )
            db.add(scheduled)
            db.flush()
            schedule_sms_task.apply_async(args=[scheduled.id], eta=msg.send_datetime_utc)
            new_scheduled_count += 1

    db.commit()
    return {"scheduled": new_scheduled_count}

@router.get("/stats/{business_id}")
def get_engagement_stats(business_id: int, db: Session = Depends(get_db)):
    total_customers = db.query(Customer).filter(Customer.business_id == business_id).count()
    roadmap = db.query(RoadmapMessage).join(Customer).filter(Customer.business_id == business_id)
    scheduled = db.query(ScheduledSMS).join(Customer).filter(Customer.business_id == business_id)

    return {
        "communitySize": total_customers,
        "pending": roadmap.filter(RoadmapMessage.status == "pending_review").count(),
        "rejected": roadmap.filter(RoadmapMessage.status == "rejected").count(),
        "scheduled": scheduled.filter(ScheduledSMS.status == "scheduled").count(),
        "sent": (
            db.query(ScheduledSMS).join(Customer)
            .filter(Customer.business_id == business_id, ScheduledSMS.status == "sent")
            .count()
            +
            db.query(Engagement).join(Customer)
            .filter(Customer.business_id == business_id, Engagement.status == "sent")
            .count()
        )
    }

@router.get("/customers/without-engagement-count/{business_id}")
def get_contact_stats(business_id: int, db: Session = Depends(get_db)):
    total_customers = db.query(Customer).filter(Customer.business_id == business_id).count()
    with_engagement = db.query(RoadmapMessage.customer_id).distinct().subquery()
    without = db.query(Customer).filter(
        Customer.business_id == business_id,
        ~Customer.id.in_(with_engagement)
    ).count()

    return {
        "total_customers": total_customers,
        "without_engagement": without
    }

@router.get("/all-engagements")
def get_all_engagements(business_id: int, db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.business_id == business_id).all()
    customer_map = {c.id: c.customer_name for c in customers}
    if not customer_map:
        return {"engagements": []}

    roadmap = db.query(RoadmapMessage).filter(
        and_(
            RoadmapMessage.customer_id.in_(customer_map.keys()),
            RoadmapMessage.status != "scheduled"
        )
    )
    scheduled = db.query(ScheduledSMS).filter(ScheduledSMS.customer_id.in_(customer_map.keys()))

    roadmap_data = [
        {
            "id": msg.id,
            "smsContent": msg.smsContent,
            "smsTiming": msg.smsTiming,
            "status": msg.status,
            "customer_name": customer_map.get(msg.customer_id, "Unknown"),
            "send_datetime_utc": msg.send_datetime_utc.isoformat() if msg.send_datetime_utc else None,
            "source": "roadmap"
        }
        for msg in roadmap
    ]

    scheduled_data = [
        {
            "id": sms.id,
            "smsContent": sms.message,
            "smsTiming": sms.send_time.strftime("Scheduled: %b %d, %I:%M %p"),
            "status": sms.status,
            "customer_name": customer_map.get(sms.customer_id, "Unknown"),
            "send_datetime_utc": sms.send_time.isoformat() if sms.send_time else None,
            "source": "scheduled",
            "is_hidden": sms.is_hidden  # 👈 include this field
        }
        for sms in scheduled
    ]

    return {"engagements": roadmap_data + scheduled_data}

@router.put("/update-time/{id}")
def update_message_time(
    id: int,
    source: str = Query(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    print(f"📬 PUT update-time for ID={id}, source={source}, payload={payload}")

    new_time_str = payload.get("send_datetime_utc")
    if not new_time_str:
        raise HTTPException(status_code=400, detail="Missing send_datetime_utc")

    try:
        new_time = datetime.fromisoformat(new_time_str.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    if source == "roadmap":
        message = db.query(RoadmapMessage).filter(RoadmapMessage.id == id).first()
        if not message:
            raise HTTPException(status_code=404, detail="Roadmap message not found")
        print("🕓 Before:", message.send_datetime_utc)
        message.send_datetime_utc = new_time
        message.smsContent = payload.get("smsContent")
        print("✅ After:", message.send_datetime_utc)

    elif source == "scheduled":
        message = db.query(ScheduledSMS).filter(ScheduledSMS.id == id).first()
        if not message:
            raise HTTPException(status_code=404, detail="Scheduled message not found")
        print("🕓 Before:", message.send_time)
        message.send_time = new_time
        message.message = payload.get("smsContent")
        from app.celery_tasks import schedule_sms_task
        print(f"📤 Re-enqueuing SMS {message.id} for {new_time}")
        schedule_sms_task.apply_async(
            args=[message.id],
            eta=new_time,
        )
        print("✅ After:", message.send_time)

    else:
        raise HTTPException(status_code=400, detail="Invalid source type")

    db.commit()
    return {"success": True}

@router.delete("/{id}")
def delete_sms(id: int, source: str = Query(...), db: Session = Depends(get_db)):
    # Try ScheduledSMS by ID
    sms = db.query(ScheduledSMS).filter(ScheduledSMS.id == id).first()
    if sms:
        db.delete(sms)
        db.commit()
        print(f"🗑️ Deleted ScheduledSMS ID={sms.id}")
        return {"success": True, "deleted_from": "ScheduledSMS by ID", "id": sms.id}

    # Try ScheduledSMS by roadmap_id
    sms = db.query(ScheduledSMS).filter(ScheduledSMS.roadmap_id == id).first()
    if sms:
        db.delete(sms)
        db.commit()
        print(f"🗑️ Deleted ScheduledSMS (roadmap) ID={sms.id}")
        return {"success": True, "deleted_from": "ScheduledSMS by roadmap_id", "id": sms.id}

    # Fallback to RoadmapMessage
    sms = db.query(RoadmapMessage).filter(RoadmapMessage.id == id).first()
    if sms:
        db.delete(sms)
        db.commit()
        print(f"🗑️ Deleted RoadmapMessage ID={sms.id}")
        return {"success": True, "deleted_from": "RoadmapMessage", "id": sms.id}

    raise HTTPException(status_code=404, detail="SMS not found")

@router.put("/update-time-debug/{id}")
def debug_update_message_time(
    id: int,
    source: str = Query(...),
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    print("✅ REACHED DEBUG ENDPOINT")
    print(f"ID={id}, Source={source}, Payload={payload}")
    return {"received": True, "id": id, "payload": payload, "source": source}



@router.get("/customer-replies")
def get_customer_replies(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    results = (
        db.query(Engagement)
        .join(Engagement.customer)  # ensures we can access Customer.business_id
        .filter(
            Customer.business_id == business_id,
            Engagement.response.isnot(None),
            Engagement.ai_response.isnot(None),
            Engagement.status == "pending_review"
        )
        .all()
    )

    return [
        {
            "id": e.id,
            "customer_name": e.customer.customer_name if e.customer else "Unknown",
            "response": e.response,
            "ai_response": e.ai_response,
            "status": e.status,
            "phone": e.customer.phone if e.customer else None,
            "lifecycle_stage": e.customer.lifecycle_stage if e.customer else None,
            "pain_points": e.customer.pain_points if e.customer else None,
            "interaction_history": e.customer.interaction_history if e.customer else None,
        }
        for e in results
    ]
    
@router.get("/reply-stats/{business_id}")
def get_reply_stats(business_id: int, db: Session = Depends(get_db)):
    from app.models import Customer, Engagement

    pending = db.query(Engagement).join(Customer).filter(
        Customer.business_id == business_id,
        Engagement.status == "pending_review",
        Engagement.response.isnot(None),
        Engagement.customer_id.isnot(None)
    ).all()

    total_drafted = db.query(Engagement).join(Customer).filter(
        Customer.business_id == business_id,
        Engagement.response.isnot(None),
        Engagement.ai_response.isnot(None),
        Engagement.customer_id.isnot(None)
    ).count()

    customer_ids = {m.customer_id for m in pending}

    return {
        "customers_waiting": len(customer_ids),
        "messages_waiting": len(pending),
        "messages_total": total_drafted
    }

@router.post("/debug/send-sms-now/{scheduled_id}")
def debug_send_sms_now(scheduled_id: int):
    from app.celery_tasks import schedule_sms_task
    print(f"🚨 Manually triggering SMS for ScheduledSMS id={scheduled_id}")
    schedule_sms_task.apply_async(args=[scheduled_id], kwargs={"force_send": True})
    return {"status": "task_triggered", "id": scheduled_id}


@router.get("/full-customer-history")
def get_full_customer_history(
    business_id: int = Query(...),
    db: Session = Depends(get_db)
):
    results = (
        db.query(Engagement)
        .join(Engagement.customer)
        .filter(Customer.business_id == business_id)
        .all()
    )

    return [
        {
            "id": e.id,
            "customer_name": e.customer.customer_name if e.customer else "Unknown",
            "response": e.response,
            "ai_response": e.ai_response,
            "status": e.status,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "phone": e.customer.phone if e.customer else None,
            "lifecycle_stage": e.customer.lifecycle_stage if e.customer else None,
            "pain_points": e.customer.pain_points if e.customer else None,
            "interaction_history": e.customer.interaction_history if e.customer else None,
            "customer_id": e.customer_id,  # Explicitly include the customer_id
        }
        for e in results
    ]


@router.get("/review/customer-id/from-message/{message_id}")
def get_customer_id_from_message(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(Engagement).filter(Engagement.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"customer_id": msg.customer_id}

@router.put("/engagement/update-draft/{engagement_id}")
def update_engagement_draft(engagement_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    Updates the ai_response of a specific engagement record.
    """
    ai_response = payload.get("ai_response")
    if ai_response is None:
        raise HTTPException(status_code=400, detail="Missing ai_response in request body")

    engagement = db.query(Engagement).filter(Engagement.id == engagement_id).first()
    if not engagement:
        raise HTTPException(status_code=404, detail=f"Engagement with id {engagement_id} not found")

    engagement.ai_response = ai_response
    db.commit()
    return {"message": f"Engagement {engagement_id} draft updated successfully"}

@router.put("/hide-sent/{scheduled_id}")
def hide_sent_message(scheduled_id: int, hide: bool = Query(True), db: Session = Depends(get_db)):
    sms = db.query(ScheduledSMS).filter(ScheduledSMS.id == scheduled_id).first()
    if not sms:
        raise HTTPException(status_code=404, detail="Scheduled SMS not found")

    sms.is_hidden = hide
    db.commit()
    action = "hidden" if hide else "unhidden"
    print(f"🙈 ScheduledSMS ID={scheduled_id} marked as {action}")
    return {"success": True, "id": scheduled_id, "is_hidden": hide}