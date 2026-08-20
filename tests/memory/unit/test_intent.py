# tests/test_intent.py

import pytest
from lumneo.memory.retrieval.intent import analyze_intent


class TestAnalyzeIntent:

    @pytest.mark.parametrize("query,expected_historical,expected_layers,expected_types", [
        # 普通查询
        ("今天天气怎么样", False, None, None),
        ("推荐一本书", False, None, None),
        # 历史查询
        ("我之前说过什么", True, None, None),
        ("历史记录里有哪些", True, None, None),
        ("上次我提到的事情", True, None, None),
        # 纠正查询
        ("纠正一下，我不喜欢咖啡", True, None, None),
        ("实际上我更喜欢茶", True, None, None),
        # 冲突查询
        ("这两条记忆有冲突", True, None, None),
        ("矛盾的地方在哪", True, None, None),
        # 身份查询
        ("我是谁", False, ["identity"], None),
        ("我的身份是什么", False, ["identity"], None),
        # 偏好查询
        ("我喜欢什么", False, None, ["preference"]),
        ("我的偏好", False, None, ["preference"]),
        # 偏好问题不应误加 identity 硬过滤
        ("我的偏好是什么", False, None, ["preference"]),
        # 历史+纠正
        ("之前我说过喜欢咖啡，现在纠正一下", True, None, None),
    ])
    def test_intent_classification(self, query, expected_historical,
                                   expected_layers, expected_types):
        need = analyze_intent(query)
        assert need.include_historical == expected_historical
        if expected_layers is not None:
            assert set(need.layers or []) == set(expected_layers)
        else:
            assert need.layers is None or need.layers == []
        if expected_types is not None:
            assert set(need.types or []) == set(expected_types)
        else:
            assert need.types is None or need.types == []
        # keywords 是用于召回的提取词，不要求复制原始整句。
        assert need.keywords is not None
        # 其他字段为默认值
        assert need.max_results == 20
        assert need.scope_filter is None
        assert need.subject_hint is None

    def test_mixed_identity_and_preference_does_not_apply_and_filter(self):
        need = analyze_intent("我是什么人，是不是软件工程师，喜欢什么咖啡")

        assert need.layers == []
        assert need.types == []
        assert "人" in need.keywords
        assert "喜欢" in need.keywords
        assert "咖啡" in need.keywords
