# tests/memory/unit/test_time.py
"""T0.4 — UTC 时间工具单元测试"""
from datetime import datetime, timezone

import pytest

from lumneo.memory.common.time import utc_now, format_utc, parse_utc


def test_utc_now_returns_utc():
    """验证 utc_now() 返回 UTC 时区"""
    dt = utc_now()
    assert dt.tzinfo is not None
    assert dt.tzinfo == timezone.utc


def test_format_utc():
    """验证格式化输出含 Z"""
    dt = datetime(2026, 8, 13, 10, 0, 0, 123456, tzinfo=timezone.utc)
    formatted = format_utc(dt)
    assert formatted == "2026-08-13T10:00:00.123456Z"
    assert formatted.endswith("Z")


def test_format_utc_naive_raises():
    """naive datetime 传入 format_utc 应抛出 ValueError"""
    naive = datetime(2026, 8, 13, 10, 0, 0)
    with pytest.raises(ValueError, match="必须带时区"):
        format_utc(naive)


def test_parse_utc_with_z():
    """解析末尾带 Z 的 ISO 字符串"""
    dt = parse_utc("2026-08-13T10:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 8
    assert dt.hour == 10


def test_parse_utc_with_offset():
    """解析带 +00:00 的 ISO 字符串"""
    dt = parse_utc("2026-08-13T10:00:00+00:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 10


def test_parse_utc_other_offset_converts():
    """解析非 UTC 偏移量应正确转换"""
    dt = parse_utc("2026-08-13T12:00:00+02:00")  # 东二区
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 10  # 12 - 2 = 10 UTC


def test_roundtrip():
    """utc_now -> format -> parse 应返回相同时间（秒级容差）"""
    original = utc_now()
    formatted = format_utc(original)
    parsed = parse_utc(formatted)
    # 微秒可能有舍入差异，比较秒级
    assert abs((original - parsed).total_seconds()) < 1.0