# src/lumneo/memory/model/auxiliary.py
"""辅助结构（Contract §2.4）"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import AwareDatetime

from .enums import (
    MemoryLayer,
    MemoryType,
    PrivacyLevel,
    DirectiveType,
    DirectiveTargetType,
    ConversationRole,
)


class Source(BaseModel):
    """来源信息，必须至少包含一个 locator"""
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: AwareDatetime = Field(..., description="事件发生时间 (UTC)")  # 改为 AwareDatetime
    channel: Optional[str] = None
    extra: Optional[dict[str, Any]] = Field(
        default=None,
        description="受控扩展字段，仅允许 external_id, import_source, provider"
    )

    @model_validator(mode="after")
    def validate_has_locator(self) -> "Source":
        """至少存在一个有效 locator"""
        has_locator = any([
            self.chat_id is not None,
            self.message_id is not None,
            self.extra and self.extra.get("external_id") is not None,
        ])
        if not has_locator:
            raise ValueError("Source 必须至少包含一个 locator: chat_id, message_id, 或 extra.external_id")
        return self

    @field_validator("extra")
    @classmethod
    def validate_extra_keys(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            allowed_keys = {"external_id", "import_source", "provider"}
            for key in v.keys():
                if key not in allowed_keys:
                    raise ValueError(f"extra 中不允许键 '{key}'，仅允许 {allowed_keys}")
        return v

    model_config = {"extra": "forbid"}


class PrivacyInfo(BaseModel):
    level: PrivacyLevel
    reason: Optional[str] = None

    model_config = {"extra": "forbid"}


class MemoryNeed(BaseModel):
    """检索需求结构"""
    layers: list[MemoryLayer] = Field(default_factory=list)
    types: list[MemoryType] = Field(default_factory=list)
    keywords: Optional[list[str]] = None
    subject_hint: Optional[str] = None
    max_results: int = Field(default=20, ge=1, le=100)
    scope_filter: Optional[dict[str, Any]] = None
    condition_filter: Optional[dict[str, Any]] = None
    include_historical: bool = False

    @field_validator("condition_filter")
    @classmethod
    def validate_condition_filter(
        cls,
        value: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        if not value:
            raise ValueError("condition_filter 不能为空 dict")

        if "key" in value and "value" in value:
            if set(value) != {"key", "value"}:
                raise ValueError("单条件只允许 key 和 value 字段")
            if not isinstance(value["key"], str) or not isinstance(
                value["value"], str
            ):
                raise ValueError("condition_filter key/value 必须为字符串")
            return value

        if value.get("operator") == "AND":
            if set(value) != {"operator", "clauses"}:
                raise ValueError("AND 只允许 operator 和 clauses 字段")
            clauses = value.get("clauses")
            if not isinstance(clauses, list) or not clauses:
                raise ValueError("AND 必须包含非空 clauses")
            if len(clauses) > 5:
                raise ValueError("AND clauses 数量不能超过 5")
            for clause in clauses:
                if not isinstance(clause, dict) or set(clause) != {"key", "value"}:
                    raise ValueError("每个 clause 必须仅包含 key 和 value")
                if not isinstance(clause["key"], str) or not isinstance(
                    clause["value"], str
                ):
                    raise ValueError("clause key/value 必须为字符串")
            return value

        if "operator" in value:
            raise ValueError("condition_filter 仅支持 AND")
        raise ValueError("condition_filter 结构非法")

    model_config = {"extra": "forbid"}


class MemoryBudget(BaseModel):
    """上下文预算"""
    max_tokens: int = Field(default=2000, ge=1)
    max_identity: int = Field(default=3, ge=0)
    max_preferences: int = Field(default=5, ge=0)
    max_episodes: int = Field(default=3, ge=0)
    max_skills: int = Field(default=5, ge=0)
    policy_name: Optional[str] = None

    model_config = {"extra": "forbid"}


class UserDirective(BaseModel):
    """用户显式指令"""
    type: DirectiveType
    target: Optional[str] = None
    target_type: Optional[DirectiveTargetType] = None
    scope: Optional[str] = None
    raw_text: str = Field(..., min_length=1)
    created_at: AwareDatetime = Field(..., description="指令创建时间 (UTC)")  # 改为 AwareDatetime

    @model_validator(mode="after")
    def validate_target(self) -> "UserDirective":
        if self.type in {"forget", "correct"} and not self.target:
            raise ValueError(f"指令类型 '{self.type}' 必须提供 target")
        return self

    model_config = {"extra": "forbid"}


class ConversationTurn(BaseModel):
    """Capture 输入的最小结构"""
    role: ConversationRole
    content: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    chat_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    timestamp: AwareDatetime = Field(..., description="消息时间戳 (UTC)")  # 改为 AwareDatetime
    metadata: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}
