# src/lumneo/memory/storage/serializer.py
"""MemoryObject <-> Markdown 序列化/反序列化（ADR-009 §3）"""
import os
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from lumneo.memory.model import MemoryObject
from lumneo.memory.common.time import parse_utc


def _to_utc_iso(dt: datetime) -> str:
    """将 datetime 转为 UTC ISO 8601 字符串，末尾带 Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')


def _convert_datetimes_to_str(obj: Any) -> Any:
    """递归将数据结构中的所有 datetime 对象转为 ISO 字符串"""
    if isinstance(obj, datetime):
        return _to_utc_iso(obj)
    elif isinstance(obj, dict):
        return {k: _convert_datetimes_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_datetimes_to_str(item) for item in obj]
    else:
        return obj


def _convert_datetime_strings(obj: Any) -> Any:
    """递归转换所有 ISO 8601 日期字符串为 AwareDatetime"""
    if isinstance(obj, dict):
        return {k: _convert_datetime_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_datetime_strings(item) for item in obj]
    elif isinstance(obj, str):
        # 尝试解析 ISO 8601 格式（包含 T 和 Z 或 +）
        if 'T' in obj and ('Z' in obj or '+' in obj):
            try:
                return parse_utc(obj)
            except (ValueError, TypeError):
                pass
        return obj
    else:
        return obj


def serialize(memory: MemoryObject) -> str:
    """序列化 MemoryObject 为 Markdown 字符串"""
    data = memory.model_dump(mode='python')

    # 递归转换所有 datetime 为字符串
    data = _convert_datetimes_to_str(data)

    # 确保空列表和空字典输出为 [] 和 {}
    # （_convert_datetimes_to_str 不会改变这些，但 yaml.safe_dump 会处理）
    frontmatter_yaml = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    return f"---\n{frontmatter_yaml}---\n\n{memory.content}"


def deserialize(text: str) -> MemoryObject:
    """从 Markdown 字符串反序列化 MemoryObject"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        raise ValueError("Markdown 必须以 '---' 开头")

    # 查找第二个 ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("未找到结束的 '---' 分隔符")

    frontmatter_lines = lines[1:end_idx]
    body_lines = lines[end_idx+1:]
    # 去除 body 开头的空行
    while body_lines and body_lines[0].strip() == '':
        body_lines.pop(0)

    frontmatter_str = '\n'.join(frontmatter_lines)
    body_str = '\n'.join(body_lines)

    metadata = yaml.safe_load(frontmatter_str)
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter 必须为 YAML 字典")

    # 递归转换日期字符串为 AwareDatetime
    metadata = _convert_datetime_strings(metadata)
    metadata['content'] = body_str

    return MemoryObject.model_validate(metadata)


def memory_to_path(memory: MemoryObject, base_dir: Path) -> Path:
    """生成文件路径: base_dir / layer / {id}.md"""
    return base_dir / memory.layer / f"{memory.id}.md"

def write_memory_object(memory: MemoryObject, base_dir: Path) -> None:
    """
    原子写入 MemoryObject 到 data/memory/{layer}/{id}.md。
    
    流程：
    1. 确保目标目录存在
    2. 序列化为 Markdown 文本
    3. 写入临时文件 (.tmp)
    4. flush + fsync 确保物理落盘
    5. os.replace() 原子替换（同文件系统内原子操作）
    """
    file_path = memory_to_path(memory, base_dir)
    # 确保层目录存在（如 data/memory/semantic/）
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 序列化内容
    content = serialize(memory)
    
    # 临时文件路径（同一目录下，保证原子 rename 跨文件系统安全）
    tmp_path = file_path.with_suffix('.tmp')

    # 写入临时文件
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
        # 强制刷新 Python 缓冲区
        f.flush()
        # 强制操作系统刷新到磁盘（确保崩溃时数据已落盘）
        os.fsync(f.fileno())

    # 原子替换（POSIX 保证 rename 是原子的）
    os.replace(tmp_path, file_path)


def read_memory_object(file_path: Path) -> MemoryObject:
    """从文件路径直接读取并反序列化为 MemoryObject"""
    if not file_path.exists():
        raise FileNotFoundError(f"Memory file not found: {file_path}")
    text = file_path.read_text(encoding='utf-8')
    return deserialize(text)