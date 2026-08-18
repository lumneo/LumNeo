# src/lumneo/kernel/config/app_config.py
# Kernel / Config —— 配置基础能力（不拥有具体业务配置逻辑）。
#
# 仅负责加载 app_config.yaml、解析并校验路径、
# 确保可写目录存在。任何业务策略（Memory Ranking / Hardware Execution 等）
# 不得放入此处。
import os
import sys
from pathlib import Path
import yaml


def find_project_root(start: Path | None = None) -> Path:
    """向上回溯，定位包含 app_config.yaml 的项目根目录。

    同时兼容开发环境（cwd 即项目根）与打包环境（_MEIPASS 内）。
    """
    search = start or Path(__file__).resolve()
    # 也从当前工作目录开始找，覆盖 `python main.py` 直接运行的场景
    candidates = [search, Path.cwd()]
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", ".")))

    seen = set()
    for base in candidates:
        base = base.resolve()
        for _ in range(8):  # 最多向上 8 层
            if (base / "app_config.yaml").exists():
                return base
            if str(base) in seen:
                break
            seen.add(str(base))
            parent = base.parent
            if parent == base:
                break
            base = parent
    # 兜底：返回当前工作目录
    return Path.cwd().resolve()


class AppConfig:
    """全局应用配置。"""

    def __init__(self, config_file: str = "app_config.yaml"):
        self.config_file = config_file
        self.project_root = find_project_root()
        self.raw_config = self._load_yaml()
        self._resolve_paths()
        self._ensure_dirs()

    def _load_yaml(self):
        search_paths = [
            self.project_root / self.config_file,
            Path.cwd() / self.config_file,
        ]
        if getattr(sys, "frozen", False):
            search_paths.append(Path(getattr(sys, "_MEIPASS", ".")) / self.config_file)

        for path in search_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}

        # 未找到时使用内置默认，保证系统可启动
        return {}

    def _resolve_paths(self):
        if getattr(sys, "frozen", False):
            self.executable_dir = Path(sys.executable).parent
            self.resource_dir = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
            data_dir_raw = self.raw_config.get("data_dir", "data")
            self.data_dir = self._resolve_path(data_dir_raw, base=self.executable_dir)
        else:
            self.resource_dir = self.project_root
            self.data_dir = self.project_root

        self.uploads_dir = self.data_dir / self.raw_config.get("uploads_dir", "data/uploads")
        self.cache_dir = self.data_dir / self.raw_config.get("cache_dir", "data/cache")
        self.logs_dir = self.data_dir / self.raw_config.get("logs_dir", "logs")
        self.temp_dir = self.data_dir / self.raw_config.get("temp_dir", "temp")
        self.skills_dir = self.data_dir / self.raw_config.get("skills_dir", "skills")
        self.generate_dir = self.data_dir / self.raw_config.get("generate_dir", "data/generate")

        mcp_raw = self.raw_config.get("mcp_config_path", "mcp_config.json")
        if Path(mcp_raw).is_absolute():
            self.mcp_config_path = Path(mcp_raw)
        else:
            self.mcp_config_path = self.data_dir / mcp_raw

        static_rel = self.raw_config.get("static_dir", "html")
        self.static_dir = self.resource_dir / static_rel

        self.max_upload_size = int(self.raw_config.get("max_upload_size_mb", 100)) * 1024 * 1024

        # ========== MemoryOS 路径解析 ==========
        memory_cfg = self.raw_config.get("memory", {})
        memory_data_raw = memory_cfg.get("data_dir", "data/memory")
        # 支持绝对路径或相对于 data_dir
        if Path(memory_data_raw).is_absolute():
            self.memory_data_dir = Path(memory_data_raw)
        else:
            self.memory_data_dir = self.data_dir / memory_data_raw

        # 固定子目录
        self.memory_index_dir = self.memory_data_dir / "index"
        self.memory_governance_dir = self.memory_data_dir / "governance"
        # 索引数据库路径
        index_db_name = memory_cfg.get("index_db", "fts5.db")
        self.memory_index_db = self.memory_index_dir / index_db_name

        # 检索参数（保留供后续使用）
        retrieval_cfg = memory_cfg.get("retrieval", {})
        self.memory_alpha = retrieval_cfg.get("alpha", 0.65)
        self.memory_decay_coefficient = retrieval_cfg.get("decay_coefficient", 0.05)

        # 治理参数
        governance_cfg = memory_cfg.get("governance", {})
        self.memory_review_timeout_days = governance_cfg.get("review_timeout_days", 7)

    def _resolve_path(self, path_str: str, base: Path) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        return base / p

    def _ensure_dirs(self):
        dirs = [
            self.data_dir,
            self.uploads_dir,
            self.cache_dir,
            self.logs_dir,
            self.temp_dir,
            self.skills_dir,
            self.generate_dir,
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                fallback_base = Path(
                    os.environ.get("APPDATA", Path.home() / "AppData/Roaming")
                ) / ".LumNeo"
                self.data_dir = fallback_base
                self.uploads_dir = fallback_base / "uploads"
                self.cache_dir = fallback_base / "cache"
                self.logs_dir = fallback_base / "logs"
                self.temp_dir = fallback_base / "temp"
                self.skills_dir = fallback_base / "skills"
                self.mcp_config_path = fallback_base / "mcp_config.json"
                # 再次创建
                for d2 in [self.data_dir, self.uploads_dir, self.cache_dir, self.logs_dir, self.temp_dir, self.skills_dir]:
                    d2.mkdir(parents=True, exist_ok=True)
                break

        # ========== MemoryOS 目录创建 ==========
        # 定义 MemoryOS 所有子目录（按 ADR-009 §2）
        memory_subdirs = [
            self.memory_data_dir,
            self.memory_data_dir / "identity",
            self.memory_data_dir / "episodic",
            self.memory_data_dir / "semantic",
            self.memory_data_dir / "procedural",
            self.memory_governance_dir,
            self.memory_governance_dir / "needs_review",
            self.memory_governance_dir / "rejected",
            self.memory_governance_dir / "conflicts",
            self.memory_governance_dir / "auto_actions",
            self.memory_governance_dir / "index_rebuild_log",
            self.memory_index_dir,
        ]
        for d in memory_subdirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # 如果 memory_data_dir 权限不足，尝试 fallback 到应用 data_dir 下的 memory
                fallback_memory = self.data_dir / "memory"
                # 重新设定 memory_data_dir 为 fallback
                self.memory_data_dir = fallback_memory
                self.memory_index_dir = fallback_memory / "index"
                self.memory_governance_dir = fallback_memory / "governance"
                self.memory_index_db = self.memory_index_dir / "fts5.db"
                # 重新创建 fallback 子目录
                for d2 in [
                    self.data_dir,
                    self.uploads_dir,
                    self.cache_dir,
                    self.logs_dir,
                    self.temp_dir,
                    self.skills_dir,
                    fallback_memory,
                    fallback_memory / "identity",
                    fallback_memory / "episodic",
                    fallback_memory / "semantic",
                    fallback_memory / "procedural",
                    fallback_memory / "governance",
                    fallback_memory / "governance/needs_review",
                    fallback_memory / "governance/rejected",
                    fallback_memory / "governance/conflicts",
                    fallback_memory / "governance/auto_actions",
                    fallback_memory / "governance/index_rebuild_log",
                    fallback_memory / "index",
                ]:
                    d2.mkdir(parents=True, exist_ok=True)
                break

    @property
    def frontend_index(self) -> str:
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
        else:
            base_path = self.project_root

        index_path = base_path / "apps/desktop/dist/index.html"
        if not index_path.exists():
            fallback_path = self.static_dir / "index.html"
            if fallback_path.exists():
                index_path = fallback_path
            else:
                raise FileNotFoundError(f"前端入口文件不存在: {index_path}")
        return str(index_path.resolve())

    def resource_path(self, relative_path: str) -> str:
        """获取打包/开发环境下的资源绝对路径（图标等）。"""
        if getattr(sys, "frozen", False):
            base_path = Path(getattr(sys, "_MEIPASS", str(self.project_root)))
        else:
            base_path = self.project_root
        return str(base_path / relative_path)

    @property
    def db_path(self) -> Path:
        """数据库文件路径。

        与 uploads / cache / generate 同处 data 子目录（data_dir/data），
        开发态下即 项目根/data/lumneo.db，避免散落到项目根目录。
        """
        return self.data_dir / "data" / "lumneo.db"


config = AppConfig()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"