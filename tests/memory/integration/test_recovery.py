# test/memory/integration/test_recovery.py
import tempfile
import shutil
import time
from pathlib import Path
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.model import MemoryObject, Evidence, Source
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id

def test_s07_index_recovery():
    # 使用 mkdtemp 手动管理临时目录
    tmpdir = tempfile.mkdtemp()
    try:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        
        # 1. 正常创建记忆
        repo = SQLiteMemoryRepository(db_path, data_root)
        try:
            memory = MemoryObject(
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
            repo.create(memory)
        finally:
            repo.close()
            time.sleep(0.1)  # Windows 文件释放延迟

        # 2. 模拟损坏：删除 SQLite 中的该行（Markdown 保留）
        repo2 = SQLiteMemoryRepository(db_path, data_root)
        try:
            conn = repo2.conn
            conn.execute("DELETE FROM memories WHERE id = ?", (memory.id,))
            conn.commit()
        finally:
            repo2.close()
            time.sleep(0.1)

        # 3. 重新打开 Repository，应自动触发 check_consistency 并修复
        repo3 = SQLiteMemoryRepository(db_path, data_root)
        try:
            # 验证记忆已恢复
            cursor = repo3.conn.execute("SELECT id FROM memories WHERE id = ?", (memory.id,))
            row = cursor.fetchone()
            assert row is not None
            assert row['id'] == memory.id
        finally:
            repo3.close()

    finally:
        # 清理临时目录（忽略错误）
        shutil.rmtree(tmpdir, ignore_errors=True)