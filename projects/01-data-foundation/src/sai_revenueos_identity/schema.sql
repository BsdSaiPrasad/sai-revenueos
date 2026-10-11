-- SQL means Structured Query Language. This schema is the local P1.2 executable
-- specification, not a deployed production identity database.
--
-- A constraint is a database rule that rejects invalid data. A trigger is logic
-- that SQLite runs automatically before or after a specified write. Keeping core
-- identity rules here protects the data even if a future caller bypasses Python.

-- Foreign keys require referenced SourceRecords, canonical identities, and history
-- rows to exist. The busy timeout lets a concurrent writer briefly wait for the
-- atomic transaction that currently owns SQLite's write lock.
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- CANONICAL IDENTITY
-- Stores the permanent RevenueOS identifier and its entity type. A retired ID is
-- preserved with a redirect to its active survivor; it is never deleted or reused.
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

-- Prevent deletion so historical Salesforce, HubSpot, and downstream references
-- can always resolve the same canonical ID.
CREATE TRIGGER IF NOT EXISTS canonical_identity_no_delete
BEFORE DELETE ON canonical_identity
BEGIN
    SELECT RAISE(ABORT, 'canonical IDs are permanent and cannot be deleted');
END;

-- Permit only the controlled active <-> retired lifecycle used by merge/unmerge.
-- The ID and entity type themselves can never be rewritten.
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

-- SOURCE RECORD
-- Stores one stable reference to one vendor object. Both original and normalized
-- forms are retained: originals preserve provenance, while normalized values form
-- the comparison key used for idempotent registration.
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
    -- The complete vendor namespace is system + tenant + object type + object ID.
    -- For example, identical Salesforce IDs in two tenants remain distinct.
    UNIQUE (
        normalized_source_system,
        normalized_source_tenant,
        normalized_source_object_type,
        normalized_source_object_id
    )
);

-- Source identity fields are permanent after registration. Only operational facts
-- such as last_observed_at may advance as later observations arrive.
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

-- SOURCE OBSERVATION
-- Records each distinct arrival of a source object without copying its entire raw
-- payload. A fingerprint and payload reference can point to later ingestion storage.
CREATE TABLE IF NOT EXISTS source_observation (
    source_observation_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    observation_key TEXT NOT NULL UNIQUE,
    observed_at TEXT NOT NULL,
    record_fingerprint TEXT,
    payload_reference TEXT,
    FOREIGN KEY (source_record_id) REFERENCES source_record(source_record_id)
);

-- Observations are evidence. Updating or deleting them would hide what the system
-- actually received during a prior Salesforce or HubSpot processing run.
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

-- RESOLUTION CASE
-- Tracks the workflow for deciding whether one SourceRecord matches a canonical
-- identity. It intentionally allows unresolved and no-match outcomes.
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

-- Reject lifecycle jumps that would bypass required evidence or human review. For
-- example, an ambiguous case must enter pending_review before becoming resolved.
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

-- CANDIDATE EVIDENCE
-- Stores a possible match, why it was proposed, its confidence, policy version,
-- and the steward's decision. A candidate is evidence, not authoritative truth.
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

-- Preserve the original proposal. The only allowed update is its first and final
-- disposition: accepted, rejected, or expired.
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

-- AUTHORITATIVE EXTERNAL-ID CROSSWALK
-- Connects one SourceRecord to an approved canonical target over a half-open time
-- interval: valid_from is included and valid_to is excluded. Only an active row
-- with no valid_to is current; superseded and revoked rows remain historical.
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

-- Prevent one source object from pointing to two current canonical identities.
-- Without this database rule, downstream teams could count the same Salesforce
-- Account as two different companies.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_mapping_per_source
ON external_identity_crosswalk(source_record_id)
WHERE mapping_status = 'active' AND valid_to IS NULL;

-- Require the declared target type to match a real, active canonical identity.
-- This blocks an Account ID from being mislabeled as a Person, and it blocks new
-- mappings to an identity that has been retired by a merge.
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

-- Historical intervals for one SourceRecord may touch at a boundary but may not
-- overlap. This keeps "what was authoritative at this time?" unambiguous.
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

-- Crosswalk corrections are append-oriented. An active row may only be closed as
-- superseded or revoked; its original target, evidence, and start time stay intact.
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

-- Deleting a bad match would erase the explanation for a later correction.
CREATE TRIGGER IF NOT EXISTS crosswalk_no_delete
BEFORE DELETE ON external_identity_crosswalk
BEGIN
    SELECT RAISE(ABORT, 'crosswalk history cannot be deleted');
END;

-- IDENTITY MERGE EVENT
-- Records every controlled merge and unmerge. A merge names the surviving and
-- retired IDs; an unmerge points back to the root merge it reverses.
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

-- MERGE MAPPING CHANGE
-- Captures each exact crosswalk row replaced during a merge. Unmerge uses this
-- lineage to restore the old target only when no later correction superseded it.
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

-- Merge lineage is evidence and must not be rewritten or deleted.
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

-- Merge/unmerge events are an immutable stewardship record.
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

-- AUDIT EVENT
-- Stores who performed a governed operation, when it happened, which subject it
-- affected, and structured details needed to explain the state change.
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

-- Audit history can be appended but never edited or deleted.
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

-- IDEMPOTENCY OPERATION
-- Binds a caller-supplied retry key to the operation and a hash of its request.
-- An exact retry returns the first result; different input cannot reuse the key.
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

-- The only permitted change completes an in-progress claim. Because the claim and
-- business write share one transaction, rollback removes both after a failure.
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

-- Retaining completed keys prevents an old request from creating a duplicate later.
CREATE TRIGGER IF NOT EXISTS idempotency_operation_no_delete
BEFORE DELETE ON idempotency_operation
BEGIN
    SELECT RAISE(ABORT, 'idempotency history cannot be deleted');
END;
