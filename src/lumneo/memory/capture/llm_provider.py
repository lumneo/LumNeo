# src/lumneo/memory/capture/llm_provider.py
"""
Lumneo Memory OS
Capture Provider - Phase 1A (T2.4: Evidence & provenance_key)
"""
import re
from collections import defaultdict
from typing import List, Optional, Tuple

from ..common.time import utc_now
from ..model import ConversationTurn, Evidence, MemoryCandidate, Source
from .provider import CaptureConfig, CaptureProvider


class LLMCaptureProvider(CaptureProvider):
    VERSION = "1.1.0"

    # 确认类关键词（用于助手消息）
    CONFIRMATION_PATTERNS = re.compile(
        r"(所以|那|对|确认|是吗|对吧|right|correct|yes|对的|没错)",
        re.IGNORECASE
    )

    def __init__(self, config: Optional[CaptureConfig] = None):
        super().__init__(config)
        self._version = self.VERSION
        self._user_cache = defaultdict(list)

    def extract_candidates(self, turns: List[ConversationTurn]) -> List[MemoryCandidate]:
        candidates = []
        chats = defaultdict(list)

        for turn in turns:
            chats[turn.chat_id or "default"].append(turn)

        for chat_turns in chats.values():
            # 维护最近用户消息，用于补全（暂未使用，但保留）
            recent_users = []

            for turn in chat_turns:
                # ---- 处理用户消息 ----
                if turn.role == "user":
                    cands = self._extract_from_turn(turn, recent_users, origin_actor="user")
                    candidates.extend(cands)
                    recent_users.append(turn)
                    if len(recent_users) > 5:
                        recent_users.pop(0)

                # ---- 处理助手确认消息 ----
                elif turn.role == "assistant":
                    if self._is_confirmation(turn.content):
                        # 从助手内容中提取候选（例如 "所以你喜欢咖啡，对吗？" -> 偏好）
                        cands = self._extract_from_turn(turn, recent_users, origin_actor="assistant")
                        candidates.extend(cands)
                    # 非确认的助手消息忽略

        return candidates

    # ---------- 确认检测 ----------
    def _is_confirmation(self, text: str) -> bool:
        """判断消息内容是否属于确认/总结性质"""
        if not text:
            return False
        # 包含确认关键词，或句末带"吗"、"吧"等疑问确认语气
        if self.CONFIRMATION_PATTERNS.search(text):
            return True
        if re.search(r"[吗吧]$", text):
            return True
        return False

    # ---------- 提取主逻辑 ----------
    def _extract_from_turn(
        self,
        turn: ConversationTurn,
        recent_users: List[ConversationTurn],
        origin_actor: str = "user"
    ) -> List[MemoryCandidate]:
        text = (turn.content or "").strip()
        if not text:
            return []

        extracted = []
        provenance_key = turn.reply_to_message_id  # 统一设置

        extractors = [
            self._extract_identity,
            self._extract_preference,
            self._extract_skill,
            self._extract_event,
            self._extract_relationship,
            self._extract_value,
            self._extract_style,
        ]

        for extractor in extractors:
            results = extractor(text)
            for item in results:
                extracted.append(
                    self._build_candidate(
                        turn,
                        *item,
                        observation=text,
                        origin_actor=origin_actor,
                        provenance_key=provenance_key,
                    )
                )

        if not extracted:
            extracted.append(
                self._build_candidate(
                    turn,
                    "用户",
                    "generic_statement",
                    text,
                    "semantic",
                    "fact",
                    observation=text,
                    origin_actor=origin_actor,
                    standardization_issue=True,
                    provenance_key=provenance_key,
                )
            )

        return extracted[:self.config.max_candidates_per_turn]

    # ---------- 提取器（保持不变，仅示例） ----------
    def _extract_identity(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        match = re.search(r"我是(.+)$", text)
        if match:
            obj = match.group(1).strip()
            if obj:
                results.append(("用户", "fact", obj, "identity", "fact"))
        name = re.search(r"我的名字是(.+)$", text)
        if name:
            obj = name.group(1).strip()
            results.append(("用户", "fact", "名字是" + obj, "identity", "fact"))
        return results

    def _extract_preference(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        # 支持任意主语（包括 "A喜欢安静"）
        match = re.search(r"(?:.*?)(?:喜欢|偏好|爱|prefer|likes)\s*(.+)$", text, re.IGNORECASE)
        if match:
            obj = match.group(1).strip()
            for item in self._split_compound(obj):
                results.append(("用户", "preference", item, "semantic", "preference"))
        return results

    def _extract_skill(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        match = re.search(r"(?:我)?(?:会|擅长|能|can)\s*(.+)$", text, re.IGNORECASE)
        if match:
            obj = match.group(1).strip()
            for item in self._split_compound(obj):
                results.append(("用户", "skill", item, "procedural", "skill"))
        return results

    def _extract_event(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        match = re.search(r"(去了|去过|参加)(.+)$", text)
        if match:
            results.append(("用户", "event", match.group(1) + match.group(2), "episodic", "event"))
        return results

    def _extract_relationship(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        match = re.search(r"(.+?)是我的朋友", text)
        if match:
            person = match.group(1).strip()
            if person:
                results.append(("用户", "relationship", person, "semantic", "relationship"))
        return results

    def _extract_value(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        match = re.search(r"(?:我)?认为(.+)$", text)
        if match:
            value = match.group(1).strip()
            if value:
                results.append(("用户", "value", value, "semantic", "value"))
        return results

    def _extract_style(self, text: str) -> List[Tuple[str, str, str, str, str]]:
        results = []
        if "风格" in text:
            obj = text.split("风格", 1)[1].strip()
            if obj.startswith("是"):
                obj = obj[1:].strip()
            if obj:
                results.append(("用户", "style", obj, "semantic", "style"))
        return results

    def _split_compound(self, text: str) -> List[str]:
        return [x.strip() for x in re.split(r"[和与及,，]", text) if x.strip()]

    # ---------- Candidate 构建（关键） ----------
    def _build_candidate(
        self,
        turn: ConversationTurn,
        subject: str,
        predicate: str,
        obj: str,
        layer: str,
        type_: str,
        observation: str,
        origin_actor: str = "user",
        standardization_issue: bool = False,
        confidence_hint: Optional[float] = None,
        provenance_key: Optional[str] = None,
        capture_id: Optional[str] = None,
    ) -> MemoryCandidate:
        """
        构建 MemoryCandidate，证据中的 origin_actor 和 provenance_key 由外部传入。
        """
        evidence = Evidence(
            type="explicit_statement",
            weight=1.0,
            source=Source(
                tenant_id=None,
                agent_id=None,
                chat_id=turn.chat_id,
                message_id=turn.message_id,
                timestamp=turn.timestamp,
            ),
            observation=observation,
            origin_actor=origin_actor,          # 动态传入
            created_at=utc_now(),
            provenance_key=provenance_key,      # 如果来自助手确认，则为用户消息ID
        )

        source = Source(
            tenant_id=None,
            agent_id=None,
            chat_id=turn.chat_id,
            message_id=turn.message_id,
            timestamp=turn.timestamp,
        )

        metadata = {
            "standardization_issue": standardization_issue,
            "user_forgotten": False,
        }
        if layer == "identity":
            metadata["identity_scope"] = "self"

        return MemoryCandidate(
            raw_content=observation,
            suggested_layer=layer,
            suggested_type=type_,
            subject=subject,
            predicate=predicate,
            object=obj,
            evidence=[evidence],
            source=source,
            origin_actor=origin_actor,          # 候选级也记录
            confidence_hint=confidence_hint,
            capture_id=capture_id or "pending",  # 调用方会覆盖，留作占位
            dedup_key=None,
            metadata=metadata,
        )

    # ---------- Health ----------
    def health_check(self):
        return {
            "status": "healthy",
            "latency_ms": 0.0,
            "version": self._version,
        }