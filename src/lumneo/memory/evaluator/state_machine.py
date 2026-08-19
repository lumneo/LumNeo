# src/lumneo/memory/evaluator/state_machine.py
"""
状态流转引擎（Contract §5.1, §6）
整合 Layer-Type 判定、证据去重、置信度计算、冲突检测，
输出最终的 MemoryObject 状态。
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from rapidfuzz import fuzz

from lumneo.memory.model.memory_candidate import MemoryCandidate
from lumneo.memory.model.memory_object import MemoryObject
from lumneo.memory.model.enums import MemoryOrigin
from lumneo.memory.model.auxiliary import Source
from lumneo.memory.model.user_directive import UserDirective
from lumneo.memory.storage.repository import AuditLogEntry
from ..common.time import utc_now
from .layer_type import classify_layer_type
from .dedup import deduplicate_evidence
from .confidence import calculate_confidence

# 活跃阈值（Contract §5.1）
ACTIVE_CONFIDENCE_THRESHOLD = 0.55
# Batch 内冲突判定阈值
BATCH_CONFLICT_SIMILARITY_THRESHOLD = 0.75


def _string_similarity(s1: Optional[str], s2: Optional[str]) -> float:
    """基于字符集合的 Jaccard 相似度，用于 object 比较"""
    s1 = s1 or ""
    s2 = s2 or ""
    if s1 == s2:
        return 1.0
    set1 = set(s1)
    set2 = set(s2)
    if not set1 and not set2:
        return 1.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0

def _condition_conflict(cond1: Optional[dict], cond2: Optional[dict]) -> bool:
    """
    检测两个 condition 是否存在互斥键值对。
    仅支持扁平对象和 AND 组合（最多 5 项）。
    若存在任一键值对冲突（相同 key，不同 value），返回 True。
    """
    if cond1 is None or cond2 is None:
        return False
    # 展平 clause
    def flatten(cond):
        if cond is None:
            return {}
        if "operator" in cond and cond["operator"] == "AND":
            # 将 AND 的 clauses 合并为 dict
            result = {}
            for clause in cond.get("clauses", []):
                if isinstance(clause, dict) and "key" in clause and "value" in clause:
                    result[clause["key"]] = clause["value"]
            return result
        # 扁平对象
        if "key" in cond and "value" in cond:
            return {cond["key"]: cond["value"]}
        return {}
    d1 = flatten(cond1)
    d2 = flatten(cond2)
    for key, val in d1.items():
        if key in d2 and d2[key] != val:
            return True
    return False


class Evaluator:
    def __init__(self, confidence_cap: float = 1.0, repository=None):
        self.confidence_cap = confidence_cap
        self.repository = repository

    def _build_base_object(self, candidate: MemoryCandidate) -> MemoryObject:
        """
        构建基础 MemoryObject（不处理冲突），仅根据 layer-type 和 confidence 决定状态。
        返回的对象状态可能为 active 或 needs_review。
        """
        # 1. 证据去重
        deduped = deduplicate_evidence(candidate.evidence)

        # 2. 计算置信度
        conf = calculate_confidence(deduped, cap=self.confidence_cap)

        # 3. Layer-Type 判定
        layer = candidate.suggested_layer
        mem_type = candidate.suggested_type
        if layer is None or mem_type is None:
            layer_verdict = "suspicious"
        else:
            layer_verdict = classify_layer_type(layer, mem_type)

        # 4. 状态初步决策
        if layer_verdict == "suspicious":
            status = "needs_review"
            reason = "layer_type_mismatch"
        elif conf >= ACTIVE_CONFIDENCE_THRESHOLD:
            status = "active"
            reason = "confidence_ok"
        else:
            status = "needs_review"
            reason = "low_confidence"

        # 5. 生成唯一 ID
        timestamp_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)
        rand_hex = uuid.uuid4().hex[:12]
        obj_id = f"mem_{timestamp_ns}_{rand_hex}"
        now = datetime.now(timezone.utc)

        # origin 映射
        origin_map = {
            "user": "explicit_user",
            "assistant": "assistant_inferred",
            "system": "system_generated",
            "external": "external_import",
        }
        origin = origin_map.get(candidate.origin_actor, "assistant_inferred")

        # 构建对象
        return MemoryObject(
            id=obj_id,
            schema_version="2.1.2",
            layer=layer if layer else "semantic",
            type=mem_type if mem_type else "fact",
            subject=candidate.subject,
            predicate=candidate.predicate,
            object=candidate.object,
            condition=candidate.condition,
            content=candidate.raw_content,
            confidence=conf,
            confidence_detail=None,
            importance=3,            # 默认中等，后续可由 Importance 规则调整
            status=status,
            evidence=deduped,
            source=candidate.source,
            origin=origin,
            supersedes=None,
            superseded_by=None,
            last_accessed=None,
            access_count=0,
            tags=[],
            privacy=None,
            created_at=now,
            updated_at=now,
            metadata={
                "standardization_issue": False,
                "user_forgotten": False,
                "evaluation_reason": reason,
                "layer_type_verdict": layer_verdict,
            }
        )

    def _check_cycle(self, old_memory: MemoryObject, new_id: str) -> bool:
        """检查如果让 new_id 指向 old_memory，是否会形成环（假设 old_memory 可能已有 supersedes 链）"""
        # 如果 old_memory 的 supersedes 链中包含 new_id，则成环（但 new_id 是新生成的，不可能在链中）
        # 为安全，我们遍历祖先链
        current = old_memory
        visited = set()
        while current:
            if current.id == new_id:
                return True
            if current.id in visited:
                # 已存在环（理论上不应该），视为危险
                return True
            visited.add(current.id)
            if current.supersedes:
                # 需要加载被 supersedes 的记忆（可能不在内存中）
                if self.repository is None:
                    break
                current = self.repository.get_by_id(current.supersedes)
                if current is None:
                    break
            else:
                break
        return False

    def _process_conflicts(self, base_items: List[Tuple[MemoryCandidate, MemoryObject]]) -> List[MemoryObject]:
        """原有的冲突检测逻辑（从 evaluate_batch 中提取）"""
        groups = defaultdict(list)
        for cand, obj in base_items:
            groups[cand.capture_id].append((cand, obj))

        final_map = {}
        ordered_ids = []

        for cap_id, items in groups.items():
            seen = {}
            for cand, obj in items:
                key = (cand.subject, cand.predicate)
                if cand.subject is None or cand.predicate is None:
                    final_map[obj.id] = obj
                    ordered_ids.append(obj.id)
                    continue
                if key not in seen:
                    seen[key] = (cand, obj)
                    final_map[obj.id] = obj
                    ordered_ids.append(obj.id)
                else:
                    prev_cand, prev_obj = seen[key]
                    sim = _string_similarity(prev_cand.object, cand.object)
                    if obj.metadata.get("layer_type_verdict") == "suspicious":
                        final_map[obj.id] = obj
                        ordered_ids.append(obj.id)
                    else:
                        if sim >= 0.75:
                            updated_prev = prev_obj.model_copy(update={
                                "status": "superseded",
                                "superseded_by": obj.id,
                                "updated_at": datetime.now(timezone.utc)
                            })
                            updated_new = obj.model_copy(update={
                                "status": "active",
                                "supersedes": prev_obj.id,
                                "updated_at": datetime.now(timezone.utc),
                                "metadata": {
                                    **obj.metadata,
                                    "superseded_old_id": prev_obj.id,
                                }
                            })
                            final_map[prev_obj.id] = updated_prev
                            final_map[obj.id] = updated_new
                            seen[key] = (cand, updated_new)
                            ordered_ids.append(obj.id)
                        elif sim <= 0.40:
                            final_map[obj.id] = obj
                            ordered_ids.append(obj.id)
                        else:
                            updated_new = obj.model_copy(update={
                                "status": "needs_review",
                                "updated_at": datetime.now(timezone.utc),
                                "metadata": {
                                    **obj.metadata,
                                    "conflict_unclear": True,
                                    "conflict_with": prev_obj.id,
                                }
                            })
                            final_map[obj.id] = updated_new
                            ordered_ids.append(obj.id)
        return [final_map[oid] for oid in ordered_ids if oid in final_map]

    def _resolve_conflict_with_existing(
        self,
        candidate: MemoryCandidate,
        new_obj: MemoryObject,
        existing: List[MemoryObject]
    ) -> Tuple[MemoryObject, Optional[MemoryObject]]:
        if not existing:
            return new_obj, None
        old = existing[0]

        # 1. Condition 交叉校验（不变）
        if _condition_conflict(candidate.condition, old.condition):
            updated_new = new_obj.model_copy(update={
                "status": "needs_review",
                "metadata": {**new_obj.metadata, "conflict_reason": "condition_conflict", "conflict_with": old.id}
            })
            return updated_new, None

        # 2. generic_statement 特殊去重（不变）
        is_generic_new = candidate.predicate == "generic_statement" or new_obj.predicate == "generic_statement"
        is_generic_old = old.predicate == "generic_statement"
        if is_generic_new and is_generic_old and candidate.subject == old.subject:
            sim = fuzz.ratio(candidate.object or "", old.object or "") / 100.0
            if sim >= 0.65:
                updated_new = new_obj.model_copy(update={
                    "status": "needs_review",
                    "metadata": {**new_obj.metadata, "conflict_reason": "generic_statement_conflict", "conflict_with": old.id}
                })
                return updated_new, None

        # 3. 计算相似度
        sim = fuzz.ratio(candidate.object or "", old.object or "") / 100.0

        # 4. 判断是否为偏好类
        is_preference = (candidate.suggested_type in {"preference", "value", "decision"} or 
                        new_obj.type in {"preference", "value", "decision"})

        if is_preference:
            # 计算 object 相似度
            sim = fuzz.ratio(candidate.object or "", old.object or "") / 100.0
            if sim <= 0.40:
                # 对象完全不同，视为独立偏好，不覆盖旧记忆
                return new_obj, None
            elif sim >= 0.75:
                # 对象高度相似，标记旧记忆为 stale（偏好类更倾向 stale 而非 supersede）
                old_updated = old.model_copy(update={
                    "status": "stale",
                    "updated_at": datetime.now(timezone.utc)
                })
                return new_obj, old_updated
            else:
                # 不确定，新记忆进入 needs_review
                new_updated = new_obj.model_copy(update={
                    "status": "needs_review",
                    "metadata": {
                        **new_obj.metadata,
                        "conflict_reason": "preference_similarity_unclear",
                        "conflict_with": old.id,
                        "similarity_score": sim,
                    }
                })
                return new_updated, None
    
    def _batch_conflict_detection(
        self,
        items: List[Tuple[MemoryCandidate, MemoryObject]]
    ) -> List[Tuple[MemoryCandidate, MemoryObject]]:
        """
        同一 capture_id 内冲突检测（T4.4）。
        对同 subject+predicate 且 object 相似度 < 阈值的候选，将除第一个外的候选标记为 needs_review。
        若候选已因其他原因（如 layer_type）为 needs_review，保持不变。
        """
        # 按 capture_id 分组
        groups: Dict[str, List[Tuple[MemoryCandidate, MemoryObject]]] = defaultdict(list)
        for cand, obj in items:
            groups[cand.capture_id].append((cand, obj))

        result = []
        for cap_id, group in groups.items():
            # 再按 (subject, predicate) 分组
            conflict_groups: Dict[Tuple[str, str], List[Tuple[MemoryCandidate, MemoryObject]]] = defaultdict(list)
            for cand, obj in group:
                key = (cand.subject, cand.predicate)
                # 若 subject 或 predicate 缺失，不参与冲突检测（视为独立）
                if cand.subject is None or cand.predicate is None:
                    conflict_groups[("__none__", "__none__")].append((cand, obj))
                else:
                    conflict_groups[key].append((cand, obj))

            for key, sub_items in conflict_groups.items():
                if key == ("__none__", "__none__"):
                    # 缺失 subject/predicate 的不参与冲突，直接保留
                    result.extend(sub_items)
                    continue

                # 若组内只有一条，无冲突
                if len(sub_items) <= 1:
                    result.extend(sub_items)
                    continue

                # 组内有多条，按 object 相似度检测
                # 先按置信度排序（降序），高置信度优先保留
                sorted_items = sorted(sub_items, key=lambda x: x[1].confidence, reverse=True)
                # 取第一个作为参考
                first_cand, first_obj = sorted_items[0]
                # 保留第一个，其余检测
                for idx in range(1, len(sorted_items)):
                    cand, obj = sorted_items[idx]
                    # 如果该对象已因其他原因（如 layer_type）为 needs_review，保留其状态
                    if obj.status == "needs_review":
                        result.append((cand, obj))
                        continue

                    # 计算 object 相似度（使用 rapidfuzz.ratio）
                    sim = fuzz.ratio(first_cand.object or "", cand.object or "") / 100.0
                    if sim < BATCH_CONFLICT_SIMILARITY_THRESHOLD:
                        # 互斥 object → 标记为 needs_review
                        updated_obj = obj.model_copy(update={
                            "status": "needs_review",
                            "metadata": {
                                **obj.metadata,
                                "batch_conflict": True,
                                "conflict_with_capture": cap_id,
                                "conflict_reason": "batch_conflict",
                            }
                        })
                        result.append((cand, updated_obj))
                    else:
                        # 相似度高，视为重复（或可保留原状态，但我们保留第一个，此条可能重复，但保留）
                        # 为了安全，也将此条标记为 needs_review？但契约未明确，我们保留其原状态（可能 active）
                        # 但为了避免重复，我们将其标记为 needs_review 并说明重复？但契约未要求。
                        # 根据 T4.4 仅互斥 object 才 needs_review，相似度高的不视为冲突。
                        # 我们保留原状态（可能 active），但注意它们有相同 subject/predicate 和相近 object，
                        # 后续全局冲突可能处理。这里不做额外处理。
                        result.append((cand, obj))

                # 将第一个也加入结果
                result.append((first_cand, first_obj))

        return result
    
    def evaluate(self, candidate: MemoryCandidate, directives: Optional[List[UserDirective]] = None) -> MemoryObject:
        if directives:
            for d in directives:
                if d.type == "correct" and d.target_type == "memory_id" and d.target == candidate.correction_target:
                    if self.repository is None:
                        raise RuntimeError("处理 correct 指令需要提供 repository")
                    old_memory = self.repository.get_by_id(d.target)
                    if old_memory is None or old_memory.status != "active":
                        break
                    # 构建新对象
                    obj = self._build_base_object(candidate)
                    # 检查环
                    if self._check_cycle(old_memory, obj.id):
                        raise ValueError("版本链成环，禁止操作")
                    # 更新新对象元数据
                    obj = obj.model_copy(update={
                        "supersedes": old_memory.id,
                        "status": "active",
                        "metadata": {
                            **obj.metadata,
                            "corrected": True,
                            "corrected_at": datetime.now(timezone.utc).isoformat(),
                            "old_version": old_memory.id,
                        }
                    })
                    # 先持久化新记忆
                    created = self.repository.create(obj)
                    # 再更新旧记忆
                    old_memory_updated = old_memory.model_copy(update={
                        "status": "superseded",
                        "superseded_by": created.id,
                        "updated_at": datetime.now(timezone.utc)
                    })
                    self.repository.update_with_version(old_memory_updated)
                    try:
                        self.repository.append_audit_log(
                            AuditLogEntry(
                                timestamp=utc_now(),
                                action="correct",
                                memory_id=old_memory.id,
                                reason="用户纠正记忆",
                                source={"directive": d.raw_text, "actor": "user"},
                                payload={"old_object": old_memory.object, "new_object": candidate.object}
                            )
                        )
                    except Exception:
                        pass
                    return created
        return self._build_base_object(candidate)

    def evaluate_batch(
        self,
        candidates: List[MemoryCandidate],
        directives: Optional[List[UserDirective]] = None
    ) -> List[MemoryObject]:
        if not candidates:
            return []

        # ---------- 1. 构建基础对象 ----------
        base_items = [(cand, self._build_base_object(cand)) for cand in candidates]

        # ---------- 2. 处理 correct 指令（提前分离） ----------
        corrected_results = []
        remaining_items = []
        correct_map = {}
        if directives:
            for d in directives:
                if d.type == "correct" and d.target_type == "memory_id" and d.target:
                    correct_map[d.target] = d

        for cand, obj in base_items:
            if cand.correction_target and cand.correction_target in correct_map:
                old = self.repository.get_by_id(cand.correction_target)
                if old and old.status == "active":
                    if self._check_cycle(old, obj.id):
                        raise ValueError("版本链成环")
                    # 更新对象
                    obj = obj.model_copy(update={
                        "supersedes": old.id,
                        "status": "active",
                        "metadata": {**obj.metadata, "corrected": True, "old_version": old.id}
                    })
                    old_updated = old.model_copy(update={
                        "status": "superseded",
                        "superseded_by": obj.id,
                        "updated_at": utc_now()
                    })
                    # 持久化（先创建新，再更新旧）
                    created = self.repository.create(obj)
                    self.repository.update_with_version(old_updated)
                    corrected_results.append(created)
                    continue
            remaining_items.append((cand, obj))

        # ---------- 3. Batch 内冲突检测 ----------
        batch_processed = self._batch_conflict_detection(remaining_items)

        # ---------- 4. 全局冲突检测（与已有 active 记忆） ----------
        global_results = []
        for cand, obj in batch_processed:
            # 如果对象已经是 needs_review（包括因 batch 冲突标记的），跳过全局冲突
            if obj.status == "needs_review":
                global_results.append((cand, obj, None))
                continue

            # 查询已有 active 记忆
            existing = []
            if cand.subject and cand.predicate:
                existing = self.repository.find_active_by_subject_predicate(cand.subject, cand.predicate)
            if existing:
                new_obj, old_to_update = self._resolve_conflict_with_existing(cand, obj, existing)
                global_results.append((cand, new_obj, old_to_update))
            else:
                global_results.append((cand, obj, None))

        # ---------- 5. 持久化 ----------
        final_objects = []
        for cand, new_obj, old_to_update in global_results:
            if old_to_update:
                # 先创建新记忆
                created = self.repository.create(new_obj)
                # 更新旧记忆
                if old_to_update.superseded_by is None:
                    # stale 情况
                    old_to_update = old_to_update.model_copy(update={"updated_at": utc_now()})
                    action = "stale"  # 或 "state_transition"
                    reason = "旧记忆标记为 stale（偏好类或相似度低）"
                else:
                    old_to_update = old_to_update.model_copy(update={"superseded_by": created.id})
                    action = "supersede"
                    reason = "新记忆取代旧记忆（相似度高）"
                self.repository.update_with_version(old_to_update)
                final_objects.append(created)

                # 记录审计
                try:
                    self.repository.append_audit_log(
                        AuditLogEntry(
                            timestamp=utc_now(),
                            action=action,
                            memory_id=old_to_update.id,
                            reason=reason,
                            source={"candidate": cand.raw_content, "actor": cand.origin_actor},
                            payload={
                                "old_status": old_to_update.status,  # 可能已变化，但我们在更新前记录？注意我们已经复制了
                                "new_status": old_to_update.status,
                                "new_memory_id": created.id,
                                "similarity": None  # 可计算
                            }
                        )
                    )
                except Exception:
                    pass
            else:
                created = self.repository.create(new_obj)
                final_objects.append(created)

        # 合并 correct 结果（已持久化）和全局结果
        return corrected_results + final_objects


# 模块级便捷函数
def evaluate(candidate: MemoryCandidate, confidence_cap: float = 1.0) -> MemoryObject:
    return Evaluator(confidence_cap).evaluate(candidate)


def evaluate_batch(candidates: List[MemoryCandidate], confidence_cap: float = 1.0) -> List[MemoryObject]:
    return Evaluator(confidence_cap).evaluate_batch(candidates)