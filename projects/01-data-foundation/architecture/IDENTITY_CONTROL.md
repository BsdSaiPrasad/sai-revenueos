# P1.2 Identity Control — Learning Guide

P1.2 turns the approved identity rules into a local, executable reference. It uses Python and SQLite to prove behavior; it is not the future production identity database and it does not match records automatically.

## 1. Canonical ID generation

**WHAT:** P1 creates permanent identifiers from an entity prefix plus a Universally Unique Identifier version 7 (UUIDv7), such as `sai_acc_<uuidv7>`.

**WHY:** A real company needs IDs that do not belong to Salesforce, HubSpot, or another vendor. UUIDv7 also carries sortable creation-time bits without exposing a business key.

**EXAMPLE:** Globex Health receives one `sai_acc_...` Account ID. A rebrand to Helio Health changes name history, not that ID.

**HOW:** `ids.py` owns the controlled prefix registry, standards-compliant UUIDv7 layout, validation, collision check, and retry. `canonical_identity` prevents deletion and ID mutation. Only `p1_identity_writer` can create one through `IdentityStore`.

**FAILURE:** A bad prefix, malformed UUID, reused operation key, collision, or unauthorized caller is rejected. A collision is retried safely.

## 2. Source identity and idempotency

**WHAT:** One source object is identified by `(source_system, source_tenant, source_object_type, source_object_id)`. Idempotency means a retry has the same effect as the first request.

**WHY:** Salesforce Account `001ABC` in two tenants is two different records; the same record arriving twice is not two records.

**EXAMPLE:** Replaying Globex Health's Salesforce Account adds a new immutable observation but returns the existing SourceRecord. HubSpot can use its own tenant and object ID.

**HOW:** `normalization.py` preserves vendor identifier semantics. A database unique constraint covers the normalized four-part key. `BEGIN IMMEDIATE` makes the lookup-and-insert atomic, while `idempotency_operation` protects governed commands.

**FAILURE:** Empty/control-character input is rejected. Concurrent retries serialize at the database boundary. Reusing an idempotency key for different input raises a conflict.

## 3. Resolution, evidence, and authoritative mapping

**WHAT:** A `resolution_case` holds workflow state; `candidate_evidence` holds possible matches and decisions; `external_identity_crosswalk` holds only governed mappings. Only an `active` crosswalk is authoritative.

**WHY:** A possible match is not the same thing as an approved company identity. Separating them prevents a score or guess from silently becoming truth.

**EXAMPLE:** A Globex domain and name point to one Account, so a steward accepts the candidate before the mapping is activated. Two plausible Northstar Labs candidates make the case `ambiguous` and require review.

**HOW:** Database checks and triggers constrain statuses and transitions. The service exposes proposal, review, explicit decision, activation, and revocation commands. It contains no complete matching or artificial-intelligence scoring engine.

**FAILURE:** An unresolved or unapproved candidate cannot become authoritative. Invalid transitions and unauthorized decisions fail without partial writes.

## 4. Correction, merge, and unmerge

**WHAT:** Corrections close prior mapping intervals and append replacements. A merge retires one canonical ID, redirects it to a survivor, and moves active mappings. Unmerge restores the original ID and safely restores mappings when their lineage is unchanged.

**WHY:** Deleting mistakes destroys auditability. Durable redirects also stop old IDs from being reused.

**EXAMPLE:** Northstar Labs is mistakenly merged into Globex Health after an acquisition rumor. Unmerge reactivates Northstar's original Account ID. If a mapping changed after the merge, it is sent to human review instead of guessed.

**HOW:** `identity_merge_event`, `merge_mapping_change`, crosswalk history, and `audit_event` are immutable. Merge and unmerge run in one transaction under `p1_identity_steward` authority.

**FAILURE:** Cross-entity-type merges, repeated reversals, missing redirects, and unauthorized operations are rejected. An acquisition never triggers an automatic merge.

## 5. Transactions, recovery, and reconciliation

**WHAT:** A transaction makes a governed change all-or-nothing. Reconciliation reports inconsistent states that need repair or review.

**WHY:** A service failure after closing an old mapping must not leave Globex with no authoritative mapping.

**EXAMPLE:** A simulated failure during correction rolls back the closed row, audit record, and idempotency claim. The same request can then be retried safely.

**HOW:** SQLite constraints enforce uniqueness, immutability, valid transitions, one active mapping, and non-overlapping intervals. `store.py` uses atomic transactions and exposes `reconcile()` checks. `tests/test_identity_reference.py` proves concurrency, rollback, retry, and interval behavior.

**FAILURE:** Partial writes roll back. Reconciliation flags resolved cases without active mappings, active mappings to retired identities, invalid review flags, and interval overlap.

## Data flow

```text
Source payload
  -> four-part SourceRecord + immutable observation
  -> ResolutionCase
  -> CandidateEvidence
  -> explicit steward decision
  -> active ExternalIdentityCrosswalk
  -> durable canonical Account/Person/etc.
```

See the [runtime ERD](diagrams/identity-control.mmd), [ADRs](adr/), and [executable tests](../tests/test_identity_reference.py).

## Implementation map

Use this order when reviewing or explaining the implementation:

| Topic | Start with | What to notice |
|---|---|---|
| 1. Canonical ID generation | [`ids.py`](../src/sai_revenueos_identity/ids.py): `uuid7()`, `PrefixedIDGenerator.generate()` | The RFC 9562 bit layout, controlled prefixes, clock rollback guard, and collision retry. |
| 2. Source registration | [`normalization.py`](../src/sai_revenueos_identity/normalization.py): `normalize_source_identity()`; [`store.py`](../src/sai_revenueos_identity/store.py): `get_or_create_source_record()` | Original identifiers are preserved while the four-part comparison key is database-unique. |
| 3. Resolution cases | [`store.py`](../src/sai_revenueos_identity/store.py): `request_manual_review()`; [`schema.sql`](../src/sai_revenueos_identity/schema.sql): `resolution_case` | A source may remain unresolved, ambiguous, under review, resolved, or no-match. |
| 4. Candidate evidence | [`store.py`](../src/sai_revenueos_identity/store.py): `propose_candidate()` and `decide_candidate()` | Confidence and evidence support a decision but never become authoritative by themselves. |
| 5. Crosswalk mappings | [`store.py`](../src/sai_revenueos_identity/store.py): `activate_mapping()`; [`schema.sql`](../src/sai_revenueos_identity/schema.sql): `external_identity_crosswalk` | Only one approved, active, open-ended mapping is current for a SourceRecord. |
| 6. Corrections | [`store.py`](../src/sai_revenueos_identity/store.py): `correct_mapping()` | The old interval closes and a replacement row starts; history is not overwritten. |
| 7. Merge and unmerge | [`store.py`](../src/sai_revenueos_identity/store.py): `merge_identities()` and `unmerge_identities()` | Retired IDs redirect to a survivor, while exact mapping lineage enables safe reversal. |
| 8. Transactions and rollback | [`store.py`](../src/sai_revenueos_identity/store.py): `_transaction()` | `BEGIN IMMEDIATE` protects concurrent read-then-write operations; exceptions roll back business, audit, and idempotency rows together. |
| 9. Reconciliation | [`store.py`](../src/sai_revenueos_identity/store.py): `reconcile()` | Read-only checks report inconsistent states; they do not silently repair them. |
| 10. Executable proof | [`test_identity_reference.py`](../tests/test_identity_reference.py) | Synthetic Globex Health and Northstar Labs scenarios prove retry, concurrency, correction, rollback, and reversal behavior. |

In `schema.sql`, a **constraint** is a database rule that rejects invalid data. A **trigger** is Structured Query Language (SQL) logic that SQLite runs automatically when a specified write is attempted. They provide a second enforcement layer when code outside `IdentityStore` accesses the database.

## Run the verification

From the repository root, using Python 3.9 or newer:

```bash
python3 -m unittest discover -s projects/01-data-foundation/tests -v
python3 projects/01-data-foundation/scripts/validate_architecture.py
```

The first command executes the P1.2 behavior scenarios. The second checks the unchanged canonical contract, Entity Relationship Diagram (ERD), Architecture Decision Records (ADRs), P1.2 artifacts, continuity files, and secret-like filenames. Neither command requires credentials or a live Salesforce, HubSpot, Snowflake, or production service.

## Production evolution boundary

A production component can keep these contracts while replacing SQLite with a transactional operational database, an authenticated service interface, durable queues, metrics, and scheduled reconciliation. It would publish canonical IDs and crosswalk changes to Snowflake. That deployment, its Snowflake tables, connectors, and matching engine are deliberately deferred.

The shared `canonical-model.v1.json` remains version `1.0.0`: its 23 entities, 31 relationships, and approved P1.1 meanings did not change. P1.2 adds an operational reference schema and separate runtime ERD, so no canonical-contract migration is required.
