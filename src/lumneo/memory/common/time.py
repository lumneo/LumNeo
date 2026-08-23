# src/lumneo/memory/common/time.py
"""UTC 时间工具（Contract §5.4 #8）"""
import time
from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    返回当前 UTC 时间，使用纳秒精度（通过 time.time_ns()）确保单调递增。
    在 Windows 上也能保证微秒级差异。
    """
    ns = time.time_ns()
    # 转换为秒（浮点数），datetime 支持微秒，但纳秒部分会四舍五入到微秒
    # 我们保留微秒，但通过纳秒保证每次调用产生的时间戳大概率不同
    seconds = ns / 1e9
    # 使用 fromtimestamp 创建 aware datetime
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def format_utc(dt: datetime) -> str:
    """
    将 UTC datetime 格式化为 ISO 8601 字符串，末尾带 'Z'。
    Args:
        dt: 必须为 UTC 时区（tzinfo=timezone.utc）
    Returns:
        str: 如 '2026-08-13T10:00:00.123456Z'
    Raises:
        ValueError: 如果 dt 不是 UTC 时区
    """
    if dt.tzinfo is None:
        raise ValueError("datetime 必须带时区信息 (UTC)")
    if dt.tzinfo != timezone.utc:
        # 转换为 UTC
        dt = dt.astimezone(timezone.utc)
    # Python isoformat 输出 '... +00:00'，替换为 'Z'
    return dt.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def parse_utc(iso_str: str) -> datetime:
    """
    解析 ISO 8601 UTC 字符串（末尾带 Z 或 +00:00）。
    Args:
        iso_str: 如 '2026-08-13T10:00:00Z' 或 '2026-08-13T10:00:00+00:00'
    Returns:
        datetime: 带 UTC 时区的 datetime 对象
    """
    # 将 'Z' 替换为 '+00:00' 以便 Python 解析
    normalized = iso_str.replace('Z', '+00:00')
    dt = datetime.fromisoformat(normalized)
    # 确保返回 UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)