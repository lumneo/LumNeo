# tests/memory/unit/test_repository.py
import pytest
import tempfile
import time
from datetime import datetime
from pathlib import Path
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.model import MemoryObject, Evidence, Source
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.common.exceptions import ConcurrentModificationError

def create_test_memory():
    return MemoryObject(
        id=generate_memory_id(),
        schema_version="2.1.2",
        layer="semantic",
        type="preference",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        content="用户喜欢美式咖啡",
        confidence=0.87,
        importance=4,
        status="active",
        evidence=[
            Evidence(
                type="explicit_statement",
                weight=1.0,
                source=Source(tenant_id="t1", agent_id="a1", chat_id="c1", message_id="m1", timestamp=utc_now()),
                observation="测试",
                origin_actor="user",
                created_at=utc_now(),
                provenance_key="m1"
            )
        ],
        source=Source(tenant_id="t1", agent_id="a1", chat_id="c1", message_id="m1", timestamp=utc_now()),
        origin="explicit_user",
        created_at=utc_now(),
        updated_at=utc_now(),
        tags=[],
        metadata={"standardization_issue": False, "user_forgotten": False},
    )

def test_s10_optimistic_lock_interface():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)
        try:
            memory = create_test_memory()
            repo.create(memory)

            # 第一次更新
            time.sleep(0.1)
            memory.content = "新内容"
            updated_memory = repo.update_with_version(memory)
            
            # 从数据库读取第一次更新后的时间
            cursor = repo.conn.execute("SELECT updated_at FROM memories WHERE id = ?", (memory.id,))
            row = cursor.fetchone()
            db_updated1 = datetime.fromisoformat(row[0])
            assert updated_memory.updated_at == db_updated1  # 确保对象与数据库一致

            # 第二次更新
            time.sleep(0.1)
            memory2 = updated_memory
            memory2.content = "再更新"
            updated2 = repo.update_with_version(memory2, expected_updated_at=updated_memory.updated_at)

            # 从数据库读取第二次更新后的时间
            cursor2 = repo.conn.execute("SELECT updated_at FROM memories WHERE id = ?", (memory.id,))
            row2 = cursor2.fetchone()
            db_updated2 = datetime.fromisoformat(row2[0])
            assert updated2.updated_at == db_updated2

            # 关键断言：第二次数据库时间 > 第一次数据库时间
            assert db_updated2 > db_updated1

            # 带错误 expected 应抛 ConcurrentModificationError
            memory3 = updated2
            memory3.content = "错误预期"
            with pytest.raises(ConcurrentModificationError):
                repo.update_with_version(memory3, expected_updated_at=db_updated1)  # 故意使用旧时间

        finally:
            repo.close()