# tests/memory/unit/test_interfaces.py
"""T0.5 — 接口冻结测试：ABC 可导入，方法签名完整"""
from datetime import datetime

from lumneo.memory.storage.repository import MemoryRepository, ConsistencyReport, AuditLogEntry
from lumneo.memory.capture.provider import CaptureProvider, CaptureConfig
from lumneo.memory.common.config import MemoryConfig


def test_memory_repository_abc_importable():
    """验证 MemoryRepository ABC 可导入"""
    assert MemoryRepository is not None
    # 检查是否有抽象方法（至少 9 个）
    methods = [m for m in dir(MemoryRepository) if not m.startswith('_') and callable(getattr(MemoryRepository, m))]
    # 至少包含 create, update_with_version, append_audit_log, get_by_id, query_active, query_by_status, rebuild_index, check_consistency, close
    required = {'create', 'update_with_version', 'append_audit_log', 'get_by_id',
                'query_active', 'query_by_status', 'rebuild_index', 'check_consistency', 'close'}
    assert required.issubset(set(methods))


def test_audit_log_entry_importable():
    """AuditLogEntry 可实例化"""
    entry = AuditLogEntry(
        timestamp=datetime.now(),
        action="capture",
        memory_id="mem_123",
        reason="test",
        source={"tenant": "t1"},
    )
    assert entry.action == "capture"


def test_consistency_report_importable():
    """ConsistencyReport 可实例化"""
    report = ConsistencyReport(status="healthy")
    assert report.status == "healthy"
    assert report.missing_in_index == []


def test_capture_provider_abc_importable():
    """CaptureProvider ABC 可导入，含抽象方法"""
    assert CaptureProvider is not None
    methods = [m for m in dir(CaptureProvider) if not m.startswith('_') and callable(getattr(CaptureProvider, m))]
    assert 'extract_candidates' in methods
    assert 'health_check' in methods


def test_capture_config_importable():
    """CaptureConfig 可实例化"""
    cfg = CaptureConfig(mapping_mode="strict", max_candidates_per_turn=3)
    assert cfg.mapping_mode == "strict"


def test_memory_config_from_app_config():
    """MemoryConfig 可构建（需要 mock AppConfig）"""
    # 我们只测试 dataclass 构造，不从 app_config 加载
    from pathlib import Path
    cfg = MemoryConfig(
        data_dir=Path("/tmp/memory"),
        index_db=Path("/tmp/memory/index/fts5.db"),
        index_dir=Path("/tmp/memory/index"),
        governance_dir=Path("/tmp/memory/governance"),
    )
    assert cfg.data_dir == Path("/tmp/memory")