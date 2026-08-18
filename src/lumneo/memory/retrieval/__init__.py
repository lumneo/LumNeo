import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional
from lumneo.memory.model import MemoryNeed, MemoryObject, MemoryStatus
from lumneo.memory.storage.repository import MemoryRepository
from lumneo.memory.retrieval.ranking import compute_scores

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1)  # 单线程后台更新

def retrieve(
    need: MemoryNeed,
    repository: MemoryRepository,
    alpha: float = 0.65,
    dynamic_alpha_threshold: float = 0.5,
    dynamic_alpha_fallback: float = 0.4,
) -> List[MemoryObject]:
    """
    根据 MemoryNeed 检索记忆，按 final_score 降序排序。
    默认只返回 active 记忆；若 need.include_historical=True，则返回所有状态（active, superseded, stale, archived）。
    副作用：异步更新返回记忆的 last_accessed 和 access_count。
    """
    # ---------- 1. 获取记忆（scope 过滤由 repository 负责） ----------
    if need.include_historical:
        # 允许查询 active, superseded, stale, archived
        statuses: List[MemoryStatus] = ["active", "superseded", "stale", "archived"]
        memories: List[MemoryObject] = []
        seen = set()
        for status in statuses:
            batch = repository.query_by_status(status, scope_filter=need.scope_filter, limit=need.max_results * 2)
            for mem in batch:
                if mem.id not in seen:
                    seen.add(mem.id)
                    memories.append(mem)
        # 如果超过 max_results，按 final_score 最终截断（后续会排序）
    else:
        memories = repository.query_active(need)

    if not memories:
        return []

    # ---------- 2. 构建评分所需数据 ----------
    memories_map = {
        mem.id: (mem.confidence, mem.importance, mem.last_accessed, mem.created_at)
        for mem in memories
    }
    memory_ids = list(memories_map.keys())

    # 查询字符串
    query_str = ' '.join(need.keywords) if need.keywords else ''

    # ---------- 3. 计算 final_score ----------
    # 需要将 repository 的数据库连接传给 compute_scores（暂时通过私有属性访问）
    # 更好的方式：在 repository 中暴露 get_connection() 或直接传入 conn
    # 这里暂时通过 repository.conn 访问（需确保 repository 是 SQLiteMemoryRepository 实例）
    conn = getattr(repository, 'conn', None)
    if conn is None:
        raise RuntimeError("Repository does not provide SQLite connection for BM25 query")

    scores = compute_scores(
        conn=conn,
        memory_ids=memory_ids,
        query_str=query_str,
        memories_map=memories_map,
        alpha=alpha,
        dynamic_alpha_threshold=dynamic_alpha_threshold,
        dynamic_alpha_fallback=dynamic_alpha_fallback,
    )

    # ---------- 4. 排序并截断 ----------
    sorted_ids = sorted(memory_ids, key=lambda mid: scores.get(mid, 0.0), reverse=True)
    # 若 need.max_results 存在，则截断
    if need.max_results:
        sorted_ids = sorted_ids[:need.max_results]

    result = [repository.get_by_id(mid) for mid in sorted_ids if mid in scores]
    # 确保过滤掉 None
    result = [mem for mem in result if mem is not None]

    # ---------- 5. 异步更新访问元数据（严格非阻塞） ----------
    def update_side_effect():
        for mem in result:
            try:
                repository.record_access(mem.id)
            except Exception as e:
                logger.warning(f"Failed to record access for {mem.id}: {e}")

    _executor.submit(update_side_effect)

    return result