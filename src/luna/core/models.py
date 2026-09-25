"""Small, framework-agnostic domain types shared across layers.

Deliberately NOT the Pydantic API schemas (those live in api/schemas.py
and are the wire contract with callers) and NOT the SQLAlchemy ORM models
(those will live in db/models.py, Phase 3, and are the persistence
contract). This is the plain type agents/, routing/, and llm/ actually
operate on — so those modules never need to import from api/ or db/ just
to know what a "chat message" is. Converting between this and the API
schema happens at the boundary, in the route handler.
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
