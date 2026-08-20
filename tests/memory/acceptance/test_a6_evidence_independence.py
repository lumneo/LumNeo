"""A.6 Evidence Independence acceptance tests (10 cases).

The frozen appendix specifies A.6.1-A.6.6. Cases A.6.7-A.6.10 complete
coverage using the mandatory independence rules and confidence anchors in §5.1.
"""

from datetime import timedelta

import pytest

from lumneo.memory.common.time import utc_now
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.model import Evidence, MemoryCandidate, Source


def create_evidence(
    type_: str,
    *,
    weight: float = 1.0,
    chat_id: str,
    message_id: str,
    timestamp,
    provenance_key: str | None = None,
    origin_actor: str = "user",
) -> Evidence:
    source = Source(
        chat_id=chat_id,
        message_id=message_id,
        timestamp=timestamp,
    )
    return Evidence(
        type=type_,
        weight=weight,
        source=source,
        observation="用户喜欢美式咖啡",
        origin_actor=origin_actor,
        created_at=timestamp,
        provenance_key=provenance_key,
    )


def make_candidate(evidence: list[Evidence]) -> MemoryCandidate:
    return MemoryCandidate(
        raw_content="用户喜欢美式咖啡",
        suggested_layer="semantic",
        suggested_type="preference",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        evidence=evidence,
        source=evidence[0].source,
        origin_actor="user",
        capture_id="cap_a6",
        dedup_key="semantic:用户:preference:美式咖啡",
        metadata={},
    )


def build_case(case_id: str) -> tuple[list[Evidence], int, float]:
    now = utc_now()

    if case_id == "A6.1":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id="same-message",
                timestamp=now,
            )
            for _ in range(5)
        ]
        return evidence, 1, 1.0 / 1.4

    if case_id == "A6.2":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id=f"message-{index}",
                timestamp=now + timedelta(seconds=index * 10),
            )
            for index in range(2)
        ]
        return evidence, 1, 1.0 / 1.4

    if case_id == "A6.3":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id=f"message-{index}",
                timestamp=now + timedelta(seconds=index * 10),
            )
            for index in range(5)
        ]
        return evidence, 1, 1.0 / 1.4

    if case_id == "A6.4":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-explicit",
                message_id="explicit-message",
                timestamp=now,
                provenance_key="explicit-origin",
            ),
            create_evidence(
                "behavioral",
                chat_id="chat-behavior",
                message_id="behavior-message",
                timestamp=now,
                provenance_key="behavior-origin",
            ),
        ]
        return evidence, 2, 1.7 / 2.1

    if case_id == "A6.5":
        evidence = [
            create_evidence(
                "inference",
                chat_id="chat-1",
                message_id=f"fragment-{index}",
                timestamp=now + timedelta(seconds=index * 10),
                provenance_key="same-source-document",
            )
            for index in range(10)
        ]
        return evidence, 1, 0.5

    if case_id == "A6.6":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id="user-message",
                timestamp=now,
                provenance_key="user-message",
            ),
            create_evidence(
                "confirmation",
                chat_id="chat-1",
                message_id="assistant-message",
                timestamp=now + timedelta(seconds=10),
                provenance_key="user-message",
                origin_actor="assistant",
            ),
            create_evidence(
                "confirmation",
                chat_id="chat-1",
                message_id="user-confirmation",
                timestamp=now + timedelta(seconds=20),
                provenance_key="user-message",
            ),
        ]
        return evidence, 1, 1.0 / 1.4

    if case_id == "A6.7":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id=f"chat-{index}",
                message_id=f"message-{index}",
                timestamp=now,
            )
            for index in range(2)
        ]
        return evidence, 2, 2.0 / 2.4

    if case_id == "A6.8":
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id=f"chat-{index}",
                message_id=f"message-{index}",
                timestamp=now,
            )
            for index in range(5)
        ]
        return evidence, 5, 5.0 / 5.4

    if case_id == "A6.9":
        evidence = [
            create_evidence(
                "explicit_statement",
                weight=0.6,
                chat_id="chat-1",
                message_id="same-message",
                timestamp=now,
            ),
            create_evidence(
                "explicit_statement",
                weight=1.0,
                chat_id="chat-1",
                message_id="same-message",
                timestamp=now,
            ),
            create_evidence(
                "explicit_statement",
                weight=0.8,
                chat_id="chat-1",
                message_id="same-message",
                timestamp=now,
            ),
        ]
        return evidence, 1, 1.0 / 1.4

    if case_id == "A6.10":
        # Phase 1A 当前用 60 秒近似五轮；这里同时用 message-1/message-7
        # 表达契约的 >5 轮语义，并让时间间隔越过该实现窗口。
        evidence = [
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id="message-1",
                timestamp=now,
            ),
            create_evidence(
                "explicit_statement",
                chat_id="chat-1",
                message_id="message-7",
                timestamp=now + timedelta(seconds=120),
            ),
        ]
        return evidence, 2, 2.0 / 2.4

    raise AssertionError(f"Unknown A.6 case: {case_id}")


@pytest.mark.parametrize(
    "case_id",
    [f"A6.{index}" for index in range(1, 11)],
)
def test_a6_evidence_independence(case_id: str) -> None:
    evidence, expected_count, expected_confidence = build_case(case_id)

    memory = Evaluator(repository=None, confidence_cap=1.0).evaluate(
        make_candidate(evidence)
    )

    assert len(memory.evidence) == expected_count
    assert memory.confidence == pytest.approx(expected_confidence, abs=0.001)

    if case_id == "A6.9":
        assert memory.evidence[0].weight == 1.0
