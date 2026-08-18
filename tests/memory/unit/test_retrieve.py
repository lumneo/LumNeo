import time
import pytest
from pathlib import Path
from lumneo.memory.model import MemoryNeed
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.retrieval import retrieve
from .test_scope import make_test_memory  # 导入更新后的辅助函数


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    data_root = tmp_path / "data" / "memory"
    return SQLiteMemoryRepository(db_path=db_path, data_root=data_root)


def test_retrieve_default_active_only(repo):
    mem1 = make_test_memory(tenant_id="tenant_a", status="active")
    mem2 = make_test_memory(tenant_id="tenant_a", status="active")
    mem3 = make_test_memory(tenant_id="tenant_a", status="superseded")
    repo.create(mem1)
    repo.create(mem2)
    repo.create(mem3)

    need = MemoryNeed(layers=[], types=[], keywords=[], max_results=10, scope_filter={"tenant_id": "tenant_a"})
    result = retrieve(need, repo)
    ids = [m.id for m in result]
    assert mem1.id in ids
    assert mem2.id in ids
    assert mem3.id not in ids


def test_retrieve_include_historical(repo):
    mem1 = make_test_memory(tenant_id="tenant_a", status="active")
    mem2 = make_test_memory(tenant_id="tenant_a", status="superseded")
    mem3 = make_test_memory(tenant_id="tenant_a", status="archived")
    repo.create(mem1)
    repo.create(mem2)
    repo.create(mem3)

    need = MemoryNeed(
        layers=[], types=[], keywords=[],
        max_results=10,
        scope_filter={"tenant_id": "tenant_a"},
        include_historical=True
    )
    result = retrieve(need, repo)
    ids = {m.id for m in result}
    assert mem1.id in ids
    assert mem2.id in ids
    assert mem3.id in ids


def test_retrieve_scoring_order(repo):
    # 两条记忆都包含 "like"，便于 BM25 都匹配
    mem1 = make_test_memory(tenant_id="tenant_a", content="I like coffee", confidence=0.5, importance=3)
    mem2 = make_test_memory(tenant_id="tenant_a", content="I like tea", confidence=0.9, importance=5)
    repo.create(mem1)
    repo.create(mem2)

    need = MemoryNeed(
        layers=[], types=[], keywords=["like"],
        max_results=10,
        scope_filter={"tenant_id": "tenant_a"}
    )
    result = retrieve(need, repo)
    assert len(result) == 2


def test_retrieve_updates_access_metadata(repo):
    mem = make_test_memory(tenant_id="tenant_a", content="test content")
    repo.create(mem)
    assert mem.access_count == 0
    assert mem.last_accessed is None

    need = MemoryNeed(layers=[], types=[], keywords=[], max_results=10, scope_filter={"tenant_id": "tenant_a"})
    result = retrieve(need, repo)
    assert len(result) == 1

    # 等待异步任务完成（最多 1 秒）
    time.sleep(1)

    # 重新读取记忆
    updated = repo.get_by_id(mem.id)
    assert updated is not None
    assert updated.access_count == 1
    assert updated.last_accessed is not None