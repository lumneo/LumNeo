# src/lumneo/memory/model/evidence.py
"""Evidence 模型（Contract §2.3）"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic.types import AwareDatetime

from .enums import EvidenceType, EvidenceActor
from .auxiliary import Source


class Evidence(BaseModel):
    """证据对象，必须至少有一条证据才能形成 MemoryObject"""

    type: EvidenceType
    weight: float = Field(default=1.0, ge=0.3, le=1.0, description="个体调整系数，默认1.0")
    source: Source = Field(..., description="必须包含可追溯 locator")
    observation: str = Field(..., min_length=1, description="原始观察描述")
    origin_actor: EvidenceActor = Field(..., description="证据原始信息来自谁")
    created_at: AwareDatetime = Field(..., description="证据创建时间 (UTC)")
    provenance_key: Optional[str] = Field(
        default=None,
        description="证据溯源键，用于独立性判定，如关联用户原始 message_id"
    )

    @field_validator("provenance_key")
    @classmethod
    def validate_provenance_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("provenance_key 若提供，不能为空字符串")
        return v

    model_config = {
        "json_encoders": {datetime: lambda dt: dt.isoformat() + "Z"},
        "extra": "forbid",
    }