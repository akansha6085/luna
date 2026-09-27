"""Integration tests for MessageRepository — against a real Postgres,
including the constraints Postgres itself enforces (CheckConstraint,
FK cascade) that a mock could never actually verify."""

import pytest
from sqlalchemy.exc import IntegrityError

from luna.db.repositories.conversations import ConversationRepository
from luna.db.repositories.messages import MessageRepository


async def test_add_and_list_for_conversation(db_session):
    conversations = ConversationRepository(db_session)
    messages = MessageRepository(db_session)
    conversation = await conversations.create()

    await messages.add(conversation.id, role="user", content="hello")
    await messages.add(conversation.id, role="assistant", content="hi there", agent_name="assistant")

    rows = await messages.list_for_conversation(conversation.id)
    assert [r.content for r in rows] == ["hello", "hi there"]
    assert rows[1].agent_name == "assistant"


async def test_list_as_core_messages_converts_to_the_domain_type(db_session):
    conversations = ConversationRepository(db_session)
    messages = MessageRepository(db_session)
    conversation = await conversations.create()
    await messages.add(conversation.id, role="user", content="hello")

    core_messages = await messages.list_as_core_messages(conversation.id)
    assert len(core_messages) == 1
    assert core_messages[0].role == "user"
    assert core_messages[0].content == "hello"


async def test_invalid_role_is_rejected_by_the_database_constraint(db_session):
    conversations = ConversationRepository(db_session)
    messages = MessageRepository(db_session)
    conversation = await conversations.create()

    # The CheckConstraint (db/models.py) is what actually enforces this,
    # not application code — confirming it fires is the whole point of
    # an integration test over a mock, which would happily accept anything.
    with pytest.raises(IntegrityError):
        await messages.add(conversation.id, role="not-a-real-role", content="x")

    # Postgres leaves the transaction aborted after a constraint
    # violation — nothing else can run on this session until it's rolled
    # back, including the _clean_tables fixture's own teardown query.
    await db_session.rollback()


async def test_deleting_conversation_cascades_to_its_messages(db_session):
    conversations = ConversationRepository(db_session)
    messages = MessageRepository(db_session)
    conversation = await conversations.create()
    await messages.add(conversation.id, role="user", content="hello")

    await conversations.delete(conversation.id)

    remaining = await messages.list_for_conversation(conversation.id)
    assert remaining == []
