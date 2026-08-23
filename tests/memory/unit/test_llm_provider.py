
# tests/memory/unit/test_llm_provider.py
import pytest
from datetime import datetime, timezone

from lumneo.memory.capture.llm_provider import LLMCaptureProvider
from lumneo.memory.capture.provider import CaptureConfig
from lumneo.memory.model import ConversationTurn


@pytest.fixture
def provider():
    return LLMCaptureProvider(CaptureConfig(max_candidates_per_turn=5))


@pytest.fixture
def user_turn_factory():
    def _factory(
        content,
        message_id="msg_001",
        chat_id="chat_001",
        reply_to=None,
        timestamp=None,
    ):
        if timestamp is None:
            timestamp = datetime(
                2026,
                8,
                13,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )

        return ConversationTurn(
            role="user",
            content=content,
            message_id=message_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to,
            timestamp=timestamp,
        )

    return _factory


# ======================================================
# Basic semantic extraction
# ======================================================


@pytest.mark.parametrize(
    "content,expected_predicate,expected_object,expected_layer,expected_type",
    [
        (
            "我喜欢美式咖啡",
            "preference",
            "美式咖啡",
            "semantic",
            "preference",
        ),
        (
            "我偏好安静的地方",
            "preference",
            "安静的地方",
            "semantic",
            "preference",
        ),
        (
            "我爱吃巧克力",
            "preference",
            "吃巧克力",
            "semantic",
            "preference",
        ),
        (
            "I prefer dark mode",
            "preference",
            "dark mode",
            "semantic",
            "preference",
        ),
        (
            "我会用 Python",
            "skill",
            "用 Python",
            "procedural",
            "skill",
        ),
        (
            "我擅长写诗",
            "skill",
            "写诗",
            "procedural",
            "skill",
        ),
        (
            "我能跑十公里",
            "skill",
            "跑十公里",
            "procedural",
            "skill",
        ),
        (
            "I can cook",
            "skill",
            "cook",
            "procedural",
            "skill",
        ),
        (
            "我是工程师",
            "fact",
            "工程师",
            "identity",
            "fact",
        ),
        (
            "我的名字是小明",
            "fact",
            "名字是小明",
            "identity",
            "fact",
        ),
        (
            "昨天我去了台北",
            "event",
            "去了台北",
            "episodic",
            "event",
        ),
        (
            "小明是我的朋友",
            "relationship",
            "小明",
            "semantic",
            "relationship",
        ),
        (
            "我认为努力很重要",
            "value",
            "努力很重要",
            "semantic",
            "value",
        ),
        (
            "我的风格是简约",
            "style",
            "简约",
            "semantic",
            "style",
        ),
    ],
)
def test_extract_single_candidate(
    provider,
    user_turn_factory,
    content,
    expected_predicate,
    expected_object,
    expected_layer,
    expected_type,
):
    turn = user_turn_factory(content)
    candidates = provider.extract_candidates([turn])

    assert len(candidates) == 1

    candidate = candidates[0]
    assert candidate.subject == "用户"
    assert candidate.predicate == expected_predicate
    assert candidate.object == expected_object
    assert candidate.suggested_layer == expected_layer
    assert candidate.suggested_type == expected_type


# ======================================================
# Multi candidate
# ======================================================


def test_multi_candidate_split(
    provider,
    user_turn_factory,
):
    turn = user_turn_factory("我喜欢咖啡和茶，也擅长编程")
    candidates = provider.extract_candidates([turn])

    preference_objects = [
        c.object for c in candidates if c.predicate == "preference"
    ]

    skill_objects = [
        c.object for c in candidates if c.predicate == "skill"
    ]

    assert "咖啡" in preference_objects
    assert "茶" in preference_objects
    assert any("编程" in obj for obj in skill_objects)


# ======================================================
# Candidate limit
# ======================================================


def test_max_candidates_limit(
    provider,
    user_turn_factory,
):
    provider.config.max_candidates_per_turn = 1
    turn = user_turn_factory("我喜欢咖啡和茶")
    candidates = provider.extract_candidates([turn])

    assert len(candidates) == 1


# ======================================================
# Fallback
# ======================================================


def test_generic_statement_fallback(
    provider,
    user_turn_factory,
):
    turn = user_turn_factory("今天天气真好，阳光明媚")
    candidates = provider.extract_candidates([turn])

    assert len(candidates) == 1

    candidate = candidates[0]
    assert candidate.predicate == "generic_statement"
    assert candidate.suggested_layer == "semantic"
    assert candidate.suggested_type == "fact"
    assert candidate.metadata["standardization_issue"] is True


# ======================================================
# Evidence provenance
# ======================================================


def test_provenance_key(
    provider,
    user_turn_factory,
):
    turn = user_turn_factory("我喜欢咖啡", reply_to="msg_000")
    candidates = provider.extract_candidates([turn])

    assert candidates[0].evidence[0].provenance_key == "msg_000"


# ======================================================
# Health
# ======================================================


def test_health_check(
    provider,
):
    status = provider.health_check()

    assert status["status"] == "healthy"
    assert status["version"] == "1.1.0"


def test_assistant_confirmation_provenance(provider, user_turn_factory):
    user_msg = user_turn_factory("我喜欢咖啡", message_id="user_001")
    assistant_msg = ConversationTurn(
        role="assistant",
        content="所以你喜欢咖啡，对吗？",
        message_id="assist_001",
        chat_id=user_msg.chat_id,
        reply_to_message_id="user_001",
        timestamp=datetime(2026, 8, 13, 12, 1, 0, tzinfo=timezone.utc)
    )
    candidates = provider.extract_candidates([user_msg, assistant_msg])
    # 从助手中提取的候选，其 origin_actor 应为 "assistant"
    assistant_candidates = [c for c in candidates if c.origin_actor == "assistant"]
    assert len(assistant_candidates) >= 1, "应至少有一个来自助手的候选"
    cand = assistant_candidates[0]
    ev = cand.evidence[0]
    assert ev.origin_actor == "assistant"
    assert ev.provenance_key == "user_001"