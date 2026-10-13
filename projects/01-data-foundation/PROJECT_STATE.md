# P1 Project State

**As of:** 2026-10-13

**Current phase:** P1.8 Identity Resolution, Survivorship, and Manual Review complete; P1.9 not started

**Completed phases:** P1.0 Engineering Foundation; P1.1 Canonical Business Model and Entity Relationship Diagram (ERD); P1.2 Canonical ID and Crosswalk Control; P1.3 Salesforce + HubSpot Source Model; P1.4 Source of Truth and Write Authority; P1.5 Synthetic GTM Data Generation; P1.6 Live Salesforce and HubSpot Ingestion; P1.7 Snowflake + dbt Core Staging and Normalization; P1.8 Identity Resolution, Survivorship, and Manual Review

## Current implementation status

P1 retains the unchanged canonical v1.0.0 architecture: 23 entities, 31 declared relationships, and its canonical ERD. Decisions D001–D040 remain unchanged. P1.8 adds accepted Decisions D041–D044, deterministic Account/Person matching from P1.7 staging, versioned manual review, P1.2 crosswalk activation, P1.4 survivorship, and an approved-mapping boundary for future P1.9 models.

All checked-in examples and automated test records are synthetic. Authenticated acceptance used only explicitly marked fictional records in Salesforce Developer Edition and HubSpot Free; credentials and local raw evidence remain ignored. No external write-back, automatic identity merge, or downstream workflow runs.

### What is working

- Every capability previously verified through P1.4, including identity control, raw source history, checkpoint replay, field authority, human conflict review, and authorization-only write-back.
- Connected company ecosystems with Globex Health, its Diagnostics subsidiary, acquired-but-separate Northstar Labs, people, employment, Opportunities, and Activities.
- Salesforce Account, Lead, Contact, and Opportunity plus HubSpot Company, Contact, and Deal fixtures using the unchanged P1.3 contracts.
- Deterministic generation for 25, 250, and 2,500 company presets plus custom sizes from 3 through 100,000 and configurable integer seeds.
- Deterministic P1.2-prefixed UUIDv7 fixture identifiers and a SHA-256 dataset fingerprint.
- Intentional duplicates, missing optional values, source conflicts, acquisition, rebrand, job change, ambiguous identity evidence, and late/out-of-order events.
- Expected-outcome entries that keep unknown identities unresolved and set `automatic_merge` to false.
- Effective-dated Account-name and employment history plus append-oriented late source events.
- JSON, JSON Lines (JSONL), Comma-Separated Values (CSV), and versioned scenario-manifest output.
- A 13-line Globex demonstration by default with `--verbose` for complete generated records and P1.2–P1.4 evidence.
- GitHub Actions coverage for Python 3.9 and 3.14, all tests, architecture validation, all five credential-free demonstrations, and a generated 25-company smoke dataset.
- Reusable Salesforce OAuth 2.0 and HubSpot scoped-token connectors with credential-free request traces.
- Salesforce full QueryAll pagination, complete active-record reads, Get Updated/Get Deleted polling, and OAuth refresh.
- HubSpot `2026-09` CRM Objects pagination, last-modified search, and archived-record deletion polling.
- Bounded exponential retries, `Retry-After` handling, timeouts, per-stream error isolation, deterministic event replay, and checkpoint protection.
- Explicit, marker-protected Globex seeding and updates that refuse unmarked CRM-record collisions.
- Ignored mode-600 local credential storage plus a browser-based Salesforce PKCE helper and hidden HubSpot token entry.
- A 14-line credential-free P1.6 demonstration with complete `--verbose` request, raw-storage, replay, failure, checkpoint, and recovery evidence.
- Stable Salesforce event identity that preserves `LastViewedDate` and `LastReferencedDate` in raw evidence without treating their read-side changes as new business versions.
- Complete authenticated acceptance for the marked Salesforce Account and HubSpot Company: initial retrieval, raw storage, real field updates, incremental capture, unchanged-version replay, durable checkpoints, and unresolved source identities.
- An atomic and idempotent loader that copies immutable P1.3 source-event envelopes from local SQLite into Snowflake RAW without changing the source history.
- Ten dbt Core staging models covering the shared event envelope, seven approved Salesforce/HubSpot object types, and cross-source company and people views.
- Safe timestamp, boolean, number, and date conversions that retain invalid input in the raw `VARIANT` payload instead of failing or silently rewriting evidence.
- Explicit latest-version and late-arrival metadata derived from source and arrival times while preserving every historical event.
- Seventy-one declared dbt data tests for keys, required fields, accepted values, relationships, payload identity, typed values, and source-history integrity.
- A least-privilege Snowflake bootstrap with an extra-small warehouse, 60-second auto-suspend, five-minute statement timeout, separate loader/dbt roles, and a one-credit monthly resource monitor.
- Separate service users with 30-day role-restricted PATs, a current-address network policy, and ignored mode-600 local credential storage.
- Credential-free static validation, dbt parsing, a concise real-data demonstration, and an isolated intentionally failing data-quality demonstration.
- Deterministic Account matching from domain, normalized name, and country evidence plus Person matching from email, name, and mapped-employer evidence.
- Immutable resolution runs and candidate results, mandatory identity-steward review, version-locked decisions, unauthorized-actor denial, and stale-review protection.
- Safe replay and recoverable approval operations that reuse P1.2 `ResolutionCase`, `CandidateEvidence`, and active crosswalk behavior without automatic merges.
- Authority-first survivorship through the existing P1.4 engine, preserving previous values, losing values, provenance, conflicts, and review history.
- A versioned output contract that publishes only active approved Account/Person mappings for future P1.9 consumption.

### Verification status

On 2026-10-13, all 117 scenarios passed locally: 23 P1.2 identity scenarios, 13 P1.3 source-model scenarios, 15 P1.4 field-authority scenarios, 11 P1.5 generator scenarios, 20 mocked P1.6 connector scenarios, 10 demonstration-output scenarios, 12 P1.7 warehouse scenarios, and 13 P1.8 resolution scenarios.

Architecture validation passed with 23 canonical entities, 31 relationships, 44 accepted decisions, P1.2–P1.8 artifacts, continuity files, generated-data exclusion, and secret-filename checks. Python compilation, JSON parsing, local Markdown links, all five credential-free demonstrations, and the dbt project validator passed locally. The project contains 10 models, 71 declared data tests, 1 isolated failure-demo seed, and 1 RAW source.

The P1.6 Salesforce idempotency repair passed the complete Python 3.9 and 3.14 GitHub Actions matrix on 2026-10-12: [Actions run 38320413720](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38320413720). The run executed all 90 tests, architecture validation, four demonstrations, and a generated 25-company smoke dataset without vendor credentials.

Authenticated acceptance also passed on 2026-10-12. Salesforce preserved the marked Account's raw versions, captured its phone update, replayed repeated initial and overlap polls without row growth, and kept its checkpoint stable on unchanged data. HubSpot preserved three marked Company versions, changed the name from `[SAI TEST] Globex Health` to `[SAI TEST] Globex Health - Incremental Update`, processed that incremental event once, and advanced the Company checkpoint to `2026-10-12T23:14:40.388000Z`. Both source identities remain unresolved with no active canonical crosswalk.

The final P1.6 acceptance status commit passed the complete Python 3.9 and 3.14 GitHub Actions matrix: [Actions run 38321426966](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38321426966).

Authenticated P1.7 acceptance passed on 2026-10-12. The loader inserted 39 immutable Salesforce/HubSpot source events into Snowflake RAW, then inserted 0 on immediate replay while recognizing all 39 existing event IDs. dbt built 9 views and passed 63 production data tests with no warnings or errors; documentation and lineage catalog generation succeeded. The real Globex demonstration preserved 3 HubSpot history rows from the original name through `[SAI TEST] Globex Health - Incremental Update`. The isolated missing-name fixture failed as expected and its table was removed. [GitHub Actions run 38340822278](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38340822278) passed the Python 3.9 and 3.14 checks plus the credential-free dbt parse job.

Authenticated P1.8 acceptance passed on 2026-10-13. The existing restricted dbt role built 10 views and passed 68 production data tests (`PASS=78`, `WARN=0`, `ERROR=0`). The read-only Snowflake verifier read 16 latest Account rows, matched the real staged HubSpot Globex record to the staged Salesforce-backed canonical candidate with score `0.70`, required explicit steward approval, activated the crosswalk only in a temporary copy of the local identity database, and exposed 2 approved mappings through the P1.9 boundary. Snowflake, Salesforce, HubSpot, and the original local identity database were not modified by this verification.

### Verified preset counts with seed 42

| Companies | People | Opportunities | Activities | Source events |
|---:|---:|---:|---:|---:|
| 25 | 50 | 25 | 50 | 205 |
| 250 | 500 | 250 | 500 | 2,005 |
| 2,500 | 5,000 | 2,500 | 5,000 | 20,005 |

## Intentionally deferred

- Webhook receivers, periodic scheduling, production reconciliation orchestration, and managed secret rotation.
- Automatic candidate approval, automatic merge, unrestricted survivorship, or production-scale fuzzy/entity matching.
- Production object storage, message queues, distributed execution, observability, privacy controls, and retention enforcement.
- Production scheduling, cloud object storage, and reverse Extract-Transform-Load (ETL).
- Live write-back delivery, connector-specific permissions, and vendor delivery retry handling.
- Subscription, renewal, billing, revenue-intelligence, customer-health, or other P4–P6 workflows.
- P1.9 and all P2–P7 implementation.

## Blockers and architecture flags

No **MASTER ARCHITECTURE DECISION NEEDED** item was introduced. P1.8 reuses the existing canonical model, P1.2 identity controls, P1.4 authority rules, and P1.7 staging views. It does not change canonical entities, relationships, approved earlier decisions, or write-back behavior.

The complete P1.8 checklist passed without changing the approved architecture. P1 progress is 9 of 16 milestones (56.25%), and overall RevenueOS progress is approximately 8.04%.

## Next immediate step

Review the completed P1.8 evidence and define P1.9 scope separately. Do not start P1.9 without approval.

## Relevant paths

- `projects/01-data-foundation/src/sai_revenueos_synthetic/`
- `projects/01-data-foundation/contracts/synthetic-dataset-manifest.v1.json`
- `projects/01-data-foundation/tests/test_synthetic_data.py`
- `projects/01-data-foundation/tests/test_demo_output.py`
- `projects/01-data-foundation/scripts/generate_synthetic_gtm_data.py`
- `projects/01-data-foundation/scripts/demo_synthetic_data.py`
- `projects/01-data-foundation/architecture/SYNTHETIC_DATA.md`
- `projects/01-data-foundation/architecture/adr/0026-connected-synthetic-business-ecosystem.md`
- `projects/01-data-foundation/architecture/adr/0027-deterministic-configurable-generation.md`
- `projects/01-data-foundation/architecture/adr/0028-intentional-quality-scenarios.md`
- `projects/01-data-foundation/architecture/adr/0029-historical-synthetic-timelines.md`
- `projects/01-data-foundation/architecture/adr/0030-portable-validated-synthetic-outputs.md`
- `projects/01-data-foundation/src/sai_revenueos_connectors/`
- `projects/01-data-foundation/contracts/live-ingestion-policy.v1.json`
- `projects/01-data-foundation/tests/test_live_connectors.py`
- `projects/01-data-foundation/scripts/configure_live_auth.py`
- `projects/01-data-foundation/scripts/run_live_ingestion.py`
- `projects/01-data-foundation/scripts/demo_live_ingestion.py`
- `projects/01-data-foundation/architecture/LIVE_INGESTION.md`
- `projects/01-data-foundation/architecture/adr/0031-use-controlled-live-crm-accounts.md`
- `projects/01-data-foundation/architecture/adr/0032-use-scoped-vendor-authentication.md`
- `projects/01-data-foundation/architecture/adr/0033-poll-full-then-incremental.md`
- `projects/01-data-foundation/architecture/adr/0034-store-live-data-raw-first-locally.md`
- `projects/01-data-foundation/architecture/adr/0035-bound-retries-and-protect-checkpoints.md`
- `projects/01-data-foundation/architecture/adr/0036-test-connectors-with-mocks-and-live-accounts.md`
- `projects/01-data-foundation/src/sai_revenueos_warehouse/`
- `projects/01-data-foundation/contracts/warehouse-normalization-policy.v1.json`
- `projects/01-data-foundation/warehouse/snowflake/bootstrap.sql`
- `projects/01-data-foundation/warehouse/snowflake/pat_auth_setup.sql`
- `projects/01-data-foundation/warehouse/dbt/`
- `projects/01-data-foundation/tests/test_warehouse_staging.py`
- `projects/01-data-foundation/scripts/load_source_events_to_snowflake.py`
- `projects/01-data-foundation/scripts/configure_snowflake_auth.py`
- `projects/01-data-foundation/scripts/run_snowflake_dbt.py`
- `projects/01-data-foundation/scripts/demo_snowflake_dbt.py`
- `projects/01-data-foundation/scripts/demo_dbt_failure.py`
- `projects/01-data-foundation/architecture/SNOWFLAKE_DBT.md`
- `projects/01-data-foundation/architecture/adr/0037-use-snowflake-and-dbt-core.md`
- `projects/01-data-foundation/architecture/adr/0038-standardize-sources-with-provenance.md`
- `projects/01-data-foundation/architecture/adr/0039-handle-types-history-and-late-data-safely.md`
- `projects/01-data-foundation/architecture/adr/0040-test-document-and-demonstrate-dbt-lineage.md`
- `projects/01-data-foundation/src/sai_revenueos_resolution/`
- `projects/01-data-foundation/contracts/identity-resolution-policy.v1.json`
- `projects/01-data-foundation/contracts/identity-resolution-output.v1.json`
- `projects/01-data-foundation/tests/test_identity_resolution.py`
- `projects/01-data-foundation/scripts/demo_identity_resolution.py`
- `projects/01-data-foundation/scripts/verify_identity_resolution_snowflake.py`
- `projects/01-data-foundation/warehouse/dbt/models/staging/shared/stg_crm_people.sql`
- `projects/01-data-foundation/architecture/IDENTITY_RESOLUTION.md`
- `projects/01-data-foundation/architecture/adr/0041-deterministic-entity-specific-matching.md`
- `projects/01-data-foundation/architecture/adr/0042-human-approval-for-new-crosswalks.md`
- `projects/01-data-foundation/architecture/adr/0043-authority-first-survivorship.md`
- `projects/01-data-foundation/architecture/adr/0044-versioned-resolution-review.md`
- `shared/contracts/canonical-model.v1.json` (unchanged v1.0.0)
- `PROGRESS.md`
