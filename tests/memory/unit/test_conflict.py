# tests/memory/unit/test_conflict.py
import gc
import time
import tempfile
from pathlib import Path
from datetime import datetime

import pytest
from rapidfuzz import fuzz

from lumneo.memory.model import MemoryObject, Evidence, Source, MemoryCandidate
from lumneo.memory.model.user_directive import UserDirective
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.common.exceptions import PersistenceError


# ---------- 辅助函数 ----------
def create_test_memory(
    subject="用户",
    predicate="preference",
    object="美式咖啡",
    status="active",
    condition=None,
    mem_type="preference",
    layer="semantic"
) -> MemoryObject:
    return MemoryObject(
        id=generate_memory_id(),
        schema_version="2.1.2",
        layer=layer,
        type=mem_type,
        subject=subject,
        predicate=predicate,
        object=object,
        condition=condition,
        content=f"{subject} {predicate} {object}",
        confidence=0.87,
        importance=4,
        status=status,
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


def create_test_candidate(
    subject="用户",
    predicate="preference",
    object="拿铁",
    correction_target=None,
    condition=None,
    mem_type="preference",
    layer="semantic"
) -> MemoryCandidate:
    evidence = [
        Evidence(
            type="explicit_statement",
            weight=1.0,
            source=Source(tenant_id="t1", agent_id="a1", chat_id="c1", message_id="m2", timestamp=utc_now()),
            observation=f"候选：{subject} {predicate} {object}",
            origin_actor="user",
            created_at=utc_now(),
            provenance_key="m2"
        )
    ]
    source = Source(tenant_id="t1", agent_id="a1", chat_id="c1", message_id="m2", timestamp=utc_now())
    return MemoryCandidate(
        raw_content=f"{subject} {predicate} {object}",
        suggested_layer=layer,
        suggested_type=mem_type,
        subject=subject,
        predicate=predicate,
        object=object,
        condition=condition,
        evidence=evidence,
        source=source,
        origin_actor="user",
        confidence_hint=0.9,
        capture_id="capture_123",
        correction_target=correction_target,
        metadata={}
    )


# ---------- Fixture ----------
@pytest.fixture
def repo_and_evaluator():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir) / "data" / "memory"
        db_path = data_root / "index" / "fts5.db"
        repo = SQLiteMemoryRepository(db_path, data_root)
        evaluator = Evaluator(confidence_cap=1.0, repository=repo)
        yield repo, evaluator
        repo.close()
        gc.collect()
        time.sleep(0.1)


# ---------- 测试用例 ----------
def test_conflict_condition_mismatch(repo_and_evaluator):
    """Condition 互斥 → 新记忆 needs_review"""
    repo, evaluator = repo_and_evaluator

    # 已有记忆：condition = {"place": "客厅"}
    old = create_test_memory(
        subject="用户",
        predicate="preference",
        object="看电视",
        condition={"key": "place", "value": "客厅"}
    )
    repo.create(old)

    # 新候选：condition = {"place": "卧室"}，其他相同
    cand = create_test_candidate(
        subject="用户",
        predicate="preference",
        object="看电视",
        condition={"key": "place", "value": "卧室"}
    )

    # 执行评估（没有 correct 指令）
    result = evaluator.evaluate(cand, directives=None)
    # 注意：evaluate 目前未实现全局冲突，我们需要调用 evaluate_batch，因为那里才有全局检测。
    # 我们用 evaluate_batch 传入单个候选
    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "needs_review"
    assert obj.metadata.get("conflict_reason") == "condition_conflict"
    assert obj.metadata.get("conflict_with") == old.id


def test_conflict_generic_statement_similar(repo_and_evaluator):
    """generic_statement 相似 ≥0.65 → needs_review"""
    repo, evaluator = repo_and_evaluator

    # 已有记忆：predicate="generic_statement", object="喜欢咖啡"
    old = create_test_memory(
        subject="用户",
        predicate="generic_statement",
        object="喜欢咖啡",
        mem_type="fact",
        layer="semantic"
    )
    repo.create(old)

    # 新候选：predicate="generic_statement", object="喜欢咖啡哦"（相似度约 0.8）
    cand = create_test_candidate(
        subject="用户",
        predicate="generic_statement",
        object="喜欢咖啡哦",
        mem_type="fact",
        layer="semantic"
    )
    # 计算相似度确认 ≥0.65
    sim = fuzz.ratio("喜欢咖啡", "喜欢咖啡哦") / 100.0
    assert sim >= 0.65

    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "needs_review"
    assert obj.metadata.get("conflict_reason") == "generic_statement_conflict"


def test_conflict_preference_stale_old(repo_and_evaluator):
    """preference 类型 → 旧记忆标记 stale，新记忆 active"""
    repo, evaluator = repo_and_evaluator

    # 已有记忆：type="preference", object="美式咖啡"
    old = create_test_memory(
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        mem_type="preference"
    )
    repo.create(old)

    # 新候选：type="preference", object="拿铁"（相似度低于 0.75）
    cand = create_test_candidate(
        subject="用户",
        predicate="preference",
        object="拿铁",
        mem_type="preference"
    )

    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "active"
    assert obj.supersedes is None  # 不建立版本链

    # 检查旧记忆是否变为 stale
    updated_old = repo.get_by_id(old.id)
    assert updated_old.status == "stale"


def test_conflict_supersede_high_similarity(repo_and_evaluator):
    repo, evaluator = repo_and_evaluator
    old = create_test_memory(
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        mem_type="fact"   # 改为 fact
    )
    repo.create(old)

    cand = create_test_candidate(
        subject="用户",
        predicate="preference",
        object="美式咖啡加糖",
        mem_type="fact"   # 改为 fact
    )
    sim = fuzz.ratio("美式咖啡", "美式咖啡加糖") / 100.0
    assert sim >= 0.75

    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "active"
    assert obj.supersedes == old.id
    old_after = repo.get_by_id(old.id)
    assert old_after.status == "superseded"
    assert old_after.superseded_by == obj.id


def test_conflict_independent_low_similarity(repo_and_evaluator):
    """相似度 ≤0.40 → 独立写入，旧记忆保持 active"""
    repo, evaluator = repo_and_evaluator

    old = create_test_memory(
        subject="用户",
        predicate="preference",
        object="咖啡"
    )
    repo.create(old)

    # 新候选：object="茶"（相似度低）
    cand = create_test_candidate(
        subject="用户",
        predicate="preference",
        object="茶"
    )
    sim = fuzz.ratio("咖啡", "茶") / 100.0
    assert sim <= 0.40

    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "active"
    assert obj.supersedes is None

    # 旧记忆状态不变
    old_after = repo.get_by_id(old.id)
    assert old_after.status == "active"


def test_conflict_independent_low_similarity(repo_and_evaluator):
    repo, evaluator = repo_and_evaluator
    old = create_test_memory(
        subject="用户",
        predicate="preference",
        object="咖啡",
        mem_type="preference"
    )
    repo.create(old)

    cand = create_test_candidate(
        subject="用户",
        predicate="preference",
        object="茶",
        mem_type="preference"
    )
    sim = fuzz.ratio("咖啡", "茶") / 100.0
    assert sim <= 0.40

    results = evaluator.evaluate_batch([cand], directives=None)
    assert len(results) == 1
    obj = results[0]
    assert obj.status == "active"
    assert obj.supersedes is None

    old_after = repo.get_by_id(old.id)
    assert old_after.status == "stale"   # 改为 stale

def test_batch_conflict_same_subject_predicate_different_object(repo_and_evaluator):
    """同 capture_id 内同 subject+predicate 但 object 不同 → 后置候选 needs_review"""
    repo, evaluator = repo_and_evaluator

    cand1 = create_test_candidate(subject="用户", predicate="preference", object="美式咖啡")
    cand2 = create_test_candidate(subject="用户", predicate="preference", object="拿铁")
    # 确保两个候选的 capture_id 相同（默认都是 "capture_123"）
    cand2.capture_id = cand1.capture_id

    # 评估
    results = evaluator.evaluate_batch([cand1, cand2], directives=None)
    assert len(results) == 2

    # cand1 应该 active（第一个）
    obj1 = next(o for o in results if o.object == "美式咖啡")
    assert obj1.status == "active"
    # cand2 应该 needs_review（因为 object 不同，相似度 < 0.75）
    obj2 = next(o for o in results if o.object == "拿铁")
    assert obj2.status == "needs_review"
    assert obj2.metadata.get("batch_conflict") is True