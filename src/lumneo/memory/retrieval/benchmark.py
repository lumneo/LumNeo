"""Retrieval benchmark helpers for the Phase 1A T8.2 ablation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from lumneo.memory.model import MemoryNeed, MemoryObject, MemoryStatus
from lumneo.memory.storage.repository import MemoryRepository


@dataclass(frozen=True)
class RankingMetrics:
    precision_at_3: float
    recall_at_5: float
    mrr: float


def calculate_ranking_metrics(
    ranked_ids: Sequence[str],
    relevant_ids: Iterable[str],
) -> RankingMetrics:
    """Calculate per-query P@3, R@5, and reciprocal rank."""
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must contain at least one id")

    precision_at_3 = len(relevant.intersection(ranked_ids[:3])) / 3.0
    recall_at_5 = len(relevant.intersection(ranked_ids[:5])) / len(relevant)

    reciprocal_rank = 0.0
    for rank, memory_id in enumerate(ranked_ids, start=1):
        if memory_id in relevant:
            reciprocal_rank = 1.0 / rank
            break

    return RankingMetrics(
        precision_at_3=precision_at_3,
        recall_at_5=recall_at_5,
        mrr=reciprocal_rank,
    )


def macro_average(metrics: Sequence[RankingMetrics]) -> RankingMetrics:
    """Macro-average query metrics so every query has equal weight."""
    if not metrics:
        raise ValueError("metrics must not be empty")

    count = len(metrics)
    return RankingMetrics(
        precision_at_3=sum(item.precision_at_3 for item in metrics) / count,
        recall_at_5=sum(item.recall_at_5 for item in metrics) / count,
        mrr=sum(item.mrr for item in metrics) / count,
    )


def retrieve_bm25_only(
    need: MemoryNeed,
    repository: MemoryRepository,
) -> list[MemoryObject]:
    """Rank the allowed corpus using BM25 relevance and no memory features.

    Status and scope remain hard safety filters. Layer/type restrictions are
    removed because they are Memory OS intent signals, not BM25 signals.
    Importance, confidence, decay, and semantic boosts never participate,
    including as tie-breakers.
    """
    statuses: list[MemoryStatus] = (
        ["active", "superseded", "stale", "archived"]
        if need.include_historical
        else ["active"]
    )
    baseline_need = need.model_copy(update={"layers": [], "types": []})
    candidates = repository.search_candidates(
        need=baseline_need,
        statuses=statuses,
        limit=need.max_results * 5,
    )
    if not candidates:
        return []

    memory_ids = [memory.id for memory in candidates]
    query = " ".join(need.keywords) if need.keywords else ""
    relevance = repository.get_relevance_scores(memory_ids, query)

    ranked = sorted(
        candidates,
        key=lambda memory: (-relevance.get(memory.id, 0.0), memory.id),
    )
    return ranked[: need.max_results]
