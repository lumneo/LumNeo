"""Hardware storage metadata without behavior or Domain coupling."""

SCHEMA_VERSION = 1
HARDWARE_TABLES = (
    "hardware_devices",
    "hardware_capabilities",
    "hardware_actions",
    "hardware_action_results",
    "hardware_approvals",
    "hardware_action_transitions",
    "hardware_events",
    "hardware_reconciliations",
    "hardware_audits",
    "hardware_idempotency_keys",
)

__all__ = ("HARDWARE_TABLES", "SCHEMA_VERSION")
