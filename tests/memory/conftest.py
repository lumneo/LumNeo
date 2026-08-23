# tests/memory/conftest.py
"""MemoryOS 测试共用配置"""
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径，确保 lumneo 可导入
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 确保 lumneo.memory 可被导入
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
