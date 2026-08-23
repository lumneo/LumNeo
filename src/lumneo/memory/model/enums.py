# src/lumneo/memory/model/enums.py
"""MemoryOS 枚举定义（Contract §3）"""
from typing import Literal

# 正交分类层
MemoryLayer = Literal["identity", "episodic", "semantic", "procedural"]

# 记忆类型
MemoryType = Literal[
    "fact",
    "preference",
    "decision",
    "relationship",
    "event",
    "value",
    "style",
    "skill"
]

# 生命周期状态
MemoryStatus = Literal[
    "candidate",
    "active",
    "superseded",
    "archived",
    "stale",
    "rejected",
    "needs_review"
]

# 证据类型
EvidenceType = Literal[
    "explicit_statement",
    "confirmation",
    "repeated_observation",
    "behavioral",
    "inference"
]

# 记忆创建语义来源
MemoryOrigin = Literal[
    "explicit_user",
    "assistant_inferred",
    "system_generated",
    "external_import"
]

# 证据原始信息来自谁
EvidenceActor = Literal["user", "assistant", "system", "external"]

# 用户指令类型
DirectiveType = Literal["forget", "do_not_remember", "temporary", "correct"]

# 指令目标类型
DirectiveTargetType = Literal["memory_id", "semantic_match", "predicate_match"]

# 隐私等级
PrivacyLevel = Literal["public", "private", "secret"]

# 对话角色
ConversationRole = Literal["user", "assistant", "system"]

# 评估模式
MappingMode = Literal["strict", "loose"]