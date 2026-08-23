# test/memory/integration/test_fts5.py
import tempfile
from pathlib import Path
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.model import MemoryObject, Evidence, Source
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id

def test_s05_fts5_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)
        try:
            # 检查 FTS5 表是否存在
            conn = repo.conn
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
            )
            assert cursor.fetchone() is not None, "memories_fts 表未创建"

            # 构造记忆
            memory = MemoryObject(
                id=generate_memory_id(),
                schema_version="2.1.2",
                layer="semantic",
                type="preference",
                subject="用户",
                predicate="preference",
                object="美式咖啡",
                content="用户喜欢喝美式咖啡，尤其偏爱深度烘焙的",
                confidence=0.87,
                importance=4,
                status="active",
                evidence=[
                    Evidence(
                        type="explicit_statement",
                        weight=1.0,
                        source=Source(
                            tenant_id="t1",
                            agent_id="a1",
                            chat_id="c1",
                            message_id="m1",
                            timestamp=utc_now(),
                        ),
                        observation="用户说：我喜欢美式咖啡",
                        origin_actor="user",
                        created_at=utc_now(),
                        provenance_key="m1"
                    )
                ],
                source=Source(
                    tenant_id="t1",
                    agent_id="a1",
                    chat_id="c1",
                    message_id="m1",
                    timestamp=utc_now(),
                ),
                origin="explicit_user",
                created_at=utc_now(),
                updated_at=utc_now(),
                tags=["咖啡", "美式"],
                metadata={"standardization_issue": False, "user_forgotten": False},
            )

            repo.create(memory)

            # 获取 rowid
            rowid_cursor = conn.execute("SELECT rowid FROM memories WHERE id = ?", (memory.id,))
            rowid = rowid_cursor.fetchone()[0]

            # 测试 FTS5 基本搜索（不使用 bm25，先验证 MATCH 能工作）
            cursor = conn.execute("""
                SELECT rowid
                FROM memories_fts
                WHERE memories_fts MATCH ?
            """, ("美式咖啡",))
            results = cursor.fetchall()
            assert len(results) > 0
            assert results[0]['rowid'] == rowid

            # 测试 bm25 函数（如果上一步通过，通常 bm25 也可用）
            cursor2 = conn.execute("""
                SELECT rowid, bm25(memories_fts) as score
                FROM memories_fts
                WHERE memories_fts MATCH ?
                ORDER BY score
            """, ("美式咖啡",))
            results2 = cursor2.fetchall()
            assert len(results2) > 0
            assert results2[0]['rowid'] == rowid

        finally:
            repo.close()