# src/lumneo/memory/model/memory_candidate.py
"""MemoryCandidate 模型（Contract §2.2）"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator

from .enums import MemoryLayer, MemoryType, EvidenceActor
from .evidence import Evidence
from .auxiliary import Source


class MemoryCandidate(BaseModel):
    """Capture 产出的候选记忆"""

    raw_content: str = Field(..., min_length=1)
    suggested_layer: Optional[MemoryLayer] = None
    suggested_type: Optional[MemoryType] = None
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    condition: Optional[dict] = None
    evidence: list[Evidence] = Field(..., min_length=1)
    source: Source
    origin_actor: EvidenceActor
    confidence_hint: Optional[float] = Field(None, ge=0.0, le=1.0)
    capture_id: str = Field(..., min_length=1)
    correction_target: Optional[str] = None
    dedup_key: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dedup_key")
    @classmethod
    def validate_dedup_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("dedup_key 不能为空字符串")
        return v

    model_config = {
        "extra": "forbid",
        "json_encoders": {
            datetime: lambda dt: dt.isoformat() + "Z"
        }
    }