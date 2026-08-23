# tests/memory/unit/test_ddl.py
"""T0.5 — DDL 测试：在内存 SQLite 中执行迁移脚本"""
import sqlite3
import pytest
from lumneo.kernel.config.app_config import MIGRATIONS_DIR


migration_file = MIGRATIONS_DIR / "migrate_v0.0_to_v1.0.sql"


def test_ddl_executes_without_error():
    """验证 DDL 在 SQLite 3.39+ 中执行成功"""
    if not migration_file.exists():
        pytest.skip(f"迁移文件不存在: {migration_file}")

    conn = sqlite3.connect(":memory:")
    
    # 检查 FTS5 支持
    try:
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(content)")
        conn.execute("DROP TABLE test_fts")
    except sqlite3.OperationalError:
        pytest.skip("SQLite 未编译 FTS5 支持")

    # 读取迁移脚本
    with open(migration_file, "r", encoding="utf-8") as f:
        script = f.read()

    # 使用 executescript 一次性执行所有语句（SQLite 原生支持）
    try:
        conn.executescript(script)
    except sqlite3.OperationalError as e:
        pytest.fail(f"DDL 执行失败: {e}")


def test_schema_meta_initialized():
    """验证 _schema_meta 表正确初始化 storage_schema_version = 1.0"""
    # 我们直接通过执行完整的 DDL 来验证，而不是手工插入
    # 先确保 DDL 能正常执行（复用上面的逻辑）
    if not migration_file.exists():
        pytest.skip(f"迁移文件不存在: {migration_file}")

    conn = sqlite3.connect(":memory:")
    
    try:
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(content)")
        conn.execute("DROP TABLE test_fts")
    except sqlite3.OperationalError:
        pytest.skip("SQLite 未编译 FTS5 支持")

    with open(migration_file, "r", encoding="utf-8") as f:
        script = f.read()

    conn.executescript(script)

    # 现在查询 _schema_meta
    row = conn.execute("SELECT value FROM _schema_meta WHERE key = 'storage_schema_version'").fetchone()
    assert row is not None
    assert row[0] == "1.0"