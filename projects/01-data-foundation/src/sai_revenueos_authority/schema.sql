-- P1.4 local field-authority schema. This executable reference evaluates policy
-- and records decisions; it is not a deployed master-data or write-back service.

PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- One current governed value per canonical entity field. Provenance points back
-- to the source evidence that supplied the accepted value. Manual verification
-- is explicit so later automated proposals cannot silently replace human truth.
CREATE TABLE IF NOT EXISTS canonical_field_state (
    canonical_entity_type TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_record_id TEXT,
    source_event_id TEXT,
    evidence_json TEXT NOT NULL,
    manual_verified INTEGER NOT NULL DEFAULT 0 CHECK (manual_verified IN (0, 1)),
    verified_by TEXT,
    revision INTEGER NOT NULL CHECK (revision > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (canonical_entity_type, canonical_entity_id, field_name)
);

-- Every accepted value or human verification appends history. A correction never
-- overwrites the value and provenance that RevenueOS previously trusted.
CREATE TABLE IF NOT EXISTS field_value_history (
    history_id TEXT PRIMARY KEY,
    canonical_entity_type TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    prior_value_json TEXT,
    value_json TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('initial_value', 'source_update', 'manual_verification',
                   'conflict_approved', 'conflict_rejected')
    ),
    source_system TEXT NOT NULL,
    source_record_id TEXT,
    source_event_id TEXT,
    evidence_json TEXT NOT NULL,
    manual_verified INTEGER NOT NULL CHECK (manual_verified IN (0, 1)),
    actor_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS field_value_history_lookup
ON field_value_history(canonical_entity_type, canonical_entity_id, field_name, recorded_at);

CREATE TRIGGER IF NOT EXISTS field_value_history_immutable
BEFORE UPDATE ON field_value_history
BEGIN
    SELECT RAISE(ABORT, 'field value history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS field_value_history_no_delete
BEFORE DELETE ON field_value_history
BEGIN
    SELECT RAISE(ABORT, 'field value history is immutable');
END;

-- A conflict preserves both values, the evidence supplied for the proposal, and
-- an assigned human owner. Opening a case never changes canonical_field_state.
CREATE TABLE IF NOT EXISTS field_conflict (
    conflict_id TEXT PRIMARY KEY,
    canonical_entity_type TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    current_value_json TEXT NOT NULL,
    current_source_system TEXT NOT NULL,
    current_revision INTEGER NOT NULL CHECK (current_revision > 0),
    proposed_value_json TEXT NOT NULL,
    proposed_source_system TEXT NOT NULL,
    proposed_source_record_id TEXT,
    proposed_source_event_id TEXT,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'escalated', 'approved', 'rejected')),
    assigned_owner_role TEXT NOT NULL,
    assigned_owner_id TEXT,
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    reviewed_by TEXT,
    resolution_reason TEXT
);

CREATE INDEX IF NOT EXISTS field_conflict_queue
ON field_conflict(status, assigned_owner_role, opened_at);

CREATE TRIGGER IF NOT EXISTS field_conflict_evidence_immutable
BEFORE UPDATE ON field_conflict
WHEN NEW.canonical_entity_type <> OLD.canonical_entity_type
  OR NEW.canonical_entity_id <> OLD.canonical_entity_id
  OR NEW.field_name <> OLD.field_name
  OR NEW.current_value_json <> OLD.current_value_json
  OR NEW.current_source_system <> OLD.current_source_system
  OR NEW.current_revision <> OLD.current_revision
  OR NEW.proposed_value_json <> OLD.proposed_value_json
  OR NEW.proposed_source_system <> OLD.proposed_source_system
  OR COALESCE(NEW.proposed_source_record_id, '') <> COALESCE(OLD.proposed_source_record_id, '')
  OR COALESCE(NEW.proposed_source_event_id, '') <> COALESCE(OLD.proposed_source_event_id, '')
  OR NEW.evidence_json <> OLD.evidence_json
  OR NEW.opened_at <> OLD.opened_at
BEGIN
    SELECT RAISE(ABORT, 'field conflict evidence is immutable');
END;

-- Review events are append-only so assignment, escalation, approval, and rejection
-- remain visible even after the conflict's current status changes.
CREATE TABLE IF NOT EXISTS conflict_review_event (
    review_event_id TEXT PRIMARY KEY,
    conflict_id TEXT NOT NULL REFERENCES field_conflict(conflict_id),
    action TEXT NOT NULL CHECK (action IN ('opened', 'assigned', 'escalated', 'approved', 'rejected')),
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    reason TEXT NOT NULL,
    details_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS conflict_review_event_immutable
BEFORE UPDATE ON conflict_review_event
BEGIN
    SELECT RAISE(ABORT, 'conflict review history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS conflict_review_event_no_delete
BEFORE DELETE ON conflict_review_event
BEGIN
    SELECT RAISE(ABORT, 'conflict review history is immutable');
END;

-- A stable change ID makes policy evaluation replay-safe. The original request,
-- outcome, and optional conflict are immutable evidence of every proposal.
CREATE TABLE IF NOT EXISTS field_change_attempt (
    change_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'unchanged', 'review_required', 'denied')),
    conflict_id TEXT,
    field_revision INTEGER,
    reason TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS field_change_attempt_immutable
BEFORE UPDATE ON field_change_attempt
BEGIN
    SELECT RAISE(ABORT, 'field change attempts are immutable');
END;

CREATE TRIGGER IF NOT EXISTS field_change_attempt_no_delete
BEFORE DELETE ON field_change_attempt
BEGIN
    SELECT RAISE(ABORT, 'field change attempts are immutable');
END;

-- Write-back is authorization-only in P1.4. An authorized row records permission
-- to send a trusted value; no network delivery or vendor API call occurs here.
CREATE TABLE IF NOT EXISTS write_back_request (
    request_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    canonical_entity_type TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    target_system TEXT NOT NULL,
    value_json TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    approval_reference TEXT,
    status TEXT NOT NULL CHECK (status IN ('authorized', 'denied')),
    reason TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS write_back_request_immutable
BEFORE UPDATE ON write_back_request
BEGIN
    SELECT RAISE(ABORT, 'write-back authorization history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS write_back_request_no_delete
BEFORE DELETE ON write_back_request
BEGIN
    SELECT RAISE(ABORT, 'write-back authorization history is immutable');
END;

-- A compact general audit stream records all policy decisions. Details are JSON
-- so the reference can preserve evidence without changing the canonical contract.
CREATE TABLE IF NOT EXISTS authority_audit_event (
    audit_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS authority_audit_event_immutable
BEFORE UPDATE ON authority_audit_event
BEGIN
    SELECT RAISE(ABORT, 'authority audit history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS authority_audit_event_no_delete
BEFORE DELETE ON authority_audit_event
BEGIN
    SELECT RAISE(ABORT, 'authority audit history is immutable');
END;
