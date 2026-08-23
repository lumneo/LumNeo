"""
Layer‑Type 合法性判定（Contract §5.8）
返回 "preferred" / "acceptable" / "suspicious"
"""

from typing import Literal

# 使用项目已有的枚举别名（实际为 Literal 联合类型）
from lumneo.memory.model.enums import MemoryLayer, MemoryType


# 推荐组合（preferred）
PREFERRED: dict[MemoryLayer, set[MemoryType]] = {
    "identity": {"preference", "value", "style", "fact", "relationship"},
    "episodic": {"event", "decision"},
    "semantic": {"fact", "value", "relationship", "preference"},
    "procedural": {"skill", "decision"},
}

# 可接受组合（acceptable）
ACCEPTABLE: dict[MemoryLayer, set[MemoryType]] = {
    "episodic": {"fact"},
    "semantic": {"style"},
}


def classify_layer_type(
    layer: MemoryLayer,
    mem_type: MemoryType
) -> Literal["preferred", "acceptable", "suspicious"]:
    """
    判定 layer + type 组合的合法性等级。

    规则：
      - 若 type 在 PREFERRED[layer] 中 → "preferred"
      - 否则若 type 在 ACCEPTABLE[layer] 中 → "acceptable"
      - 否则 → "suspicious"

    实现要求：
      必须在 evaluate() / evaluate_batch() 的置信度计算和冲突检测之前调用。
    """
    if mem_type in PREFERRED.get(layer, set()):
        return "preferred"
    if mem_type in ACCEPTABLE.get(layer, set()):
        return "acceptable"
    return "suspicious"