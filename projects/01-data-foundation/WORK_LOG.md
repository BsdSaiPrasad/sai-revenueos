# P1 Engineering Work Log

## 2026-10-08 — P1.0 Engineering Foundation and P1.1 Canonical Model

### Implemented

- Adapted the existing `GTM_codex` GitHub repository; did not initialize or overwrite a repository.
- Added root project orientation, master architecture boundary, safe `.gitignore`, and non-secret `.env.example`.
- Added P1 README, authoritative state, decision index, work log, and eight ADRs for D001–D008.
- Added a shared logical contract with 23 entities, explicit relationships, supported polymorphic targets, and architecture invariants.
- Added a canonical model narrative and complete Mermaid ERD.
- Added an offline Python validator for model, relationship, history, documentation, decision, ERD, and secret-filename checks.

### Important technical choices

- Used JSON for the machine-readable shared contract so validation requires no external packages.
- Kept source references distinct from canonical entities and allowed unresolved identity state.
- Used explicit effective-dated tables only for attributes and mappings that require as-of history.
- Documented polymorphic references as constrained logical contracts and deferred their physical enforcement pattern.
- Avoided empty P2–P7 or future P1 implementation directories.

### Files created or modified

- Root: `.gitignore`, `.env.example`, `README.md`, `docs/MASTER_ARCHITECTURE.md`.
- Shared: `shared/contracts/README.md`, `shared/contracts/canonical-model.v1.json`.
- P1: `README.md`, `PROJECT_STATE.md`, `DECISIONS.md`, `WORK_LOG.md`.
- P1 architecture: canonical model, Mermaid ERD, and ADR-0001 through ADR-0008.
- P1 tooling: `scripts/validate_architecture.py`.

### Verification evidence

Verification was executed after all artifacts were written and is repeated after continuity metadata updates. Observed results:

- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 8 decisions, ERD coverage, continuity files, and secret-filename checks.
- `python3 -m py_compile projects/01-data-foundation/scripts/validate_architecture.py` — **passed** with no output.
- `python3 -m json.tool shared/contracts/canonical-model.v1.json` — **passed** with exit code 0.
- Custom relative Markdown-link check across repository documentation — **passed**.
- Required-path and forbidden P2–P7 scaffold check — **passed**.
- `npx --yes @mermaid-js/mermaid-cli@11.12.0 ...` — **passed** for SVG and PNG output; rendered PNG was visually inspected. NPM emitted a transitive Puppeteer deprecation warning, but rendering completed with exit code 0.
- `git status --short --ignored` — confirmed local `.env`, `.DS_Store`, and Python bytecode are ignored; no secret file is selected for commit.

### Failures and fixes

No architecture failure occurred. A global `mmdc` binary was unavailable, so the ERD render check used an ephemeral pinned Mermaid CLI through `npx`; no package manifest or generated render was added to the repository.

### Outstanding issues

- This is a logical architecture only; no physical schema or pipeline has been executed.
- Mermaid source receives offline structural validation. Visual rendering depends on an external Mermaid-compatible renderer and is not claimed until executed.
- P1.2 must finalize canonical ID and crosswalk operational rules.

### Git commit

Implementation commit: `33e35c9` (`feat: establish P1 canonical data architecture`). Authored and committed under the repository user's configured Git identity. This log entry is added by a follow-up documentation-only continuity commit to avoid a self-referential hash.

## 2026-10-10 — Repository Cleanup and Documentation Improvement

### Implemented

- Renamed the existing GitHub repository from `BsdSaiPrasad/GTM_codex` to `BsdSaiPrasad/sai-revenueos` without creating a new repository or changing history.
- Updated the repository description and local `origin` URL.
- Reworked the main README as a beginner-friendly landing page with the seven-project map, current progress, repository structure, and reading order.
- Added one central glossary and one continuous beginner walkthrough using synthetic Globex Health, Sarah Kim, John Lee, and related examples.
- Rewrote all eight ADRs with the same approved decisions and a consistent problem → example → options → decision → technical design → reasoning → tradeoffs structure.
- Reorganized the canonical model explanation into five logical learning sections and added an ERD reading guide while preserving all 23 entity names and technical identifiers.
- Simplified the P1 README, master architecture, and decision index while keeping each document focused on one responsibility.
- Updated repository-wide documentation guidelines in `AGENTS.md`.

### Architecture boundaries

- `shared/contracts/canonical-model.v1.json` was not modified.
- `architecture/diagrams/canonical-model.mmd` was not modified.
- D001–D008 retain their original accepted meaning.
- No P1.2 ID, crosswalk lifecycle, matching, or implementation decision was added.
- No P2–P7 functionality or scaffolding was created.

### Verification evidence

Observed results after the complete documentation edit:

- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 8 decisions, ERD coverage, continuity files, and secret-filename checks.
- `python3 -m json.tool shared/contracts/canonical-model.v1.json` and Python compilation of the validator — **passed**.
- Contract/model consistency script — **passed**: all 23 contract entities appear in the teaching guide, all 31 relationships remain declared, all 8 ADRs remain Accepted with the required sections, and all relative Markdown links resolve.
- Protected-file comparison — **passed**: shared contract, technical ERD, and validator are byte-for-byte unchanged from the prior commit.
- Mermaid CLI 11.12.0 — **passed**: canonical ERD, root overview, and master-architecture diagrams compiled to SVG; the two new overview diagrams also compiled to PNG and were visually inspected.
- Repository-reference and boundary checks — **passed**: no active old GitHub URL, no P1.2/later implementation directory, and no unrelated staged path.
- GitHub and Git remote checks — **passed**: `BsdSaiPrasad/sai-revenueos`, expected description, default branch `main`, new `origin`, and reachable remote `main`.
- Secret checks — **passed**: no tracked `.env`/`.DS_Store`, private-key marker, GitHub token pattern, AWS access-key pattern, or password assignment in staged files.

### Git commit

Documentation milestone commit: `77b1614` (`docs: improve repository learning experience`). Authored and committed under the repository user's configured Git identity. This hash is recorded by a follow-up continuity commit to avoid self-reference.

## 2026-10-10 — P1.2 Canonical ID and External-ID Crosswalk Strategy

### Implemented

- Added a standards-compliant UUIDv7 generator, controlled entity prefixes, validation, collision detection, and retry.
- Added a SQLite schema for permanent canonical identities, database-unique four-part source keys, immutable observations, resolution cases, candidate evidence, effective-dated crosswalks, merge lineage, audit events, and idempotency operations.
- Added a transactional Python interface for source upsert, evidence proposal, manual review, explicit decisions, mapping activation/revocation/correction, merge/unmerge, and reconciliation.
- Added write-authority checks for identity creation, source ingestion, resolution proposals, and steward-only decisions.
- Added five accepted ADRs (D009–D013), a P1.2 learning guide, and a separate runtime ERD. The canonical v1.0.0 contract and its technical ERD remain unchanged.
- Added the repository's authoritative milestone progress tracker.

### Verification evidence

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 23/23 scenarios. This includes all 14 required behaviors, malformed input, unauthorized transitions, permanent-ID protection, rebrand/acquisition boundaries, uncertain unmerge review, revocation, and reconciliation.
- Concurrent upsert used two worker-owned SQLite connections and produced one SourceRecord plus two observations.
- Injected failure after closing a mapping rolled back mapping, audit, and idempotency state; retry then succeeded.
- Direct invalid-transition and overlapping-interval writes were rejected by SQLite enforcement.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed** after extension for 13 decisions and required P1.2 artifacts; canonical counts remained 23 entities and 31 relationships.
- Python compilation, JSON parsing, relative documentation links, canonical protected-file comparison, Mermaid rendering, and secret scans were run in final verification before commit.

### Architecture boundaries

- No Salesforce/HubSpot connector, complete matching engine, survivorship algorithm, production database, Snowflake deployment, dbt pipeline, reverse ETL, or P2–P7 workflow was added.
- SQLite is a local executable specification only. A future operational service can preserve these transaction and contract semantics and publish governed identity changes to Snowflake.
- No **MASTER ARCHITECTURE DECISION NEEDED** item was introduced.

### Git commit

Implementation commit: `69e9c4e` (`feat: implement P1.2 identity control`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>`. This hash is recorded by a follow-up documentation-only continuity commit to avoid self-reference.

## 2026-10-10 — P1.0–P1.2 Code Documentation and Readability

### Improved

- Added plain-English module, class, function, and method docstrings across the P1.2 ID generation, source normalization, transactional store, architecture validator, and all 23 acceptance scenarios.
- Added targeted inline comments for UUIDv7 bit placement, source-key normalization, atomic source upsert, idempotency, rollback, candidate state, crosswalk activation, corrections, retired-ID redirects, merge lineage, safe unmerge, and reconciliation.
- Documented every important SQLite table and explained the business failure prevented by its key constraints, indexes, and triggers.
- Expanded the identity-control learning guide with a ten-topic implementation map, direct source references, beginner definitions, and exact verification commands.

### Boundaries and verification

- Documentation-only change: no executable statement, assertion, SQL definition, public name, contract, ERD relationship, architecture decision, or dependency changed.
- Existing P1.2 tests, architecture validation, Python compilation, JSON validation, link checks, semantic Python comparison, SQL definition comparison, protected-file comparison, and secret scan were executed before commit.
- P1 remains 18.75% complete and overall RevenueOS remains approximately 2.7%. P1.3 has not started.

### Git commit

Pending the documentation commit. The final hash is reported in the task handoff rather than written here to avoid a self-referential commit.

## 2026-10-11 — ADR Example Clarity Improvement

### Improved

- Reworked the existing example in every Architecture Decision Record (ADR), D001–D013, into one consistent three-part format: business example, failure risk, and RevenueOS solution.
- Connected the examples through Globex Health, Northstar Labs, Sarah Kim, Salesforce, and HubSpot while keeping each example to three short sentences.
- Expanded technical acronyms where needed and preserved the concise alternatives, decision, and tradeoff explanations.

### Verification and boundaries

- Confirmed 13/13 ADRs contain exactly one `Example`, `Problem`, and `Our Solution` section.
- Confirmed D001–D013 retain their existing decision IDs, approval statuses, scopes, technical meanings, and tradeoffs.
- Architecture validation, 23 P1.2 tests, Python compilation, JSON parsing, relative Markdown links, documentation-only diff review, and secret checks passed.
- No executable code, schema, test, contract, diagram, progress percentage, P1.3 work, or new architecture decision was introduced.

### Git commit

Pending the documentation commit. The final hash is reported in the task handoff rather than written here to avoid a self-referential commit.

## 2026-10-11 — ADR Visual Redesign

### Improved

- Redesigned ADR-0001 through ADR-0013 around one compact problem statement, one rendered diagram, one short business example, one implementation table, and one design rationale.
- Removed audience-specific explanation sections and wording while preserving each accepted decision, scope, alternative, recovery behavior, and tradeoff.
- Clearly separated logical relationships from executable workflows and distinguished the local P1.2 reference layer from deferred production capabilities.

### Verification and boundaries

- Confirmed 13/13 ADRs contain the approved five-section structure and exactly one Mermaid diagram; Mermaid CLI 11.12.0 rendered all 13 diagrams successfully.
- Architecture validation passed with 23 entities, 31 relationships, and 13 accepted decisions; all 23 P1.2 tests passed.
- All 64 local links across 26 tracked Markdown files resolved, and the Git whitespace check passed.
- Changes are documentation-only. No code, schema, contract, canonical diagram, approved decision, progress percentage, or P1.3 work changed.

### Git commit

Pending the documentation commit. The final hash is reported in the task handoff rather than written here to avoid a self-referential commit.

## 2026-10-11 — P1.3 Salesforce + HubSpot Source Model

### Implemented

- Added version 1 source-event, checkpoint, Salesforce, and HubSpot contracts plus realistic synthetic Globex Health payloads.
- Added a standard-library Python + SQLite source reference that commits full raw JSON first, validates an essential field subset, appends immutable versions, maintains current source state, and records deletion tombstones.
- Added durable checkpoint advancement, a configurable overlap replay window, exact-event idempotency, conflicting replay detection, late-update handling, and injected failure recovery.
- Reused P1.2 `get_or_create_source_record()` with the source event ID as its observation key. P1.3 has source-writer authority only and never approves an identity match.
- Added accepted Decisions D014–D019, a concise source-model guide, and a runnable temporary-database demonstration.

### Verification evidence

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 36/36 scenarios: 23 P1.2 and 13 P1.3.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 19 decisions, P1.2/P1.3 artifacts, continuity files, and secret-filename checks.
- `python3 projects/01-data-foundation/scripts/demo_source_model.py` — **passed** with actual before/after, duplicate replay, injected failure, safe retry, HubSpot processing, tombstone, and overlap output.
- Python compilation and all nine JSON files passed; 84 local links across 33 Markdown files resolved.
- Mermaid CLI 11.12.0 rendered all 19 ADR diagrams plus the repository and master-architecture diagrams.
- The canonical v1.0.0 contract and canonical ERD remain unchanged.

### Boundaries and progress

- No live vendor API client, OAuth flow, webhook, scheduler, Snowflake pipeline, dbt model, production service, complete matcher, automatic approval, survivorship logic, or P1.4 work was added.
- All examples are synthetic. No credentials, real customers, or vendor data are included.
- P1 is now 25% complete (4 of 16 milestones); overall RevenueOS completion is approximately 3.6%.

### Git commit

Pending the implementation commit. The final hash is reported in the task handoff rather than written here to avoid a self-referential commit.

## 2026-10-11 — GitHub Actions Continuous Integration

### Implemented

- Added a least-privilege GitHub Actions workflow for pushes to `main`, pull requests targeting `main`, and manual runs.
- Added Python 3.9 and 3.14 jobs that independently run all 36 tests, architecture validation, Python syntax checks, all nine JSON contracts/examples, and the synthetic Globex demonstration.
- Added a README status badge only after the first GitHub-hosted run completed successfully.

### Verification and boundaries

- Local verification passed: 36/36 tests, 23 entities, 31 relationships, 19 decisions, nine JSON files, Python compilation, and the synthetic demonstration.
- GitHub Actions run [38188026670](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38188026670) passed for both supported Python versions.
- The workflow uses only GitHub-hosted runners and repository contents. It has `contents: read` permission and uses no credentials, paid service, or live Salesforce/HubSpot connection.
- No business logic, schema, contract, architecture decision, P1.2/P1.3 behavior, or progress percentage changed. P1.4 has not started.

### Git commit

CI workflow commit: `12182ed` (`ci: add continuous integration workflow`). Authored and committed under the repository user's configured Git identity with no co-author attribution.

## 2026-10-12 — P1.4 Source of Truth and Write Authority

### Implemented

- Added a version 1 field-authority policy covering sales, marketing, enrichment, usage, billing, payments, accounting, customer health, and consent boundaries.
- Added a standard-library Python + SQLite reference for default-deny field evaluation, current trusted values, provenance, replay-safe changes, and append-only value history.
- Added conflict cases with preserved current/proposed values, evidence, owner roles and people, assignment, escalation, approval, rejection, and immutable review/audit events.
- Added authorization-only write-back evaluation that requires the current canonical value, an approved target, data-steward authority, and a resolved conflict. It performs no network delivery.
- Reused P1.2 canonical identities and SourceRecords plus P1.3 source-event evidence through public interfaces.
- Added accepted Decisions D020–D025, a field-authority guide, 15 acceptance scenarios, and a runnable synthetic Globex Health demonstration.

### Verification evidence

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 51/51 scenarios: 23 P1.2, 13 P1.3, and 15 P1.4.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 25 decisions, P1.2–P1.4 artifacts, continuity files, and secret-filename checks.
- `python3 projects/01-data-foundation/scripts/demo_field_authority.py` — **passed** with actual synthetic input, P1.2/P1.3 integration, replay, conflicts, assignment, approvals, rejected writes, and before/after history.
- Python compilation and the independent `--salesforce-decision keep_current` exercise path passed.
- GitHub Actions run [38207646780](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38207646780) passed the complete workflow on Python 3.9 and 3.14, including all 51 tests and both demonstrations.

### Boundaries and progress

- The canonical v1.0.0 contract, its 23 entities and 31 relationships, and Decisions D001–D019 remain unchanged.
- No live API, write-back delivery, connector, warehouse, dbt model, downstream P4–P6 workflow, consent entity, health-score model, or P1.5 work was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required. Consent and downstream domains are documented as future extension points only.
- P1 is now 31.25% complete (5 of 16 milestones); overall RevenueOS completion is approximately 4.5%.

### Git commit

Implementation commit: `400274d` (`feat: implement P1.4 field authority`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

## 2026-10-12 — Concise P1.3 and P1.4 Demonstrations

### Improved

- Changed both synthetic Globex demonstrations to show beginner-friendly 13–14 line summaries by default.
- Added `--verbose` to retain the complete P1.3 event, replay, failure, checkpoint, and tombstone evidence and the complete P1.4 policy, conflict, review, history, and audit evidence.
- Added four command-line output scenarios that enforce the summary limit and verify the detailed paths, including the existing overlap and alternate review-decision options.

### Verification and boundaries

- Local verification passed all 55 tests, architecture validation, Python compilation, JSON parsing, both default summaries, and both verbose demonstrations.
- Processing sequences, scenarios, business logic, database schemas, contracts, the 23 entities, 31 relationships, and 25 accepted decisions remain unchanged.
- P1 stays at 31.25%, overall RevenueOS stays at approximately 4.5%, and P1.5 has not started.

## 2026-10-12 — P1.5 Synthetic GTM Data Generation

### Implemented

- Added a deterministic standard-library generator for connected fictional companies, hierarchy and acquisition relationships, people, employment history, Salesforce Leads and Contacts, HubSpot Contacts, Opportunities, Deals, and canonical Activity fixtures.
- Added 25, 250, and 2,500 company presets plus custom company counts and integer seeds. Identical parameters produce identical records, files, and SHA-256 fingerprints.
- Added deliberate duplicate records and event replays, missing optional values, source conflicts, a rebrand, an employee job change, ambiguous identity evidence, and late/out-of-order history.
- Added expected outcomes that keep unknown identities unresolved, preserve acquired Accounts separately, and never enable automatic identity merging.
- Added deterministic JSON, JSONL, CSV, and versioned scenario-manifest output while ignoring generated bulk data in Git.
- Reused P1.2 identifier and identity interfaces, every existing P1.3 Salesforce/HubSpot contract, and the P1.4 field-authority policy.
- Added accepted Decisions D026–D030, a concise synthetic-data guide, 11 generator scenarios, and a 13-line Globex demonstration with complete `--verbose` evidence.

### Verification evidence

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 68/68 scenarios.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 30 decisions, P1.2–P1.5 artifacts, continuity files, generated-data exclusion, and secret-filename checks.
- Python compilation and all 12 checked-in JSON files passed.
- All 112 local Markdown links resolved, and Mermaid CLI 11.12.0 rendered the five new ADR diagrams plus the P1.5 guide diagram.
- The 25-company seed-42 dataset produced 50 people, 25 Opportunities, 50 Activities, 104 Salesforce events, and 101 HubSpot events.
- The 250- and 2,500-company scale scenarios generated and validated successfully; the largest contained 20,005 source events.
- All three concise demonstrations and the P1.5 verbose path passed. The P1.5 default output contains 13 lines.

### Boundaries and progress

- The canonical v1.0.0 contract, 23 entities, 31 relationships, Decisions D001–D025, P1.2–P1.4 behavior, and all database schemas remain unchanged.
- No live API, automatic identity approval, external write, warehouse pipeline, distributed generator, P5 workflow, or P1.6 work was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required.
- P1 is now 37.5% complete (6 of 16 milestones); overall RevenueOS completion is approximately 5.4%.

### Git commit

Implementation commit: `14474eb` (`feat: implement P1.5 synthetic data generation`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

GitHub Actions run [38213609446](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38213609446) passed the complete workflow on Python 3.9 and 3.14, including all 68 tests, architecture validation, three demonstrations, and 25-company file generation.

## 2026-10-12 — P1.6 Live Salesforce and HubSpot Ingestion

### Implemented

- Added standard-library Salesforce and HubSpot connectors that translate current vendor API responses into the unchanged P1.3 event envelope and P1.2 source-identity interface.
- Added Salesforce OAuth 2.0 External Client App browser authorization with PKCE, refresh-token handling, QueryAll pagination, complete active-record reads, and Get Updated/Get Deleted polling.
- Added HubSpot scoped Service Key or existing private-app token support with the `2026-09` CRM Objects API, pagination, last-modified search, and archived-object deletion polling.
- Added bounded exponential retries, timeouts, `Retry-After` handling, redacted diagnostics, deterministic source-version events, five-minute overlap, per-stream isolation, and checkpoint protection.
- Added explicit, marker-protected Globex test seeding and updates that stop on an unmarked Salesforce Website or HubSpot domain collision.
- Added a versioned ingestion policy, accepted Decisions D031–D036, a live-ingestion guide, 17 mocked connector scenarios, and a 14-line demonstration with complete `--verbose` evidence.

### Verification evidence

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 87/87 scenarios.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 36 decisions, P1.2–P1.6 artifacts, continuity files, generated-data exclusion, and secret-filename checks.
- Python compilation and all 13 checked-in JSON files passed.
- The P1.6 default demonstration passed in 14 lines; verbose mode showed credential-free requests, raw input, stored history, duplicate replay, API failure, unchanged checkpoint, and successful recovery.
- Both local credential files were absent. Salesforce real API status is **unverified**; HubSpot real API status is **unverified**. No live success is claimed.

### Boundaries and progress

- The canonical v1.0.0 contract, 23 entities, 31 relationships, Decisions D001–D030, P1.2 identity behavior, and P1.4 authority behavior remain unchanged.
- P1.3 source contracts gained optional vendor deletion-time paths so real Salesforce `DeletedDate` and HubSpot `archivedAt` timestamps remain raw and validate as tombstones.
- No credential, live identity approval, CRM write-back, webhook receiver, scheduler, Snowflake pipeline, downstream workflow, or P1.7 work was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required.
- P1.6 remains incomplete until both authenticated test accounts pass. P1 stays at 37.5%, and overall RevenueOS stays at approximately 5.4%.

### Git commit and CI

Implementation commit: `3c6a9df` (`feat: implement P1.6 live CRM ingestion`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

GitHub Actions run [38276397965](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38276397965) passed the complete workflow on Python 3.9 and 3.14, including all 87 tests, architecture validation, four demonstrations, and 25-company file generation. This CI evidence is credential-free and does not replace the two pending authenticated account checks.

## 2026-10-12 — P1.6 Salesforce Incremental Idempotency Repair

### Finding and fix

- Confirmed from the live SQLite history that Salesforce kept `LastModifiedDate` and `SystemModstamp` unchanged while each read advanced `LastViewedDate` and `LastReferencedDate`.
- Before the fix, two authenticated incremental polls each reported `fetched=1, processed=1, replayed=0`; total source events grew from 36 to 38 and the Globex version count grew from 7 to 9 with no business change.
- Changed P1.6 event identity to exclude only Salesforce's `attributes`, `LastViewedDate`, and `LastReferencedDate`. The complete first API response remains raw, and every business field still participates in deterministic identity.
- Added compatibility lookup for already-stored pre-fix envelopes. Historical duplicates remain immutable; the repair neither deletes nor rewrites them.

### Verification evidence

- Two authenticated incremental polls each reported `fetched=1, processed=0, replayed=1`; source events stayed at 38, Globex versions stayed at 9, and the checkpoint stayed at `2026-10-12T22:57:31.000000Z`.
- Two authenticated initial polls each fetched 14 Accounts and replayed all 14; source events stayed at 38, Salesforce events stayed at 35, and source-history rows stayed at 38.
- Added regression coverage for changing view timestamps, overlap-window replay, legitimate stable-field changes, and compatibility with pre-fix history.
- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 90/90 scenarios; architecture validation, Python compilation, 13 JSON files, Markdown links, and the concise/verbose P1.6 demonstrations also passed.
- P1.2–P1.6 contracts, canonical entities, relationships, approved decisions, and completion percentages remain unchanged. P1.7 was not started.

### Git commit and CI

Repair commit: `6c485e5` (`fix: stabilize Salesforce incremental replay`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

GitHub Actions run [38320413720](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38320413720) passed the complete workflow on Python 3.9 and 3.14, including all 90 tests, architecture validation, four demonstrations, and 25-company file generation.

## 2026-10-12 — P1.6 Final Acceptance

### Authenticated evidence

- Salesforce initial and incremental checks passed against the explicitly marked fictional Account. Raw versions preserved the real phone change to `202-555-0186`; repeated initial and overlap polls replayed existing versions without adding rows, and the checkpoint stayed stable when Salesforce reported no business change.
- HubSpot preserved three raw versions of marked Company `351778399989`. The final `PATCH` returned HTTP 200, incremental ingestion reported `fetched=1, processed=1, failures=0`, and the stored name changed from `[SAI TEST] Globex Health` to `[SAI TEST] Globex Health - Incremental Update`.
- Before the HubSpot field update, two authenticated no-change polls each reported `processed=0, replayed=1`; HubSpot event and version counts stayed at three across those polls. After the real change, the durable Company checkpoint advanced to `2026-10-12T23:14:40.388000Z` and referenced the new stored event.
- The marked Salesforce and HubSpot source identities remain `unresolved` with no active canonical crosswalk. Ingestion did not approve or merge either record.

### Complete acceptance checklist

- **Raw history:** passed for both platforms; original vendor payloads and immutable source versions remain stored locally.
- **Incremental updates:** passed with a Salesforce phone change and HubSpot Company-name change.
- **Duplicate prevention:** passed for repeated Salesforce initial/incremental polls and repeated HubSpot incremental polls.
- **Checkpoints:** passed; unchanged replays did not advance data watermarks, and the HubSpot checkpoint advanced only after the new version was durably processed.
- **Unresolved identities:** passed; no automatic mapping or merge occurred.
- **Failure recovery:** passed through mocked API and durable-processing failure scenarios, including unchanged checkpoints and successful retry.
- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 90/90 scenarios.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 36 accepted decisions, ERD coverage, continuity files, and P1.2–P1.6 artifacts.
- Python compilation and all 13 checked-in JSON files passed. No credential or generated live evidence entered Git.

### Status and progress

- P1.6 is complete. P1 is now 43.75% complete (7 of 16 milestones), and overall RevenueOS completion is 6.25%.
- P1.2–P1.6 contracts, the 23 canonical entities, 31 relationships, and 36 approved decisions remain unchanged in meaning.
- P1.7 was not started. No **MASTER ARCHITECTURE DECISION NEEDED** change was required.

### Git commit and CI

Acceptance commit: `8e1c4f8` (`docs: complete P1.6 acceptance`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

GitHub Actions run [38321426966](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38321426966) passed the complete workflow on Python 3.9 and 3.14, including all 90 tests, architecture validation, four demonstrations, and 25-company file generation.

## 2026-10-12 — P1.7 Snowflake + dbt Core (Complete)

### Implemented

- Added an atomic, idempotent loader from the existing P1.6 SQLite source-event history to a Snowflake RAW table. Exact replays are no-ops; conflicting reuse of an event ID rolls back the transaction.
- Added a dbt Core project with 9 staging models for the shared event envelope and all 7 approved Salesforce/HubSpot object types, plus 66 quality tests and lineage metadata.
- Preserved raw payloads, source identity, source and arrival timestamps, event hashes, historical versions, and explicit latest/late-arrival markers.
- Added a cost-controlled Snowflake bootstrap with separate least-privilege loader and dbt roles, an extra-small warehouse, 60-second auto-suspend, five-minute statement timeout, and a one-credit monthly resource monitor.
- Added a concise real Globex demonstration, an isolated intentionally failing data-quality demonstration, a versioned normalization policy, and accepted Decisions D037–D040.
- Extended credential-free CI with static dbt validation and `dbt parse`; no live credentials or Snowflake connection are used in GitHub Actions.

### Local verification

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 102/102 scenarios.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 40 accepted decisions, and P1.2–P1.7 artifacts.
- `python3 projects/01-data-foundation/scripts/validate_dbt_project.py` — **passed**.
- dbt Core 1.12.5 with dbt-snowflake 1.12.2 parsed the project without connecting to Snowflake: 9 models, 66 tests, 1 failure-demo seed, and 1 source.
- Python compilation, JSON parsing, Markdown links, and diff whitespace checks passed.

### Authenticated acceptance and boundaries

- Created the authorized Snowflake database, RAW and STAGING schemas, immutable event table, two least-privilege roles, X-Small warehouse, 60-second auto-suspend, five-minute statement timeout, and one-credit monthly resource monitor.
- Created separate loader and dbt service users with current-address network enforcement and role-restricted 30-day PATs. Secrets remain only in an ignored mode-600 local file and were not printed in project output.
- `dbt debug` — **passed** with the restricted dbt service role.
- First RAW load — **passed**: selected 39, inserted 39, row count 0 → 39.
- Immediate RAW replay — **passed**: selected 39, inserted 0, replayed 39, row count remained 39.
- Authenticated `dbt build --exclude tag:failure_demo` — **passed**: 9 views and 63 production data tests; `PASS=72`, `WARN=0`, `ERROR=0`.
- `dbt docs generate` — **passed** and wrote the lineage catalog.
- Real Globex demonstration — **passed**: 3 HubSpot RAW history rows; latest staged name matched `[SAI TEST] Globex Health - Incremental Update`.
- Isolated bad-data demonstration — **passed**: the required-name test returned dbt exit code 1 as expected, then cleanup removed the temporary table.
- The canonical v1.0.0 contract, 23 entities, 31 relationships, P1.2–P1.6 behavior, and Decisions D001–D036 remain unchanged.
- No reverse ETL, live write-back, scheduler, Snowflake ingestion service, downstream workflow, or P1.8 work was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required.
- P1.7 is complete. P1 is 50% complete (8 of 16 milestones), and overall RevenueOS completion is approximately 7.14%.

Implementation commit: `e3580ee` (`feat: complete P1.7 Snowflake and dbt staging`). Authored and committed as `BsdSaiPrasad <bsdsaiprasad1@gmail.com>` with no co-author attribution.

[GitHub Actions run 38340822278](https://github.com/BsdSaiPrasad/sai-revenueos/actions/runs/38340822278) passed the Python 3.9 and 3.14 required checks and the credential-free dbt Core Snowflake parse job.

## 2026-10-13 — P1.8 Identity Resolution, Survivorship, and Manual Review (Complete)

### Implemented

- Added deterministic, versioned Account and Person matching over the real P1.7 `STG_CRM_COMPANIES` and new `STG_CRM_PEOPLE` views.
- Added immutable resolution runs, explainable feature evidence, manual review work, audit events, version-locked decisions, and recoverable approval operations.
- Reused P1.2 cases, candidate evidence, active crosswalks, idempotency, and transactions; every new authoritative mapping requires an authorized identity steward.
- Reused P1.4 field authority for survivorship so manually verified values, conflicts, provenance, previous values, and resolution history remain protected.
- Added a versioned active-mapping output contract for future P1.9 use without implementing P1.9.
- Added Decisions D041–D044, a 14-line Globex demonstration, an authenticated read-only Snowflake verifier, and 13 focused resolution scenarios.

### Verification

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 117/117 scenarios.
- `python3 projects/01-data-foundation/scripts/validate_architecture.py` — **passed**: 23 entities, 31 relationships, 44 accepted decisions, and P1.2–P1.8 artifacts.
- `python3 projects/01-data-foundation/scripts/validate_dbt_project.py` — **passed**: 10 models and 71 declared tests.
- Python compilation, JSON parsing, local Markdown links, the five credential-free demonstrations, and diff whitespace checks passed.
- Authenticated dbt build — **passed**: 10 views and 68 production data tests; `PASS=78`, `WARN=0`, `ERROR=0`.
- Authenticated P1.7-to-P1.8 verification — **passed**: 16 latest Account rows read, real staged Globex candidate score `0.70`, explicit steward approval, active crosswalk in a temporary database copy, and 2 approved mappings available through the P1.9 boundary.

### Boundaries and status

- The canonical v1.0.0 contract, 23 entities, 31 relationships, source history, prior decisions, and write-back controls remain unchanged.
- No automatic merge, automatic crosswalk approval, production user interface, live write-back, or P1.9 model was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required.
- P1.8 is complete. P1 is 56.25% complete (9 of 16 milestones), and overall RevenueOS completion is approximately 8.04%.

## 2026-10-13 — P1.9 Canonical Business Models (Complete)

### Implemented

- Added Decisions D045–D047 and a versioned P1.9 contract without changing the 23 canonical entities or 31 relationships.
- Added atomic, content-addressed publication of complete P1.8 Account/Person mapping snapshots into the existing Snowflake `STAGING` schema.
- Added 10 dbt models for active mappings, canonical Accounts/People, complete mapped history, conflict evidence, unresolved identities, Person/Account relationship inputs, and Opportunity inputs.
- Reused P1.4 Salesforce lifecycle authority and deliberately left unowned Account names/domains and CRM Person fields as evidence.
- Kept Opportunities and relationship inputs explicit without inventing unsupported canonical IDs.
- Added 8 Python scenarios, dbt generic/singular tests, and a 14-line authenticated Globex demonstration with exact read-only SQL in verbose mode.

### Verification

- `python3 -m unittest discover -s projects/01-data-foundation/tests -v` — **passed**, 125/125 scenarios.
- Architecture validation — **passed**: 23 entities, 31 relationships, 47 decisions, and P1.2–P1.9 artifacts.
- Credential-free dbt parse and static validation — **passed**: 20 models, 130 declared data tests, and 3 sources.
- First real identity publication — **inserted** 1 complete snapshot containing 2 Globex mappings; exact replay inserted none.
- Authenticated Snowflake/dbt build — **passed**: 20 views and 127 production data tests; `PASS=147`, `WARN=0`, `ERROR=0`.
- `dbt docs generate` — **passed** and regenerated documentation and lineage metadata for all P1.9 models.
- Real Globex queries — **passed**: 2 source IDs resolved to 1 stable canonical Account, 12 historical events remained queryable, and unrelated records remained unresolved.
- No current authoritative Salesforce lifecycle value existed, so P1.9 correctly left the field unpromoted rather than using HubSpot or arrival order.

### Boundaries and status

- The acceptance mapping lives in an ignored isolated P1.9 identity store; the original P1.6 database and both CRM accounts were unchanged.
- No automatic merge, new field owner, fabricated Opportunity/relationship ID, write-back, P1.10 capability, or downstream workflow was added.
- No **MASTER ARCHITECTURE DECISION NEEDED** change was required.
- P1.9 is complete. P1 is 62.5% complete (10 of 16 milestones), and overall RevenueOS completion is approximately 8.93%.
