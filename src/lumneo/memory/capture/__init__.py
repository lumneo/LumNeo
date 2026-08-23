# src/lumneo/memory/capture/__init__.py
import time
import secrets
from typing import List, Optional, Union

from ..model import ConversationTurn, MemoryCandidate
from ..common.hash_utils import compute_dedup_key
from .provider import CaptureProvider

# 默认 Provider 占位（延迟导入）
DEFAULT_PROVIDER_CLASS = None

def _get_default_provider() -> CaptureProvider:
    global DEFAULT_PROVIDER_CLASS
    if DEFAULT_PROVIDER_CLASS is None:
        try:
            from .llm_provider import LLMCaptureProvider
            DEFAULT_PROVIDER_CLASS = LLMCaptureProvider
        except ImportError:
            raise ImportError("LLMCaptureProvider not available. Please install required dependencies or provide a custom provider.")
    return DEFAULT_PROVIDER_CLASS()

def capture(turns: Union[List[ConversationTurn], ConversationTurn],
            provider: Optional[CaptureProvider] = None) -> List[MemoryCandidate]:
    """
    从对话中提取候选记忆。

    Args:
        turns: 单轮或多轮对话。
        provider: 可选的自定义 CaptureProvider，若未提供则使用默认 LLMCaptureProvider。

    Returns:
        List[MemoryCandidate]: 候选列表，所有候选共享相同的 capture_id，且 dedup_key 已填充。

    Raises:
        CaptureError: 若 Provider 提取失败。
    """
    # 统一为列表
    if not isinstance(turns, list):
        turns = [turns]

    # 生成 capture_id
    capture_id = f"cap_{time.time_ns()}_{secrets.token_hex(4)}"

    # 获取 Provider
    if provider is None:
        provider = _get_default_provider()

    # 调用 Provider 提取
    candidates = provider.extract_candidates(turns)

    # 补全 capture_id 和 dedup_key
    for cand in candidates:
        cand.capture_id = capture_id  # 覆盖确保一致
        if not cand.dedup_key:
            # 从 source 中取 message_id，若无则尝试 chat_id 或 external_id
            message_id = None
            if cand.source.message_id:
                message_id = cand.source.message_id
            elif cand.source.chat_id:
                message_id = cand.source.chat_id
            elif cand.source.extra and cand.source.extra.get("external_id"):
                message_id = cand.source.extra["external_id"]
            cand.dedup_key = compute_dedup_key(
                cand.suggested_layer,
                cand.subject,
                cand.predicate,
                cand.object,
                message_id
            )

    return candidates