"""SQLAlchemy 2.0 ORM models — the persistence contract.

Deliberately a THIRD type system, distinct from `core.models.Message`
(what agents/routing operate on) and `api.schemas` (the wire contract
with callers). Converting between the three happens at the boundaries —
db/repositories/ converts ORM rows to/from `core.models.Message`;
api/routes_chat.py never touches an ORM object directly.

Design notes worth knowing:
- UUID primary keys, generated in Python (`default=uuid.uuid4`) rather
  than by Postgres, so a caller can know a row's id before it's
  committed — no round-trip needed to find out what id got assigned.
- `role`/`status`/`method` are plain strings with a CheckConstraint,
  NOT a native Postgres ENUM type. This is deliberate: native enums are
  painful to extend later (`ALTER TYPE ... ADD VALUE` has real caveats
  inside transactions on older Postgres, and can't be done at all in
  the same transaction as other DDL on some versions). A CheckConstraint
  gets you the same validation with a trivial migration if a new value
  is ever needed.
- Timestamps are timezone-aware (`DateTime(timezone=True)`) — always
  store UTC-aware, never naive, to avoid ambiguity later.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luna.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("status in ('active', 'archived')", name="ck_conversations_status"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column()
    # Which agent produced this message — null for user/system messages.
    # A single conversation can be routed to different agents turn by
    # turn, mirroring the real platform this project is inspired by.
    agent_name: Mapped[str | None] = mapped_column(default=None)
    content: Mapped[str] = mapped_column()
    finish_reason: Mapped[str | None] = mapped_column(default=None)
    # Token counts / latency: nullable, populated starting Phase 4 (cost
    # tracking). Columns exist now so Phase 4 is additive, not a migration
    # that has to backfill or restructure this table.
    prompt_tokens: Mapped[int | None] = mapped_column(default=None)
    completion_tokens: Mapped[int | None] = mapped_column(default=None)
    latency_ms: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant', 'system')", name="ck_messages_role"),
        # Composite index for the actual access pattern: "give me this
        # conversation's messages, in order" — a single-column index on
        # conversation_id alone would still need to sort created_at
        # separately for every query.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )


class RoutingDecision(Base):
    """One row per routed user message — an audit trail of routing
    quality: which agent got picked, by which method, at what confidence.
    Not read by the app at request time; exists for debugging/analysis."""

    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    chosen_agent: Mapped[str] = mapped_column()
    method: Mapped[str] = mapped_column()
    confidence: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("method in ('heuristic', 'llm_classifier')", name="ck_routing_decisions_method"),
    )
