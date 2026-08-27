"""
Social Media Studio — FastAPI entrypoint.

Endpoints map directly to the brief's 5 build blocks:
  1. Post ingestion       -> POST /posts
  2. Variant generation    -> POST /posts/{id}/generate
  3. Review workflow       -> POST /variants/{id}/approve|reject
  4. Adapter layer         -> app/adapters.py (used by scheduler)
  5. Idempotent scheduling -> POST /variants/{id}/schedule, GET /publish-history
"""
import datetime
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .models import init_db, get_session, Post, Variant, ScheduleSlot, PublishAttempt
from .constraints import generate_variant, validate, ConstraintViolation, PROFILES
from . import scheduler as sched

app = FastAPI(title="Social Media Studio")


@app.on_event("startup")
def startup():
    init_db()
    sched.start()


# ---------- 1. Post ingestion ----------

class PostIn(BaseModel):
    source: str          # "url" or "markdown"
    content: str          # the URL, or the raw markdown/text


@app.post("/posts")
def create_post(payload: PostIn):
    if payload.source not in ("url", "markdown"):
        raise HTTPException(400, "source must be 'url' or 'markdown'")

    # NOTE: real URL fetching is intentionally out of scope for the MVP —
    # for "url" source we store the URL as a placeholder body. Swap in a
    # requests.get() + readability extraction if you want full fidelity.
    body = payload.content if payload.source == "markdown" else f"[content fetched from {payload.content}]"

    db = get_session()
    try:
        post = Post(source=payload.source, raw_input=payload.content, body=body)
        db.add(post)
        db.commit()
        db.refresh(post)
        return {"id": post.id, "source": post.source, "body": post.body}
    finally:
        db.close()


# ---------- 2. Variant generation ----------

class GenerateIn(BaseModel):
    platforms: list[str] = ["x", "linkedin"]


@app.post("/posts/{post_id}/generate")
def generate_variants(post_id: str, payload: GenerateIn):
    db = get_session()
    try:
        post = db.query(Post).filter_by(id=post_id).first()
        if not post:
            raise HTTPException(404, "post not found")

        created, blocked = [], []
        for platform in payload.platforms:
            try:
                text = generate_variant(platform, post.body)
                validate(platform, text)
            except ConstraintViolation as e:
                blocked.append({"platform": platform, "rule": e.rule, "detail": e.detail})
                continue

            variant = Variant(post_id=post.id, platform=platform, text=text, status="draft")
            db.add(variant)
            db.commit()
            db.refresh(variant)
            created.append({"id": variant.id, "platform": platform, "text": text})

        return {"created": created, "blocked": blocked}
    finally:
        db.close()


# ---------- 3. Review workflow ----------

@app.post("/variants/{variant_id}/approve")
def approve_variant(variant_id: str):
    return _set_status(variant_id, "approved", allowed_from=("draft",))


@app.post("/variants/{variant_id}/reject")
def reject_variant(variant_id: str):
    return _set_status(variant_id, "rejected", allowed_from=("draft",))


def _set_status(variant_id: str, new_status: str, allowed_from: tuple[str, ...]):
    db = get_session()
    try:
        v = db.query(Variant).filter_by(id=variant_id).first()
        if not v:
            raise HTTPException(404, "variant not found")
        if v.status not in allowed_from:
            raise HTTPException(400, f"cannot {new_status} a variant in status '{v.status}'")
        v.status = new_status
        db.commit()
        return {"id": v.id, "status": v.status}
    finally:
        db.close()


# ---------- 5. Idempotent scheduling ----------

class ScheduleIn(BaseModel):
    publish_at: datetime.datetime


@app.post("/variants/{variant_id}/schedule")
def schedule_variant(variant_id: str, payload: ScheduleIn):
    db = get_session()
    try:
        v = db.query(Variant).filter_by(id=variant_id).first()
        if not v:
            raise HTTPException(404, "variant not found")
        if v.status != "approved":
            # This is Probe 3: refuse scheduling an unapproved variant.
            raise HTTPException(400, f"variant status is '{v.status}', must be 'approved' to schedule")

        idem_key = f"{v.id}:{payload.publish_at.isoformat()}"
        slot = ScheduleSlot(
            variant_id=v.id,
            publish_at=payload.publish_at,
            idempotency_key=idem_key,
        )
        db.add(slot)
        db.commit()
        db.refresh(slot)

        sched.schedule_slot(slot.id, payload.publish_at)

        return {"slot_id": slot.id, "publish_at": payload.publish_at.isoformat(), "idempotency_key": idem_key}
    finally:
        db.close()


@app.get("/publish-history")
def publish_history():
    db = get_session()
    try:
        rows = db.query(PublishAttempt).order_by(PublishAttempt.attempted_at.desc()).all()
        return [
            {
                "slot_id": r.slot_id,
                "result": r.result,
                "detail": r.detail,
                "attempted_at": r.attempted_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/constraint-profiles")
def constraint_profiles():
    return PROFILES
