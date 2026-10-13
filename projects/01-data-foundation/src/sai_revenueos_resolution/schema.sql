PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- One immutable evaluation of one staged source version under one policy.
-- The fingerprint makes retries safe while a new event or policy version creates
-- a new run instead of rewriting earlier evidence.
CREATE TABLE IF NOT EXISTS resolution_run (
    run_id TEXT PRIMARY KEY,
    input_fingerprint TEXT NOT NULL UNIQUE,
    source_record_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('Account', 'Person')),
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    outcome TEXT CHECK (outcome IN ('already_resolved', 'candidate', 'ambiguous', 'pending_review')),
    candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    evidence_json TEXT NOT NULL,
    error_code TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

-- Candidate scores are explainable run evidence. They do not replace P1.2
-- CandidateEvidence and cannot activate an authoritative crosswalk.
CREATE TABLE IF NOT EXISTS match_candidate_result (
    run_id TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0.0 AND score <= 1.0),
    rank INTEGER NOT NULL CHECK (rank > 0),
    reference_source_record_id TEXT NOT NULL,
    features_json TEXT NOT NULL,
    candidate_evidence_id TEXT,
    PRIMARY KEY (run_id, canonical_entity_id),
    FOREIGN KEY (run_id) REFERENCES resolution_run(run_id)
);

-- One work item can contain one or several candidates. expected_case_version
-- prevents an old browser page or delayed worker from deciding newer evidence.
CREATE TABLE IF NOT EXISTS identity_review_work_item (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    source_record_id TEXT NOT NULL,
    candidate_evidence_ids_json TEXT NOT NULL,
    expected_case_version INTEGER NOT NULL CHECK (expected_case_version > 0),
    assigned_owner_role TEXT NOT NULL,
    assigned_owner_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'stale')),
    selected_candidate_evidence_id TEXT,
    resulting_crosswalk_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decision_reason TEXT,
    FOREIGN KEY (run_id) REFERENCES resolution_run(run_id)
);

-- Append-only review and processing evidence supports troubleshooting and audit.
CREATE TABLE IF NOT EXISTS resolution_audit_event (
    audit_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS resolution_run_no_delete
BEFORE DELETE ON resolution_run
BEGIN
    SELECT RAISE(ABORT, 'resolution runs cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS match_candidate_no_delete
BEFORE DELETE ON match_candidate_result
BEGIN
    SELECT RAISE(ABORT, 'candidate results cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS resolution_audit_immutable
BEFORE UPDATE ON resolution_audit_event
BEGIN
    SELECT RAISE(ABORT, 'resolution audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS resolution_audit_no_delete
BEFORE DELETE ON resolution_audit_event
BEGIN
    SELECT RAISE(ABORT, 'resolution audit events cannot be deleted');
END;
