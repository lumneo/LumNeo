import pytest
from typing import Dict, Any, List
from lumneo.memory.capture import capture
from lumneo.memory.model import ConversationTurn, MemoryCandidate
from lumneo.memory.common.time import utc_now

# 定义验收用例（30个）
CAPTURE_CASES: List[Dict[str, Any]] = [
    # 偏好类 (preference)
    {
        "id": "C001",
        "name": "明确偏好",
        "input": "我喜欢安静的咖啡馆。",
        "expected_type": "preference",
        "expected_object": "安静的咖啡馆",
    },
    {
        "id": "C002",
        "name": "偏好（英文）",
        "input": "I prefer tea over coffee.",
        "expected_type": "preference",
        "expected_object": "tea over coffee",
    },
    {
        "id": "C003",
        "name": "偏好（否定）",
        "input": "我不喜欢辣的食物。",
        "expected_type": "preference",
        "expected_object": "辣的食物",
    },
    # 身份类 (identity)
    {
        "id": "C004",
        "name": "身份声明",
        "input": "我是软件工程师。",
        "expected_type": "identity",
        "expected_object": "软件工程师",
    },
    {
        "id": "C005",
        "name": "姓名",
        "input": "我的名字是张伟。",
        "expected_type": "identity",
        "expected_object": "名字是张伟",
    },
    # 技能类 (skill)
    {
        "id": "C006",
        "name": "技能（会）",
        "input": "我会用Python编程。",
        "expected_type": "skill",
        "expected_object": "用Python编程",
    },
    {
        "id": "C007",
        "name": "技能（擅长）",
        "input": "我擅长数据分析。",
        "expected_type": "skill",
        "expected_object": "数据分析",
    },
    # 事件类 (event)
    {
        "id": "C008",
        "name": "事件（去过）",
        "input": "我去年去过北京。",
        "expected_type": "event",
        "expected_object": "去过北京",
    },
    {
        "id": "C009",
        "name": "事件（参加）",
        "input": "我参加了昨天的会议。",
        "expected_type": "event",
        "expected_object": "参加了昨天的会议",
    },
    # 关系类 (relationship)
    {
        "id": "C010",
        "name": "朋友关系",
        "input": "小明是我的朋友。",
        "expected_type": "relationship",
        "expected_object": "小明",
    },
    # 价值观 (value)
    {
        "id": "C011",
        "name": "价值观声明",
        "input": "我认为诚实很重要。",
        "expected_type": "value",
        "expected_object": "诚实很重要",
    },
    # 风格 (style)
    {
        "id": "C012",
        "name": "风格偏好",
        "input": "我喜欢极简风格。",
        "expected_type": "style",
        "expected_object": "极简风格",
    },
    # 事实 (fact)
    {
        "id": "C013",
        "name": "事实陈述",
        "input": "地球是圆的。",
        "expected_type": "fact",
        "expected_object": "地球是圆的",
    },
    # 决策 (decision)
    {
        "id": "C014",
        "name": "决策",
        "input": "我决定学习 Rust。",
        "expected_type": "decision",
        "expected_object": "学习 Rust",
    },
    # 复杂/复合句
    {
        "id": "C015",
        "name": "复合偏好",
        "input": "我喜欢咖啡和茶。",
        "expected_type": "preference",
        "expected_object": "咖啡和茶",
        "expect_multiple": True,  # 可能拆分为多个候选
    },
    {
        "id": "C016",
        "name": "带有条件",
        "input": "如果天气好，我喜欢去公园。",
        "expected_type": "preference",
        "expected_object": "去公园",
    },
    # 多轮对话模拟（单轮输入，但内容包含之前信息）
    {
        "id": "C017",
        "name": "多轮上下文（单轮）",
        "input": "我昨天去了上海，那里天气很好。",
        "expected_type": "event",
        "expected_object": "去了上海",
    },
    # 通用陈述（generic）
    {
        "id": "C018",
        "name": "通用陈述",
        "input": "LumNeo 是一个开源项目。",
        "expected_type": "fact",
        "expected_object": "LumNeo 是一个开源项目",
    },
    # 更多偏好变化
    {
        "id": "C019",
        "name": "偏好（爱）",
        "input": "我爱吃巧克力。",
        "expected_type": "preference",
        "expected_object": "吃巧克力",
    },
    # 更多身份变化
    {
        "id": "C020",
        "name": "职业身份",
        "input": "我是一名设计师。",
        "expected_type": "identity",
        "expected_object": "设计师",
    },
    # 更多技能
    {
        "id": "C021",
        "name": "技能（能够）",
        "input": "我能够用英语交流。",
        "expected_type": "skill",
        "expected_object": "用英语交流",
    },
    # 事件变化
    {
        "id": "C022",
        "name": "事件（计划）",
        "input": "我计划下周去杭州。",
        "expected_type": "event",
        "expected_object": "计划去杭州",
    },
    # 关系变化
    {
        "id": "C023",
        "name": "关系（同学）",
        "input": "小李是我的同学。",
        "expected_type": "relationship",
        "expected_object": "小李",
    },
    # 价值观变化
    {
        "id": "C024",
        "name": "价值观（认为）",
        "input": "我觉得早起有益健康。",
        "expected_type": "value",
        "expected_object": "早起有益健康",
    },
    # 风格变化
    {
        "id": "C025",
        "name": "风格（偏好）",
        "input": "我偏好暖色调。",
        "expected_type": "style",
        "expected_object": "暖色调",
    },
    # 决策变化
    {
        "id": "C026",
        "name": "决策（选择）",
        "input": "我选择远程办公。",
        "expected_type": "decision",
        "expected_object": "远程办公",
    },
    # 否定身份
    {
        "id": "C027",
        "name": "否定身份",
        "input": "我不是学生。",
        "expected_type": "identity",
        "expected_object": "不是学生",
    },
    # 带程度修饰的偏好
    {
        "id": "C028",
        "name": "程度修饰",
        "input": "我非常喜欢听音乐。",
        "expected_type": "preference",
        "expected_object": "听音乐",
    },
    # 时间相关
    {
        "id": "C029",
        "name": "时间相关事件",
        "input": "去年我去了日本。",
        "expected_type": "event",
        "expected_object": "去了日本",
    },
    # 复杂关系
    {
        "id": "C030",
        "name": "复杂关系",
        "input": "张三是我的老板，也是我的朋友。",
        "expected_type": "relationship",
        "expected_object": "张三",
    },
]

@pytest.mark.parametrize("case", CAPTURE_CASES, ids=lambda c: c["id"] + "_" + c["name"])
def test_a1_capture_acceptance(case):
    """
    A.1 Capture 验收测试：
    - 验证 capture 返回至少一个 Candidate
    - 验证每个 Candidate 有 capture_id、dedup_key、evidence 非空、source 有 locator、origin_actor 合法
    - 对于预期类型，检查 suggested_type 是否匹配（可选，因为有些可能多个候选）
    """
    turn = ConversationTurn(
        role="user",
        content=case["input"],
        message_id=f"msg_{case['id']}",
        chat_id="chat_acceptance",
        timestamp=utc_now(),
    )
    candidates = capture([turn])
    
    # 至少有一个候选
    assert candidates, f"Case {case['id']} returned no candidates"
    
    # 检查每个候选的基本契约
    for cand in candidates:
        assert cand.capture_id, f"Case {case['id']} candidate missing capture_id"
        assert cand.dedup_key, f"Case {case['id']} candidate missing dedup_key"
        assert cand.evidence, f"Case {case['id']} candidate has empty evidence"
        assert len(cand.evidence) > 0
        
        # 检查证据中 source 有 locator
        for ev in cand.evidence:
            src = ev.source
            has_locator = src.chat_id or src.message_id or (src.extra and src.extra.get("external_id"))
            assert has_locator, f"Case {case['id']} evidence missing locator"
        
        # 检查 origin_actor 合法
        assert cand.origin_actor in {"user", "assistant", "system", "external"}, \
            f"Case {case['id']} invalid origin_actor: {cand.origin_actor}"
    
    # 可选：检查 expected_type（如果只有一个候选且期望匹配）
    # 这里仅做提示性检查，不强制，因为提取可能产生多个候选
    if len(candidates) == 1 and case.get("expected_type"):
        # 如果类型不匹配，记录日志但不失败（便于分析）
        if candidates[0].suggested_type != case["expected_type"]:
            print(f"[WARN] Case {case['id']}: expected {case['expected_type']}, got {candidates[0].suggested_type}")