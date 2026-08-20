# src/lumneo/memory/retrieval/intent.py

from typing import Optional, Dict, Any, List

from lumneo.memory.model import MemoryNeed, MemoryLayer, MemoryType

# 尝试引入 jieba
try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("WARNING: jieba not installed, keyword extraction will be basic.")


# ==========================================================
# Stop Words
#
# 注意：
# 这里不能删除所有功能词。
#
# 例如：
# "会什么"
# "会" 本身代表 skill intent。
#
# 所以不要简单把所有助词过滤掉。
# ==========================================================

STOP_WORDS = {
    "什么", "哪些", "怎么", "为什么",
    "之前", "以前", "过去", "历史",
    "我的", "我", "的",
    "吗", "呢", "了", "吧", "啊", "呀", "哦",
    "请", "帮", "给", "把", "被", "让", "使",
    "从", "到", "在",
    "是", "有",
    "这", "那", "个", "些",
    "都", "也", "还", "就",
    "要", "能", "可以", "可能", "应该",
    "但", "却", "而",
    "并且", "或者", "不过",
    "因为", "所以", "如果", "那么",
    # 历史英文
    "prior", "history", "previous", "past", "before",
    "曾经", "早先",
}

# 单字通常噪声较高，但这些字本身携带明确的检索意图。
# 尤其是混合查询不能用 layer/type 做硬过滤，只能把意图信号交给 ranking。
INTENT_SINGLE_CHAR_KEYWORDS = {"会", "人", "谁"}


def extract_keywords(query: str) -> List[str]:
    """
    提取 Retrieval keyword。

    注意：
    keyword 只是用于召回，
    不是 MemoryType 判断。

    例如：
    "喜欢的编程语言"
    keyword:
        喜欢
        编程
        语言
    不应该直接变成:
        type=preference
    """
    if not query or not query.strip():
        return []

    if HAS_JIEBA:
        words = jieba.lcut(query)
    else:
        words = query.split()

    keywords = []
    for word in words:
        word = word.strip()
        if not word:
            continue

        # 保留携带检索意图的单字。
        if word in STOP_WORDS:
            if word not in INTENT_SINGLE_CHAR_KEYWORDS:
                continue

        if len(word) < 2 and word not in INTENT_SINGLE_CHAR_KEYWORDS:
            continue

        keywords.append(word)

    return list(dict.fromkeys(keywords))


def analyze_intent(
    query: str,
    context: Optional[Dict[str, Any]] = None
) -> MemoryNeed:
    query_lower = query.lower().strip()

    include_historical = False
    layers: List[MemoryLayer] = []
    types: List[MemoryType] = []
    subject_hint: Optional[str] = None

    # ======================================================
    # Historical
    # ======================================================
    history_keywords = [
        "之前", "曾经", "过去", "历史", "上次", "以前", "早先",
        "prior", "history", "previous", "past",
    ]
    correction_keywords = [
        "纠正", "更正", "不对", "不是", "实际上", "修正",
        "actually", "correct",
    ]
    conflict_keywords = [
        "冲突", "矛盾", "不一致",
        "conflict", "contradict",
    ]

    if any(kw in query_lower for kw in history_keywords):
        include_historical = True
    if any(kw in query_lower for kw in correction_keywords):
        include_historical = True
    if any(kw in query_lower for kw in conflict_keywords):
        include_historical = True

    # ======================================================
    # Intent detection
    #
    # 原则：
    # 只有非常确定的查询，才限制 layer/type。
    # 否则让 ranking 决定。
    # ======================================================
    identity_query = any(
        word in query_lower
        for word in [
            "我是谁", "用户是谁", "我的身份",
            "我的名字", "我的职业", "什么人",
            "哪类人",
        ]
    )
    skill_query = any(
        word in query_lower
        for word in [
            "会什么", "会哪些", "技能", "擅长",
            "编程语言", "能力",
        ]
    )
    preference_query = any(
        word in query_lower
        for word in [
            "偏好", "喜欢什么", "喜欢的",
        ]
    )

    # ------------------------------------------------------
    # 混合查询
    #
    # 例如:
    # 我是什么人，喜欢什么
    # 不能生成:
    #   layer=identity
    #   type=preference
    # 因为这是 AND，会导致所有数据被过滤。
    # ------------------------------------------------------
    mixed_query = identity_query and preference_query

    if mixed_query:
        # layer/type 在 Repository 中是 AND 硬过滤。混合查询若限制任一维度，
        # 都会在 ranking 前丢失另一类目标记忆。
        pass
    elif identity_query:
        layers.append("identity")
    elif skill_query:
        layers.append("procedural")
        types.append("skill")
    elif preference_query:
        types.append("preference")

    # ======================================================
    # Keywords
    # ======================================================
    keywords = extract_keywords(query)

    return MemoryNeed(
        layers=layers,
        types=types,
        keywords=keywords,
        subject_hint=subject_hint,
        max_results=20,
        scope_filter=None,
        include_historical=include_historical,
    )
