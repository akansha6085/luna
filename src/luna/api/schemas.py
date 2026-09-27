"""Pydantic request/response models — the actual wire contract.

Kept separate from `core.models.Message` and `db.models`: this is what a
caller sends/receives over HTTP, not what agents/routing operate on
internally, and not what Postgres stores. Converting between the three
happens at the boundary, in the route handlers.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    # None on the first message of a new conversation — the server
    # creates one and returns its id via the `conversation` SSE event
    # (see routes_chat.py). Provided on every subsequent message in the
    # same thread, which is what makes replies multi-turn.
    conversation_id: uuid.UUID | None = None


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # build directly from an ORM row


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    agent_name: str | None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
