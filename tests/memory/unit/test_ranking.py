import sqlite3
from datetime import datetime, timedelta, timezone
from lumneo.memory.retrieval.ranking import (
    calculate_decay,
    compute_final_score,
    compute_bm25_relevance,
    compute_scores
)


def test_calculate_decay():
    now = datetime.now(timezone.utc)
    # 新记忆
    assert calculate_decay(None, now) == 1.0
    # 今天访问过
    last = now - timedelta(hours=6)
    decay = calculate_decay(last, now)
    assert 0.9 < decay < 1.0
    # 30天前访问
    last = now - timedelta(days=30)
    decay = calculate_decay(last, now, decay_coefficient=0.05)
    expected = 1.0 / (1.0 + 30 * 0.05)  # 0.4
    assert abs(decay - expected) < 0.0001


def test_compute_final_score():
    # 高相关性，高重要性，高置信度，无衰减 → 0.9
    score = compute_final_score(relevance=0.9, importance=5, confidence=0.9, decay=1.0)
    assert abs(score - 0.9) < 0.0001

    # 低相关性，高重要性 → 0.38
    score = compute_final_score(relevance=0.1, importance=5, confidence=0.9, decay=1.0, alpha=0.65)
    assert abs(score - 0.38) < 0.0001

    # 衰减 → 0.7425
    score = compute_final_score(relevance=0.9, importance=5, confidence=0.9, decay=0.5, alpha=0.65)
    assert abs(score - 0.7425) < 0.0001


def test_compute_bm25_relevance(tmp_path):
    # 创建内存数据库
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE VIRTUAL TABLE memories_fts USING fts5(content)")
    # 插入测试数据（需要匹配 memories 表结构，但这里只测试公式）
    # 实际我们会用 JOIN，但此处简化测试
    conn.execute("INSERT INTO memories_fts(rowid, content) VALUES (1, 'I like coffee')")
    conn.execute("INSERT INTO memories_fts(rowid, content) VALUES (2, 'I prefer tea')")
    # 创建 memories 表（只用于测试）
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, rowid INTEGER)")
    conn.execute("INSERT INTO memories (id, rowid) VALUES ('mem1', 1), ('mem2', 2)")
    conn.commit()

    # 查询 "coffee"
    result = compute_bm25_relevance(conn, ['mem1', 'mem2'], 'coffee')
    assert 'mem1' in result and result['mem1'] > 0
    assert 'mem2' in result and result['mem2'] == 0.0  # 无匹配

    # 空查询
    result_empty = compute_bm25_relevance(conn, ['mem1', 'mem2'], '')
    assert result_empty == {'mem1': 0.0, 'mem2': 0.0}


def test_compute_scores_uses_dynamic_alpha(tmp_path):
    # 创建必要表
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE VIRTUAL TABLE memories_fts USING fts5(content)")
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, rowid INTEGER, confidence REAL, importance INTEGER, last_accessed TEXT, created_at TEXT)")
    conn.execute("INSERT INTO memories_fts(rowid, content) VALUES (1, 'hello world')")
    conn.execute("INSERT INTO memories (id, rowid, confidence, importance, last_accessed, created_at) VALUES ('mid1', 1, 0.9, 5, NULL, '2026-01-01T00:00:00Z')")
    conn.commit()

    # 准备 memories_map
    from lumneo.memory.common.time import parse_utc
    memories_map = {
        'mid1': (0.9, 5, None, parse_utc('2026-01-01T00:00:00Z'))
    }

    # 查询弱相关性
    scores = compute_scores(
        conn,
        ['mid1'],
        'coffee',  # 与内容无关，BM25强度≈0
        memories_map,
        alpha=0.65,
        dynamic_alpha_threshold=0.5,
        dynamic_alpha_fallback=0.4
    )
    # 因最大强度 < 0.5，alpha 降至 0.4
    # relevance ≈ 0，所以 final_score = (1-0.4) * (1.0 * 0.9 * 1) = 0.54
    assert abs(scores['mid1'] - 0.54) < 0.0001