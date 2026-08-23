# src/lumneo/memory/common/id_gen.py
"""Memory ID 生成器（Contract §5.4 #8）"""
import time
import secrets
import re
from typing import Optional

# 预编译 ID 正则表达式，用于校验
ID_PATTERN = re.compile(r'^mem_\d+_[a-f0-9]{12}$')


def generate_memory_id() -> str:
    """
    生成全局唯一的 Memory ID。
    格式: mem_{timestamp_nano}_{random}
    其中 random 为 12 位十六进制（6 bytes = 12 hex chars）
    Returns:
        str: 如 'mem_1754918400000000000_a1b2c3d4e5f6'
    """
    timestamp_ns = time.time_ns()
    random_hex = secrets.token_hex(6)  # 12 个字符
    return f"mem_{timestamp_ns}_{random_hex}"


def generate_evidence_id() -> str:
    """
    生成 Evidence ID（用于 SQLite 存储）。
    格式: evi_{timestamp_nano}_{random}
    """
    timestamp_ns = time.time_ns()
    random_hex = secrets.token_hex(6)
    return f"evi_{timestamp_ns}_{random_hex}"


def generate_audit_id() -> str:
    """
    生成 Audit Log ID。
    格式: aud_{timestamp_nano}_{random}
    """
    timestamp_ns = time.time_ns()
    random_hex = secrets.token_hex(6)
    return f"aud_{timestamp_ns}_{random_hex}"


def is_valid_memory_id(memory_id: str) -> bool:
    """校验 ID 是否符合 mem_... 格式"""
    return bool(ID_PATTERN.match(memory_id))