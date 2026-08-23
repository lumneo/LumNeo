# tests/memory/test_dedup.py
from datetime import datetime, timezone, timedelta
from lumneo.memory.model.evidence import Evidence, EvidenceType, EvidenceActor
from lumneo.memory.model.auxiliary import Source
from lumneo.memory.evaluator.dedup import deduplicate_evidence


def make_evidence(
    type_: EvidenceType,
    weight: float = 1.0,
    message_id: str = None,
    chat_id: str = None,
    timestamp: datetime = None,
    provenance_key: str = None,
) -> Evidence:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return Evidence(
        type=type_,
        weight=weight,
        source=Source(
            chat_id=chat_id,
            message_id=message_id,
            timestamp=timestamp,
        ),
        observation="test",
        origin_actor="user",
        created_at=timestamp,
        provenance_key=provenance_key,
    )


class TestEvidenceDedup:
    """Contract §5.1 阶段一 证据独立性去重测试 (A.6)"""

    def test_a6_1_same_message_id(self):
        """A.6.1: 同一 message_id 5条 explicit → 去重后1条"""
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("explicit_statement", weight=0.8, message_id="msg_1", chat_id="chat_1", timestamp=ts),
            make_evidence("explicit_statement", weight=1.0, message_id="msg_1", chat_id="chat_1", timestamp=ts),
            make_evidence("explicit_statement", weight=0.9, message_id="msg_1", chat_id="chat_1", timestamp=ts),
            make_evidence("explicit_statement", weight=0.7, message_id="msg_1", chat_id="chat_1", timestamp=ts),
            make_evidence("explicit_statement", weight=0.6, message_id="msg_1", chat_id="chat_1", timestamp=ts),
        ]
        deduped = deduplicate_evidence(evs)
        assert len(deduped) == 1
        assert deduped[0].weight == 1.0  # 最高权重保留

    def test_a6_2_same_chat_2_consecutive(self):
        """A.6.2: 同一 chat_id 连续2轮 → 去重后1条"""
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("explicit_statement", weight=0.8, chat_id="chat_1", message_id="m1", timestamp=ts),
            make_evidence("explicit_statement", weight=0.9, chat_id="chat_1", message_id="m2", timestamp=ts + timedelta(seconds=10)),
        ]
        deduped = deduplicate_evidence(evs, window_seconds=60)  # 10秒<60
        assert len(deduped) == 1
        assert deduped[0].weight == 0.9

    def test_a6_3_same_chat_5_rounds_no_new_evidence(self):
        """A.6.3: 同一 chat_id 5轮无新证据 → 去重后1条"""
        ts = datetime.now(timezone.utc)
        evs = []
        for i in range(5):
            evs.append(make_evidence(
                "explicit_statement",
                weight=0.8 + i*0.05,
                chat_id="chat_1",
                message_id=f"m{i}",
                timestamp=ts + timedelta(seconds=i*30)  # 间隔30秒，总时间2分钟
            ))
        deduped = deduplicate_evidence(evs, window_seconds=120)  # 窗口覆盖所有
        assert len(deduped) == 1
        # 最高权重是最后一个 (0.8+0.2=1.0)
        assert deduped[0].weight == 1.0

    def test_a6_4_different_provenance(self):
        """A.6.4: explicit + behavioral（不同 provenance）→ 保留2条"""
        evs = [
            make_evidence("explicit_statement", weight=1.0, message_id="m1", provenance_key="p1"),
            make_evidence("behavioral", weight=0.8, message_id="m2", provenance_key="p2"),
        ]
        deduped = deduplicate_evidence(evs)
        assert len(deduped) == 2

    def test_a6_5_inference_same_text_shard(self):
        """A.6.5: 10条 inference 同文本分片 → 去重后少数独立片段"""
        # 这里模拟10条inference但共享同一个provenance_key（例如同一原始消息）
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("inference", weight=0.4, provenance_key="src1", chat_id="chat_1", timestamp=ts + timedelta(seconds=i*10))
            for i in range(10)
        ]
        deduped = deduplicate_evidence(evs, window_seconds=0)  # 时间窗口不合并，但provenance合并
        assert len(deduped) == 1
        assert deduped[0].weight == 0.4

    def test_a6_6_user_says_assistant_confirms_shared_provenance(self):
        """A.6.6: 用户说 + 助手确认（共享 provenance）→ 去重后1条"""
        # 模拟用户消息和助手回复，但provenance_key相同（如用户message_id）
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("explicit_statement", weight=1.0, message_id="u1", provenance_key="user_msg_1"),
            make_evidence("confirmation", weight=0.9, message_id="a1", provenance_key="user_msg_1"),  # 共享provenance
        ]
        deduped = deduplicate_evidence(evs)
        assert len(deduped) == 1
        assert deduped[0].weight == 1.0  # explicit权重更高

    # 额外：测试不同chat_id间隔远，应保留多个
    def test_different_chat(self):
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("explicit_statement", weight=1.0, chat_id="chat_1", message_id="m1"),
            make_evidence("explicit_statement", weight=0.9, chat_id="chat_2", message_id="m2"),
        ]
        deduped = deduplicate_evidence(evs)
        assert len(deduped) == 2

    # 测试混合情况：同一chat但间隔大于窗口，应保留2条
    def test_same_chat_long_interval(self):
        ts = datetime.now(timezone.utc)
        evs = [
            make_evidence("explicit_statement", weight=0.8, chat_id="chat_1", timestamp=ts),
            make_evidence("explicit_statement", weight=0.9, chat_id="chat_1", timestamp=ts + timedelta(seconds=600)),  # 10分钟
        ]
        deduped = deduplicate_evidence(evs, window_seconds=300)  # 窗口5分钟
        assert len(deduped) == 2  # 间隔大于窗口，独立