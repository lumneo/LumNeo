CREATE TABLE IF NOT EXISTS hardware_devices (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_capabilities (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hardware_capabilities_device
    ON hardware_capabilities(device_id);
CREATE TABLE IF NOT EXISTS hardware_actions (
    action_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_action_results (
    action_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_approvals (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_action_transitions (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    action_id TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_reconciliations (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_audits (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hardware_idempotency_keys (
    requester TEXT NOT NULL,
    device_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    parameters_digest TEXT NOT NULL,
    action_id TEXT NOT NULL,
    PRIMARY KEY (requester, device_id, capability_id, idempotency_key)
);
