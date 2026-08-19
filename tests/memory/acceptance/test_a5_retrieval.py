"""
A.5 Retrieval 验收测试（15 cases, Top-3 Hit ≥ 80%）
同时计算 BM25 baseline 对比
"""
import pytest
from typing import List, Dict, Any
from lumneo.memory.capture import capture
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.retrieval import retrieve
from lumneo.memory.retrieval.ranking import compute_scores, compute_bm25_relevance
from lumneo.memory.model import (
    ConversationTurn, MemoryNeed, MemoryObject, Evidence, Source,
    MemoryLayer, MemoryType
)
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id
from lumneo.memory.storage.repository import SQLiteMemoryRepository


# ---------- 准备测试记忆（手动构造，确保 active） ----------
def create_test_memories(repo):
    """手动构造 MemoryObject 并写入，返回 id 到内容的映射"""
    test_data: List[tuple[str, MemoryLayer, MemoryType]] = [
        ("我喜欢咖啡", "semantic", "preference"),
        ("我喜欢茶", "semantic", "preference"),
        ("我是软件工程师", "identity", "fact"),
        ("我是设计师", "identity", "fact"),
        ("我会Python编程", "procedural", "skill"),
        ("我会数据分析", "procedural", "skill"),
        ("我去过北京", "episodic", "event"),
        ("我参加昨天的会议", "episodic", "event"),
        ("我计划去上海", "episodic", "event"),
        ("我选择远程办公", "semantic", "decision"),
        ("我偏好极简风格", "semantic", "style"),
        ("小明是我的朋友", "semantic", "relationship"),
    ]

    now = utc_now()
    for content, layer, mem_type in test_data:
        source = Source(
            tenant_id=None,
            agent_id=None,
            chat_id="test_chat",
            message_id=f"msg_{content[:5]}",
            timestamp=now,
        )
        evidence = Evidence(
            type="explicit_statement",
            weight=1.0,
            source=source,
            observation=content,
            origin_actor="user",
            created_at=now,
            provenance_key=None,
        )
        mem = MemoryObject(
            id=generate_memory_id(),
            schema_version="2.1.2",
            layer=layer,
            type=mem_type,
            subject="用户",
            predicate="preference" if mem_type == "preference" else "fact",
            object=content,
            condition=None,
            content=content,
            confidence=0.9,
            confidence_detail=None,
            importance=3,
            status="active",
            evidence=[evidence],
            source=source,
            origin="explicit_user",
            supersedes=None,
            superseded_by=None,
            last_accessed=None,
            access_count=0,
            tags=[],
            privacy=None,
            created_at=now,
            updated_at=now,
            metadata={"standardization_issue": False, "user_forgotten": False},
        )
        repo.create(mem)

    all_mems = repo.query_active(MemoryNeed(keywords=[], layers=[], types=[]), scope_filter=None)
    mem_map = {m.id: m.content for m in all_mems}
    if len(mem_map) < 5:
        raise RuntimeError(f"活动记忆不足，只有 {len(mem_map)} 条")
    return list(mem_map.keys()), mem_map


# ---------- 查询用例定义 ----------
RETRIEVAL_CASES = [
    {"id": "R001", "query": "我喜欢什么", "expected": ["咖啡", "茶"], "desc": "偏好查询"},
    {"id": "R002", "query": "我的职业", "expected": ["软件工程师", "设计师"], "desc": "身份查询"},
    {"id": "R003", "query": "我会什么技能", "expected": ["Python编程", "数据分析"], "desc": "技能查询"},
    {"id": "R004", "query": "我去过哪里", "expected": ["北京"], "desc": "事件查询"},
    {"id": "R005", "query": "我参加过什么会议", "expected": ["昨天的会议"], "desc": "事件查询"},
    {"id": "R006", "query": "我计划去哪里", "expected": ["上海"], "desc": "事件查询"},
    {"id": "R007", "query": "我选择什么工作方式", "expected": ["远程办公"], "desc": "决策查询"},
    {"id": "R008", "query": "我的风格", "expected": ["极简风格"], "desc": "风格查询"},
    {"id": "R009", "query": "我的朋友", "expected": ["小明"], "desc": "关系查询"},
    {"id": "R010", "query": "咖啡和茶", "expected": ["咖啡", "茶"], "desc": "多偏好查询"},
    {"id": "R011", "query": "Python 数据分析", "expected": ["Python编程", "数据分析"], "desc": "技能组合"},
    {"id": "R012", "query": "北京上海", "expected": ["北京", "上海"], "desc": "地点查询"},
    {"id": "R013", "query": "工程师设计师", "expected": ["软件工程师", "设计师"], "desc": "职业查询"},
    {"id": "R014", "query": "远程办公", "expected": ["远程办公"], "desc": "决策查询"},
    {"id": "R015", "query": "咖啡", "expected": ["咖啡"], "desc": "简单偏好"},
]


# ---------- 辅助函数 ----------
def compute_metrics(results: List[MemoryObject], expected_ids: List[str]) -> Dict[str, float]:
    top3_ids = [m.id for m in results[:3]]
    top5_ids = [m.id for m in results[:5]]

    hit = any(eid in top3_ids for eid in expected_ids)
    relevant_in_top3 = sum(1 for eid in expected_ids if eid in top3_ids)
    precision = relevant_in_top3 / len(top3_ids) if top3_ids else 0.0
    relevant_in_top5 = sum(1 for eid in expected_ids if eid in top5_ids)
    recall = relevant_in_top5 / len(expected_ids) if expected_ids else 0.0

    mrr = 0.0
    for rank, mid in enumerate(results[:5], start=1):
        if mid in expected_ids:
            mrr = 1.0 / rank
            break

    return {"hit": hit, "precision": precision, "recall": recall, "mrr": mrr}


def bm25_only_retrieve(repo: SQLiteMemoryRepository, need: MemoryNeed, query_str: str) -> List[MemoryObject]:
    all_mems = repo.query_active(
        MemoryNeed(keywords=[], layers=need.layers, types=need.types, scope_filter=need.scope_filter),
        scope_filter=need.scope_filter
    )
    if not all_mems:
        return []

    memories_map = {m.id: (m.confidence, m.importance, m.last_accessed, m.created_at) for m in all_mems}
    memory_ids = list(memories_map.keys())
    conn = repo.conn
    relevance_map = compute_bm25_relevance(conn, memory_ids, query_str)

    sorted_ids = sorted(memory_ids, key=lambda mid: relevance_map.get(mid, 0.0), reverse=True)
    if need.max_results:
        sorted_ids = sorted_ids[:need.max_results]

    result = [repo.get_by_id(mid) for mid in sorted_ids if mid in relevance_map]
    return [m for m in result if m is not None]


# ---------- 测试 ----------
@pytest.fixture(scope="function")
def repo_and_memories(tmp_path):
    db_path = tmp_path / "test.db"
    data_root = tmp_path / "memory"
    repo = SQLiteMemoryRepository(db_path, data_root)
    ids, mem_map = create_test_memories(repo)
    yield repo, ids, mem_map
    repo.close()


def test_a5_retrieval_acceptance(repo_and_memories):
    repo, all_ids, mem_map = repo_and_memories

    print("\n=== All active memories ===")
    # 修正：items() 返回 (id, content)，所以循环变量顺序应为 mid, content
    for mid, content in mem_map.items():
        print(f"  {content}")
    print("===========================\n")

    # 构建期望 ID 列表
    expanded_cases = []
    for case in RETRIEVAL_CASES:
        expected_ids = []
        missing = []
        for keyword in case["expected"]:
            found = False
            # 修正：正确的循环变量顺序
            for mid, content in mem_map.items():
                if keyword in content:
                    expected_ids.append(mid)
                    found = True
                    break
            if not found:
                missing.append(keyword)
        if missing:
            print(f"警告: Case {case['id']} 未找到包含 {missing} 的记忆，跳过")
        else:
            expanded_cases.append({**case, "expected_ids": expected_ids})

    if len(expanded_cases) < 12:
        pytest.fail(f"有效用例只有 {len(expanded_cases)}，少于 12，无法进行有意义的检索测试")

    all_metrics = []
    bm25_metrics = []
    query_logs = []

    for case in expanded_cases:
        need = MemoryNeed(
            keywords=case["query"].split(),
            layers=[],
            types=[],
            max_results=5,
            scope_filter=None,
        )
        results_os = retrieve(need, repository=repo, alpha=0.65)
        metrics_os = compute_metrics(results_os, case["expected_ids"])

        results_bm25 = bm25_only_retrieve(repo, need, case["query"])
        metrics_bm25 = compute_metrics(results_bm25, case["expected_ids"])

        all_metrics.append(metrics_os)
        bm25_metrics.append(metrics_bm25)

        # 修正：正确的变量顺序
        top3_os = [mem_map.get(m.id, "未知") for m in results_os[:3]]
        top3_bm25 = [mem_map.get(m.id, "未知") for m in results_bm25[:3]]
        expected_contents = [mem_map.get(eid, "未知") for eid in case["expected_ids"]]

        query_logs.append({
            "id": case["id"],
            "query": case["query"],
            "expected": expected_contents,
            "os_top3": top3_os,
            "bm25_top3": top3_bm25,
            "os_hit": metrics_os["hit"],
            "bm25_hit": metrics_bm25["hit"],
        })

    total = len(expanded_cases)
    if total == 0:
        pytest.fail("没有任何有效用例，无法进行检索测试")

    hit_count_os = sum(1 for m in all_metrics if m["hit"])
    hit_count_bm25 = sum(1 for m in bm25_metrics if m["hit"])

    avg_precision_os = sum(m["precision"] for m in all_metrics) / total
    avg_precision_bm25 = sum(m["precision"] for m in bm25_metrics) / total
    avg_recall_os = sum(m["recall"] for m in all_metrics) / total
    avg_recall_bm25 = sum(m["recall"] for m in bm25_metrics) / total
    avg_mrr_os = sum(m["mrr"] for m in all_metrics) / total
    avg_mrr_bm25 = sum(m["mrr"] for m in bm25_metrics) / total

    hit_rate_os = hit_count_os / total
    hit_rate_bm25 = hit_count_bm25 / total

    print("\n" + "=" * 70)
    print("A.5 Retrieval 验收报告")
    print("=" * 70)
    print(f"总用例数: {total}")
    print("\n--- 指标对比 ---")
    print(f"指标                Memory OS      BM25-only     提升")
    print(f"Top-3 Hit Rate      {hit_rate_os:.2%}          {hit_rate_bm25:.2%}          {(hit_rate_os - hit_rate_bm25):.2%}")
    print(f"Precision@3         {avg_precision_os:.3f}          {avg_precision_bm25:.3f}          {(avg_precision_os - avg_precision_bm25):.3f}")
    print(f"Recall@5            {avg_recall_os:.3f}          {avg_recall_bm25:.3f}          {(avg_recall_os - avg_recall_bm25):.3f}")
    print(f"MRR                 {avg_mrr_os:.3f}          {avg_mrr_bm25:.3f}          {(avg_mrr_os - avg_mrr_bm25):.3f}")

    print("\n--- 详细查询结果 ---")
    for log in query_logs:
        status = "✅" if log["os_hit"] else "❌"
        print(f"{log['id']} {status} 查询: '{log['query']}'")
        print(f"    期望: {log['expected']}")
        print(f"    OS Top-3: {log['os_top3']}")
        print(f"    BM25 Top-3: {log['bm25_top3']}")
    print("=" * 70)

    assert hit_rate_os >= 0.80, f"Top-3 Hit Rate {hit_rate_os:.2%} < 80%"

    return {
        "hit_rate": hit_rate_os,
        "precision": avg_precision_os,
        "recall": avg_recall_os,
        "mrr": avg_mrr_os,
        "bm25_hit_rate": hit_rate_bm25,
        "bm25_precision": avg_precision_bm25,
        "bm25_recall": avg_recall_bm25,
        "bm25_mrr": avg_mrr_bm25,
    }