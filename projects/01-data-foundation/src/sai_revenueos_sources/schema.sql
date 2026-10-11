-- P1.3 local source-history schema. This is an executable reference, not a
-- deployed Salesforce, HubSpot, or Snowflake ingestion database.

PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- Persist the complete available source payload before standardization. Identity,
-- tracing, and checkpoint fields are immutable; processing status may advance.
CREATE TABLE IF NOT EXISTS source_event (
    event_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
    source_system TEXT NOT NULL CHECK (source_system IN ('salesforce', 'hubspot')),
    source_tenant TEXT NOT NULL,
    source_object_type TEXT NOT NULL,
    source_object_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('upsert', 'delete')),
    source_updated_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    extraction_id TEXT NOT NULL,
    stream_name TEXT NOT NULL,
    checkpoint_cursor TEXT NOT NULL,
    checkpoint_high_watermark_at TEXT NOT NULL,
    raw_payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    envelope_sha256 TEXT NOT NULL,
    processing_status TEXT NOT NULL CHECK (processing_status IN ('received', 'failed', 'processed')),
    processing_attempts INTEGER NOT NULL DEFAULT 0 CHECK (processing_attempts >= 0),
    last_error_type TEXT,
    last_error_message TEXT,
    source_record_id TEXT,
    became_current INTEGER CHECK (became_current IN (0, 1)),
    received_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TRIGGER IF NOT EXISTS source_event_immutable_envelope
BEFORE UPDATE ON source_event
WHEN NEW.contract_version <> OLD.contract_version
  OR NEW.source_system <> OLD.source_system
  OR NEW.source_tenant <> OLD.source_tenant
  OR NEW.source_object_type <> OLD.source_object_type
  OR NEW.source_object_id <> OLD.source_object_id
  OR NEW.event_type <> OLD.event_type
  OR NEW.source_updated_at <> OLD.source_updated_at
  OR NEW.observed_at <> OLD.observed_at
  OR NEW.trace_id <> OLD.trace_id
  OR NEW.extraction_id <> OLD.extraction_id
  OR NEW.stream_name <> OLD.stream_name
  OR NEW.checkpoint_cursor <> OLD.checkpoint_cursor
  OR NEW.checkpoint_high_watermark_at <> OLD.checkpoint_high_watermark_at
  OR NEW.raw_payload_json <> OLD.raw_payload_json
  OR NEW.payload_sha256 <> OLD.payload_sha256
  OR NEW.envelope_sha256 <> OLD.envelope_sha256
BEGIN
    SELECT RAISE(ABORT, 'source event envelope is immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_event_no_delete
BEFORE DELETE ON source_event
BEGIN
    SELECT RAISE(ABORT, 'source event history is immutable');
END;

-- One successfully standardized history row references its immutable raw event.
-- A deletion is stored as a tombstone rather than removing prior versions.
CREATE TABLE IF NOT EXISTS source_record_version (
    event_id TEXT PRIMARY KEY REFERENCES source_event(event_id),
    source_record_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('upsert', 'delete')),
    source_updated_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    is_tombstone INTEGER NOT NULL CHECK (is_tombstone IN (0, 1)),
    standardized_payload_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS source_record_version_history
ON source_record_version(source_record_id, source_updated_at, observed_at, event_id);

CREATE TRIGGER IF NOT EXISTS source_record_version_immutable
BEFORE UPDATE ON source_record_version
BEGIN
    SELECT RAISE(ABORT, 'source record history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_record_version_no_delete
BEFORE DELETE ON source_record_version
BEGIN
    SELECT RAISE(ABORT, 'source record history is immutable');
END;

-- This table is only the latest source state. It never replaces immutable event
-- and version history, and a tombstone never deletes a P1.2 canonical identity.
CREATE TABLE IF NOT EXISTS source_current_state (
    source_record_id TEXT PRIMARY KEY,
    latest_event_id TEXT NOT NULL UNIQUE REFERENCES source_record_version(event_id),
    source_updated_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL CHECK (is_deleted IN (0, 1)),
    standardized_payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- The checkpoint advances in the same transaction as durable history. The cursor
-- is opaque; high_watermark_at supports a small time-based overlap on the next run.
CREATE TABLE IF NOT EXISTS connector_checkpoint (
    source_system TEXT NOT NULL,
    source_tenant TEXT NOT NULL,
    stream_name TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
    cursor TEXT NOT NULL,
    high_watermark_at TEXT NOT NULL,
    last_event_id TEXT NOT NULL REFERENCES source_event(event_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_system, source_tenant, stream_name)
);
