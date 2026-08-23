from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumneo.memory.model import MemoryNeed
from lumneo.memory.retrieval.benchmark import (
    RankingMetrics,
    calculate_ranking_metrics,
    macro_average,
    retrieve_bm25_only,
)


def test_calculate_ranking_metrics() -> None:
    metrics = calculate_ranking_metrics(
        ["irrelevant-1", "relevant-1", "irrelevant-2", "relevant-2"],
        ["relevant-1", "relevant-2"],
    )

    assert metrics.precision_at_3 == pytest.approx(1.0 / 3.0)
    assert metrics.recall_at_5 == 1.0
    assert metrics.mrr == 0.5


def test_calculate_ranking_metrics_for_miss() -> None:
    metrics = calculate_ranking_metrics(["irrelevant"], ["relevant"])

    assert metrics == RankingMetrics(0.0, 0.0, 0.0)


def test_calculate_ranking_metrics_rejects_empty_judgment() -> None:
    with pytest.raises(ValueError, match="relevant_ids"):
        calculate_ranking_metrics(["memory"], [])


def test_macro_average() -> None:
    result = macro_average(
        [
            RankingMetrics(1.0 / 3.0, 1.0, 1.0),
            RankingMetrics(0.0, 0.5, 0.25),
        ]
    )

    assert result.precision_at_3 == pytest.approx(1.0 / 6.0)
    assert result.recall_at_5 == 0.75
    assert result.mrr == 0.625


def test_macro_average_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        macro_average([])


def test_bm25_baseline_removes_memory_os_intent_filters() -> None:
    repository = Mock()
    repository.search_candidates.return_value = []
    need = MemoryNeed(
        layers=["semantic"],
        types=["preference"],
        keywords=["coffee"],
        scope_filter={"user_id": "user-1"},
        max_results=4,
        include_historical=True,
    )

    assert retrieve_bm25_only(need, repository) == []

    baseline_need = repository.search_candidates.call_args.kwargs["need"]
    assert baseline_need.layers == []
    assert baseline_need.types == []
    assert baseline_need.keywords == ["coffee"]
    assert baseline_need.scope_filter == {"user_id": "user-1"}
    assert repository.search_candidates.call_args.kwargs["statuses"] == [
        "active",
        "superseded",
        "stale",
        "archived",
    ]
    assert repository.search_candidates.call_args.kwargs["limit"] == 20


def test_bm25_baseline_uses_only_relevance_then_id_for_ranking() -> None:
    low_quality = SimpleNamespace(
        id="mem_1_000000000001", importance=1, confidence=0.1
    )
    high_quality = SimpleNamespace(
        id="mem_2_000000000002", importance=5, confidence=1.0
    )
    repository = Mock()
    repository.search_candidates.return_value = [high_quality, low_quality]
    repository.get_relevance_scores.return_value = {
        low_quality.id: 0.5,
        high_quality.id: 0.5,
    }

    result = retrieve_bm25_only(
        MemoryNeed(keywords=["coffee"], max_results=2), repository
    )

    assert [memory.id for memory in result] == [low_quality.id, high_quality.id]
    repository.get_relevance_scores.assert_called_once_with(
        [high_quality.id, low_quality.id], "coffee"
    )
