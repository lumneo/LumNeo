# src/lumneo/memory/common/__init__.py
"""MemoryOS 公共基础工具"""

from .exceptions import (
    MemoryOSError,
    ValidationError,
    InvalidMemoryError,
    ConflictError,
    ConcurrentModificationError,
    PersistenceError,
    IndexError,
    NotFoundError,
    ConsistencyError,
    ScopeViolationError,
)
from .time import utc_now, format_utc, parse_utc
from .id_gen import (
    generate_memory_id,
    generate_evidence_id,
    generate_audit_id,
    is_valid_memory_id,
)
from .config import MemoryConfig

__all__ = [
    # 异常
    "MemoryOSError",
    "ValidationError",
    "InvalidMemoryError",
    "ConflictError",
    "ConcurrentModificationError",
    "PersistenceError",
    "IndexError",
    "NotFoundError",
    "ConsistencyError",
    "ScopeViolationError",
    # 时间
    "utc_now",
    "format_utc",
    "parse_utc",
    # ID 生成
    "generate_memory_id",
    "generate_evidence_id",
    "generate_audit_id",
    "is_valid_memory_id",
    # 配置
    "MemoryConfig",
]