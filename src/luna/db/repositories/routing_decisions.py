"""Repository for the routing_decisions audit trail."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from luna.db.models import RoutingDecision
from luna.routing.heuristics import RoutingDecision as RoutingDecisionValue


class RoutingDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, message_id: uuid.UUID, decision: RoutingDecisionValue) -> RoutingDecision:
        row = RoutingDecision(
            message_id=message_id,
            chosen_agent=decision.agent_name,
            method=decision.method,
            confidence=decision.confidence,
        )
        self._session.add(row)
        await self._session.commit()
        return row
