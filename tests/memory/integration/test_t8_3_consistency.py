from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.model import Evidence, MemoryNeed, MemoryObject, Source
from lumneo.memory.retrieval import retrieve
from lumneo.memory.storage.repository import SQLiteMemoryRepository


def _memory(
    *,
    content: str,
    status: str = "active",
    supersedes: str | None = None,
) -> MemoryObject:
    now = datetime.now(timezone.utc)
    memory_id = generate_memory_id()
    source = Source(
        tenant_id="tenant-t8-3",
        agent_id="agent-t8-3",
        chat_id="chat-t8-3",
        message_id=f"message-{memory_id}",
        timestamp=now,
    )
    return MemoryObject(
        id=memory_id,
        layer="semantic",
        type="fact",
        subject="T8.3 user",
        predicate="lifecycle",
        object=content,
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
        supersedes=supersedes,
        created_at=now,
        updated_at=now,
    )


def _markdown_path(data_root: Path, memory: MemoryObject) -> Path:
    return data_root / memory.layer / f"{memory.id}.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_fts_document(repo: SQLiteMemoryRepository, memory_id: str) -> None:
    row = repo.conn.execute(
        "SELECT rowid, content, subject, predicate, object, tags_json "
        "FROM memories WHERE id = ?",
        (memory_id,),
    ).fetchone()
    assert row is not None
    repo.conn.execute(
        "INSERT INTO memories_fts("
        "memories_fts, rowid, content, subject, predicate, object, tags"
        ") VALUES('delete', ?, ?, ?, ?, ?, ?)",
        tuple(row),
    )
    repo.conn.commit()


def test_t8_3_lifecycle_and_fts_rebuild_preserve_markdown(tmp_path: Path) -> None:
    data_root = tmp_path / "memory"
    repository = SQLiteMemoryRepository(tmp_path / "memory.db", data_root)
    try:
        original = repository.create(_memory(content="initial_unique_token"))

        original.content = "updated_unique_token"
        original.object = original.content
        repository.update_with_version(original)

        successor = repository.create(
            _memory(content="successor_unique_token", supersedes=original.id)
        )
        original.status = "superseded"
        original.superseded_by = successor.id
        repository.update_with_version(original)
        successor.status = "archived"
        repository.update_with_version(successor)

        paths = {
            original.id: _markdown_path(data_root, original),
            successor.id: _markdown_path(data_root, successor),
        }
        hashes_before = {memory_id: _sha256(path) for memory_id, path in paths.items()}

        _remove_fts_document(repository, original.id)
        damaged = repository.check_consistency()
        assert damaged.status == "critical"
        assert original.id in damaged.missing_in_index
        assert hashes_before == {
            memory_id: _sha256(path) for memory_id, path in paths.items()
        }

        rebuilt = repository.rebuild_index()
        assert rebuilt.status == "healthy"
        assert hashes_before == {
            memory_id: _sha256(path) for memory_id, path in paths.items()
        }

        restored_original = repository.get_by_id(original.id)
        restored_successor = repository.get_by_id(successor.id)
        assert restored_original is not None
        assert restored_successor is not None
        assert restored_original.content == "updated_unique_token"
        assert restored_original.status == "superseded"
        assert restored_original.superseded_by == successor.id
        assert restored_successor.status == "archived"
        assert restored_successor.supersedes == original.id

        repository.record_access = lambda _memory_id: None
        results = retrieve(
            MemoryNeed(
                keywords=["updated_unique_token"],
                include_historical=True,
            ),
            repository=repository,
        )
        assert original.id in {memory.id for memory in results}
    finally:
        repository.close()


def test_consistency_accepts_a_valid_document_with_no_fts_tokens(
    tmp_path: Path,
) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.db", tmp_path / "memory")
    try:
        memory = _memory(content="!!!")
        memory.subject = None
        memory.predicate = None
        memory.object = None
        memory.tags = []
        repository.create(memory)

        report = repository.check_consistency()

        assert report.status == "healthy"
        assert report.missing_in_index == []
    finally:
        repository.close()
