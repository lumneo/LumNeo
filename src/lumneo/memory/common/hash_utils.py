# src/lumneo/memory/common/hash_utils.py
import hashlib
from typing import Optional

def compute_dedup_key(layer: Optional[str], subject: Optional[str],
                      predicate: Optional[str], obj: Optional[str],
                      message_id: Optional[str]) -> str:
    """生成 dedup_key：使用 SHA256 对非空字段拼接后取十六进制摘要。"""
    parts = [layer, subject, predicate, obj, message_id]
    # 过滤掉 None 或空字符串
    parts = [p for p in parts if p]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()