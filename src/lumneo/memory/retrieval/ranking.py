from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import sqlite3


def compute_bm25_relevance(
    conn: sqlite3.Connection,
    memory_ids: List[str],
    query_str: str
) -> Dict[str, float]:
    if not memory_ids or not query_str:
        return {mid: 0.0 for mid in memory_ids}

    placeholders = ','.join(['?'] * len(memory_ids))
    sql = f"""
        SELECT m.id, COALESCE(bm25(memories_fts), 0.0) as raw_bm25
        FROM memories m
        LEFT JOIN memories_fts ON m.rowid = memories_fts.rowid AND memories_fts MATCH ?
        WHERE m.id IN ({placeholders})
    """
    # 注意参数顺序：先 MATCH 的 query_str，再是 ID 列表
    params = [query_str] + memory_ids
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()

    result = {}
    for row in rows:
        memory_id = row[0]
        raw_bm25 = row[1] if row[1] is not None else 0.0
        bm25_strength = -raw_bm25
        relevance = bm25_strength / (bm25_strength + 0.5) if bm25_strength > 0 else 0.0
        result[memory_id] = relevance

    # 确保所有 ID 都在结果中（理论上 LEFT JOIN 已经包含了所有）
    for mid in memory_ids:
        if mid not in result:
            result[mid] = 0.0
    return result


def calculate_decay(
    last_accessed: Optional[datetime],
    created_at: datetime,
    decay_coefficient: float = 0.05
) -> float:
    """
    计算衰减因子（§5.2）。
    若 last_accessed 存在则使用，否则使用 created_at。
    新记忆（last_accessed 为 None）初始 decay=1.0。
    """
    if last_accessed is None:
        return 1.0
    now = datetime.now(timezone.utc)
    delta = now - last_accessed
    days = delta.total_seconds() / 86400.0
    return 1.0 / (1.0 + days * decay_coefficient)


def compute_final_score(
    relevance: float,
    importance: int,
    confidence: float,
    decay: float,
    alpha: float = 0.65
) -> float:
    """
    计算 final_score（§5.2）。
    importance_norm = importance / 5.0  (映射至 [0.2, 1.0])
    final_score = α × relevance + (1-α) × (importance_norm × confidence × decay)
    """
    importance_norm = importance / 5.0
    rank_part = importance_norm * confidence * decay
    return alpha * relevance + (1.0 - alpha) * rank_part


def compute_scores(
    conn: sqlite3.Connection,
    memory_ids: List[str],
    query_str: str,
    memories_map: Dict[str, Tuple[float, int, Optional[datetime], datetime]],
    alpha: float = 0.65,
    dynamic_alpha_threshold: float = 0.5,
    dynamic_alpha_fallback: float = 0.4,
) -> Dict[str, float]:
    if not memory_ids:
        return {}

    # 1. 计算 BM25 relevance（现在返回所有 ID）
    relevance_map = compute_bm25_relevance(conn, memory_ids, query_str)

    # 2. 动态降级判定
    strengths = []
    for mid, rel in relevance_map.items():
        if rel > 0 and rel < 1:
            strength = (0.5 * rel) / (1 - rel)
            strengths.append(strength)
        elif rel >= 1:
            strengths.append(float('inf'))
    max_strength = max(strengths) if strengths else 0.0

    if max_strength < dynamic_alpha_threshold:
        alpha = dynamic_alpha_fallback

    # 3. 计算每条记忆的最终分数
    result = {}
    for mid in memory_ids:
        relevance = relevance_map.get(mid, 0.0)
        confidence, importance, last_accessed, created_at = memories_map[mid]
        decay = calculate_decay(last_accessed, created_at)
        score = compute_final_score(relevance, importance, confidence, decay, alpha)
        result[mid] = score

    return result