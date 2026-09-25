"""Pydantic request/response models — the actual wire contract.

Kept separate from `core.models.Message`: this is what a caller sends
over HTTP, not what agents/routing operate on internally. Phase 1 is
deliberately single-turn/stateless — no conversation_id yet (Phase 3).
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
