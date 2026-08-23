from lumneo.memory.evaluator.layer_type import classify_layer_type


class TestLayerTypeGuard:
    """Contract §5.8 风险矩阵校验"""

    # ---------- Preferred ----------
    def test_preferred_identity(self):
        for t in ("preference", "value", "style", "fact", "relationship"):
            assert classify_layer_type("identity", t) == "preferred"

    def test_preferred_episodic(self):
        for t in ("event", "decision"):
            assert classify_layer_type("episodic", t) == "preferred"

    def test_preferred_semantic(self):
        for t in ("fact", "value", "relationship", "preference"):
            assert classify_layer_type("semantic", t) == "preferred"

    def test_preferred_procedural(self):
        for t in ("skill", "decision"):
            assert classify_layer_type("procedural", t) == "preferred"

    # ---------- Acceptable ----------
    def test_acceptable_episodic(self):
        assert classify_layer_type("episodic", "fact") == "acceptable"

    def test_acceptable_semantic(self):
        assert classify_layer_type("semantic", "style") == "acceptable"

    # ---------- Suspicious (E01‑E04 对应) ----------
    def test_suspicious_identity_event(self):
        # E03: identity + event → suspicious
        assert classify_layer_type("identity", "event") == "suspicious"

    def test_suspicious_episodic_preference(self):
        assert classify_layer_type("episodic", "preference") == "suspicious"

    def test_suspicious_semantic_event(self):
        assert classify_layer_type("semantic", "event") == "suspicious"

    def test_suspicious_procedural_relationship(self):
        assert classify_layer_type("procedural", "relationship") == "suspicious"

    # 额外覆盖所有未在 preferred/acceptable 中的组合
    def test_suspicious_other_combinations(self):
        # identity 中未列出的 type (如 skill, event) 已覆盖
        # episodic 中未列出的 type (如 preference, style, skill, relationship, value)
        for t in ("preference", "style", "skill", "relationship", "value"):
            assert classify_layer_type("episodic", t) == "suspicious"
        # semantic 中未列出的 type (除了 fact, value, relationship, preference, style)
        assert classify_layer_type("semantic", "event") == "suspicious"
        assert classify_layer_type("semantic", "skill") == "suspicious"
        # procedural 中未列出的 type (除了 skill, decision)
        for t in ("fact", "preference", "relationship", "style", "value", "event"):
            assert classify_layer_type("procedural", t) == "suspicious"