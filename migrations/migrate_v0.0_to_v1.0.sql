-- migrations/migrate_v0.0_to_v1.0.sql
-- ADR-007: SQLite Storage Schema v1.0
-- 基线初始化脚本，幂等可重复执行

BEGIN TRANSACTION;

-- 3.1 元信息表
CREATE TABLE IF NOT EXISTS _schema_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

INSERT OR IGNORE INTO _schema_meta (key, value) VALUES ('storage_schema_version', '1.0');
INSERT OR IGNORE INTO _schema_meta (key, value) VALUES ('contract_version', '2.1.2');
INSERT OR IGNORE INTO _schema_meta (key, value) VALUES ('created_at', datetime('now'));

-- 3.2 memories 主表
CREATE TABLE IF NOT EXISTS memories (
    id                  TEXT PRIMARY KEY,
    schema_version      TEXT NOT NULL DEFAULT '2.1.2',
    layer               TEXT NOT NULL CHECK(layer IN ('identity','episodic','semantic','procedural')),
    type                TEXT NOT NULL CHECK(type IN ('fact','preference','decision','relationship','event','value','style','skill')),
    subject             TEXT,
    predicate           TEXT,
    object              TEXT,
    condition_json      TEXT,               -- JSON 序列化
    content             TEXT NOT NULL,
    confidence          REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    importance          INTEGER NOT NULL CHECK(importance >= 1 AND importance <= 5),
    status              TEXT NOT NULL CHECK(status IN ('candidate','active','superseded','archived','stale','rejected','needs_review')),
    origin              TEXT NOT NULL CHECK(origin IN ('explicit_user','assistant_inferred','system_generated','external_import')),
    supersedes          TEXT,
    superseded_by       TEXT,
    last_accessed       TEXT,
    access_count        INTEGER NOT NULL DEFAULT 0,
    tags_json           TEXT,               -- JSON 数组
    privacy_json        TEXT,               -- JSON 对象
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    metadata_json       TEXT,
    source_json         TEXT NOT NULL,
    evidence_count      INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (supersedes) REFERENCES memories(id) ON DELETE SET NULL,
    FOREIGN KEY (superseded_by) REFERENCES memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_layer_type ON memories(layer, type);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_subject_predicate ON memories(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_origin ON memories(origin);

-- Scope 隔离索引
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(
    json_extract(source_json, '$.tenant_id'),
    json_extract(source_json, '$.agent_id')
);

-- 3.3 evidence 表
CREATE TABLE IF NOT EXISTS evidence (
    id              TEXT PRIMARY KEY,     -- evi_{timestamp_nano}_{random}
    memory_id       TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('explicit_statement','confirmation','repeated_observation','behavioral','inference')),
    weight          REAL NOT NULL CHECK(weight >= 0.3 AND weight <= 1.0),
    source_json     TEXT NOT NULL,
    observation     TEXT NOT NULL,
    origin_actor    TEXT NOT NULL CHECK(origin_actor IN ('user','assistant','system','external')),
    created_at      TEXT NOT NULL,
    provenance_key  TEXT,

    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evidence_memory ON evidence(memory_id);
CREATE INDEX IF NOT EXISTS idx_evidence_provenance ON evidence(provenance_key);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(type);

-- 3.4 audit_logs 表
CREATE TABLE IF NOT EXISTS audit_logs (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    action      TEXT NOT NULL,
    memory_id   TEXT,
    reason      TEXT NOT NULL,
    source_json TEXT NOT NULL,
    payload_json TEXT,

    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_memory ON audit_logs(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);

-- 3.5 FTS5 虚拟表（外部内容）
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    subject,
    predicate,
    object,
    tags,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- 触发器：保持 FTS5 与主表同步
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, subject, predicate, object, tags)
    VALUES (new.rowid, new.content, new.subject, new.predicate, new.object, new.tags_json);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, subject, predicate, object, tags)
    VALUES ('delete', old.rowid, old.content, old.subject, old.predicate, old.object, old.tags_json);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, subject, predicate, object, tags)
    VALUES ('delete', old.rowid, old.content, old.subject, old.predicate, old.object, old.tags_json);
    INSERT INTO memories_fts(rowid, content, subject, predicate, object, tags)
    VALUES (new.rowid, new.content, new.subject, new.predicate, new.object, new.tags_json);
END;

COMMIT;