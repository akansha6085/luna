"""Repository for the conversations aggregate.

Repository pattern: route handlers never write raw SQL/ORM queries
directly — they call a repository method. That's what makes it possible
to swap the storage backend (exactly what's happening this phase: the
UI moves from localStorage to this) without route handlers changing,
and what makes routes_conversations.py testable against a fake
repository instead of a real database.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from luna.db.models import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, title: str | None = None) -> Conversation:
        conversation = Conversation(title=title)
        self._session.add(conversation)
        await self._session.commit()
        return conversation

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        return await self._session.get(Conversation, conversation_id)

    async def list_recent(self, limit: int = 50) -> list[Conversation]:
        stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def set_title_if_unset(self, conversation_id: uuid.UUID, title: str) -> None:
        conversation = await self.get(conversation_id)
        if conversation is not None and conversation.title is None:
            conversation.title = title
            await self._session.commit()

    async def touch(self, conversation_id: uuid.UUID) -> None:
        """Bump updated_at — called whenever a message is added, so the
        sidebar's "most recently active" ordering (list_recent above)
        reflects actual conversation activity, not just creation time."""
        conversation = await self.get(conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(UTC)
            await self._session.commit()

    async def delete(self, conversation_id: uuid.UUID) -> None:
        conversation = await self.get(conversation_id)
        if conversation is not None:
            await self._session.delete(conversation)  # cascades to messages
            await self._session.commit()
