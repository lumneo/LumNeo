# src/lumneo/memory/context/builder.py
from typing import List
from datetime import timedelta

from lumneo.memory.model import MemoryObject, MemoryBudget
from lumneo.memory.common.time import utc_now


def build_context(memories: List[MemoryObject], budget: MemoryBudget) -> str:
    """
    在预算约束下构建上下文文本。
    算法严格按照 Contract §4 描述执行。
    """
    if not memories:
        return ""

    now = utc_now()
    decay_coeff = 0.05  # 默认衰减系数，可配置

    # 1. 计算每个记忆的分数 (importance_norm * confidence * decay)
    scored = []
    for mem in memories:
        imp_norm = mem.importance / 5.0
        ref_time = mem.last_accessed if mem.last_accessed is not None else mem.created_at
        days = (now - ref_time).days
        decay = 1.0 / (1.0 + days * decay_coeff)
        score = imp_norm * mem.confidence * decay
        scored.append((score, mem))

    # 2. 按层分组（identity / semantic / episodic / procedural）
    groups = {
        'identity': [],
        'semantic': [],   # 只包含 preference 和 value
        'episodic': [],
        'procedural': [],
    }

    for score, mem in scored:
        layer = mem.layer
        if layer == 'identity':
            groups['identity'].append((score, mem))
        elif layer == 'semantic' and mem.type in ('preference', 'value'):
            groups['semantic'].append((score, mem))
        elif layer == 'episodic':
            groups['episodic'].append((score, mem))
        elif layer == 'procedural':
            groups['procedural'].append((score, mem))
        # 其他组合（如 semantic 非 preference/value）忽略

    # 3. 配额映射
    quota_map = {
        'identity': budget.max_identity,
        'semantic': budget.max_preferences,
        'episodic': budget.max_episodes,
        'procedural': budget.max_skills,
    }

    # 4. 每组截取前 N 个（按分数降序）
    selected = []  # 存放 (score, mem)
    for group_name, items in groups.items():
        items.sort(key=lambda x: x[0], reverse=True)
        limit = quota_map.get(group_name, 0)
        for i in range(min(limit, len(items))):
            selected.append(items[i])

    # 5. 全局按分数降序排序
    selected.sort(key=lambda x: x[0], reverse=True)

    # 6. 按 token 预算截断，跳过超预算条目
    max_tokens = budget.max_tokens
    accumulated = 0
    result_parts = []

    for _, mem in selected:
        # 简单估算 token（约 4 字符 / token），可替换为 tiktoken
        est_tokens = len(mem.content) // 4 + 1
        if accumulated + est_tokens <= max_tokens:
            result_parts.append(mem.content)
            accumulated += est_tokens
        else:
            # 跳过，继续尝试后续
            continue

    return "\n\n".join(result_parts)