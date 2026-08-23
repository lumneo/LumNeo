# tests/memory/unit/test_id_gen.py
"""T0.4 — ID 生成器单元测试"""
import re

from lumneo.memory.common.id_gen import (
    generate_memory_id,
    generate_evidence_id,
    generate_audit_id,
    is_valid_memory_id,
)


def test_generate_memory_id_format():
    """验证 ID 格式符合 mem_{timestamp}_{random}"""
    mid = generate_memory_id()
    assert re.match(r'^mem_\d+_[a-f0-9]{12}$', mid) is not None


def test_generate_memory_id_unique_1000():
    """生成 1000 个 ID 无碰撞"""
    ids = set()
    for _ in range(1000):
        mid = generate_memory_id()
        assert mid not in ids, f"碰撞: {mid}"
        ids.add(mid)
    assert len(ids) == 1000


def test_generate_evidence_id_format():
    eid = generate_evidence_id()
    assert re.match(r'^evi_\d+_[a-f0-9]{12}$', eid) is not None


def test_generate_audit_id_format():
    aid = generate_audit_id()
    assert re.match(r'^aud_\d+_[a-f0-9]{12}$', aid) is not None


def test_is_valid_memory_id():
    assert is_valid_memory_id("mem_123_abcdef123456") is True
    assert is_valid_memory_id("mem_123_abc") is False  # 长度不足
    assert is_valid_memory_id("mem_abc_abcdef123456") is False  # 时间戳非数字
    assert is_valid_memory_id("invalid_id") is False