"""Reproducible Phase 1A performance benchmark support."""

from __future__ import annotations

import math
import random
import statistics
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from lumneo.memory.model import Evidence, MemoryObject, Source
from lumneo.memory.retrieval import retrieve
from lumneo.memory.retrieval.intent import analyze_intent
from lumneo.memory.storage.repository import SQLiteMemoryRepository


TOTAL_MEMORIES = 10_000
WARMUP_QUERIES = 100
MEASURED_QUERIES = 1_000
P95_TARGET_MS = 200.0

LAYER_DISTRIBUTION = {
    "identity": 1_500,
    "episodic": 3_000,
    "semantic": 4_000,
    "procedural": 1_500,
}
TYPE_DISTRIBUTION = {
    "fact": 2_000,
    "preference": 1_500,
    "decision": 1_000,
    "relationship": 1_000,
    "event": 2_000,
    "value": 1_000,
    "style": 1_000,
    "skill": 500,
}
STATUS_DISTRIBUTION = {
    "active": 8_000,
    "superseded": 500,
    "archived": 1_000,
    "stale": 300,
    "needs_review": 200,
}
QUERY_MIX = {
    "simple_keyword": 0.4,
    "preference_query": 0.2,
    "identity_query": 0.1,
    "historical_query": 0.1,
    "with_condition": 0.2,
}


@dataclass(frozen=True)
class DatasetSpec:
    index: int
    layer: str
    memory_type: str
    status: str
    has_condition: bool


@dataclass(frozen=True)
class QuerySpec:
    kind: str
    query: str
    scope_filter: dict[str, str]
    condition_filter: dict[str, str] | None = None


def expand_distribution(distribution: Mapping[str, int]) -> list[str]:
    """Expand exact contract counts into a dimension vector."""
    return [value for value, count in distribution.items() for _ in range(count)]


def build_dataset_specs(seed: int = 21_212) -> list[DatasetSpec]:
    """Build a deterministic 10k corpus with exact independent marginals."""
    dimensions = []
    for offset, distribution in enumerate(
        (LAYER_DISTRIBUTION, TYPE_DISTRIBUTION, STATUS_DISTRIBUTION)
    ):
        values = expand_distribution(distribution)
        random.Random(seed + offset).shuffle(values)
        dimensions.append(values)

    layers, memory_types, statuses = dimensions
    condition_flags = [True] * 2_000 + [False] * 8_000
    random.Random(seed + 3).shuffle(condition_flags)
    return [
        DatasetSpec(
            index=index,
            layer=layers[index],
            memory_type=memory_types[index],
            status=statuses[index],
            has_condition=condition_flags[index],
        )
        for index in range(TOTAL_MEMORIES)
    ]


def _query_for(kind: str, index: int) -> str:
    topic = index % 20
    if kind == "simple_keyword":
        return f"simple_topic_{topic}"
    if kind == "preference_query":
        return f"喜欢的 preference_topic_{topic}"
    if kind == "identity_query":
        return f"我的职业 identity_topic_{topic}"
    if kind == "historical_query":
        return f"过去 historical_topic_{topic}"
    if kind == "with_condition":
        return f"在 room_{topic} 做什么 condition_topic_{topic}"
    raise ValueError(f"unknown query kind: {kind}")


def build_query_workload(count: int, seed: int = 8_300) -> list[QuerySpec]:
    """Build an exact query mix; count must support the frozen ratios."""
    raw_counts = {kind: ratio * count for kind, ratio in QUERY_MIX.items()}
    if any(not value.is_integer() for value in raw_counts.values()):
        raise ValueError("count cannot represent the query mix exactly")

    kinds = [
        kind
        for kind, raw_count in raw_counts.items()
        for _ in range(int(raw_count))
    ]
    random.Random(seed).shuffle(kinds)
    return [
        QuerySpec(
            kind=kind,
            query=_query_for(kind, index),
            scope_filter={
                "tenant_id": f"tenant-{index % 10}",
                "agent_id": f"agent-{index % 2}",
            },
            condition_filter=(
                {"key": "place", "value": f"room_{index % 20}"}
                if kind == "with_condition"
                else None
            ),
        )
        for index, kind in enumerate(kinds)
    ]


def nearest_rank_percentile(samples: Sequence[float], percentile: float) -> float:
    """Return the nearest-rank percentile used by the benchmark report."""
    if not samples:
        raise ValueError("samples must not be empty")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    ordered = sorted(samples)
    rank = math.ceil(percentile / 100.0 * len(ordered))
    return ordered[rank - 1]


def latency_summary(samples_ms: Sequence[float]) -> dict[str, float]:
    if not samples_ms:
        raise ValueError("samples_ms must not be empty")
    return {
        "p50_ms": nearest_rank_percentile(samples_ms, 50),
        "p95_ms": nearest_rank_percentile(samples_ms, 95),
        "p99_ms": nearest_rank_percentile(samples_ms, 99),
        "mean_ms": statistics.fmean(samples_ms),
        "std_ms": statistics.pstdev(samples_ms),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
    }


def _memory_from_spec(spec: DatasetSpec) -> MemoryObject:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=spec.index
    )
    memory_id = f"mem_{1767225600000000000 + spec.index}_{spec.index + 1:012x}"
    source = Source(
        tenant_id=f"tenant-{spec.index % 10}",
        agent_id=f"agent-{spec.index % 2}",
        chat_id="t8-3-benchmark",
        message_id=f"benchmark-message-{spec.index}",
        timestamp=created_at,
    )
    topic = spec.index % 20
    content = (
        f"benchmark memory {spec.index} simple_topic_{topic} "
        f"{spec.layer}_topic identity_topic_{topic} historical_topic_{topic} "
        f"{spec.memory_type}_topic_{topic}"
    )
    condition_topic = (spec.index // 5) % 20
    condition = (
        {"key": "place", "value": f"room_{condition_topic}"}
        if spec.has_condition
        else None
    )
    if condition is not None:
        content += f" condition_topic_{condition_topic} room_{condition_topic}"
    return MemoryObject(
        id=memory_id,
        layer=spec.layer,
        type=spec.memory_type,
        subject=f"benchmark-user-{spec.index % 100}",
        predicate=spec.memory_type,
        object=f"benchmark-object-{spec.index}",
        condition=condition,
        content=content,
        confidence=0.6 + (spec.index % 4) * 0.1,
        importance=(spec.index % 5) + 1,
        status=spec.status,
        evidence=[
            Evidence(
                type="explicit_statement",
                weight=1.0,
                source=source,
                observation=content,
                origin_actor="user",
                created_at=created_at,
                provenance_key=f"benchmark-message-{spec.index}",
            )
        ],
        source=source,
        origin="explicit_user",
        created_at=created_at,
        updated_at=created_at,
        tags=["t8-3", spec.layer, spec.memory_type],
    )


def configure_benchmark_sqlite(
    repository: SQLiteMemoryRepository,
) -> dict[str, int | str]:
    journal_mode = repository.conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    repository.conn.execute("PRAGMA synchronous = NORMAL")
    repository.conn.execute("PRAGMA cache_size = -64000")
    return {
        "journal_mode": journal_mode,
        "synchronous": repository.conn.execute("PRAGMA synchronous").fetchone()[0],
        "cache_size": repository.conn.execute("PRAGMA cache_size").fetchone()[0],
    }


def seed_benchmark_dataset(
    repository: SQLiteMemoryRepository,
    progress: Callable[[int, int], None] | None = None,
) -> float:
    started = time.perf_counter()
    specs = build_dataset_specs()
    for completed, spec in enumerate(specs, start=1):
        repository.create(_memory_from_spec(spec))
        if progress is not None and completed % 1_000 == 0:
            progress(completed, len(specs))
    return time.perf_counter() - started


def _execute_query(
    repository: SQLiteMemoryRepository,
    query: QuerySpec,
) -> tuple[float, int]:
    started_ns = time.perf_counter_ns()
    context = (
        {"condition_filter": query.condition_filter}
        if query.condition_filter is not None
        else None
    )
    need = analyze_intent(query.query, context=context)
    need.scope_filter = query.scope_filter
    memories = retrieve(need, repository=repository)
    serialized = [memory.model_dump_json() for memory in memories]
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    return elapsed_ms, len(serialized)


def run_query_protocol(
    repository: SQLiteMemoryRepository,
) -> dict[str, object]:
    """Execute the frozen warmup and measured protocol at concurrency one."""
    repository.record_access = lambda _memory_id: None

    for query in build_query_workload(WARMUP_QUERIES, seed=8_301):
        _execute_query(repository, query)

    samples_by_kind: dict[str, list[float]] = {
        kind: [] for kind in QUERY_MIX
    }
    result_counts: list[int] = []
    for query in build_query_workload(MEASURED_QUERIES, seed=8_302):
        elapsed_ms, result_count = _execute_query(repository, query)
        samples_by_kind[query.kind].append(elapsed_ms)
        result_counts.append(result_count)

    all_samples = [sample for samples in samples_by_kind.values() for sample in samples]
    ordinary_samples = [
        sample
        for kind, samples in samples_by_kind.items()
        if kind != "with_condition"
        for sample in samples
    ]
    return {
        "warmup_queries": WARMUP_QUERIES,
        "measured_queries": MEASURED_QUERIES,
        "concurrency": 1,
        "query_counts": {
            kind: len(samples) for kind, samples in samples_by_kind.items()
        },
        "overall": latency_summary(all_samples),
        "ordinary": latency_summary(ordinary_samples),
        "by_query_type": {
            kind: latency_summary(samples)
            for kind, samples in samples_by_kind.items()
        },
        "result_count": {
            "min": min(result_counts),
            "max": max(result_counts),
            "mean": statistics.fmean(result_counts),
        },
        "p95_target_ms": P95_TARGET_MS,
        "p95_target_met": nearest_rank_percentile(all_samples, 95)
        <= P95_TARGET_MS,
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_fts_document(
    repository: SQLiteMemoryRepository,
    memory_id: str,
) -> None:
    row = repository.conn.execute(
        "SELECT rowid, content, subject, predicate, object, tags_json "
        "FROM memories WHERE id = ?",
        (memory_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"memory missing before FTS corruption: {memory_id}")
    repository.conn.execute(
        "INSERT INTO memories_fts("
        "memories_fts, rowid, content, subject, predicate, object, tags"
        ") VALUES('delete', ?, ?, ?, ?, ?, ?)",
        tuple(row),
    )
    repository.conn.commit()


def run_consistency_protocol(root: Path) -> dict[str, object]:
    """Exercise update/version/archive, FTS corruption, rebuild, and query."""
    repository = SQLiteMemoryRepository(root / "consistency.db", root / "memory")
    try:
        original = _memory_from_spec(
            DatasetSpec(20_001, "semantic", "fact", "active", False)
        )
        original.content = "initial_consistency_token"
        original.object = original.content
        original.evidence[0].observation = original.content
        repository.create(original)

        original.content = "updated_consistency_token"
        original.object = original.content
        repository.update_with_version(original)

        successor = _memory_from_spec(
            DatasetSpec(20_002, "semantic", "fact", "active", False)
        )
        successor.content = "successor_consistency_token"
        successor.object = successor.content
        successor.evidence[0].observation = successor.content
        successor.supersedes = original.id
        repository.create(successor)

        original.status = "superseded"
        original.superseded_by = successor.id
        repository.update_with_version(original)
        successor.status = "archived"
        repository.update_with_version(successor)

        paths = {
            memory.id: root / "memory" / memory.layer / f"{memory.id}.md"
            for memory in (original, successor)
        }
        hashes_before = {
            memory_id: _file_sha256(path) for memory_id, path in paths.items()
        }

        _remove_fts_document(repository, original.id)
        damaged = repository.check_consistency()
        source_preserved_after_damage = hashes_before == {
            memory_id: _file_sha256(path) for memory_id, path in paths.items()
        }

        rebuilt = repository.rebuild_index()
        source_preserved_after_rebuild = hashes_before == {
            memory_id: _file_sha256(path) for memory_id, path in paths.items()
        }
        restored_original = repository.get_by_id(original.id)
        restored_successor = repository.get_by_id(successor.id)

        repository.record_access = lambda _memory_id: None
        query_results = retrieve(
            analyze_intent("过去 updated_consistency_token"),
            repository=repository,
        )
        query_ids = {memory.id for memory in query_results}

        checks = {
            "fts_damage_detected": (
                damaged.status == "critical"
                and original.id in damaged.missing_in_index
            ),
            "markdown_preserved_after_damage": source_preserved_after_damage,
            "rebuild_healthy": rebuilt.status == "healthy",
            "markdown_preserved_after_rebuild": source_preserved_after_rebuild,
            "updated_content_restored": (
                restored_original is not None
                and restored_original.content == "updated_consistency_token"
            ),
            "supersede_chain_restored": (
                restored_original is not None
                and restored_successor is not None
                and restored_original.status == "superseded"
                and restored_original.superseded_by == successor.id
                and restored_successor.supersedes == original.id
            ),
            "archive_state_restored": (
                restored_successor is not None
                and restored_successor.status == "archived"
            ),
            "historical_query_after_rebuild": original.id in query_ids,
        }
        return {
            "sequence": [
                "write",
                "update",
                "supersede",
                "archive",
                "corrupt_fts",
                "detect",
                "rebuild",
                "query",
            ],
            "checks": checks,
            "all_checks_passed": all(checks.values()),
            "damage_report": {
                "status": damaged.status,
                "missing_in_index": damaged.missing_in_index,
                "orphan_in_index": damaged.orphan_in_index,
                "checksum_mismatch": damaged.checksum_mismatch,
            },
            "rebuild_report": {
                "status": rebuilt.status,
                "missing_in_index": rebuilt.missing_in_index,
                "orphan_in_index": rebuilt.orphan_in_index,
                "checksum_mismatch": rebuilt.checksum_mismatch,
            },
        }
    finally:
        repository.close()
