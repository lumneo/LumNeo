# src/lumneo/memory/evaluator/confidence.py
"""
Confidence 饱和归一化计算（Contract §5.1 阶段二）
输入：已去重的证据列表
输出：置信度浮点数 [0.0, cap]
"""

from typing import List

from lumneo.memory.model.evidence import Evidence, EvidenceType


# 类型基准权重（契约表）
TYPE_BASE_WEIGHT: dict[EvidenceType, float] = {
    "explicit_statement": 1.0,
    "confirmation": 0.9,
    "behavioral": 0.7,
    "repeated_observation": 0.6,
    "inference": 0.4,
}


def calculate_confidence(
    evidence_list: List[Evidence],
    cap: float = 1.0,
) -> float:
    """
    计算饱和归一化置信度。

    公式：
        raw_sum = Σ(e.weight × TYPE_BASE_WEIGHT[e.type])
        confidence = min(cap, raw_sum / (raw_sum + 0.4))

    要求：
        - evidence_list 应已经过独立性去重（否则会通胀）
        - cap 默认 1.0，可配置降低上限
    """
    if not evidence_list:
        return 0.0

    raw_sum = 0.0
    for ev in evidence_list:
        base = TYPE_BASE_WEIGHT.get(ev.type, 0.0)
        raw_sum += ev.weight * base

    raw_conf = raw_sum / (raw_sum + 0.4)  # 锚点 0.4 对应单条 inference
    return min(cap, raw_conf)