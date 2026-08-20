"""
A.5 Retrieval Acceptance Test

15 cases
Top-3 Hit Rate >= 80%

Memory OS Retrieval validation:
- intent aware retrieval
- semantic ranking
- historical retrieval
- condition retrieval
- correction retrieval
"""

import pytest
import warnings

from typing import List, Dict, Any

from lumneo.memory.capture import capture
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.model import ConversationTurn
from lumneo.memory.common.time import utc_now
from lumneo.memory.storage.repository import SQLiteMemoryRepository
from lumneo.memory.retrieval import retrieve
from lumneo.memory.retrieval.intent import analyze_intent


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="function")
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    data_root = tmp_path / "memory"
    repository = SQLiteMemoryRepository(db_path, data_root)
    yield repository
    repository.close()


@pytest.fixture(scope="function")
def evaluator(repo):
    return Evaluator(
        repository=repo,
        confidence_cap=1.0
    )


def create_turn(
    content: str,
    msg_id: str,
    chat_id: str = "chat1",
):
    return ConversationTurn(
        role="user",
        content=content,
        message_id=msg_id,
        chat_id=chat_id,
        timestamp=utc_now(),
    )


# ============================================================
# Seed Memories
# ============================================================
SEED_MEMORIES = [
    {
        "case_ids": ["R01", "R03", "R15"],
        "content": "我喜欢美式咖啡",
        "subject": "用户",
        "predicate": "preference",
        "object": "美式咖啡",
        "layer": "semantic",
        "type": "preference",
        "importance": 4,
    },
    {
        "case_ids": ["R02", "R04"],
        "content": "我在学习Python编程",
        "subject": "用户",
        "predicate": "has_skill",
        "object": "Python",
        "layer": "procedural",
        "type": "skill",
        "importance": 3,
    },
    {
        "case_ids": ["R05", "R06"],
        "content": "我是软件工程师",
        "subject": "用户",
        "predicate": "fact",
        "object": "软件工程师",
        "layer": "identity",
        "type": "fact",
        "importance": 5,
    },
    {
        "case_ids": ["R07"],
        "content": "我以前喜欢拿铁",
        "subject": "用户",
        "predicate": "preference",
        "object": "拿铁",
        "layer": "semantic",
        "type": "preference",
        "importance": 3,
    },
    {
        "case_ids": ["R08"],
        "content": "去年我去了日本旅游",
        "subject": "用户",
        "predicate": "event",
        "object": "去了日本",
        "layer": "episodic",
        "type": "event",
        "importance": 2,
    },
    {
        "case_ids": ["R09"],
        "content": "我在客厅看电视",
        "subject": "用户",
        "predicate": "fact",
        "object": "看电视",
        "layer": "semantic",
        "type": "fact",
        "condition": {
            "key": "place",
            "value": "客厅"
        },
        "importance": 2,
    },
    {
        "case_ids": ["R10"],
        "content": "周末我常去公园",
        "subject": "用户",
        "predicate": "preference",
        "object": "去公园",
        "layer": "semantic",
        "type": "preference",
        "condition": {
            "key": "time",
            "value": "周末"
        },
        "importance": 3,
    },
    {
        "case_ids": ["R11"],
        "content": "我喜欢喝茶",
        "subject": "用户",
        "predicate": "preference",
        "object": "茶",
        "layer": "semantic",
        "type": "preference",
        "importance": 4,
    },
    {
        "case_ids": ["R12"],
        "content": "我喜欢安静的咖啡馆",
        "subject": "用户",
        "predicate": "preference",
        "object": "安静的咖啡馆",
        "layer": "semantic",
        "type": "preference",
        "importance": 4,
    },
    {
        "case_ids": ["R13"],
        "content": "我喝过咖啡和茶",
        "subject": "用户",
        "predicate": "generic_statement",
        "object": "喝过咖啡和茶",
        "layer": "semantic",
        "type": "fact",
        "importance": 2,
    },
    {
        "case_ids": ["R14"],
        "content": "我会用Excel做报表",
        "subject": "用户",
        "predicate": "has_skill",
        "object": "Excel报表",
        "layer": "procedural",
        "type": "skill",
        "importance": 3,
    },
    # extra memories
    {
        "case_ids": [],
        "content": "我住在中国",
        "subject": "用户",
        "predicate": "fact",
        "object": "中国",
        "layer": "semantic",
        "type": "fact",
        "importance": 3,
    },
    {
        "case_ids": [],
        "content": "我喜欢跑步",
        "subject": "用户",
        "predicate": "preference",
        "object": "跑步",
        "layer": "semantic",
        "type": "preference",
        "importance": 3,
    },
    {
        "case_ids": [],
        "content": "我养了一只猫",
        "subject": "用户",
        "predicate": "fact",
        "object": "猫",
        "layer": "semantic",
        "type": "fact",
        "importance": 2,
    },
    {
        "case_ids": [],
        "content": "我生日在六月",
        "subject": "用户",
        "predicate": "fact",
        "object": "六月",
        "layer": "identity",
        "type": "fact",
        "importance": 1,
    },
]


# ============================================================
# Seed fixture
# ============================================================
@pytest.fixture(scope="function")
def seeded_repo_and_memories(
    repo,
    evaluator,
):
    memory_map = {}

    for idx, seed in enumerate(SEED_MEMORIES):
        turn = create_turn(
            seed["content"],
            f"msg_seed_{idx}",
            f"chat_seed_{idx}",
        )

        candidates = capture([turn])
        assert candidates

        for c in candidates:
            c.subject = seed.get("subject", "用户")
            c.predicate = seed.get("predicate", "fact")
            c.object = seed.get("object", seed["content"])
            c.suggested_layer = seed.get("layer", "semantic")
            c.suggested_type = seed.get("type", "fact")

            if "condition" in seed:
                c.condition = seed["condition"]

        memories = evaluator.evaluate_batch(candidates)
        assert len(memories) == 1

        mem = memories[0]
        mem.importance = seed.get("importance", 3)
        repo.update_with_version(mem)

        # 关键修复：按 case_ids 建立映射
        for case_id in seed["case_ids"]:
            memory_map[case_id] = mem

    # =====================================================
    # R07 superseded
    # =====================================================
    r07_mem = memory_map["R07"]

    turn = create_turn(
        "我不喜欢拿铁，喜欢红茶",
        "msg_correct_r07",
        "chat_correct",
    )

    candidates = capture([turn])
    cand = candidates[0]
    cand.correction_target = r07_mem.id
    cand.subject = "用户"
    cand.predicate = "preference"
    cand.object = "红茶"

    from lumneo.memory.governance.directives import UserDirective

    directive = UserDirective(
        type="correct",
        target=r07_mem.id,
        target_type="memory_id",
        raw_text="纠正为红茶",
        created_at=utc_now(),
    )

    evaluator.evaluate_batch(
        [cand],
        directives=[directive]
    )

    # =====================================================
    # R08 archived
    # =====================================================
    r08_mem = memory_map["R08"]

    from lumneo.memory.governance.directives import (
        apply_user_directives,
        UserDirective,
    )

    forget = UserDirective(
        type="forget",
        target=r08_mem.id,
        target_type="memory_id",
        raw_text="忘记日本旅游",
        created_at=utc_now(),
    )

    apply_user_directives(
        [forget],
        repository=repo,
    )

    return repo, memory_map

# ============================================================
# Retrieval Cases
# ============================================================


RETRIEVAL_CASES = [

    {
        "id":"R01",
        "query":"美式咖啡",
        "expected_ids":["R01"],
    },


    {
        "id":"R02",
        "query":"Python 编程",
        "expected_ids":["R02"],
    },


    {
        "id":"R03",
        "query":"用户喜欢什么咖啡",
        "expected_ids":["R01"],
    },


    {
        "id":"R04",
        "query":"喜欢的编程语言",
        "expected_ids":["R02"],
    },


    {
        "id":"R05",
        "query":"用户是谁",
        "expected_ids":["R05"],
    },


    {
        "id":"R06",
        "query":"我的名字",
        "expected_ids":["R05"],
    },


    {
        "id":"R07",
        "query":"之前喜欢什么",
        "expected_ids":["R07"],
        "include_historical":True,
    },


    {
        "id":"R08",
        "query":"过去的旅游经历",
        "expected_ids":["R08"],
        "include_historical":True,
    },


    {
        "id":"R09",
        "query":"在客厅做什么",
        "expected_ids":["R09"],
    },


    {
        "id":"R10",
        "query":"周末常去哪",
        "expected_ids":["R10"],
    },


    {
        "id":"R11",
        "query":"纠正后的偏好",
        "expected_ids":["R11"],
    },


    {
        "id":"R12",
        "query":"安静 咖啡馆",
        "expected_ids":["R12"],
    },


    {
        "id":"R13",
        "query":"喝茶还是咖啡",
        "expected_ids":["R13"],
    },


    {
        "id":"R14",
        "query":"会什么",
        "expected_ids":["R14"],
    },


    {
        "id":"R15",
        # 混合意图必须同时包含 identity 与 preference；加入“咖啡”以消除
        # 多条同 importance/confidence 偏好之间无法由契约评分判定的并列。
        "query":"我是什么人，是不是软件工程师，喜欢什么咖啡",
        "expected_ids":[
            "R05",
            "R01"
        ],
    },

]

@pytest.mark.parametrize(
    "case",
    RETRIEVAL_CASES,
    ids=lambda c:c["id"]
)
def test_a5_retrieval(
    case,
    seeded_repo_and_memories,
):

    repo, memory_map = seeded_repo_and_memories


    need = analyze_intent(
        case["query"]
    )


    if case.get(
        "include_historical"
    ):

        need.include_historical = True



    results = retrieve(
        need,
        repository=repo,
    )


    returned_ids = [
        m.id
        for m in results
    ]


    expected_ids = [
        memory_map[key].id
        for key in case["expected_ids"]
    ]



    top3 = returned_ids[:3]


    hits = [
        eid
        for eid in expected_ids
        if eid in top3
    ]


    print(
        f"\nCase {case['id']}:",
        "expected=",
        expected_ids,
        "top3=",
        top3,
        "hits=",
        len(hits),
    )


    assert len(hits) == len(expected_ids), \
        (
            f"{case['id']} failed: "
            f"expected {expected_ids}, "
            f"got {top3}"
        )
