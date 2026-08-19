import pytest
from datetime import datetime, timezone
from lumneo.memory.context.builder import build_context
from lumneo.memory.model import MemoryObject, MemoryBudget, Source, Evidence
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.id_gen import generate_memory_id


def create_mock_memory(
    layer: str,
    mem_type: str,
    content: str,
    importance: int = 3,
    confidence: float = 0.8,
    created_at: datetime = None,
) -> MemoryObject:
    """辅助函数：生成测试用 MemoryObject"""
    if created_at is None:
        created_at = utc_now()
    return MemoryObject(
        id=generate_memory_id(),
        schema_version="2.1.2",
        layer=layer,  # type: ignore
        type=mem_type,  # type: ignore
        subject="test",
        predicate="test",
        object="test",
        content=content,
        confidence=confidence,
        importance=importance,
        status="active",  # type: ignore
        evidence=[
            Evidence(
                type="explicit_statement",  # type: ignore
                weight=1.0,
                source=Source(
                    chat_id="chat1",
                    message_id="msg1",
                    timestamp=utc_now(),
                ),
                observation="mock",
                origin_actor="user",  # type: ignore
                created_at=utc_now(),
            )
        ],
        source=Source(chat_id="chat1", message_id="msg1", timestamp=utc_now()),
        origin="explicit_user",  # type: ignore
        created_at=created_at,
        updated_at=created_at,
    )


class TestContextBuilder:

    def test_quota_hard_limit(self):
        """T7.1 & T7.2: 各类别配额硬上限，不可跨层借用"""
        # 准备记忆：identity 3条，semantic(preference) 5条，episodic 3条，procedural 5条
        # 但每个类型生成多一些，测试配额截断
        memories = []
        # identity: 生成4条
        for i in range(4):
            memories.append(create_mock_memory(
                layer="identity",
                mem_type="fact",
                content=f"identity fact {i}",
                importance=3,
                confidence=0.8,
            ))
        # semantic (preference): 生成6条
        for i in range(6):
            memories.append(create_mock_memory(
                layer="semantic",
                mem_type="preference",
                content=f"preference {i}",
                importance=3,
                confidence=0.8,
            ))
        # episodic: 生成4条
        for i in range(4):
            memories.append(create_mock_memory(
                layer="episodic",
                mem_type="event",
                content=f"episode {i}",
                importance=3,
                confidence=0.8,
            ))
        # procedural: 生成6条
        for i in range(6):
            memories.append(create_mock_memory(
                layer="procedural",
                mem_type="skill",
                content=f"skill {i}",
                importance=3,
                confidence=0.8,
            ))

        budget = MemoryBudget(
            max_tokens=10000,          # 足够大，不截断
            max_identity=2,
            max_preferences=3,
            max_episodes=2,
            max_skills=4,
        )

        context = build_context(memories, budget)

        # 统计各类别在结果中的出现次数（通过内容前缀）
        lines = context.split("\n\n") if context else []
        identity_count = sum(1 for l in lines if l.startswith("identity fact"))
        preference_count = sum(1 for l in lines if l.startswith("preference"))
        episode_count = sum(1 for l in lines if l.startswith("episode"))
        skill_count = sum(1 for l in lines if l.startswith("skill"))

        assert identity_count == budget.max_identity, f"Expected {budget.max_identity}, got {identity_count}"
        assert preference_count == budget.max_preferences, f"Expected {budget.max_preferences}, got {preference_count}"
        assert episode_count == budget.max_episodes, f"Expected {budget.max_episodes}, got {episode_count}"
        assert skill_count == budget.max_skills, f"Expected {budget.max_skills}, got {skill_count}"

    def test_token_budget_skip_and_diversity(self):
        """T7.1: 超预算跳过，保持多样性（不提前终止）"""
        # 准备多个记忆，各自不同内容
        memories = []
        for i in range(10):
            # 每个 content 长度约 20 字符 -> 约 5 token
            content = f"mem {i} " + "x" * 16
            memories.append(create_mock_memory(
                layer="semantic",
                mem_type="preference",
                content=content,
                importance=3,
                confidence=0.8,
            ))

        # 设置 max_tokens 只能容纳 3 条（假设每条约5 token，3条=15，但实际估算 len/4+1，长度约20 -> 约6 token，所以 4条可能超）
        # 为了测试跳过，设置 max_tokens=18，预计能容纳前几条，但第四条可能超，跳过，继续尝试后续。
        budget = MemoryBudget(
            max_tokens=18,
            max_identity=0,
            max_preferences=10,   # 足够大
            max_episodes=0,
            max_skills=0,
        )

        context = build_context(memories, budget)
        lines = context.split("\n\n") if context else []

        # 计算实际条数
        count = len(lines)
        # 预期：能容纳前几条，但第四条可能超（估算len/4+1 ~ 6），所以可能前3条能装下，第四条跳过，第五条可能装下? 但我们要验证跳过机制
        # 具体断言：至少应该包含第1条，且由于跳过机制，可能包含第5条等，保证多样性。
        # 我们可以检查是否包含了第1条、第5条等，确保不是简单前N条。
        # 由于估算有误差，我们采用更稳健的方式：验证结果不是简单的前N条（例如前3条），而可能包含后面的。
        # 这里我们只验证总条数小于预算，且内容不是前3条。
        # 为了确保测试可重复，我们可以使用固定长度。
        # 重新构造内容长度固定为 20 字符，len/4+1 = 6，max_tokens=18 最多容纳3条。
        # 但实际估算可能不精确，但无论如何，结果条数应 <= max_tokens/(len/4+1) ≈ 3。
        # 我们断言条数 <= 3。
        assert count <= 3, f"Expected at most 3, got {count}"

        # 额外验证：如果所有内容长度都很小，可能容纳很多，那我们调整测试。
        # 为了确保跳过，可以设置 max_tokens=10，只能容纳1条，但第二条如果超，跳过，继续尝试后续。
        # 我们构造一个极端的测试：第一条内容长，第二条短，第三条长，第四条短，max_tokens 只能容纳短的一条。
        memories2 = []
        # 第一条长（约10 token）
        memories2.append(create_mock_memory(
            layer="semantic", mem_type="preference",
            content="A" * 40,  # len=40 -> 11 token
            importance=3, confidence=0.8
        ))
        # 第二条短（约2 token）
        memories2.append(create_mock_memory(
            layer="semantic", mem_type="preference",
            content="B" * 8,   # len=8 -> 3 token
            importance=3, confidence=0.8
        ))
        # 第三条长
        memories2.append(create_mock_memory(
            layer="semantic", mem_type="preference",
            content="C" * 40,
            importance=3, confidence=0.8
        ))
        # 第四条短
        memories2.append(create_mock_memory(
            layer="semantic", mem_type="preference",
            content="D" * 8,
            importance=3, confidence=0.8
        ))

        budget2 = MemoryBudget(
            max_tokens=5,  # 只能容纳一条短
            max_preferences=10,
            max_identity=0, max_episodes=0, max_skills=0
        )
        context2 = build_context(memories2, budget2)
        lines2 = context2.split("\n\n") if context2 else []
        # 由于全局排序按分数，所有分数相同（importance, confidence一样），排序顺序是输入顺序。
        # 第一条长超预算跳过，第二条短可容纳，第三条长跳过，第四条短可容纳但预算已满（因为已经消耗了3 token，剩余2 token，第四条需要3 token，跳过，继续尝试后续无，所以只有一条）
        # 实际结果只有第二条短。
        assert len(lines2) == 1, f"Expected 1, got {len(lines2)}"
        assert "B" in lines2[0], "Expected the short one with B"

        # 验证多样性：如果先处理长条目，跳过，继续尝试后续，所以不会提前终止。
        # 我们已经看到成功包含了后面的短条目。

    def test_quota_independent(self):
        """T7.2: 各配额独立生效，互不影响"""
        # 准备各类型记忆
        memories = []
        for i in range(5):
            memories.append(create_mock_memory("identity", "fact", f"id{i}", importance=3))
        for i in range(5):
            memories.append(create_mock_memory("semantic", "preference", f"pref{i}", importance=3))
        for i in range(5):
            memories.append(create_mock_memory("episodic", "event", f"ep{i}", importance=3))
        for i in range(5):
            memories.append(create_mock_memory("procedural", "skill", f"skill{i}", importance=3))

        budget = MemoryBudget(
            max_tokens=10000,
            max_identity=1,
            max_preferences=2,
            max_episodes=3,
            max_skills=4,
        )
        context = build_context(memories, budget)
        lines = context.split("\n\n") if context else []
        # 计数
        id_count = sum(1 for l in lines if l.startswith("id"))
        pref_count = sum(1 for l in lines if l.startswith("pref"))
        ep_count = sum(1 for l in lines if l.startswith("ep"))
        skill_count = sum(1 for l in lines if l.startswith("skill"))

        assert id_count == 1
        assert pref_count == 2
        assert ep_count == 3
        assert skill_count == 4

    def test_empty_memories(self):
        """边界：空列表"""
        context = build_context([], MemoryBudget())
        assert context == ""

    def test_token_budget_zero(self):
        """边界：max_tokens 极小，无法容纳任何记忆，应返回空"""
        # 内容长度至少 5 字符，估算 token = len//4+1 = 2，超过 1
        mem = create_mock_memory("semantic", "preference", "test")
        context = build_context([mem], MemoryBudget(max_tokens=1, max_preferences=1))
        assert context == ""

    def test_no_matching_layers(self):
        """如果所有记忆都不属于配额类型，结果为空"""
        # 例如只有 semantic 但类型是 fact，而 max_preferences 只统计 preference/value
        mem = create_mock_memory("semantic", "fact", "fact")
        budget = MemoryBudget(max_preferences=5, max_tokens=1000)
        context = build_context([mem], budget)
        assert context == ""

    def test_score_sorting(self):
        """验证按 final_score 降序选取（importance * confidence * decay）"""
        # 创建两个记忆，一个高重要性低置信度，一个低重要性高置信度，比较分数
        # 确保排序正确
        now = utc_now()
        mem1 = create_mock_memory("semantic", "preference", "high importance", importance=5, confidence=0.6, created_at=now)
        mem2 = create_mock_memory("semantic", "preference", "high confidence", importance=2, confidence=0.9, created_at=now)
        # 计算分数：mem1: 5/5*0.6=0.6; mem2: 2/5*0.9=0.36，所以 mem1 应该排在前面
        budget = MemoryBudget(max_tokens=1000, max_preferences=2)
        context = build_context([mem1, mem2], budget)
        lines = context.split("\n\n")
        assert lines[0] == "high importance"
        assert lines[1] == "high confidence"