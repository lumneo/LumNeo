# tests/memory/unit/test_schema.py
"""T0.3/T1.1 Schema 校验框架 — 单元测试 (42+ cases)"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from lumneo.memory.model import (
    MemoryObject,
    MemoryCandidate,
    Evidence,
    Source,
    PrivacyInfo,
    MemoryNeed,
    MemoryBudget,
    UserDirective,
    ConversationTurn,
)


# ---------- 辅助函数 ----------
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sample_source(message_id="msg_001", chat_id="chat_001") -> Source:
    return Source(
        tenant_id="tenant_a",
        agent_id="agent_1",
        chat_id=chat_id,
        message_id=message_id,
        timestamp=utc_now(),
        channel="chat",
    )


def sample_evidence(provenance_key=None, weight=1.0) -> Evidence:
    return Evidence(
        type="explicit_statement",
        weight=weight,
        source=sample_source(),
        observation="用户明确说喜欢美式咖啡",
        origin_actor="user",
        created_at=utc_now(),
        provenance_key=provenance_key,
    )


def make_minimal_memory(**overrides) -> MemoryObject:
    """构造最小合法 MemoryObject"""
    defaults = {
        "id": "mem_1754918400000000000_a1b2c3d4e5f6",
        "layer": "semantic",
        "type": "preference",
        "content": "用户喜欢美式咖啡",
        "confidence": 0.87,
        "importance": 4,
        "status": "active",
        "evidence": [sample_evidence()],
        "source": sample_source(),
        "origin": "explicit_user",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    defaults.update(overrides)
    return MemoryObject(**defaults)


# ========== Group A: 合法构造 (8 cases) ==========
def test_a01_minimal_valid():
    """A01: 最小合法 MemoryObject"""
    obj = make_minimal_memory()
    assert obj.id == "mem_1754918400000000000_a1b2c3d4e5f6"
    assert obj.confidence == 0.87
    assert obj.importance == 4


def test_a02_full_valid():
    """A02: 完整 MemoryObject（所有字段填充）"""
    obj = make_minimal_memory(
        schema_version="2.1.2",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        condition={"key": "place", "value": "咖啡店"},
        confidence_detail={"reason": "用户明确陈述"},
        tags=["咖啡", "偏好"],
        privacy=PrivacyInfo(level="private", reason="用户偏好"),
        metadata={"standardization_issue": False, "user_forgotten": False, "custom": "value"},
        last_accessed=utc_now(),
        access_count=5,
    )
    assert obj.subject == "用户"
    assert obj.privacy.level == "private"
    assert obj.access_count == 5


def test_a03_supersedes_valid():
    """A03: supersedes 引用合法 ID"""
    obj = make_minimal_memory(supersedes="mem_1234567890_abcdef123456")
    assert obj.supersedes == "mem_1234567890_abcdef123456"


def test_a04_superseded_by_valid():
    """A04: superseded_by 引用合法 ID"""
    obj = make_minimal_memory(superseded_by="mem_1234567890_abcdef123456")
    assert obj.superseded_by == "mem_1234567890_abcdef123456"


def test_a05_condition_single():
    """A05: condition 单条件"""
    obj = make_minimal_memory(condition={"key": "place", "value": "客厅"})
    assert obj.condition["key"] == "place"


def test_a06_condition_and_5():
    """A06: condition AND 组合（5 条）"""
    obj = make_minimal_memory(condition={
        "operator": "AND",
        "clauses": [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2"},
            {"key": "k3", "value": "v3"},
            {"key": "k4", "value": "v4"},
            {"key": "k5", "value": "v5"},
        ]
    })
    assert len(obj.condition["clauses"]) == 5


def test_a07_tags_nonempty():
    """A07: tags 非空列表"""
    obj = make_minimal_memory(tags=["tag1", "tag2"])
    assert len(obj.tags) == 2


def test_a08_privacy_full():
    """A08: privacy 完整填充"""
    obj = make_minimal_memory(privacy=PrivacyInfo(level="secret", reason="敏感信息"))
    assert obj.privacy.level == "secret"


# ========== Group B: 字段级校验 (12 cases) ==========
def test_b01_id_no_mem_prefix():
    """B01: id 无 mem_ 前缀"""
    with pytest.raises(ValidationError):
        make_minimal_memory(id="invalid_123")


def test_b02_id_timestamp_non_numeric():
    """B02: id timestamp 非数字"""
    with pytest.raises(ValidationError):
        make_minimal_memory(id="mem_abc_abcdef123456")


def test_b03_id_random_length_short():
    """B03: id random 长度不足 12"""
    with pytest.raises(ValidationError):
        make_minimal_memory(id="mem_123_abc")


def test_b04_confidence_gt_1():
    """B04: confidence > 1.0"""
    with pytest.raises(ValidationError):
        make_minimal_memory(confidence=1.5)


def test_b05_confidence_lt_0():
    """B05: confidence < 0.0"""
    with pytest.raises(ValidationError):
        make_minimal_memory(confidence=-0.1)


def test_b06_importance_0():
    """B06: importance = 0"""
    with pytest.raises(ValidationError):
        make_minimal_memory(importance=0)


def test_b07_importance_6():
    """B07: importance = 6"""
    with pytest.raises(ValidationError):
        make_minimal_memory(importance=6)


def test_b08_evidence_empty():
    """B08: evidence = []"""
    with pytest.raises(ValidationError):
        make_minimal_memory(evidence=[])


def test_b09_content_empty():
    """B09: content = ''"""
    with pytest.raises(ValidationError):
        make_minimal_memory(content="")


def test_b10_condition_or():
    """B10: condition 含 OR"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={"operator": "OR", "clauses": [{"key": "k1", "value": "v1"}]})
    assert "不支持" in str(exc.value) or "OR" in str(exc.value)


def test_b11_condition_clauses_gt_5():
    """B11: AND clauses > 5"""
    with pytest.raises(ValidationError):
        make_minimal_memory(condition={
            "operator": "AND",
            "clauses": [
                {"key": "k1", "value": "v1"},
                {"key": "k2", "value": "v2"},
                {"key": "k3", "value": "v3"},
                {"key": "k4", "value": "v4"},
                {"key": "k5", "value": "v5"},
                {"key": "k6", "value": "v6"},
            ]
        })


def test_b12_condition_clause_nested():
    """B12: clause 嵌套"""
    with pytest.raises(ValidationError):
        make_minimal_memory(condition={
            "operator": "AND",
            "clauses": [
                {"key": "k1", "value": "v1"},
                {"operator": "AND", "clauses": [{"key": "k2", "value": "v2"}]}
            ]
        })


# ========== Group C: Source/Evidence 校验 (6 cases) ==========
def test_c01_source_no_locator():
    """C01: Source 无 locator"""
    with pytest.raises(ValidationError) as exc:
        Source(tenant_id="t1", timestamp=utc_now())
    assert "locator" in str(exc.value).lower()


def test_c02_source_extra_bad_key():
    """C02: Source extra 含非法键"""
    with pytest.raises(ValidationError):
        Source(
            tenant_id="t1",
            timestamp=utc_now(),
            chat_id="c1",
            extra={"bad_key": "value"}
        )


def test_c03_evidence_weight_lt_03():
    """C03: Evidence.weight < 0.3"""
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=0.2,
            source=sample_source(),
            observation="test",
            origin_actor="user",
            created_at=utc_now()
        )


def test_c04_evidence_weight_gt_1():
    """C04: Evidence.weight > 1.0"""
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=1.5,
            source=sample_source(),
            observation="test",
            origin_actor="user",
            created_at=utc_now()
        )


def test_c05_evidence_provenance_empty():
    """C05: provenance_key 为空字符串"""
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=1.0,
            source=sample_source(),
            observation="test",
            origin_actor="user",
            created_at=utc_now(),
            provenance_key=""  # 空字符串
        )


def test_c06_evidence_created_at_naive():
    """C06: Evidence.created_at naive"""
    naive = datetime(2026, 8, 13, 10, 0, 0)
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=1.0,
            source=sample_source(),
            observation="test",
            origin_actor="user",
            created_at=naive
        )


# ========== Group D: 版本链与自引用 (4 cases) ==========
def test_d01_supersedes_self():
    """D01: supersedes 自引用"""
    obj_id = "mem_123_abcdef123456"
    with pytest.raises(ValidationError):
        make_minimal_memory(id=obj_id, supersedes=obj_id)


def test_d02_superseded_by_self():
    """D02: superseded_by 自引用"""
    obj_id = "mem_123_abcdef123456"
    with pytest.raises(ValidationError):
        make_minimal_memory(id=obj_id, superseded_by=obj_id)


def test_d03_supersedes_bad_format():
    """D03: supersedes 格式非法"""
    with pytest.raises(ValidationError):
        make_minimal_memory(supersedes="bad_id")


def test_d04_superseded_by_bad_format():
    """D04: superseded_by 格式非法"""
    with pytest.raises(ValidationError):
        make_minimal_memory(superseded_by="bad_id")


# ========== Group E: Round-trip 序列化 (12 cases) ==========
def roundtrip_test(obj: MemoryObject) -> bool:
    """辅助：序列化 -> 反序列化 -> 比对"""
    data = obj.model_dump()
    # datetime 序列化后为 ISO 字符串，需要确保解析正确
    # 使用 model_validate 自动处理
    reconstructed = MemoryObject.model_validate(data)
    # 比对关键字段（排除 datetime 微秒可能差异）
    assert reconstructed.id == obj.id
    assert reconstructed.layer == obj.layer
    assert reconstructed.type == obj.type
    assert reconstructed.confidence == obj.confidence
    assert reconstructed.importance == obj.importance
    assert reconstructed.status == obj.status
    assert len(reconstructed.evidence) == len(obj.evidence)
    return True


def test_e01_roundtrip_minimal():
    """E01: 最小对象 round-trip"""
    obj = make_minimal_memory()
    assert roundtrip_test(obj)


def test_e02_roundtrip_full():
    """E02: 完整对象 round-trip"""
    obj = make_minimal_memory(
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        condition={"key": "place", "value": "咖啡店"},
        confidence_detail={"reason": "用户明确陈述"},
        tags=["咖啡", "偏好"],
        privacy=PrivacyInfo(level="private", reason="用户偏好"),
        metadata={"standardization_issue": False, "user_forgotten": False, "custom": "value"},
        last_accessed=utc_now(),
        access_count=5,
        supersedes="mem_123_abcdef123456",
        superseded_by=None,
    )
    assert roundtrip_test(obj)


def test_e03_roundtrip_supersedes():
    """E03: 带 supersedes round-trip"""
    obj = make_minimal_memory(supersedes="mem_123_abcdef123456")
    assert roundtrip_test(obj)


def test_e04_roundtrip_superseded_by():
    """E04: 带 superseded_by round-trip"""
    obj = make_minimal_memory(superseded_by="mem_123_abcdef123456")
    assert roundtrip_test(obj)


def test_e05_roundtrip_condition_single():
    """E05: condition 单条件 round-trip"""
    obj = make_minimal_memory(condition={"key": "place", "value": "客厅"})
    assert roundtrip_test(obj)


def test_e06_roundtrip_condition_and():
    """E06: condition AND 组合 round-trip"""
    obj = make_minimal_memory(condition={
        "operator": "AND",
        "clauses": [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2"},
            {"key": "k3", "value": "v3"},
        ]
    })
    assert roundtrip_test(obj)


def test_e07_roundtrip_tags():
    """E07: tags 非空 round-trip"""
    obj = make_minimal_memory(tags=["tag1", "tag2", "tag3"])
    assert roundtrip_test(obj)


def test_e08_roundtrip_privacy():
    """E08: privacy 完整 round-trip"""
    obj = make_minimal_memory(privacy=PrivacyInfo(level="secret", reason="敏感"))
    assert roundtrip_test(obj)


def test_e09_roundtrip_datetime_preserved():
    """E09: datetime 时区保留 round-trip"""
    now = utc_now()
    obj = make_minimal_memory(created_at=now, updated_at=now, last_accessed=now)
    data = obj.model_dump()
    reconstructed = MemoryObject.model_validate(data)
    # 检查时区保留（字符串解析后仍为 aware）
    assert reconstructed.created_at.tzinfo is not None
    assert reconstructed.updated_at.tzinfo is not None
    if reconstructed.last_accessed:
        assert reconstructed.last_accessed.tzinfo is not None


def test_e10_roundtrip_metadata_standardization():
    """E10: metadata 含 standardization_issue round-trip"""
    obj = make_minimal_memory(metadata={"standardization_issue": True, "user_forgotten": False})
    data = obj.model_dump()
    reconstructed = MemoryObject.model_validate(data)
    assert reconstructed.metadata["standardization_issue"] is True


def test_e11_roundtrip_metadata_user_forgotten():
    """E11: metadata 含 user_forgotten round-trip"""
    obj = make_minimal_memory(metadata={"standardization_issue": False, "user_forgotten": True})
    data = obj.model_dump()
    reconstructed = MemoryObject.model_validate(data)
    assert reconstructed.metadata["user_forgotten"] is True


def test_e12_roundtrip_all_fields():
    """E12: 所有字段全部填充 round-trip"""
    obj = make_minimal_memory(
        schema_version="2.1.2",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        condition={"key": "place", "value": "咖啡店"},
        confidence_detail={"source": "golden_dataset"},
        tags=["咖啡", "偏好", "美式"],
        privacy=PrivacyInfo(level="private", reason="用户偏好"),
        metadata={"standardization_issue": False, "user_forgotten": False, "source": "import"},
        last_accessed=utc_now(),
        access_count=10,
        supersedes="mem_111_aaaaaaaaaaaa",
        superseded_by="mem_222_bbbbbbbbbbbb",
    )
    assert roundtrip_test(obj)


# ========== MemoryCandidate 专项测试 ==========

def test_memory_candidate_confidence_hint_out_of_range():
    """confidence_hint 超出 0~1 范围应报错"""
    with pytest.raises(ValidationError):
        MemoryCandidate(
            raw_content="test",
            evidence=[sample_evidence()],
            source=sample_source(),
            origin_actor="user",
            capture_id="cap_123",
            confidence_hint=1.5,
        )


def test_memory_candidate_capture_id_empty():
    """capture_id 为空字符串应报错"""
    with pytest.raises(ValidationError):
        MemoryCandidate(
            raw_content="test",
            evidence=[sample_evidence()],
            source=sample_source(),
            origin_actor="user",
            capture_id="",
        )


def test_memory_candidate_dedup_key_empty_string():
    """dedup_key 若提供，不能为空字符串"""
    with pytest.raises(ValidationError):
        MemoryCandidate(
            raw_content="test",
            evidence=[sample_evidence()],
            source=sample_source(),
            origin_actor="user",
            capture_id="cap_123",
            dedup_key="",  # 空字符串非法
        )


def test_memory_candidate_origin_actor_invalid():
    """origin_actor 必须为合法枚举值"""
    with pytest.raises(ValidationError):
        MemoryCandidate(
            raw_content="test",
            evidence=[sample_evidence()],
            source=sample_source(),
            origin_actor="invalid",  # type: ignore
            capture_id="cap_123",
        )


def test_memory_candidate_roundtrip():
    """MemoryCandidate 序列化/反序列化一致"""
    cand = MemoryCandidate(
        raw_content="用户喜欢美式咖啡",
        suggested_layer="semantic",
        suggested_type="preference",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        evidence=[sample_evidence()],
        source=sample_source(),
        origin_actor="user",
        confidence_hint=0.9,
        capture_id="cap_123",
        dedup_key="hash_abc",
        metadata={"source": "test"},
    )
    data = cand.model_dump()
    reconstructed = MemoryCandidate.model_validate(data)
    assert reconstructed.capture_id == cand.capture_id
    assert reconstructed.dedup_key == cand.dedup_key
    assert reconstructed.confidence_hint == cand.confidence_hint


# ========== T1.3: Evidence + Source + 辅助模型专项测试 ==========

# ---------- Evidence ----------
def test_evidence_type_enum():
    """Evidence.type 必须为合法枚举值"""
    # 合法值
    ev = Evidence(
        type="explicit_statement",
        weight=1.0,
        source=sample_source(),
        observation="test",
        origin_actor="user",
        created_at=utc_now(),
    )
    assert ev.type == "explicit_statement"
    
    # 非法值
    with pytest.raises(ValidationError):
        Evidence(
            type="invalid_type",  # type: ignore
            weight=1.0,
            source=sample_source(),
            observation="test",
            origin_actor="user",
            created_at=utc_now(),
        )


def test_evidence_origin_actor_enum():
    """Evidence.origin_actor 必须为合法枚举值"""
    # 合法值
    ev = Evidence(
        type="explicit_statement",
        weight=1.0,
        source=sample_source(),
        observation="test",
        origin_actor="assistant",
        created_at=utc_now(),
    )
    assert ev.origin_actor == "assistant"
    
    # 非法值
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=1.0,
            source=sample_source(),
            observation="test",
            origin_actor="bot",  # type: ignore
            created_at=utc_now(),
        )


def test_evidence_observation_nonempty():
    """Evidence.observation 不能为空"""
    with pytest.raises(ValidationError):
        Evidence(
            type="explicit_statement",
            weight=1.0,
            source=sample_source(),
            observation="",  # 空字符串
            origin_actor="user",
            created_at=utc_now(),
        )


# ---------- Source ----------
def test_source_with_chat_id():
    """Source 仅包含 chat_id 也可作为 locator"""
    src = Source(
        tenant_id="t1",
        chat_id="chat_123",
        timestamp=utc_now(),
    )
    assert src.chat_id == "chat_123"


def test_source_with_external_id():
    """Source 仅包含 extra.external_id 也可作为 locator"""
    src = Source(
        tenant_id="t1",
        timestamp=utc_now(),
        extra={"external_id": "ext_123"},
    )
    assert src.extra["external_id"] == "ext_123"


def test_source_extra_allowed_keys():
    """Source extra 仅允许 external_id, import_source, provider"""
    # 合法
    src = Source(
        tenant_id="t1",
        timestamp=utc_now(),
        chat_id="c1",
        extra={"import_source": "file.csv", "provider": "test"},
    )
    assert "import_source" in src.extra
    assert "provider" in src.extra
    
    # 非法键已在 test_c02 中覆盖


def test_source_extra_none():
    """Source extra 为 None 是合法的"""
    src = Source(
        tenant_id="t1",
        timestamp=utc_now(),
        chat_id="c1",
        extra=None,
    )
    assert src.extra is None


# ---------- PrivacyInfo ----------
def test_privacy_info_valid():
    """PrivacyInfo 合法构造"""
    pi = PrivacyInfo(level="secret", reason="敏感信息")
    assert pi.level == "secret"
    assert pi.reason == "敏感信息"


def test_privacy_info_reason_optional():
    """PrivacyInfo.reason 可选"""
    pi = PrivacyInfo(level="public")
    assert pi.reason is None


def test_privacy_info_invalid_level():
    """PrivacyInfo.level 必须为合法枚举值"""
    with pytest.raises(ValidationError):
        PrivacyInfo(level="top_secret")  # type: ignore


# ---------- MemoryNeed ----------
def test_memory_need_valid():
    """MemoryNeed 合法构造"""
    need = MemoryNeed(
        layers=["semantic", "episodic"],
        types=["preference", "fact"],
        keywords=["咖啡", "偏好"],
        subject_hint="用户",
        max_results=10,
        scope_filter={"tenant_id": "t1"},
        include_historical=True,
    )
    assert need.max_results == 10
    assert need.include_historical is True


def test_memory_need_defaults():
    """MemoryNeed 默认值"""
    need = MemoryNeed()
    assert need.layers == []
    assert need.types == []
    assert need.max_results == 20
    assert need.include_historical is False
    assert need.keywords is None


def test_memory_need_max_results_bounds():
    """MemoryNeed.max_results 必须在 1~100 之间"""
    # 合法
    need = MemoryNeed(max_results=50)
    assert need.max_results == 50
    
    # 非法：0
    with pytest.raises(ValidationError):
        MemoryNeed(max_results=0)
    
    # 非法：>100
    with pytest.raises(ValidationError):
        MemoryNeed(max_results=101)


# ---------- MemoryBudget ----------
def test_memory_budget_valid():
    """MemoryBudget 合法构造"""
    budget = MemoryBudget(
        max_tokens=3000,
        max_identity=5,
        max_preferences=10,
        max_episodes=3,
        max_skills=5,
        policy_name="test_policy",
    )
    assert budget.max_tokens == 3000


def test_memory_budget_defaults():
    """MemoryBudget 默认值"""
    budget = MemoryBudget()
    assert budget.max_tokens == 2000
    assert budget.max_identity == 3
    assert budget.max_preferences == 5
    assert budget.max_episodes == 3
    assert budget.max_skills == 5
    assert budget.policy_name is None


def test_memory_budget_tokens_positive():
    """MemoryBudget.max_tokens 必须 >= 1"""
    with pytest.raises(ValidationError):
        MemoryBudget(max_tokens=0)
    
    # 合法
    budget = MemoryBudget(max_tokens=1)
    assert budget.max_tokens == 1


# ---------- UserDirective ----------
def test_user_directive_valid():
    """UserDirective 合法构造"""
    directive = UserDirective(
        type="forget",
        target="mem_123_abcdef123456",
        target_type="memory_id",
        scope="semantic",
        raw_text="忘记这个记忆",
        created_at=utc_now(),
    )
    assert directive.type == "forget"
    assert directive.target == "mem_123_abcdef123456"


def test_user_directive_do_not_remember():
    """UserDirective.do_not_remember 不需要 target"""
    directive = UserDirective(
        type="do_not_remember",
        raw_text="不要再记住这件事",
        created_at=utc_now(),
    )
    assert directive.type == "do_not_remember"


def test_user_directive_temporary():
    """UserDirective.temporary 不需要 target"""
    directive = UserDirective(
        type="temporary",
        raw_text="仅临时记住",
        created_at=utc_now(),
    )
    assert directive.type == "temporary"


def test_user_directive_correct_requires_target():
    """UserDirective.correct 必须提供 target"""
    with pytest.raises(ValidationError):
        UserDirective(
            type="correct",
            raw_text="纠正这个记忆",
            created_at=utc_now(),
            # target 缺失
        )


def test_user_directive_raw_text_nonempty():
    """UserDirective.raw_text 不能为空"""
    with pytest.raises(ValidationError):
        UserDirective(
            type="forget",
            target="mem_123",
            raw_text="",  # 空
            created_at=utc_now(),
        )


def test_user_directive_target_type_enum():
    """UserDirective.target_type 必须为合法枚举值"""
    # 合法
    directive = UserDirective(
        type="forget",
        target="mem_123",
        target_type="semantic_match",
        raw_text="测试",
        created_at=utc_now(),
    )
    assert directive.target_type == "semantic_match"
    
    # 非法
    with pytest.raises(ValidationError):
        UserDirective(
            type="forget",
            target="mem_123",
            target_type="invalid",  # type: ignore
            raw_text="测试",
            created_at=utc_now(),
        )


# ---------- ConversationTurn ----------
def test_conversation_turn_valid():
    """ConversationTurn 合法构造"""
    turn = ConversationTurn(
        role="user",
        content="我喜欢美式咖啡",
        message_id="msg_001",
        chat_id="chat_001",
        reply_to_message_id="msg_000",
        timestamp=utc_now(),
        metadata={"source": "test"},
    )
    assert turn.role == "user"
    assert turn.content == "我喜欢美式咖啡"
    assert turn.reply_to_message_id == "msg_000"


def test_conversation_turn_minimal():
    """ConversationTurn 最小结构（仅必填）"""
    turn = ConversationTurn(
        role="assistant",
        content="好的",
        message_id="msg_002",
        timestamp=utc_now(),
    )
    assert turn.chat_id is None
    assert turn.reply_to_message_id is None


def test_conversation_turn_role_enum():
    """ConversationTurn.role 必须为合法枚举值"""
    # 合法
    turn = ConversationTurn(
        role="system",
        content="系统消息",
        message_id="msg_003",
        timestamp=utc_now(),
    )
    assert turn.role == "system"
    
    # 非法
    with pytest.raises(ValidationError):
        ConversationTurn(
            role="admin",  # type: ignore
            content="test",
            message_id="msg_004",
            timestamp=utc_now(),
        )


def test_conversation_turn_content_nonempty():
    """ConversationTurn.content 不能为空"""
    with pytest.raises(ValidationError):
        ConversationTurn(
            role="user",
            content="",
            message_id="msg_005",
            timestamp=utc_now(),
        )


def test_conversation_turn_message_id_nonempty():
    """ConversationTurn.message_id 不能为空"""
    with pytest.raises(ValidationError):
        ConversationTurn(
            role="user",
            content="test",
            message_id="",
            timestamp=utc_now(),
        )


def test_conversation_turn_timestamp_utc():
    """ConversationTurn.timestamp 必须为 UTC"""
    naive = datetime(2026, 8, 13, 10, 0, 0)
    with pytest.raises(ValidationError):
        ConversationTurn(
            role="user",
            content="test",
            message_id="msg_006",
            timestamp=naive,
        )

# ========== T1.4: Condition 结构校验专项测试 ==========

def test_condition_single_with_non_string_key():
    """单条件中 key 为非字符串 -> ValidationError"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={"key": 123, "value": "客厅"})
    assert "字符串" in str(exc.value) or "str" in str(exc.value).lower()


def test_condition_single_with_non_string_value():
    """单条件中 value 为非字符串 -> ValidationError"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={"key": "place", "value": 456})
    assert "字符串" in str(exc.value) or "str" in str(exc.value).lower()


def test_condition_and_clause_key_non_string():
    """AND 组合中 clause.key 为非字符串 -> ValidationError"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={
            "operator": "AND",
            "clauses": [
                {"key": 123, "value": "v1"},
                {"key": "k2", "value": "v2"},
            ]
        })
    assert "字符串" in str(exc.value) or "str" in str(exc.value).lower()


def test_condition_and_clause_value_non_string():
    """AND 组合中 clause.value 为非字符串 -> ValidationError"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={
            "operator": "AND",
            "clauses": [
                {"key": "k1", "value": 456},
                {"key": "k2", "value": "v2"},
            ]
        })
    assert "字符串" in str(exc.value) or "str" in str(exc.value).lower()


def test_condition_empty_dict():
    """condition 为空 dict -> ValidationError"""
    with pytest.raises(ValidationError) as exc:
        make_minimal_memory(condition={})
    assert "空" in str(exc.value) or "empty" in str(exc.value).lower()


def test_condition_extra_field_in_single():
    """单条件中包含额外字段 -> ValidationError（已在 test_condition_nested_clause 中类似，但明确测试）"""
    with pytest.raises(ValidationError):
        make_minimal_memory(condition={"key": "place", "value": "客厅", "extra": "should_fail"})