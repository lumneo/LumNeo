# src/lumneo/memory/retrieval/intent.py

from typing import Optional, Dict, Any, List
from lumneo.memory.model import MemoryNeed, MemoryLayer, MemoryType

def analyze_intent(
    query: str,
    context: Optional[Dict[str, Any]] = None
) -> MemoryNeed:
    query_lower = query.lower()
    include_historical = False
    layers: List[MemoryLayer] = []
    types: List[MemoryType] = []
    subject_hint: Optional[str] = None

    # ----- 历史/纠正/冲突关键词 -----
    history_keywords = ["之前", "曾经", "过去", "历史", "prior", "history", "上次", "以前", "早先"]
    correct_keywords = ["纠正", "更正", "不对", "不是", "实际上", "actually", "correct", "修正"]
    conflict_keywords = ["冲突", "矛盾", "不一致", "conflict", "contradict"]

    if any(kw in query_lower for kw in history_keywords):
        include_historical = True
    if any(kw in query_lower for kw in correct_keywords):
        include_historical = True
    if any(kw in query_lower for kw in conflict_keywords):
        include_historical = True

    # ----- 身份层检测 -----
    identity_exact = ["我是谁", "我的身份", "我的名字", "我的职业"]
    if any(kw in query_lower for kw in identity_exact):
        layers.append("identity")
    elif ("是什么" in query_lower or "是谁" in query_lower) and "我的" in query_lower:
        layers.append("identity")

    # ----- 偏好类型检测（区分肯定/否定）-----
    # 只有当查询包含"喜欢"且不包含"不喜欢"和"更喜欢"时才触发
    has_like = "喜欢" in query_lower
    has_dislike = "不喜欢" in query_lower
    has_prefer_like = "更喜欢" in query_lower
    # 同时检测"偏好"、"prefer"、"like"（但like可能重复）
    if (has_like and not has_dislike and not has_prefer_like) or \
       any(kw in query_lower for kw in ["偏好", "prefer", "like"]):
        types.append("preference")

    # 关键词
    keywords = [query] if query.strip() else []

    return MemoryNeed(
        layers=layers,
        types=types,
        keywords=keywords,
        subject_hint=subject_hint,
        max_results=20,
        scope_filter=None,
        include_historical=include_historical
    )