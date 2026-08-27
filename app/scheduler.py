"""
Durable, idempotent scheduler.

Two layers of protection against duplicate posts:
1. DB-level: ScheduleSlot has a UNIQUE idempotency_key, and we check
   PublishAttempt for an existing "success" row before calling the
   adapter at all.
2. APScheduler jobs are stored in the same SQLite file (SQLAlchemyJobStore),
   so a process restart does not lose pending jobs — a worker that dies
   mid-batch resumes correctly.
"""
import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from .models import get_session, ScheduleSlot, Variant, PublishAttempt
from .adapters import get_publisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")

jobstores = {"default": SQLAlchemyJobStore(url="sqlite:///./social_studio.db")}
scheduler = BackgroundScheduler(jobstores=jobstores)


def publish_slot(slot_id: str) -> None:
    """The actual publish job. Idempotent: safe to call more than once
    for the same slot_id (e.g. APScheduler misfire + manual retry)."""
    db = get_session()
    try:
        slot = db.query(ScheduleSlot).filter_by(id=slot_id).first()
        if slot is None:
            logger.warning("slot %s no longer exists — skipping", slot_id)
            return

        existing_success = (
            db.query(PublishAttempt)
            .filter_by(slot_id=slot.id, result="success")
            .first()
        )
        if existing_success:
            # Already published — record the skip, do NOT call the adapter again.
            db.add(PublishAttempt(
                slot_id=slot.id,
                result="duplicate_skipped",
                detail=f"already published: {existing_success.detail}",
            ))
            db.commit()
            logger.info("slot %s already published — skipped duplicate call", slot_id)
            return

        variant = db.query(Variant).filter_by(id=slot.variant_id).first()
        if variant.status != "approved":
            db.add(PublishAttempt(
                slot_id=slot.id, result="error",
                detail=f"variant status is '{variant.status}', not approved",
            ))
            db.commit()
            return

        slot.status = "publishing"
        db.commit()

        try:
            publisher = get_publisher(variant.platform)
            ref = publisher.publish(variant.text, idempotency_key=slot.idempotency_key)
            db.add(PublishAttempt(slot_id=slot.id, result="success", detail=ref))
            slot.status = "done"
            variant.status = "published"
            db.commit()
            logger.info("slot %s published -> %s", slot_id, ref)
        except Exception as e:
            db.add(PublishAttempt(slot_id=slot.id, result="error", detail=str(e)))
            slot.status = "failed"
            db.commit()
            logger.error("slot %s publish failed: %s", slot_id, e)
    finally:
        db.close()


def schedule_slot(slot_id: str, publish_at: datetime.datetime) -> None:
    scheduler.add_job(
        publish_slot,
        trigger="date",
        run_date=publish_at,
        args=[slot_id],
        id=f"publish-{slot_id}",
        replace_existing=True,   # re-scheduling the same slot never doubles the job
        misfire_grace_time=3600,
    )


def start():
    if not scheduler.running:
        scheduler.start()
