# test/memory/unit/test_capture.py
import pytest
from unittest.mock import patch
from lumneo.memory.capture import capture
from lumneo.memory.model import ConversationTurn, MemoryCandidate, Source, Evidence
from lumneo.memory.common.time import utc_now
from lumneo.memory.capture.provider import CaptureProvider, CaptureError

def create_turn(role="user", content="test", msg_id="m1", chat_id="c1"):
    return ConversationTurn(
        role=role,
        content=content,
        message_id=msg_id,
        chat_id=chat_id,
        timestamp=utc_now()
    )

def create_evidence():
    return Evidence(
        type="explicit_statement",
        weight=1.0,
        source=Source(chat_id="c1", message_id="m1", timestamp=utc_now()),
        observation="test",
        origin_actor="user",
        created_at=utc_now()
    )

class MockProvider(CaptureProvider):
    def __init__(self, candidates=None):
        self.candidates = candidates or []
    def extract_candidates(self, turns):
        return self.candidates
    def health_check(self):
        return {"status": "healthy"}

def test_capture_single_turn():
    """单轮输入返回列表"""
    turn = create_turn()
    cand = MemoryCandidate(
        raw_content="test",
        evidence=[create_evidence()],
        source=Source(chat_id="c1", message_id="m1", timestamp=utc_now()),
        origin_actor="user",
        capture_id="temp",
        suggested_layer="semantic",
        subject="subject",
        predicate="predicate",
        object="object"
    )
    provider = MockProvider([cand])
    result = capture(turn, provider=provider)
    assert len(result) == 1
    assert result[0].capture_id.startswith("cap_")
    assert result[0].dedup_key is not None

def test_capture_multi_turn():
    """多轮输入返回列表"""
    turns = [create_turn(msg_id="m1"), create_turn(msg_id="m2")]
    cand1 = MemoryCandidate(
        raw_content="c1",
        evidence=[create_evidence()],
        source=Source(chat_id="c1", message_id="m1", timestamp=utc_now()),
        origin_actor="user",
        capture_id="temp1"
    )
    cand2 = MemoryCandidate(
        raw_content="c2",
        evidence=[create_evidence()],
        source=Source(chat_id="c1", message_id="m2", timestamp=utc_now()),
        origin_actor="user",
        capture_id="temp2"
    )
    provider = MockProvider([cand1, cand2])
    result = capture(turns, provider=provider)
    assert len(result) == 2
    assert result[0].capture_id == result[1].capture_id

def test_capture_id_uniqueness():
    """不同调用生成不同 capture_id"""
    def make_candidate():
        return MemoryCandidate(
            raw_content="test",
            evidence=[create_evidence()],
            source=Source(chat_id="c1", message_id="m1", timestamp=utc_now()),
            origin_actor="user",
            capture_id="temp"
        )
    
    provider1 = MockProvider([make_candidate()])
    result1 = capture([create_turn()], provider=provider1)
    
    provider2 = MockProvider([make_candidate()])
    result2 = capture([create_turn()], provider=provider2)
    
    assert result1[0].capture_id != result2[0].capture_id

def test_dedup_key_auto_completion():
    """自动补全 dedup_key"""
    cand = MemoryCandidate(
        raw_content="test",
        evidence=[create_evidence()],
        source=Source(chat_id="c1", message_id="m1", timestamp=utc_now()),
        origin_actor="user",
        capture_id="temp",
        suggested_layer="semantic",
        subject="user",
        predicate="preference",
        object="coffee"
    )
    provider = MockProvider([cand])
    result = capture([create_turn()], provider=provider)
    assert result[0].dedup_key is not None
    from lumneo.memory.common.hash_utils import compute_dedup_key
    expected = compute_dedup_key("semantic", "user", "preference", "coffee", "m1")
    assert result[0].dedup_key == expected

def test_mock_provider_injection():
    """验证可以注入自定义 Provider"""
    custom_provider = MockProvider([])
    result = capture([create_turn()], provider=custom_provider)
    assert result == []

def test_provider_exception():
    """Provider 抛出异常时，capture 也应抛出"""
    class ErrorProvider(CaptureProvider):
        def extract_candidates(self, turns):
            raise CaptureError("Provider error")
        def health_check(self): return {}
    with pytest.raises(CaptureError):
        capture([create_turn()], provider=ErrorProvider())

def test_default_provider_import_error():
    """当未提供 provider 且默认 LLM Provider 不可用时，应抛出 ImportError"""
    with patch("lumneo.memory.capture._get_default_provider", side_effect=ImportError("No provider")):
        with pytest.raises(ImportError):
            capture([create_turn()])