# tests/memory/unit/test_exceptions.py
"""T0.2 统一错误模型 — 单元测试"""
import pytest

from lumneo.memory.common.exceptions import (
    MemoryOSError,
    ValidationError,
    InvalidMemoryError,
    ConflictError,
    ConcurrentModificationError,
    PersistenceError,
    IndexError,
    ScopeViolationError,
)


class TestMemoryOSError:
    """测试根异常基础功能"""

    def test_instantiation_with_message_only(self):
        err = MemoryOSError("测试错误")
        assert err.message == "测试错误"
        assert err.context == {}
        assert str(err) == "测试错误"

    def test_instantiation_with_context(self):
        err = MemoryOSError("存储失败", {"file": "mem_001.md", "code": 13})
        assert err.message == "存储失败"
        assert err.context == {"file": "mem_001.md", "code": 13}
        assert str(err) == "存储失败 (context: {'file': 'mem_001.md', 'code': 13})"

    def test_exception_can_be_caught_as_base(self):
        with pytest.raises(MemoryOSError) as exc_info:
            raise MemoryOSError("根异常")
        assert "根异常" in str(exc_info.value)


class TestExceptionHierarchy:
    """测试所有子异常继承关系正确"""

    @pytest.mark.parametrize("exception_class", [
        ValidationError,
        InvalidMemoryError,
        ConflictError,
        ConcurrentModificationError,
        PersistenceError,
        IndexError,
        ScopeViolationError,
    ])
    def test_all_exceptions_are_subclass_of_memory_os_error(self, exception_class):
        """验证所有 MemoryOS 异常都是 MemoryOSError 的子类"""
        assert issubclass(exception_class, MemoryOSError)
        # 验证可以正常实例化
        inst = exception_class(f"测试 {exception_class.__name__}")
        assert isinstance(inst, MemoryOSError)
        assert inst.message == f"测试 {exception_class.__name__}"

    def test_concurrent_modification_error_specific_subclass(self):
        """ConcurrentModificationError 是 MemoryOSError 子类（ADR-006）"""
        err = ConcurrentModificationError("CAS 失败", {"id": "mem_123"})
        assert isinstance(err, ConcurrentModificationError)
        assert isinstance(err, MemoryOSError)
        assert err.context == {"id": "mem_123"}

    def test_validation_error_does_not_conflict_with_pydantic(self):
        """确保我们的 ValidationError 与 Pydantic 的 ValidationError 可共存"""
        # 这里仅测试我们的异常能被正确识别，不会被误认为 Pydantic 异常
        err = ValidationError("字段格式错误")
        # 不能是 Pydantic 的 ValidationError（我们不导入 pydantic）
        assert not hasattr(err, "model")  # Pydantic 异常通常有 model 属性
        assert isinstance(err, MemoryOSError)

    def test_caught_by_parent_class(self):
        """测试可以用父类捕获所有子异常"""
        try:
            raise ScopeViolationError("无权限")
        except MemoryOSError as e:
            assert isinstance(e, ScopeViolationError)
            assert e.message == "无权限"

    def test_exception_has_context_always(self):
        """验证 context 总是 dict，即使未传入"""
        err = PersistenceError("文件不存在")
        assert err.context is not None
        assert isinstance(err.context, dict)