from pathlib import Path


REPORT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "reviews"
    / "PHYSICAL_DEVICE_ACCEPTANCE_REPORT.md"
)


def test_physical_acceptance_report_contains_required_failure_and_gate_evidence() -> None:
    report = REPORT.read_text(encoding="utf-8")
    required = (
        "Overall result: **PASS — PHASE 1 READY WITH DOCUMENTED LIMITATIONS**",
        "No Critical or High Contract violation was found",
        "2/2 passed on COM3",
        "esp8266:d3ef6f",
        "FAILED / DEVICE_OFFLINE",
        "RECONCILIATION_REQUIRED",
        "automatic_retry=false",
        "15/15 permission and approval tests passed",
        "159/159 passed",
        "50/50 passed",
        "12/12 passed, none skipped",
        "24/24 passed",
        "404 passed, 2 hardware tests skipped by default",
        "Known limitations and residual risks",
        "No ADR is required",
    )
    for evidence in required:
        assert evidence in report
