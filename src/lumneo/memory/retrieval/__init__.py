# src/lumneo/memory/retrieval/__init__.py
import logging
from typing import List
from lumneo.memory.model import MemoryNeed, MemoryObject, MemoryStatus
from lumneo.memory.storage.repository import MemoryRepository
from lumneo.memory.retrieval.ranking import compute_scores

logger = logging.getLogger(__name__)


def _condition_clauses(condition: dict | None) -> list[tuple[str, str]]:
    if not condition:
        return []
    if "key" in condition:
        return [(condition["key"], condition["value"])]
    return [
        (clause["key"], clause["value"])
        for clause in condition.get("clauses", [])
    ]


def _matches_condition(
    memory_condition: dict | None,
    condition_filter: dict,
) -> bool:
    stored = set(_condition_clauses(memory_condition))
    requested = _condition_clauses(condition_filter)
    return bool(stored) and all(clause in stored for clause in requested)


def retrieve(
    need: MemoryNeed,
    repository: MemoryRepository,
    alpha: float = 0.65,
    dynamic_alpha_threshold: float = 0.5,
    dynamic_alpha_fallback: float = 0.4,
) -> List[MemoryObject]:
    # 1. 确定需要检索的状态
    statuses: List[MemoryStatus] = (
        ["active", "superseded", "stale", "archived"]
        if need.include_historical
        else ["active"]
    )

    # 2. 候选召回（扩大候选池以便后续排序）
    candidates = repository.search_candidates(
        need=need,
        statuses=statuses,
        limit=100 if need.condition_filter is not None else need.max_results * 5,
    )

    if need.condition_filter is not None:
        candidates = [
            memory
            for memory in candidates
            if _matches_condition(memory.condition, need.condition_filter)
        ]

    if not candidates:
        return []

    # 3. 构建评分所需数据
    memories_map = {
        m.id: (m.confidence, m.importance, m.last_accessed, m.created_at)
        for m in candidates
    }

    memory_object_map = {m.id: m for m in candidates}
    
    memory_ids = list(memories_map.keys())

    # 4. 获取 BM25 相关性（由仓储提供）
    query_terms = list(need.keywords or [])
    if need.condition_filter is not None:
        query_terms.extend(
            value for _, value in _condition_clauses(need.condition_filter)
        )
    query_str = " ".join(dict.fromkeys(query_terms))
    relevance_map = repository.get_relevance_scores(memory_ids, query_str)


    # 5. 计算最终分数
    scores = compute_scores(
        memory_ids=memory_ids,
        relevance_map=relevance_map,
        memories_map=memories_map,
        memories_object_map=memory_object_map,
        need=need,
        alpha=alpha,
        dynamic_alpha_threshold=dynamic_alpha_threshold,
        dynamic_alpha_fallback=dynamic_alpha_fallback,
    )

    # 6. 排序并截断
    sorted_ids = sorted(memory_ids, key=lambda mid: scores.get(mid, 0.0), reverse=True)
    sorted_ids = sorted_ids[:need.max_results]

    result_map = {m.id: m for m in candidates}
    result = [result_map[mid] for mid in sorted_ids if mid in result_map]

    # 7. Repository 负责把访问统计放入自己的后台队列。
    # 调度失败不得影响检索主路径（ADR-006 §2 / Acceptance Protocol §7）。
    for mem in result:
        try:
            repository.record_access(mem.id)
        except Exception as e:
            logger.warning("Failed to schedule access update for %s: %s", mem.id, e)

    return result
