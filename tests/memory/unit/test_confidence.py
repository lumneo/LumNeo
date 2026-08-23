import pytest
from datetime import datetime, timezone

from lumneo.memory.model.evidence import Evidence, EvidenceType, EvidenceActor
from lumneo.memory.model.auxiliary import Source
from lumneo.memory.evaluator.confidence import calculate_confidence


def make_evidence(
    type_: EvidenceType,
    weight: float = 1.0,
    chat_id: str = "chat",
    message_id: str = "msg",
    provenance_key: str = None,
) -> Evidence:
    return Evidence(
        type=type_,
        weight=weight,
        source=Source(
            chat_id=chat_id,
            message_id=message_id,
            timestamp=datetime.now(timezone.utc),
        ),
        observation="test",
        origin_actor="user",
        created_at=datetime.now(timezone.utc),
        provenance_key=provenance_key,
    )


class TestConfidence:
    """契约 §5.1 置信度公式验证（A.2 及 CONF001~CONF005）"""

    def test_conf001_1_explicit(self):
        """1 explicit → 0.714"""
        evs = [make_evidence("explicit_statement", 1.0)]
        assert round(calculate_confidence(evs), 3) == 0.714

    def test_conf002_1_inference(self):
        """1 inference → 0.500"""
        evs = [make_evidence("inference", 1.0)]
        assert calculate_confidence(evs) == 0.5

    def test_conf003_5_same_message_deduped(self):
        """已去重情况下，单条 explicit 结果仍为 0.714（去重逻辑已保证）"""
        evs = [make_evidence("explicit_statement", 1.0)]
        assert round(calculate_confidence(evs), 3) == 0.714

    def test_conf004_5_independent_explicit(self):
        """5 条独立 explicit → 0.926"""
        evs = [
            make_evidence("explicit_statement", 1.0, chat_id=f"c{i}", message_id=f"m{i}")
            for i in range(5)
        ]
        assert round(calculate_confidence(evs), 3) == 0.926

    def test_conf005_explicit_confirmation_same_provenance_deduped(self):
        """同 provenance 下 explicit + confirmation，去重后仅 explicit → 0.714"""
        evs = [make_evidence("explicit_statement", 1.0, provenance_key="same")]
        assert round(calculate_confidence(evs), 3) == 0.714

    # 补充 A.2 表格中的几个典型场景（全量 25 个 case 可由 CI 覆盖）
    def test_a2_3_inference_independent(self):
        """3 条独立 inference → 0.75"""
        evs = [make_evidence("inference", 1.0, chat_id=f"c{i}") for i in range(3)]
        assert round(calculate_confidence(evs), 3) == 0.750

    def test_a2_10_inference_independent(self):
        """10 条独立 inference → 0.909"""
        evs = [make_evidence("inference", 1.0, chat_id=f"c{i}") for i in range(10)]
        assert round(calculate_confidence(evs), 3) == 0.909

    def test_a2_explicit_plus_confirmation_independent(self):
        """explicit + confirmation 不同 provenance → 0.819"""
        evs = [
            make_evidence("explicit_statement", 1.0, provenance_key="p1"),
            make_evidence("confirmation", 0.9, provenance_key="p2"),
        ]
        assert round(calculate_confidence(evs), 3) == 0.819