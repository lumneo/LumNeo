# src/lumneo/memory/common/exceptions.py
"""
MemoryOS 统一错误模型
遵循 ADR-006 §3 和 Contract §5.7

所有异常携带 message 和可选的 context 字典。
核心包内禁止引入 FastAPI/Starlette 依赖。
"""
from typing import Any, Optional, Dict


class MemoryOSError(Exception):
    """MemoryOS 异常根类"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.context:
            return f"{self.message} (context: {self.context})"
        return self.message


# ---------- 校验与语义层 ----------
class ValidationError(MemoryOSError):
    """数据校验失败（如 Pydantic 校验不通过后的封装）"""
    pass


class InvalidMemoryError(MemoryOSError):
    """记忆对象语义非法（如 evidence 为空，或 layer-type 严重不匹配）"""
    pass


# ---------- 冲突与并发 ----------
class ConflictError(MemoryOSError):
    """业务冲突（如版本链存在环，或 SPO 条件互斥）"""
    pass


class ConcurrentModificationError(MemoryOSError):
    """乐观锁冲突（CAS 失败，数据已被其他写者修改）"""
    pass


# ---------- 存储与索引 ----------
class PersistenceError(MemoryOSError):
    """存储层故障（文件系统错误、SQLite 操作失败）"""
    pass


class IndexError(MemoryOSError):
    """索引操作失败（FTS5 重建、查询语法错误等）"""
    pass


class NotFoundError(MemoryOSError):
    """目标记忆不存在（get_by_id 或 update 时）"""
    pass


class ConsistencyError(MemoryOSError):
    """Markdown 与 FTS5/SQLite 不一致，且自动修复失败"""
    pass


# ---------- 安全与隔离 ----------
class ScopeViolationError(MemoryOSError):
    """Scope 隔离违规（尝试访问不属于当前 tenant_id / agent_id 的数据）"""
    pass