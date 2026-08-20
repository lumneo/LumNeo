import pytest
from datetime import datetime, timezone
from lumneo.memory.model.memory_candidate import MemoryCandidate
from lumneo.memory.model.evidence import Evidence, EvidenceType, EvidenceActor
from lumneo.memory.model.auxiliary import Source
from lumneo.memory.model.enums import MemoryLayer, MemoryType
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.storage.repository import SQLiteMemoryRepository


def create_evidence(
    type_: EvidenceType,
    weight: float = 1.0,
    message_id: str = "m1",
    chat_id: str = "c1",
    provenance_key: str = None,
    timestamp=None,
) -> Evidence:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return Evidence(
        type=type_,
        weight=weight,
        source=Source(
            chat_id=chat_id,
            message_id=message_id,
            timestamp=timestamp,
        ),
        observation="test",
        origin_actor="user",
        created_at=timestamp,
        provenance_key=provenance_key,
    )


def make_candidate(
    raw_content: str,
    layer: MemoryLayer = "semantic",
    mem_type: MemoryType = "fact",
    subject: str = "user",
    predicate: str = "likes",
    object: str = "coffee",
    evidence: list = None,
    capture_id: str = "cap1",
    origin_actor: EvidenceActor = "user",
) -> MemoryCandidate:
    if evidence is None:
        evidence = [create_evidence("explicit_statement", 1.0)]
    return MemoryCandidate(
        raw_content=raw_content,
        suggested_layer=layer,
        suggested_type=mem_type,
        subject=subject,
        predicate=predicate,
        object=object,
        evidence=evidence,
        source=Source(
            chat_id="chat",
            message_id="m",
            timestamp=datetime.now(timezone.utc)
        ),
        origin_actor=origin_actor,
        capture_id=capture_id,
        dedup_key=None,
        metadata={}
    )


@pytest.fixture
def persistent_evaluator(tmp_path):
    repository = SQLiteMemoryRepository(tmp_path / "memory.db", tmp_path / "memory")
    try:
        yield Evaluator(repository=repository)
    finally:
        repository.close()


class TestEvaluator:
    def test_layer_type_suspicious_goes_needs_review(self):
        cand = make_candidate("test", layer="identity", mem_type="event")
        ev = Evaluator()
        obj = ev.evaluate(cand)
        assert obj.status == "needs_review"
        assert obj.metadata["layer_type_verdict"] == "suspicious"

    def test_high_confidence_active(self):
        # 5条独立 explicit
        evs = [create_evidence("explicit_statement", 1.0, chat_id=f"c{i}", message_id=f"m{i}") for i in range(5)]
        cand = make_candidate("test", evidence=evs)
        obj = Evaluator().evaluate(cand)
        assert obj.status == "active"
        assert obj.confidence > 0.9

    def test_low_confidence_needs_review(self):
        cand = make_candidate("test", evidence=[create_evidence("inference", 1.0)])  # 改为 1.0
        obj = Evaluator().evaluate(cand)
        assert obj.status == "needs_review"
        assert obj.confidence == 0.5

    def test_batch_high_similarity_is_not_a_conflict(self, persistent_evaluator):
        cand1 = make_candidate("like coffee", subject="user", predicate="likes", object="coffee", capture_id="c1")
        cand2 = make_candidate("like tea", subject="user", predicate="likes", object="coffee", capture_id="c1")
        # 二者对象高度相似（相同）
        objs = persistent_evaluator.evaluate_batch([cand1, cand2])
        # Contract §5.3：同 capture 仅互斥 object 进入 needs_review。
        assert all(obj.status == "active" for obj in objs)
        assert all(obj.supersedes is None for obj in objs)
        assert all(obj.superseded_by is None for obj in objs)

    def test_batch_conflict_low_similarity_independent(self, persistent_evaluator):
        cand1 = make_candidate("like coffee", subject="user", predicate="likes", object="coffee", capture_id="c1")
        cand2 = make_candidate("like tea", subject="user", predicate="likes", object="tea", capture_id="c1")
        # 对象不同，sim 低
        objs = persistent_evaluator.evaluate_batch([cand1, cand2])
        by_object = {obj.object: obj for obj in objs}
        assert by_object["coffee"].status == "active"
        assert by_object["tea"].status == "needs_review"
        assert by_object["tea"].metadata.get("batch_conflict") is True

    def test_batch_conflict_unclear_goes_needs_review(self, persistent_evaluator):
        # 对象相似度介于 0.4-0.75 之间，我们构造：object = "coffee" vs "coffee beans"
        cand1 = make_candidate("like coffee", subject="user", predicate="likes", object="coffee", capture_id="c1")
        cand2 = make_candidate("like coffee beans", subject="user", predicate="likes", object="coffee beans", capture_id="c1")
        # 相似度大概 0.5~0.6
        objs = persistent_evaluator.evaluate_batch([cand1, cand2])
        by_object = {obj.object: obj for obj in objs}
        assert by_object["coffee"].status == "active"
        assert by_object["coffee beans"].status == "needs_review"
        assert by_object["coffee beans"].metadata.get("batch_conflict") is True

    def test_batch_suspicious_not_supersede(self, persistent_evaluator):
        cand1 = make_candidate("like coffee", layer="identity", mem_type="event", subject="user", predicate="likes", object="coffee", capture_id="c1")
        cand2 = make_candidate("like tea", layer="identity", mem_type="event", subject="user", predicate="likes", object="coffee", capture_id="c1")
        # 两个都是 suspicious，不会 active
        objs = persistent_evaluator.evaluate_batch([cand1, cand2])
        for obj in objs:
            assert obj.status == "needs_review"
            assert obj.metadata["layer_type_verdict"] == "suspicious"
