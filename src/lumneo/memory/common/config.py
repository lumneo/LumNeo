# src/lumneo/memory/common/config.py
"""MemoryOS 配置数据结构（从 app_config.yaml 加载）"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryConfig:
    """MemoryOS 运行时配置"""
    data_dir: Path                      # 记忆数据根目录
    index_db: Path                      # FTS5 数据库完整路径
    index_dir: Path                     # 索引目录
    governance_dir: Path                # 治理目录
    alpha: float = 0.65                 # 检索排名 α
    decay_coefficient: float = 0.05     # 衰减系数
    review_timeout_days: int = 7        # needs_review 超时天数

    @classmethod
    def from_app_config(cls, app_config):
        """从现有的 AppConfig 实例构建 MemoryConfig"""
        return cls(
            data_dir=app_config.memory_data_dir,
            index_db=app_config.memory_index_db,
            index_dir=app_config.memory_index_dir,
            governance_dir=app_config.memory_governance_dir,
            alpha=getattr(app_config, "memory_alpha", 0.65),
            decay_coefficient=getattr(app_config, "memory_decay_coefficient", 0.05),
            review_timeout_days=getattr(app_config, "memory_review_timeout_days", 7),
        )