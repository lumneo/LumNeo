from collections import Counter

import pytest

from lumneo.memory.benchmarking import (
    LAYER_DISTRIBUTION,
    MEASURED_QUERIES,
    QUERY_MIX,
    STATUS_DISTRIBUTION,
    TOTAL_MEMORIES,
    TYPE_DISTRIBUTION,
    build_dataset_specs,
    build_query_workload,
    latency_summary,
    nearest_rank_percentile,
)


def test_dataset_specs_match_contract_marginals_exactly() -> None:
    specs = build_dataset_specs()

    assert len(specs) == TOTAL_MEMORIES
    assert Counter(spec.layer for spec in specs) == LAYER_DISTRIBUTION
    assert Counter(spec.memory_type for spec in specs) == TYPE_DISTRIBUTION
    assert Counter(spec.status for spec in specs) == STATUS_DISTRIBUTION
    assert sum(spec.has_condition for spec in specs) == 2_000
    assert specs == build_dataset_specs()


def test_query_workload_matches_contract_mix_exactly() -> None:
    workload = build_query_workload(MEASURED_QUERIES)

    assert Counter(query.kind for query in workload) == {
        kind: int(ratio * MEASURED_QUERIES)
        for kind, ratio in QUERY_MIX.items()
    }
    assert workload == build_query_workload(MEASURED_QUERIES)


def test_query_workload_rejects_inexact_mix() -> None:
    with pytest.raises(ValueError, match="cannot represent"):
        build_query_workload(7)


def test_nearest_rank_latency_summary() -> None:
    samples = list(range(1, 101))

    assert nearest_rank_percentile(samples, 95) == 95
    assert latency_summary(samples) == {
        "p50_ms": 50,
        "p95_ms": 95,
        "p99_ms": 99,
        "mean_ms": 50.5,
        "std_ms": pytest.approx(28.86607004772212),
        "min_ms": 1,
        "max_ms": 100,
    }


def test_nearest_rank_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        nearest_rank_percentile([], 95)
    with pytest.raises(ValueError, match="percentile"):
        nearest_rank_percentile([1.0], 0)
