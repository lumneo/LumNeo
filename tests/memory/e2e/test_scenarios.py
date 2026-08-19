"""
E2E 场景 1-5（M7 Gate）
"""
import pytest
from lumneo.memory.capture import capture
from lumneo.memory.evaluator.state_machine import Evaluator
from lumneo.memory.retrieval import retrieve
from lumneo.memory.context.builder import build_context
from lumneo.memory.governance.directives import apply_user_directives, UserDirective
from lumneo.memory.model import ConversationTurn, MemoryBudget, MemoryNeed
from lumneo.memory.common.time import utc_now
from lumneo.memory.storage.repository import SQLiteMemoryRepository


@pytest.fixture(scope="function")
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    data_root = tmp_path / "memory"
    repo = SQLiteMemoryRepository(db_path, data_root)
    yield repo
    repo.close()


def test_e2e_01_preference(repo):
    """用户表达偏好 → Capture → Evaluate → Store → Retrieve → Context 包含该记忆"""
    turn = ConversationTurn(
        role="user",
        content="我喜欢安静的咖啡馆",
        message_id="msg1",
        chat_id="chat1",
        timestamp=utc_now(),
    )
    candidates = capture([turn])
    evaluator = Evaluator(repository=repo)
    evaluator.evaluate_batch(candidates, directives=[])

    need = MemoryNeed(keywords=[], layers=[], types=[])
    results = retrieve(need, repository=repo)

    budget = MemoryBudget(max_tokens=1000, max_preferences=5)
    ctx = build_context(results, budget)

    assert len(results) >= 1
    assert any("安静的咖啡馆" in mem.content for mem in results)
    assert "安静的咖啡馆" in ctx


def test_e2e_02_correction(repo):
    """先"喜欢咖啡"后纠正为"茶" → 咖啡 superseded，茶 active"""
    turn1 = ConversationTurn(
        role="user",
        content="我喜欢咖啡",
        message_id="msg1",
        chat_id="chat1",
        timestamp=utc_now(),
    )
    cand1 = capture([turn1])
    evaluator = Evaluator(repository=repo)
    mem1 = evaluator.evaluate_batch(cand1)[0]

    turn2 = ConversationTurn(
        role="user",
        content="其实我更喜欢茶，纠正我之前的说法",
        message_id="msg2",
        chat_id="chat1",
        reply_to_message_id="msg1",
        timestamp=utc_now(),
    )
    cand2 = capture([turn2])

    directive = UserDirective(
        type="correct",
        target=mem1.id,
        target_type="memory_id",
        raw_text="纠正为茶",
        created_at=utc_now(),
    )

    for cand in cand2:
        cand.correction_target = mem1.id

    mem2 = evaluator.evaluate_batch(cand2, directives=[directive])[0]

    need = MemoryNeed(keywords=[], layers=[], types=[])
    results = retrieve(need, repository=repo)

    active_contents = [m.content for m in results if m.status == "active"]
    assert any("茶" in c for c in active_contents)
    assert not any("咖啡" in c for c in active_contents)

    coffee_mem = repo.get_by_id(mem1.id)
    assert coffee_mem.status == "superseded"
    assert coffee_mem.superseded_by == mem2.id


def test_e2e_03_forget(repo):
    """forget 咖啡 → archived，默认 retrieve 不返回，include_historical=True 可返回"""
    turn = ConversationTurn(
        role="user",
        content="我喜欢咖啡",
        message_id="msg1",
        chat_id="chat1",
        timestamp=utc_now(),
    )
    cand = capture([turn])
    evaluator = Evaluator(repository=repo)
    mem = evaluator.evaluate_batch(cand)[0]

    directive = UserDirective(
        type="forget",
        target=mem.id,
        target_type="memory_id",
        raw_text="忘记咖啡",
        created_at=utc_now(),
    )
    apply_user_directives([directive], repository=repo)

    need = MemoryNeed(keywords=[], layers=[], types=[])
    results = retrieve(need, repository=repo)
    assert not any(m.id == mem.id for m in results)

    need_hist = MemoryNeed(keywords=[], layers=[], types=[], include_historical=True)
    hist_results = retrieve(need_hist, repository=repo)
    assert any(m.id == mem.id for m in hist_results)

    archived_mem = repo.get_by_id(mem.id)
    assert archived_mem.status == "archived"
    assert archived_mem.metadata.get("user_forgotten") is True


def test_e2e_04_independent_preferences(repo):
    """两个明显不同的偏好，各自独立写入，均保持 active"""
    # 第一个偏好：咖啡（chat1）
    turn1 = ConversationTurn(
        role="user",
        content="我喜欢咖啡",
        message_id="msg1",
        chat_id="chat1",
        timestamp=utc_now(),
    )
    cand1 = capture([turn1])
    evaluator = Evaluator(repository=repo)
    mem1 = evaluator.evaluate_batch(cand1)[0]
    assert mem1.status == "active"

    # 第二个偏好：茶（chat2，独立证据）
    turn2 = ConversationTurn(
        role="user",
        content="我喜欢茶",
        message_id="msg2",
        chat_id="chat2",
        timestamp=utc_now(),
    )
    cand2 = capture([turn2])
    for cand in cand2:
        cand.source.chat_id = "chat2"  # 明确不同 chat，确保独立

    mem2 = evaluator.evaluate_batch(cand2)[0]
    assert mem2.status == "active"

    # 查询所有 active 记忆
    all_mems = repo.query_active(
        MemoryNeed(keywords=[], layers=[], types=[]), scope_filter=None
    )
    active_ids = [m.id for m in all_mems if m.status == "active"]
    # 两个独立偏好应同时 active
    assert len(active_ids) == 2
    assert mem1.id in active_ids
    assert mem2.id in active_ids


def test_e2e_05_scope(repo):
    """tenant-A/agent-A 与 tenant-B/agent-B 数据隔离"""
    # 写入 A
    turn_a = ConversationTurn(
        role="user",
        content="A喜欢安静",
        message_id="msgA",
        chat_id="chatA",
        timestamp=utc_now(),
        metadata={"tenant_id": "tenantA", "agent_id": "agentA"},
    )
    cand_a = capture([turn_a])
    for cand in cand_a:
        cand.source.tenant_id = "tenantA"
        cand.source.agent_id = "agentA"
    evaluator = Evaluator(repository=repo)
    mem_a = evaluator.evaluate_batch(cand_a)[0]
    assert mem_a.status == "active"

    # 写入 B
    turn_b = ConversationTurn(
        role="user",
        content="B喜欢热闹",
        message_id="msgB",
        chat_id="chatB",
        timestamp=utc_now(),
        metadata={"tenant_id": "tenantB", "agent_id": "agentB"},
    )
    cand_b = capture([turn_b])
    for cand in cand_b:
        cand.source.tenant_id = "tenantB"
        cand.source.agent_id = "agentB"
    mem_b = evaluator.evaluate_batch(cand_b)[0]
    assert mem_b.status == "active"

    # 检索 A 租户
    need_a = MemoryNeed(keywords=[], layers=[], types=[])
    need_a.scope_filter = {"tenant_id": "tenantA", "agent_id": "agentA"}
    results_a = retrieve(need_a, repository=repo)
    assert len(results_a) == 1
    assert results_a[0].id == mem_a.id
    assert all(m.id != mem_b.id for m in results_a)

    # 检索 B 租户
    need_b = MemoryNeed(keywords=[], layers=[], types=[])
    need_b.scope_filter = {"tenant_id": "tenantB", "agent_id": "agentB"}
    results_b = retrieve(need_b, repository=repo)
    assert len(results_b) == 1
    assert results_b[0].id == mem_b.id
    assert all(m.id != mem_a.id for m in results_b)

    # 验证所有返回的记忆的 scope 匹配
    for m in results_a:
        assert m.source.tenant_id == "tenantA" and m.source.agent_id == "agentA"
    for m in results_b:
        assert m.source.tenant_id == "tenantB" and m.source.agent_id == "agentB"