"""GET /conversations, GET /conversations/{id}/messages, DELETE /conversations/{id}.

Read-only-ish endpoints (creation happens implicitly via POST /chat —
see routes_chat.py) that back the UI's sidebar. This is the Phase 3
counterpart to what web/index.html previously did with
loadState/saveState against localStorage: the same operations, now
against Postgres, through a real HTTP API.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from luna.api.deps import get_conversation_repo, get_message_repo
from luna.api.schemas import ConversationSummary, MessageOut
from luna.db.repositories.conversations import ConversationRepository
from luna.db.repositories.messages import MessageRepository

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> list[ConversationSummary]:
    conversations = await repo.list_recent()
    return [ConversationSummary.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
) -> list[MessageOut]:
    conversation = await conversation_repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = await message_repo.list_for_conversation(conversation_id)
    return [MessageOut.model_validate(m) for m in messages]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> None:
    await repo.delete(conversation_id)  # idempotent: deleting a
    # nonexistent id is a no-op in the repository, not an error — a
    # delete's job is "make sure it's gone," and it already is.
