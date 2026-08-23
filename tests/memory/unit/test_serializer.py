# tests/memory/unit/test_serializer.py
"""T5.1 — Markdown 序列化/反序列化单元测试"""
from pathlib import Path

from lumneo.memory.model import MemoryObject, Evidence, Source, PrivacyInfo
from lumneo.memory.storage.serializer import serialize, deserialize, memory_to_path, write_memory_object, read_memory_object
from lumneo.memory.common.time import utc_now


def sample_source(message_id="msg_001") -> Source:
    return Source(
        tenant_id="tenant_a",
        agent_id="agent_1",
        chat_id="chat_001",
        message_id=message_id,
        timestamp=utc_now(),
        channel="chat",
    )


def sample_evidence() -> Evidence:
    return Evidence(
        type="explicit_statement",
        weight=1.0,
        source=sample_source(),
        observation="用户明确说喜欢美式咖啡",
        origin_actor="user",
        created_at=utc_now(),
        provenance_key="msg_001",
    )


def make_test_memory() -> MemoryObject:
    return MemoryObject(
        id="mem_1754918400000000000_a1b2c3d4e5f6",
        schema_version="2.1.2",
        layer="semantic",
        type="preference",
        subject="用户",
        predicate="preference",
        object="美式咖啡",
        condition={"key": "place", "value": "咖啡店"},
        content="用户明确表示自己更喜欢美式咖啡，而不是拿铁。",
        confidence=0.87,
        importance=4,
        status="active",
        evidence=[sample_evidence()],
        source=sample_source(),
        origin="explicit_user",
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata={"standardization_issue": False, "user_forgotten": False},
        tags=["咖啡", "偏好"],
        privacy=PrivacyInfo(level="private", reason="用户偏好"),
    )


def test_serialize_contains_frontmatter_and_body():
    memory = make_test_memory()
    text = serialize(memory)
    assert text.startswith("---\n")
    assert "\n---\n\n" in text
    assert memory.content in text
    assert f"id: {memory.id}" in text
    assert f"schema_version: {memory.schema_version}" in text


def test_serialize_datetime_format():
    memory = make_test_memory()
    text = serialize(memory)
    lines = text.splitlines()
    created_line = [l for l in lines if l.startswith("created_at:")][0]
    assert created_line.endswith("Z") or "Z" in created_line
    updated_line = [l for l in lines if l.startswith("updated_at:")][0]
    assert updated_line.endswith("Z") or "Z" in updated_line


def test_serialize_null_values_explicit():
    memory = make_test_memory()
    memory.supersedes = None
    memory.superseded_by = None
    text = serialize(memory)
    assert "supersedes: null" in text
    assert "superseded_by: null" in text


def test_serialize_empty_list_dict():
    memory = make_test_memory()
    memory.tags = []
    # 即使显式赋空，校验器也会补全默认键，所以我们验证默认键存在
    memory.metadata = {}
    # 验证 tags 为空
    assert memory.tags == []
    # metadata 因校验器补全，不会为空，应包含默认键
    assert memory.metadata["standardization_issue"] is False
    assert memory.metadata["user_forgotten"] is False

    text = serialize(memory)

    # 空列表应输出为 []
    assert "tags: []" in text

    # metadata 不会输出为 {}，而是包含默认键的字典
    # 检查默认键是否正确序列化
    assert "standardization_issue: false" in text
    assert "user_forgotten: false" in text


def test_deserialize_roundtrip():
    original = make_test_memory()
    text = serialize(original)
    reconstructed = deserialize(text)
    assert reconstructed.id == original.id
    assert reconstructed.layer == original.layer
    assert reconstructed.type == original.type
    assert reconstructed.subject == original.subject
    assert reconstructed.predicate == original.predicate
    assert reconstructed.object == original.object
    assert reconstructed.content == original.content
    assert reconstructed.confidence == original.confidence
    assert reconstructed.importance == original.importance
    assert reconstructed.status == original.status
    assert reconstructed.origin == original.origin
    assert reconstructed.supersedes == original.supersedes
    assert reconstructed.superseded_by == original.superseded_by
    assert reconstructed.tags == original.tags
    assert len(reconstructed.evidence) == len(original.evidence)
    # 比较 datetime（忽略微秒）
    assert abs((reconstructed.created_at - original.created_at).total_seconds()) < 1
    assert abs((reconstructed.updated_at - original.updated_at).total_seconds()) < 1


def test_deserialize_without_last_accessed():
    memory = make_test_memory()
    memory.last_accessed = None
    text = serialize(memory)
    reconstructed = deserialize(text)
    assert reconstructed.last_accessed is None


def test_memory_to_path():
    memory = make_test_memory()
    base = Path("/data/memory")
    path = memory_to_path(memory, base)
    expected = base / "semantic" / f"{memory.id}.md"
    assert path.as_posix() == expected.as_posix()


def test_s04_atomic_write(tmp_path):
    """S04 原子写入测试：
    1. 正常写入文件完整可读
    2. 无 .tmp 残留文件
    3. 写入后内容与 MemoryObject 一致
    """
    base_dir = tmp_path / "data" / "memory"
    memory = make_test_memory()
    
    # 写入文件
    write_memory_object(memory, base_dir)
    expected_path = memory_to_path(memory, base_dir)
    
    # 验证文件存在且可读
    assert expected_path.exists()
    assert expected_path.is_file()
    
    # 读取并比对关键字段
    loaded = read_memory_object(expected_path)
    assert loaded.id == memory.id
    assert loaded.layer == memory.layer
    assert loaded.type == memory.type
    assert loaded.content == memory.content
    assert loaded.confidence == memory.confidence
    
    # 验证没有残留的 .tmp 文件
    tmp_files = list(base_dir.glob("**/*.tmp"))
    assert len(tmp_files) == 0, f"残留临时文件: {tmp_files}"
    
    # 验证文件内容不是空的且 YAML 完整（至少包含 schema_version）
    text = expected_path.read_text(encoding='utf-8')
    assert "schema_version: 2.1.2" in text
    assert "---" in text


def test_s04_atomic_write_interrupt_simulation(tmp_path):
    """模拟写入中断：如果只写了 .tmp 但未 rename，原文件应不受影响。
    我们故意不调用 os.replace，手动构造 .tmp，验证 read 不会读到半成品。
    """
    base_dir = tmp_path / "data" / "memory"
    memory = make_test_memory()
    
    # 先正常写入一次（模拟原文件存在）
    write_memory_object(memory, base_dir)
    expected_path = memory_to_path(memory, base_dir)
    original_content = expected_path.read_text(encoding='utf-8')
    
    # 模拟崩溃：构造一个损坏的 .tmp 但程序未执行 rename
    tmp_path = expected_path.with_suffix('.tmp')
    tmp_path.write_text("---\ncorrupted: true\n---\nbad", encoding='utf-8')
    # 但原文件应保持不变，且 read_memory_object 仍然只读原文件（不读 tmp）
    loaded = read_memory_object(expected_path)
    assert loaded.id == memory.id  # 不受影响
    
    # 清理 .tmp（实际场景中启动时会由检查机制清理，但这里只验证原文件安全）
    tmp_path.unlink()
    
    # 验证最终 rename 后依然正确（模拟恢复后重试写入）
    write_memory_object(memory, base_dir)
    assert expected_path.exists()
    assert not tmp_path.exists()  # 新写入不应残留旧 tmp
    # 读取最新内容
    reloaded = read_memory_object(expected_path)
    assert reloaded.confidence == memory.confidence
    # 也可检查版本号
    text = expected_path.read_text(encoding='utf-8')
    assert "schema_version: 2.1.2" in text