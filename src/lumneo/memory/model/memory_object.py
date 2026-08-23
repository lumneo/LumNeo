# src/lumneo/memory/model/memory_object.py
"""MemoryObject 核心模型（Contract §2.1）"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import AwareDatetime

from .enums import MemoryLayer, MemoryType, MemoryStatus, MemoryOrigin
from .evidence import Evidence
from .auxiliary import Source, PrivacyInfo


class MemoryObject(BaseModel):
    """最终持久化记忆对象"""

    # 身份与版本
    id: str = Field(..., pattern=r"^mem_\d+_[a-f0-9]{12}$")
    schema_version: str = Field(default="2.1.2", pattern=r"^\d+\.\d+\.\d+$")

    # 正交分类
    layer: MemoryLayer
    type: MemoryType

    # 结构化知识
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    condition: Optional[dict[str, Any]] = Field(
        default=None,
        description="必须为可 JSON 序列化结构，支持单条件或 AND 组合"
    )

    # 内容
    content: str = Field(..., min_length=1)

    # 质量
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_detail: Optional[dict[str, Any]] = None
    importance: int = Field(..., ge=1, le=5)

    # 生命周期
    status: MemoryStatus

    # 证据链（至少一条）
    evidence: list[Evidence] = Field(..., min_length=1)

    # 来源
    source: Source
    origin: MemoryOrigin

    # 版本链
    supersedes: Optional[str] = Field(None, pattern=r"^mem_\d+_[a-f0-9]{12}$")
    superseded_by: Optional[str] = Field(None, pattern=r"^mem_\d+_[a-f0-9]{12}$")

    # 衰减追踪
    last_accessed: Optional[AwareDatetime] = None
    access_count: int = Field(default=0, ge=0)

    # 元数据
    tags: list[str] = Field(default_factory=list)
    privacy: Optional[PrivacyInfo] = None
    created_at: AwareDatetime = Field(..., description="创建时间 (UTC)")
    updated_at: AwareDatetime = Field(..., description="最后更新时间 (UTC)")
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "standardization_issue": False,
            "user_forgotten": False,
        },
        description="含 standardization_issue, user_forgotten 等"
    )

    # ---------- 校验器 ----------
    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: Optional[dict]) -> Optional[dict]:
        if v is None:
            return v
        
        # 拒绝空 dict
        if not v:
            raise ValueError("condition 不能为空 dict")
        
        # 单条件：必须是包含 key, value 的扁平对象
        if "key" in v and "value" in v:
            if len(v) > 2:
                raise ValueError("单条件只允许 key 和 value 字段")
            if not isinstance(v["key"], str):
                raise ValueError("condition.key 必须为字符串")
            if not isinstance(v["value"], str):
                raise ValueError("condition.value 必须为字符串")
            return v
        
        # AND 组合
        if v.get("operator") == "AND":
            clauses = v.get("clauses")
            if not isinstance(clauses, list) or not clauses:
                raise ValueError("AND 组合必须包含非空 clauses 列表")
            if len(clauses) > 5:
                raise ValueError("AND 组合的 clauses 数量不能超过 5")
            for idx, clause in enumerate(clauses):
                if not isinstance(clause, dict):
                    raise ValueError(f"clauses[{idx}] 必须是 dict")
                if "key" not in clause or "value" not in clause:
                    raise ValueError(f"clauses[{idx}] 必须包含 'key' 和 'value' 字段")
                if len(clause) != 2:
                    raise ValueError(f"clauses[{idx}] 必须仅包含 'key' 和 'value' 字段")
                if not isinstance(clause["key"], str):
                    raise ValueError(f"clauses[{idx}].key 必须为字符串")
                if not isinstance(clause["value"], str):
                    raise ValueError(f"clauses[{idx}].value 必须为字符串")
            return v
        
        # 不支持 OR/NOT
        if "operator" in v:
            raise ValueError(f"不支持的运算符: {v.get('operator')}，仅支持 AND")
        raise ValueError("condition 结构非法，应为单条件或 AND 组合")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: dict[str, Any]) -> dict[str, Any]:
        """确保 metadata 包含必要字段"""
        if "standardization_issue" not in v:
            v["standardization_issue"] = False
        if "user_forgotten" not in v:
            v["user_forgotten"] = False
        return v

    @model_validator(mode="after")
    def validate_utc_timestamps(self) -> "MemoryObject":
        """确保所有 datetime 字段为 UTC（带时区）"""
        for field in ["created_at", "updated_at", "last_accessed"]:
            value = getattr(self, field, None)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{field} 必须包含时区信息 (UTC)")
        return self

    @model_validator(mode="after")
    def validate_version_chain(self) -> "MemoryObject":
        """防版本链自引用"""
        if self.supersedes == self.id:
            raise ValueError("supersedes 不能自引用")
        if self.superseded_by == self.id:
            raise ValueError("superseded_by 不能自引用")
        return self

    model_config = {
        "json_encoders": {
            datetime: lambda dt: dt.isoformat() + "Z"
        },
        "extra": "forbid",
        "validate_assignment": True,  # 运行时赋值也触发校验
    }