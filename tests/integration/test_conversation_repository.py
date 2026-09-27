"""Integration tests for ConversationRepository — against a real Postgres."""

import asyncio
import uuid

from luna.db.repositories.conversations import ConversationRepository


async def test_create_and_get(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create(title="hello")

    fetched = await repo.get(conversation.id)
    assert fetched is not None
    assert fetched.id == conversation.id
    assert fetched.title == "hello"
    assert fetched.status == "active"


async def test_get_missing_returns_none(db_session):
    repo = ConversationRepository(db_session)
    assert await repo.get(uuid.uuid4()) is None


async def test_list_recent_orders_by_updated_at_descending(db_session):
    repo = ConversationRepository(db_session)
    first = await repo.create(title="first")
    await asyncio.sleep(0.01)  # ensure a distinguishable updated_at
    second = await repo.create(title="second")

    conversations = await repo.list_recent()
    ids = [c.id for c in conversations]
    assert ids.index(second.id) < ids.index(first.id)


async def test_set_title_if_unset_only_sets_once(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()  # no title
    await repo.set_title_if_unset(conversation.id, "first title")
    await repo.set_title_if_unset(conversation.id, "should not overwrite")

    fetched = await repo.get(conversation.id)
    assert fetched.title == "first title"


async def test_touch_updates_updated_at(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    original_updated_at = conversation.updated_at

    await asyncio.sleep(0.01)
    await repo.touch(conversation.id)

    fetched = await repo.get(conversation.id)
    assert fetched.updated_at > original_updated_at


async def test_delete_removes_the_conversation(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    await repo.delete(conversation.id)
    assert await repo.get(conversation.id) is None


async def test_delete_of_missing_id_is_a_safe_no_op(db_session):
    repo = ConversationRepository(db_session)
    await repo.delete(uuid.uuid4())  # must not raise
