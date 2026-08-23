from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.model import Evidence, MemoryNeed, MemoryObject, Source
from lumneo.memory.retrieval import retrieve
from lumneo.memory.storage.repository import SQLiteMemoryRepository


@pytest.fixture
def repository(tmp_path: Path):
    instance = SQLiteMemoryRepository(tmp_path / "memory.db", tmp_path / "memory")
    instance.record_access = lambda _memory_id: None
    try:
        yield instance
    finally:
        instance.close()


def _memory(
    *,
    condition: dict | None,
    tenant_id: str = "tenant-a",
    agent_id: str = "agent-a",
    status: str = "active",
    content: str = "room_1 condition candidate",
) -> MemoryObject:
    now = datetime.now(timezone.utc)
    memory_id = generate_memory_id()
    source = Source(
        tenant_id=tenant_id,
        agent_id=agent_id,
        chat_id="condition-test",
        message_id=f"message-{memory_id}",
        timestamp=now,
    )
    return MemoryObject(
        id=memory_id,
        layer="semantic",
        type="fact",
        subject="condition user",
        predicate="activity",
        object="condition object",
        condition=condition,
        content=content,
        confidence=0.9,
        importance=4,
        status=status,
        evidence=[
            Evidence(
                type="explicit_statement",
                weight=1.0,
                source=source,
                observation=content,
                origin_actor="user",
                created_at=now,
                provenance_key=f"provenance-{memory_id}",
            )
        ],
        source=source,
        origin="explicit_user",
        created_at=now,
        updated_at=now,
    )


def _need(condition_filter: dict, *, include_historical: bool = False) -> MemoryNeed:
    return MemoryNeed(
        keywords=["room_1"],
        scope_filter={"tenant_id": "tenant-a", "agent_id": "agent-a"},
        condition_filter=condition_filter,
        include_historical=include_historical,
    )


def test_single_condition_is_exactly_post_filtered(repository) -> None:
    matching = repository.create(
        _memory(condition={"key": "place", "value": "room_1"})
    )
    repository.create(_memory(condition={"key": "place", "value": "room_10"}))
    repository.create(_memory(condition=None))

    results = retrieve(
        _need({"key": "place", "value": "room_1"}),
        repository=repository,
    )

    assert [memory.id for memory in results] == [matching.id]


def test_and_condition_requires_every_exact_clause(repository) -> None:
    matching = repository.create(
        _memory(
            condition={
                "operator": "AND",
                "clauses": [
                    {"key": "place", "value": "room_1"},
                    {"key": "time", "value": "weekend"},
                    {"key": "weather", "value": "sunny"},
                ],
            }
        )
    )
    repository.create(
        _memory(condition={"key": "place", "value": "room_1"})
    )

    results = retrieve(
        _need(
            {
                "operator": "AND",
                "clauses": [
                    {"key": "place", "value": "room_1"},
                    {"key": "time", "value": "weekend"},
                ],
            }
        ),
        repository=repository,
    )

    assert [memory.id for memory in results] == [matching.id]


def test_condition_mismatch_returns_no_memory(repository) -> None:
    repository.create(_memory(condition={"key": "place", "value": "room_2"}))

    assert retrieve(
        _need({"key": "place", "value": "room_1"}),
        repository=repository,
    ) == []


def test_scope_and_status_remain_hard_filters(repository) -> None:
    allowed = repository.create(
        _memory(condition={"key": "place", "value": "room_1"})
    )
    repository.create(
        _memory(
            condition={"key": "place", "value": "room_1"},
            tenant_id="tenant-b",
        )
    )
    repository.create(
        _memory(
            condition={"key": "place", "value": "room_1"},
            status="archived",
        )
    )

    results = retrieve(
        _need({"key": "place", "value": "room_1"}),
        repository=repository,
    )

    assert [memory.id for memory in results] == [allowed.id]


def test_condition_fts_coarse_pool_is_capped_at_100(repository) -> None:
    for _ in range(120):
        repository.create(
            _memory(condition={"key": "place", "value": "room_1"})
        )

    candidates = repository.search_candidates(
        _need({"key": "place", "value": "room_1"}),
        statuses=["active"],
        limit=500,
    )

    assert len(candidates) == 100
