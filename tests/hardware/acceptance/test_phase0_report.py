from __future__ import annotations

from pathlib import Path


REPORT = Path(__file__).resolve().parents[3] / "docs" / "reviews" / "PHASE0_ACCEPTANCE_REPORT.md"


def test_phase0_report_contains_pass_evidence_for_every_frozen_gate() -> None:
    report = REPORT.read_text(encoding="utf-8")
    required_evidence = (
        "Overall result: **PASS**",
        "159/159 passed",
        "15/15 passed",
        "33/33 passed",
        "24/24 passed",
        "12/12 passed, none skipped",
        "1,000 actions / 1,000 unique IDs / 1,000 audit records",
        "Registry query P95",
        "Validation, enqueue and simulated completion P95",
        "In-process event dispatch P95",
        "20/20 completed",
        "1,000/1,000",
    )
    for evidence in required_evidence:
        assert evidence in report

    quality_rows = [line for line in report.splitlines() if line.startswith("| ")]
    gate_rows = [
        line
        for line in quality_rows
        if " Required " not in line
        and " Threshold " not in line
        and "---" not in line
    ]
    assert all("PASS" in line for line in gate_rows)
