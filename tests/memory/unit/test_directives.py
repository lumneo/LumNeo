# tests/memory/unit/test_directives.py
import pytest
import gc
import time
import tempfile
from pathlib import Path
from datetime import datetime

from lumneo.memory.governance.directives import UserDirective, apply_user_directives
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.model import MemoryObject, MemoryCandidate, Evidence, Source
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.common.exceptions import ValidationError
from lumneo.memory.evaluator.state_machine import Evaluator


def create_test_memory():
    """辅助：创建一个测试用 MemoryObject"""
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


def test_forget_by_memory_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)

        try:
            memory = create_test_memory()
            repo.create(memory)

            directive = UserDirective(
                type="forget",
                target=memory.id,
                target_type="memory_id",
                raw_text="忘记这条记忆"
            )
            apply_user_directives([directive], repo)

            updated = repo.get_by_id(memory.id)
            assert updated is not None
            assert updated.status == "archived"
            assert updated.metadata.get("user_forgotten") is True
            assert "forgotten_at" in updated.metadata
            datetime.fromisoformat(updated.metadata["forgotten_at"])
        finally:
            repo.close()
            gc.collect()
            time.sleep(0.1)


def test_forget_non_existent_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)

        try:
            directive = UserDirective(
                type="forget",
                target="non_existent_id",
                target_type="memory_id",
                raw_text="忘记不存在的记忆"
            )
            apply_user_directives([directive], repo)
        finally:
            repo.close()
            gc.collect()
            time.sleep(0.1)


def test_forget_unsupported_target_type():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)

        try:
            directive = UserDirective(
                type="forget",
                target="某个语义描述",
                target_type="semantic_match",
                raw_text="忘记语义匹配的记忆"
            )
            with pytest.raises(NotImplementedError):
                apply_user_directives([directive], repo)
        finally:
            repo.close()
            gc.collect()
            time.sleep(0.1)


def test_forget_missing_target():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        with SQLiteMemoryRepository(db_path, data_root) as repo:
            try:
                directive = UserDirective(
                    type="forget",
                    target=None,
                    target_type="memory_id",
                    raw_text="忘记未指定目标的记忆"
                )
                with pytest.raises(ValidationError):
                    apply_user_directives([directive], repo)
            finally:
                repo.close()
                gc.collect()
                time.sleep(0.1)


def test_correct_instruction():
    """测试 correct 指令：旧记忆变为 superseded，新记忆 active，双向版本链，无环"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)

        try:
            # 1. 创建旧记忆并持久化
            old_memory = create_test_memory()
            repo.create(old_memory)

            # 2. 构造纠正候选（新记忆）
            new_evidence = [
                Evidence(
                    type="explicit_statement",
                    weight=1.0,
                    source=Source(
                        tenant_id="t1",
                        agent_id="a1",
                        chat_id="c1",
                        message_id="m2",
                        timestamp=utc_now()
                    ),
                    observation="用户现在更喜欢拿铁",
                    origin_actor="user",
                    created_at=utc_now(),
                    provenance_key="m2"
                )
            ]
            new_source = Source(
                tenant_id="t1",
                agent_id="a1",
                chat_id="c1",
                message_id="m2",
                timestamp=utc_now()
            )

            new_candidate = MemoryCandidate(
                raw_content="用户现在更喜欢拿铁",
                suggested_layer="semantic",
                suggested_type="preference",
                subject="用户",
                predicate="preference",
                object="拿铁",
                evidence=new_evidence,
                source=new_source,
                origin_actor="user",
                confidence_hint=0.9,
                capture_id="capture_123",
                correction_target=old_memory.id,   # 关键：指向旧记忆
                metadata={}
            )

            # 3. 构建 correct 指令
            directive = UserDirective(
                type="correct",
                target=old_memory.id,
                target_type="memory_id",
                raw_text="纠正为拿铁"
            )

            # 4. 创建 Evaluator，传入 repository
            evaluator = Evaluator(confidence_cap=1.0, repository=repo)
            result = evaluator.evaluate(new_candidate, directives=[directive])

            # 5. 验证新记忆
            assert result.status == "active"
            assert result.supersedes == old_memory.id
            assert result.metadata.get("corrected") is True
            assert result.object == "拿铁"

            # 6. 验证旧记忆
            updated_old = repo.get_by_id(old_memory.id)
            assert updated_old is not None
            assert updated_old.status == "superseded"
            assert updated_old.superseded_by == result.id

            # 7. 验证版本链无环（直接调用 _check_cycle，旧记忆无祖先，应返回 False）
            assert not evaluator._check_cycle(updated_old, result.id)

        finally:
            repo.close()
            gc.collect()
            time.sleep(0.1)   # Windows 文件锁释放

def test_forget_audit_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)
        try:
            memory = create_test_memory()
            repo.create(memory)

            directive = UserDirective(
                type="forget",
                target=memory.id,
                target_type="memory_id",
                raw_text="忘记这条记忆"
            )
            apply_user_directives([directive], repo)

            # 检查审计日志文件是否存在
            month_dir = data_root / "governance" / "auto_actions" / utc_now().strftime("%Y-%m")
            audit_files = list(month_dir.glob("audit_*.jsonl"))
            assert len(audit_files) >= 1

            # 检查 SQLite 中是否有记录
            cursor = repo.conn.execute("SELECT * FROM audit_logs WHERE memory_id = ?", (memory.id,))
            row = cursor.fetchone()
            assert row is not None
            assert row['action'] == "forget"
        finally:
            repo.close()