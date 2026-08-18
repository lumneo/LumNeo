# tests/memory/unit/test_structure.py
"""T0.1 目录结构与配置管理 — 单元测试"""
import yaml
import pytest
from pathlib import Path

# 导入被测模块
from lumneo.kernel.config.app_config import config, PROJECT_ROOT, MIGRATIONS_DIR


# ========== 测试 1: MemoryOS 包可导入 ==========
def test_memory_package_importable():
    """验证 lumneo.memory 可正常导入，所有子包已创建"""
    import lumneo.memory
    import lumneo.memory.capture
    import lumneo.memory.evaluator
    import lumneo.memory.model
    import lumneo.memory.storage
    import lumneo.memory.retrieval
    import lumneo.memory.governance
    import lumneo.memory.context
    import lumneo.memory.common

    # 验证包路径非空
    assert lumneo.memory.__path__ is not None
    assert lumneo.memory.capture.__path__ is not None
    assert lumneo.memory.evaluator.__path__ is not None
    assert lumneo.memory.model.__path__ is not None
    assert lumneo.memory.storage.__path__ is not None
    assert lumneo.memory.retrieval.__path__ is not None
    assert lumneo.memory.governance.__path__ is not None
    assert lumneo.memory.context.__path__ is not None
    assert lumneo.memory.common.__path__ is not None


# ========== 测试 2: data/memory 目录存在且可写 ==========
def get_expected_memory_dirs() -> list[Path]:
    """返回 ADR-009 §2 定义的所有 MemoryOS 子目录"""
    base = config.memory_data_dir
    return [
        base,
        base / "identity",
        base / "episodic",
        base / "semantic",
        base / "procedural",
        base / "governance",
        base / "governance/needs_review",
        base / "governance/rejected",
        base / "governance/conflicts",
        base / "governance/auto_actions",
        base / "governance/index_rebuild_log",
        base / "index",
    ]


def test_memory_dirs_exist():
    """验证 data/memory/ 所有子目录存在且可写"""
    for d in get_expected_memory_dirs():
        assert d.exists(), f"目录不存在: {d}"
        assert d.is_dir(), f"路径不是目录: {d}"
        # 测试可写性（创建临时文件，立即删除）
        test_file = d / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            pytest.fail(f"目录不可写: {d}，错误: {e}")


# ========== 测试 3: Golden YAML 文件可解析 ==========
def get_golden_yaml_paths() -> dict[str, Path]:
    """返回三个 Golden YAML 文件的路径"""
    fixtures_root = Path(__file__).parent.parent / "fixtures"
    return {
        "capture": fixtures_root / "capture/golden_cases.yaml",
        "evaluator": fixtures_root / "evaluator/golden_confidence.yaml",
        "retrieval": fixtures_root / "retrieval/golden_queries.yaml",
    }


def test_golden_yaml_parseable():
    """验证三个 Golden YAML 可被 yaml.safe_load() 解析，且至少含 1 条用例"""
    for name, path in get_golden_yaml_paths().items():
        assert path.exists(), f"{name} YAML 文件不存在: {path}"

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"{name} YAML 解析失败: {e}")

        # 验证至少包含 1 条用例（支持 dict 或 list 结构）
        if isinstance(data, list):
            assert len(data) >= 1, f"{name} YAML 列表为空，至少需要 1 条用例"
        elif isinstance(data, dict):
            # 允许单个 dict 结构，但必须有键
            assert len(data) >= 1, f"{name} YAML 字典为空"
        else:
            pytest.fail(f"{name} YAML 根结构应为 list 或 dict，实际为 {type(data)}")


# ========== 测试 4: Config Loader 返回正确的 MemoryOS 路径 ==========
def test_config_loader_memory_paths():
    """验证 config 对象中的 MemoryOS 路径属性为 Path 对象且存在"""
    # 类型检查
    assert isinstance(config.memory_data_dir, Path)
    assert isinstance(config.memory_index_dir, Path)
    assert isinstance(config.memory_governance_dir, Path)
    assert isinstance(config.memory_index_db, Path)

    # 路径存在性（由 config._ensure_dirs 在实例化时创建）
    assert config.memory_data_dir.exists()
    assert config.memory_data_dir.is_dir()

    # 验证索引数据库路径在 index 目录下
    assert config.memory_index_db.parent == config.memory_index_dir
    assert config.memory_index_db.name == "fts5.db"

    # 验证 governance 目录正确
    assert config.memory_governance_dir == config.memory_data_dir / "governance"

    # 检查检索参数（T0.1 仅做读取验证）
    assert 0.0 <= config.memory_alpha <= 1.0
    assert config.memory_decay_coefficient >= 0.0
    assert config.memory_review_timeout_days >= 1


# ========== 测试 5: 目录结构与 ADR-009 §2 完全一致 ==========
def test_directory_structure_matches_adr009():
    """验证目录树与 ADR-009 §2 强制要求一致"""
    # 修正路径计算：从当前文件位置向上 4 层到达项目根目录
    #   test_structure.py
    #   -> unit (parent)
    #   -> memory (parent.parent)
    #   -> tests (parent.parent.parent)
    #   -> lumneo (parent.parent.parent.parent) — 项目根
    project_root = PROJECT_ROOT

    # 检查 lumneo/memory 子包
    lumneo_memory_base = project_root / "src" / "lumneo" / "memory"
    expected_lumneo_dirs = [
        lumneo_memory_base / "capture",
        lumneo_memory_base / "evaluator",
        lumneo_memory_base / "model",
        lumneo_memory_base / "storage",
        lumneo_memory_base / "retrieval",
        lumneo_memory_base / "governance",
        lumneo_memory_base / "context",
        lumneo_memory_base / "common",
    ]

    for d in expected_lumneo_dirs:
        assert d.exists(), f"src/lumneo/memory 子包缺失: {d}"
        assert d.is_dir()
        init_file = d / "__init__.py"
        assert init_file.exists(), f"子包缺少 __init__.py: {init_file}"

    # 验证 migrations 目录
    migrations_dir = MIGRATIONS_DIR
    assert migrations_dir.exists()
    assert (migrations_dir / "migrate_v0.0_to_v1.0.sql").exists()