import pytest
from lumneo.memory.model import MemoryObject, Evidence, Source, MemoryNeed
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id


def make_test_memory(
    tenant_id: str = None,
    agent_id: str = None,
    status: str = "active",
    content: str = "Test content",
    confidence: float = 0.8,
    importance: int = 3
) -> MemoryObject:
    """辅助函数：创建测试用的 MemoryObject"""
    source = Source(
        tenant_id=tenant_id,
        agent_id=agent_id,
        chat_id="chat_123",
        message_id="msg_456",
        timestamp=utc_now(),
        channel="test"
    )
    evidence = Evidence(
        type="explicit_statement",
        weight=1.0,
        source=source,
        observation="test observation",
        origin_actor="user",
        created_at=utc_now(),
        provenance_key="prov_123"
    )
    return MemoryObject(
        id=generate_memory_id(),
        schema_version="2.1.2",
        layer="semantic",
        type="fact",
        subject="test_subject",
        predicate="test_predicate",
        object="test_object",
        condition=None,
        content=content,
        confidence=confidence,
        importance=importance,
        status=status,
        evidence=[evidence],
        source=source,
        origin="explicit_user",
        supersedes=None,
        superseded_by=None,
        last_accessed=None,
        access_count=0,
        tags=[],
        privacy=None,
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata={}
    )

@pytest.fixture
def repo(tmp_path):
    """创建临时 Repository 实例"""
    db_path = tmp_path / "test.db"
    data_root = tmp_path / "data"
    return SQLiteMemoryRepository(db_path=db_path, data_root=data_root)


def test_scope_isolation(repo):
    # 创建两条记忆，分属不同 tenant
    mem_a = make_test_memory(tenant_id="tenant_a", agent_id="agent_a")
    mem_b = make_test_memory(tenant_id="tenant_b", agent_id="agent_a")
    repo.create(mem_a)
    repo.create(mem_b)

    need_a = MemoryNeed(
        layers=[],
        types=[],
        keywords=[],
        max_results=10,
        scope_filter={"tenant_id": "tenant_a"}
    )
    results_a = repo.query_active(need_a)
    assert len(results_a) == 1
    assert results_a[0].id == mem_a.id

    need_b = MemoryNeed(
        layers=[],
        types=[],
        keywords=[],
        max_results=10,
        scope_filter={"tenant_id": "tenant_b"}
    )
    results_b = repo.query_active(need_b)
    assert len(results_b) == 1
    assert results_b[0].id == mem_b.id


def test_query_by_status_scope(repo):
    mem = make_test_memory(tenant_id="tenant_a")
    repo.create(mem)

    # 将状态改为 superseded
    mem.status = "superseded"
    repo.update_with_version(mem)

    results = repo.query_by_status("superseded", scope_filter={"tenant_id": "tenant_a"})
    assert len(results) == 1
    assert results[0].id == mem.id

    results_other = repo.query_by_status("superseded", scope_filter={"tenant_id": "tenant_b"})
    assert len(results_other) == 0


def test_explain_uses_index(repo):
    # 先插入一条记忆，使表非空，便于执行计划分析
    mem = make_test_memory(tenant_id="tenant_a")
    repo.create(mem)

    # 执行 EXPLAIN QUERY PLAN 并检查是否使用 idx_memories_scope 索引
    cursor = repo.conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM memories "
        "WHERE status='active' AND json_extract(source_json, '$.tenant_id') = 'tenant_a'"
    )
    rows = cursor.fetchall()
    # EXPLAIN QUERY PLAN 返回 4 列：id, parent, notused, detail
    # detail 列包含索引信息
    plan_details = [row[3] for row in rows]  # 第4列（索引3）是 detail
    plan_str = " ".join(plan_details)
    assert "idx_memories_scope" in plan_str, f"Index not used, plan: {plan_str}"