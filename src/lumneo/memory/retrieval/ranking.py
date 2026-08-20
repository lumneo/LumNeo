# src/lumneo/memory/retrieval/ranking.py
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# ============================================================
# Decay
# ============================================================
def calculate_decay(
    last_accessed: Optional[datetime],
    created_at: datetime,
    decay_coefficient: float = 0.05,
) -> float:
    if last_accessed is None:
        return 1.0

    now = datetime.now(timezone.utc)
    delta = now - last_accessed
    days = delta.total_seconds() / 86400.0
    return 1.0 / (1.0 + days * decay_coefficient)


# ============================================================
# Final Score
# ============================================================
def compute_final_score(
    relevance: float,
    importance: int,
    confidence: float,
    decay: float,
    boost: float = 1.0,
    alpha: float = 0.65,
) -> float:
    importance_norm = importance / 5.0
    rank_part = importance_norm * confidence * decay
    base_score = alpha * relevance + (1.0 - alpha) * rank_part
    return base_score * boost


# ============================================================
# Intent Boost
# ============================================================
def calculate_intent_boost(
    memory,
    need,
) -> float:
    """
    Context intent boost

    根据 MemoryNeed 提升：
    - layer
    - type
    - historical
    - condition
    - correction
    """
    if need is None:
        return 1.0

    boost = 1.0

    # --------------------------
    # Layer
    # --------------------------
    if getattr(need, "layers", None):
        if memory.layer in need.layers:
            boost *= 1.5

    # --------------------------
    # Type
    # --------------------------
    if getattr(need, "types", None):
        if memory.type in need.types:
            boost *= 1.3

    # --------------------------
    # Historical
    # --------------------------
    if getattr(need, "include_historical", False):
        if memory.status in ("superseded", "archived", "stale"):
            boost *= 1.5

    # --------------------------
    # Condition
    # --------------------------
    keywords = getattr(need, "keywords", [])
    condition = getattr(memory, "condition", None)
    if condition:
        condition_text = str(condition)
        for kw in keywords:
            if kw in condition_text:
                boost *= 1.4
                break

    # --------------------------
    # Correction
    # --------------------------
    if getattr(memory, "correction_target", None):
        boost *= 1.3

    return boost


# ============================================================
# Semantic Boost
# ============================================================
def calculate_semantic_boost(
    memory,
    need,
) -> float:
    if need is None:
        return 1.0

    boost = 1.0

    # ==================================================
    # Identity Query
    # ==================================================
    if "identity" in getattr(need, "layers", []):
        text = " ".join([
            str(getattr(memory, "subject", "")),
            str(getattr(memory, "predicate", "")),
            str(getattr(memory, "object", "")),
            str(getattr(memory, "content", "")),
        ])

        # 用户是谁，更关注职业/身份
        strong_identity_words = [
            "工程师", "程序员", "开发",
            "职业", "身份", "姓名", "名字",
        ]

        for word in strong_identity_words:
            if word in text:
                boost *= 2.0
                break

        # 生日、年龄等属于弱身份属性
        weak_identity_words = [
            "生日", "年龄", "出生",
            "地点", "住",
        ]

        for word in weak_identity_words:
            if word in text:
                boost *= 0.4
                break

    # ==================================================
    # Comparison / Generic Query
    # ==================================================

    query_text = " ".join(
        getattr(need, "keywords", [])
    )


    if any(
        x in query_text
        for x in [
            "还是",
            "和",
            "同时",
            "有没有",
            "区别",
        ]
    ):

        predicate = (
            memory.predicate
            or ""
        )

        if predicate == "generic_statement":

            boost *= 2.5

    # ==================================================
    # Mixed identity + preference query
    # ==================================================

    keywords = getattr(
        need,
        "keywords",
        []
    )

    keyword_text = "".join(keywords)


    # identity
    if any(
        x in keyword_text
        for x in [
            "人",
            "谁",
            "身份",
            "职业",
            "名字",
        ]
    ):

        if memory.layer == "identity":
            boost *= 2.0


    # preference
    if any(
        x in keyword_text
        for x in [
            "喜欢",
            "偏好",
        ]
    ):

        if memory.type == "preference":
            boost *= 2.0


    # ==================================================
    # Skill Query
    # ==================================================
    if (
        "skill" in getattr(need, "types", [])
        or "procedural" in getattr(need, "layers", [])
    ):
        text = " ".join([
            str(getattr(memory, "object", "")),
            str(getattr(memory, "content", "")),
        ])

        skill_words = [
            "会", "使用", "掌握",
            "编程", "开发",
        ]

        for word in skill_words:
            if word in text:
                boost *= 2.0
                break

    return boost


# ============================================================
# Main Ranking
# ============================================================
def compute_scores(
    memory_ids: List[str],
    relevance_map: Dict[str, float],
    memories_map: Dict[
        str,
        Tuple[
            float,
            int,
            Optional[datetime],
            datetime,
        ],
    ],
    memories_object_map=None,
    need=None,
    alpha: float = 0.65,
    dynamic_alpha_threshold: float = 0.5,
    dynamic_alpha_fallback: float = 0.4,
) -> Dict[str, float]:
    if not memory_ids:
        return {}

    # =====================================================
    # Dynamic Alpha
    # =====================================================
    strengths = []
    for mid, rel in relevance_map.items():
        if 0 < rel < 1:
            strength = (0.5 * rel) / (1 - rel)
            strengths.append(strength)
        elif rel >= 1:
            strengths.append(float("inf"))

    max_strength = max(strengths) if strengths else 0.0
    if max_strength < dynamic_alpha_threshold:
        alpha = dynamic_alpha_fallback

    # =====================================================
    # Calculate
    # =====================================================
    result = {}

    for mid in memory_ids:
        relevance = relevance_map.get(mid, 0.0)
        confidence, importance, last_accessed, created_at = memories_map[mid]

        decay = calculate_decay(last_accessed, created_at)

        memory = None
        if memories_object_map:
            memory = memories_object_map.get(mid)

        intent_boost = 1.0
        semantic_boost = 1.0

        if memory:
            intent_boost = calculate_intent_boost(memory, need)
            semantic_boost = calculate_semantic_boost(memory, need)

        total_boost = intent_boost * semantic_boost

        score = compute_final_score(
            relevance,
            importance,
            confidence,
            decay,
            total_boost,
            alpha,
        )

        result[mid] = score

    return result