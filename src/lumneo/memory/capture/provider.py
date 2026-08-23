# src/lumneo/memory/capture/provider.py
"""CaptureProvider 抽象接口（ADR-008 §3）"""
from abc import ABC, abstractmethod
from typing import Literal, Optional

from ..model import ConversationTurn, MemoryCandidate
from ..common.exceptions import MemoryOSError


# ---------- Provider 异常 ----------
class CaptureError(MemoryOSError):
    """Capture 处理失败（LLM API 超时、解析错误等）"""
    pass


class CaptureParsingError(CaptureError):
    """LLM 返回无法解析为 MemoryCandidate 结构"""
    pass


class CaptureTimeoutError(CaptureError):
    """提取超时"""
    pass


# ---------- 配置 ----------
class CaptureConfig:
    """Provider 行为配置"""
    def __init__(
        self,
        mapping_mode: Literal["strict", "loose"] = "loose",
        max_candidates_per_turn: int = 5,
        enable_provenance_chain: bool = True,
        timeout_seconds: float = 30.0,
        extra: Optional[dict] = None,
    ):
        self.mapping_mode = mapping_mode
        self.max_candidates_per_turn = max_candidates_per_turn
        self.enable_provenance_chain = enable_provenance_chain
        self.timeout_seconds = timeout_seconds
        self.extra = extra or {}


# ---------- Provider 抽象 ----------
class CaptureProvider(ABC):
    """
    记忆提取的抽象边界。所有实现必须遵守:
    - 只生成 MemoryCandidate，不直接持久化
    - 必须生成唯一 capture_id
    - 必须尽可能填充 dedup_key
    - 必须正确处理 provenance_key 与 reply_to 关联
    """

    def __init__(self, config: Optional[CaptureConfig] = None):
        self.config = config or CaptureConfig()

    @abstractmethod
    def extract_candidates(
        self,
        turns: list[ConversationTurn]
    ) -> list[MemoryCandidate]:
        """
        从对话中提取候选记忆列表。
        参数:
            turns: 单轮或多轮对话，必须符合 ConversationTurn 最小结构。
        返回:
            list[MemoryCandidate]: 候选列表。空列表表示无有效候选。
        保证项:
            1. 每次调用生成的所有 candidate 共享同一个 capture_id
            2. 每个 candidate 的 dedup_key 已填充
            3. 助手确认类回复的 Evidence.provenance_key 必须与用户原始 message_id 关联
            4. origin_actor 正确区分
            5. suggested_layer/type 符合枚举或 None
            6. predicate 尽量映射至标准化谓词表（strict/loose 模式）
        异常:
            CaptureParsingError, CaptureTimeoutError, CaptureError
        """
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """
        返回 Provider 健康状态。
        必须包含:
            - "status": "healthy" | "degraded" | "unavailable"
            - "latency_ms": 最近 10 次调用的平均延迟
            - "version": Provider 实现版本号
        """
        ...