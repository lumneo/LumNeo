# src/lumneo/memory/governance/directives.py
"""
用户指令处理（Contract §4, §5.4）
提供 apply_user_directives 函数，处理 forget, correct 等指令。
"""

from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from dataclasses import dataclass

from lumneo.memory.model import MemoryObject, MemoryStatus
from lumneo.memory.storage.repository import MemoryRepository, AuditLogEntry
from lumneo.memory.common.time import utc_now
from lumneo.memory.common.exceptions import ValidationError, NotFoundError


@dataclass
class UserDirective:
    """用户指令结构（与契约保持一致）"""
    type: Literal["forget", "do_not_remember", "temporary", "correct"]
    target: Optional[str] = None          # 记忆 id 或描述性文本
    target_type: Optional[Literal["memory_id", "semantic_match", "predicate_match"]] = None
    scope: Optional[str] = None           # 可选：layer / type / keyword
    raw_text: str = ""
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = utc_now()


def apply_user_directives(
    directives: List[UserDirective],
    repository: MemoryRepository,
    candidates: Optional[List] = None,   # 预留用于 do_not_remember 等候选过滤
) -> None:
    """
    应用用户指令到已有记忆（或候选）。
    目前实现：
      - forget: 将匹配记忆状态改为 archived，添加 user_forgotten 标记。
    其他指令留待后续实现。
    """
    for directive in directives:
        if directive.type == "forget":
            _process_forget(directive, repository)
        elif directive.type == "do_not_remember":
            # 用于过滤候选，暂不实现
            raise NotImplementedError("do_not_remember 将在后续实现")
        elif directive.type == "temporary":
            # 暂不实现
            raise NotImplementedError("temporary 将在后续实现")
        else:
            raise ValidationError(f"未知指令类型: {directive.type}")


def _process_forget(directive: UserDirective, repository: MemoryRepository) -> None:
    """
    处理 forget 指令：
      - 根据 target_type 匹配记忆（目前仅支持 memory_id）
      - 将状态设为 archived，metadata 中添加 user_forgotten: true 和 forgotten_at
    """
    if directive.target_type is None or directive.target_type == "memory_id":
        if not directive.target:
            raise ValidationError("forget 指令缺少 target")
        memory = repository.get_by_id(directive.target)
        if memory is None:
            # 未找到，根据契约可能忽略或记录，我们选择记录但不抛出（静默失败）
            # 但为了可观测，可记录日志，这里简单返回
            return

        # 更新状态
        updated_metadata = memory.metadata.copy()
        updated_metadata.update({
            "user_forgotten": True,
            "forgotten_at": utc_now().isoformat()
        })

        # 创建更新后的 MemoryObject
        updated_memory = memory.model_copy(update={
            "status": "archived",
            "metadata": updated_metadata,
            "updated_at": utc_now()
        })

        # 通过 Repository 更新
        try:
            repository.update_with_version(updated_memory)
            repository.append_audit_log(
                AuditLogEntry(
                    timestamp=utc_now(),
                    action="forget",
                    memory_id=memory.id,
                    reason="用户主动遗忘",
                    source={"directive": directive.raw_text, "type": directive.type},
                    payload={"old_status": memory.status, "new_status": "archived"}
                )
            )
        except NotFoundError:
            # 并发删除，忽略
            pass
        # 其他异常向上抛出

    elif directive.target_type == "semantic_match" or directive.target_type == "predicate_match":
        # Phase 1 暂不支持语义匹配，抛出异常
        raise NotImplementedError(f"匹配方式 {directive.target_type} 尚未支持")
    else:
        raise ValidationError(f"不支持的 target_type: {directive.target_type}")