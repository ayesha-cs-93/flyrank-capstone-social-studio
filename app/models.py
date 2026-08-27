"""
Data models — the single source of truth for posts, variants, schedule
slots and publish attempts. Uses SQLite via SQLAlchemy so it survives
process restarts (required for durable scheduling).
"""
import datetime
import uuid

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///./social_studio.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def new_id() -> str:
    return str(uuid.uuid4())


class Post(Base):
    """The one stored copy of the source post. All generation reads from here."""
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=new_id)
    source = Column(String, nullable=False)   # "url" or "markdown"
    raw_input = Column(Text, nullable=False)   # the URL or the pasted markdown
    body = Column(Text, nullable=False)        # resolved text content
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    variants = relationship("Variant", back_populates="post")


class Variant(Base):
    """One platform-specific version of the post."""
    __tablename__ = "variants"

    id = Column(String, primary_key=True, default=new_id)
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    platform = Column(String, nullable=False)   # "x", "linkedin", "telegram" etc.
    text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="draft")  # draft/approved/rejected/published
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post", back_populates="variants")
    slots = relationship("ScheduleSlot", back_populates="variant")


class ScheduleSlot(Base):
    """A time slot at which an approved variant should be published."""
    __tablename__ = "schedule_slots"
    __table_args__ = (
        # A variant can only occupy one slot once — this is part of what
        # makes duplicate scheduling impossible at the DB layer.
        UniqueConstraint("variant_id", "publish_at", name="uq_variant_slot"),
    )

    id = Column(String, primary_key=True, default=new_id)
    variant_id = Column(String, ForeignKey("variants.id"), nullable=False)
    publish_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending")  # pending/publishing/done/failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    variant = relationship("Variant", back_populates="slots")


class PublishAttempt(Base):
    """Every attempt to publish a slot, successful or not. This is the audit trail
    that proves idempotency: a slot published twice must show ONE 'success' row."""
    __tablename__ = "publish_attempts"

    id = Column(String, primary_key=True, default=new_id)
    slot_id = Column(String, ForeignKey("schedule_slots.id"), nullable=False)
    attempted_at = Column(DateTime, default=datetime.datetime.utcnow)
    result = Column(String, nullable=False)   # "success" / "duplicate_skipped" / "error"
    detail = Column(Text)                     # adapter response / error message / message link


def init_db():
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
