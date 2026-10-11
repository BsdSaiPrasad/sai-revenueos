PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS canonical_identity (
    canonical_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    identity_status TEXT NOT NULL DEFAULT 'active'
        CHECK (identity_status IN ('active', 'retired')),
    redirect_to_canonical_id TEXT,
    created_at TEXT NOT NULL,
    retired_at TEXT,
    FOREIGN KEY (redirect_to_canonical_id) REFERENCES canonical_identity(canonical_id),
    CHECK (
        (identity_status = 'active' AND redirect_to_canonical_id IS NULL AND retired_at IS NULL)
        OR
        (identity_status = 'retired' AND redirect_to_canonical_id IS NOT NULL AND retired_at IS NOT NULL)
    )
);

CREATE TRIGGER IF NOT EXISTS canonical_identity_no_delete
BEFORE DELETE ON canonical_identity
BEGIN
    SELECT RAISE(ABORT, 'canonical IDs are permanent and cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS canonical_identity_guard_update
BEFORE UPDATE ON canonical_identity
WHEN NEW.canonical_id IS NOT OLD.canonical_id
  OR NEW.entity_type IS NOT OLD.entity_type
  OR NOT (
      (OLD.identity_status = 'active' AND NEW.identity_status = 'retired')
      OR (OLD.identity_status = 'retired' AND NEW.identity_status = 'active')
  )
BEGIN
    SELECT RAISE(ABORT, 'invalid canonical identity mutation');
END;

CREATE TABLE IF NOT EXISTS source_record (
    source_record_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_tenant TEXT NOT NULL,
    source_object_type TEXT NOT NULL,
    source_object_id TEXT NOT NULL,
    normalized_source_system TEXT NOT NULL,
    normalized_source_tenant TEXT NOT NULL,
    normalized_source_object_type TEXT NOT NULL,
    normalized_source_object_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    UNIQUE (
        normalized_source_system,
        normalized_source_tenant,
        normalized_source_object_type,
        normalized_source_object_id
    )
);

CREATE TRIGGER IF NOT EXISTS source_record_identity_immutable
BEFORE UPDATE ON source_record
WHEN NEW.source_record_id IS NOT OLD.source_record_id
  OR NEW.source_system IS NOT OLD.source_system
  OR NEW.source_tenant IS NOT OLD.source_tenant
  OR NEW.source_object_type IS NOT OLD.source_object_type
  OR NEW.source_object_id IS NOT OLD.source_object_id
  OR NEW.normalized_source_system IS NOT OLD.normalized_source_system
  OR NEW.normalized_source_tenant IS NOT OLD.normalized_source_tenant
  OR NEW.normalized_source_object_type IS NOT OLD.normalized_source_object_type
  OR NEW.normalized_source_object_id IS NOT OLD.normalized_source_object_id
BEGIN
    SELECT RAISE(ABORT, 'source identity fields are immutable');
END;

CREATE TABLE IF NOT EXISTS source_observation (
    source_observation_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    observation_key TEXT NOT NULL UNIQUE,
    observed_at TEXT NOT NULL,
    record_fingerprint TEXT,
    payload_reference TEXT,
    FOREIGN KEY (source_record_id) REFERENCES source_record(source_record_id)
);

CREATE TRIGGER IF NOT EXISTS source_observation_immutable
BEFORE UPDATE ON source_observation
BEGIN
    SELECT RAISE(ABORT, 'source observations are immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_observation_no_delete
BEFORE DELETE ON source_observation
BEGIN
    SELECT RAISE(ABORT, 'source observations cannot be deleted');
END;

CREATE TABLE IF NOT EXISTS resolution_case (
    resolution_case_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'unresolved'
        CHECK (status IN ('unresolved', 'candidate', 'ambiguous', 'pending_review', 'resolved', 'no_match')),
    review_required INTEGER NOT NULL DEFAULT 0 CHECK (review_required IN (0, 1)),
    reason TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_record_id) REFERENCES source_record(source_record_id)
);

CREATE TRIGGER IF NOT EXISTS resolution_case_valid_transition
BEFORE UPDATE OF status ON resolution_case
WHEN OLD.status <> NEW.status
 AND NOT (
    (OLD.status = 'unresolved' AND NEW.status IN ('candidate', 'ambiguous', 'pending_review', 'resolved', 'no_match'))
    OR (OLD.status = 'candidate' AND NEW.status IN ('ambiguous', 'pending_review', 'resolved', 'no_match'))
    OR (OLD.status = 'ambiguous' AND NEW.status = 'pending_review')
    OR (OLD.status = 'pending_review' AND NEW.status IN ('ambiguous', 'resolved', 'no_match'))
    OR (OLD.status = 'resolved' AND NEW.status IN ('pending_review', 'no_match'))
    OR (OLD.status = 'no_match' AND NEW.status IN ('candidate', 'ambiguous', 'pending_review'))
 )
BEGIN
    SELECT RAISE(ABORT, 'invalid resolution status transition');
END;

CREATE TABLE IF NOT EXISTS candidate_evidence (
    candidate_evidence_id TEXT PRIMARY KEY,
    resolution_case_id TEXT NOT NULL,
    candidate_canonical_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    method TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    disposition TEXT NOT NULL DEFAULT 'proposed'
        CHECK (disposition IN ('proposed', 'accepted', 'rejected', 'expired')),
    created_at TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    decision_reason TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (resolution_case_id) REFERENCES resolution_case(resolution_case_id),
    FOREIGN KEY (candidate_canonical_id) REFERENCES canonical_identity(canonical_id),
    CHECK (
        (disposition = 'proposed' AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR
        (disposition IN ('accepted', 'rejected', 'expired') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
    )
);

CREATE TRIGGER IF NOT EXISTS candidate_evidence_guard_update
BEFORE UPDATE ON candidate_evidence
WHEN NEW.candidate_evidence_id IS NOT OLD.candidate_evidence_id
  OR NEW.resolution_case_id IS NOT OLD.resolution_case_id
  OR NEW.candidate_canonical_id IS NOT OLD.candidate_canonical_id
  OR NEW.evidence_type IS NOT OLD.evidence_type
  OR NEW.evidence_reference IS NOT OLD.evidence_reference
  OR NEW.confidence IS NOT OLD.confidence
  OR NEW.method IS NOT OLD.method
  OR NEW.policy_version IS NOT OLD.policy_version
  OR NEW.created_at IS NOT OLD.created_at
  OR NEW.idempotency_key IS NOT OLD.idempotency_key
  OR NOT (OLD.disposition = 'proposed' AND NEW.disposition IN ('accepted', 'rejected', 'expired'))
BEGIN
    SELECT RAISE(ABORT, 'candidate evidence is immutable except for its first decision');
END;

CREATE TABLE IF NOT EXISTS external_identity_crosswalk (
    external_identity_crosswalk_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    canonical_entity_type TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    mapping_status TEXT NOT NULL CHECK (mapping_status IN ('active', 'superseded', 'revoked')),
    mapping_method TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    supersedes_crosswalk_id TEXT,
    reviewed_by TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    correction_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_record_id) REFERENCES source_record(source_record_id),
    FOREIGN KEY (canonical_entity_id) REFERENCES canonical_identity(canonical_id),
    FOREIGN KEY (supersedes_crosswalk_id) REFERENCES external_identity_crosswalk(external_identity_crosswalk_id),
    CHECK (
        (mapping_status = 'active' AND valid_to IS NULL)
        OR
        (mapping_status IN ('superseded', 'revoked') AND valid_to IS NOT NULL)
    ),
    CHECK (valid_to IS NULL OR valid_from < valid_to)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_mapping_per_source
ON external_identity_crosswalk(source_record_id)
WHERE mapping_status = 'active' AND valid_to IS NULL;

CREATE TRIGGER IF NOT EXISTS crosswalk_target_type_insert
BEFORE INSERT ON external_identity_crosswalk
WHEN NOT EXISTS (
    SELECT 1 FROM canonical_identity c
    WHERE c.canonical_id = NEW.canonical_entity_id
      AND c.entity_type = NEW.canonical_entity_type
      AND c.identity_status = 'active'
)
BEGIN
    SELECT RAISE(ABORT, 'crosswalk target must be an active canonical identity of the declared type');
END;

CREATE TRIGGER IF NOT EXISTS crosswalk_no_overlap_insert
BEFORE INSERT ON external_identity_crosswalk
WHEN EXISTS (
    SELECT 1 FROM external_identity_crosswalk x
    WHERE x.source_record_id = NEW.source_record_id
      AND NEW.valid_from < COALESCE(x.valid_to, '9999-12-31T23:59:59.999999Z')
      AND x.valid_from < COALESCE(NEW.valid_to, '9999-12-31T23:59:59.999999Z')
)
BEGIN
    SELECT RAISE(ABORT, 'crosswalk validity intervals cannot overlap');
END;

CREATE TRIGGER IF NOT EXISTS crosswalk_guard_update
BEFORE UPDATE ON external_identity_crosswalk
WHEN NEW.external_identity_crosswalk_id IS NOT OLD.external_identity_crosswalk_id
  OR NEW.source_record_id IS NOT OLD.source_record_id
  OR NEW.canonical_entity_type IS NOT OLD.canonical_entity_type
  OR NEW.canonical_entity_id IS NOT OLD.canonical_entity_id
  OR NEW.mapping_method IS NOT OLD.mapping_method
  OR NEW.confidence IS NOT OLD.confidence
  OR NEW.valid_from IS NOT OLD.valid_from
  OR NEW.supersedes_crosswalk_id IS NOT OLD.supersedes_crosswalk_id
  OR NEW.reviewed_by IS NOT OLD.reviewed_by
  OR NEW.reviewed_at IS NOT OLD.reviewed_at
  OR NEW.created_at IS NOT OLD.created_at
  OR NOT (OLD.mapping_status = 'active' AND NEW.mapping_status IN ('superseded', 'revoked'))
BEGIN
    SELECT RAISE(ABORT, 'crosswalk rows are immutable except for closing an active interval');
END;

CREATE TRIGGER IF NOT EXISTS crosswalk_no_delete
BEFORE DELETE ON external_identity_crosswalk
BEGIN
    SELECT RAISE(ABORT, 'crosswalk history cannot be deleted');
END;

CREATE TABLE IF NOT EXISTS identity_merge_event (
    merge_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN ('merge', 'unmerge')),
    survivor_canonical_id TEXT NOT NULL,
    retired_canonical_id TEXT NOT NULL,
    root_merge_event_id TEXT,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (survivor_canonical_id) REFERENCES canonical_identity(canonical_id),
    FOREIGN KEY (retired_canonical_id) REFERENCES canonical_identity(canonical_id),
    FOREIGN KEY (root_merge_event_id) REFERENCES identity_merge_event(merge_event_id),
    CHECK (survivor_canonical_id <> retired_canonical_id),
    CHECK (
        (event_type = 'merge' AND root_merge_event_id IS NULL)
        OR (event_type = 'unmerge' AND root_merge_event_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS merge_mapping_change (
    merge_event_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    prior_crosswalk_id TEXT NOT NULL,
    merged_crosswalk_id TEXT NOT NULL,
    PRIMARY KEY (merge_event_id, source_record_id),
    FOREIGN KEY (merge_event_id) REFERENCES identity_merge_event(merge_event_id),
    FOREIGN KEY (source_record_id) REFERENCES source_record(source_record_id),
    FOREIGN KEY (prior_crosswalk_id) REFERENCES external_identity_crosswalk(external_identity_crosswalk_id),
    FOREIGN KEY (merged_crosswalk_id) REFERENCES external_identity_crosswalk(external_identity_crosswalk_id)
);

CREATE TRIGGER IF NOT EXISTS merge_mapping_change_immutable
BEFORE UPDATE ON merge_mapping_change
BEGIN
    SELECT RAISE(ABORT, 'merge mapping history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS merge_mapping_change_no_delete
BEFORE DELETE ON merge_mapping_change
BEGIN
    SELECT RAISE(ABORT, 'merge mapping history cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS identity_merge_event_immutable
BEFORE UPDATE ON identity_merge_event
BEGIN
    SELECT RAISE(ABORT, 'merge audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS identity_merge_event_no_delete
BEFORE DELETE ON identity_merge_event
BEGIN
    SELECT RAISE(ABORT, 'merge audit events cannot be deleted');
END;

CREATE TABLE IF NOT EXISTS audit_event (
    audit_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    operation_key TEXT,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_event_immutable
BEFORE UPDATE ON audit_event
BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_event_no_delete
BEFORE DELETE ON audit_event
BEGIN
    SELECT RAISE(ABORT, 'audit events cannot be deleted');
END;

CREATE TABLE IF NOT EXISTS idempotency_operation (
    idempotency_key TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    result_type TEXT,
    result_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TRIGGER IF NOT EXISTS idempotency_operation_guard_update
BEFORE UPDATE ON idempotency_operation
WHEN NEW.idempotency_key IS NOT OLD.idempotency_key
  OR NEW.operation_type IS NOT OLD.operation_type
  OR NEW.request_hash IS NOT OLD.request_hash
  OR NEW.created_at IS NOT OLD.created_at
  OR NOT (OLD.status = 'in_progress' AND NEW.status = 'completed')
BEGIN
    SELECT RAISE(ABORT, 'idempotency history is immutable after completion');
END;

CREATE TRIGGER IF NOT EXISTS idempotency_operation_no_delete
BEFORE DELETE ON idempotency_operation
BEGIN
    SELECT RAISE(ABORT, 'idempotency history cannot be deleted');
END;
