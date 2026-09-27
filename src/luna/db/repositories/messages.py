"""Repository for the messages aggregate."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from luna.core.models import Message as CoreMessage
from luna.db.models import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        agent_name: str | None = None,
        finish_reason: str | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_name=agent_name,
            finish_reason=finish_reason,
        )
        self._session.add(message)
        await self._session.commit()
        return message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_as_core_messages(self, conversation_id: uuid.UUID) -> list[CoreMessage]:
        """The conversion boundary: ORM rows -> the plain `core.models.Message`
        type agents actually consume. Keeps agents/ from ever importing
        the ORM — see core/models.py's docstring for why that matters."""
        rows = await self.list_for_conversation(conversation_id)
        # row.role is a plain `str` at the type level (the ORM column has
        # no way to express the Literal); the DB's CheckConstraint is what
        # actually guarantees it's one of the three valid values, not mypy.
        return [CoreMessage(role=row.role, content=row.content) for row in rows]  # type: ignore[arg-type]
