# P1 Architecture Decision Index

## What Is This File?

This is the index of Project 1's approved architecture decisions. An Architecture Decision Record (ADR) explains the problem, alternatives, decision, technical design, and tradeoffs.

All 25 decisions below are **Accepted**. D001–D008 define the canonical model, D009–D013 define P1.2 identity control, D014–D019 define the P1.3 source model, and D020–D025 define P1.4 field authority. A future change requires a new superseding ADR. A change that affects Projects 2–7 must be labeled **MASTER ARCHITECTURE DECISION NEEDED** before implementation.

## Approved Decisions

| ID | Plain-English decision | Why it matters | ADR |
|---|---|---|---|
| **D001** | One durable canonical Person represents one human across systems and employers. | Prevents duplicate people and preserves a continuous human identity. | [One Canonical Person Represents One Human](architecture/adr/0001-canonical-person.md) |
| **D002** | Parent companies and subsidiaries are separate Accounts connected by history-aware relationships. | Keeps entity-level revenue and contracts accurate while supporting rollups. | [Keep Parent and Subsidiary Accounts Separate](architecture/adr/0002-canonical-account-hierarchy.md) |
| **D003** | Preserve selected Account name, domain, and hierarchy history using selective Slowly Changing Dimension Type 2 (SCD Type 2). | Supports as-of reporting without adding history complexity everywhere. | [Preserve Important Account History Selectively](architecture/adr/0003-historical-account-attributes.md) |
| **D004** | Lead and Contact are source-system records linked to Person, not separate canonical humans. | Keeps Customer Relationship Management (CRM) lifecycle separate from human identity. | [Model Lead and Contact as Source Records](architecture/adr/0004-lead-and-contact.md) |
| **D005** | Opportunity has one primary buying Account; people participate through OpportunityPersonRole. | Makes revenue attribution clear and supports a real buying committee. | [Give Each Opportunity One Primary Account and Many People](architecture/adr/0005-opportunity-relationships.md) |
| **D006** | Customer is an Account lifecycle status; Contract and Subscription keep independent identities. | Avoids duplicate company records and preserves commercial history. | [Customer Is an Account Lifecycle Status](architecture/adr/0006-customer-lifecycle.md) |
| **D007** | Activity, Campaign, and ProductUser are different entities that share canonical context when resolved. | Prevents unlike engagement concepts from being combined. | [Keep Activity, Campaign, and ProductUser Distinct](architecture/adr/0007-interaction-model.md) |
| **D008** | An auditable, effective-dated crosswalk maps source records to canonical entities. | Keeps canonical IDs vendor-independent and makes corrections traceable. | [Use an Auditable External-ID Crosswalk](architecture/adr/0008-external-identity-crosswalk.md) |
| **D009** | Canonical IDs use a controlled entity prefix plus standards-compliant UUIDv7. | Produces durable, source-independent, time-sortable IDs without relying on new Python-only APIs. | [Generate Entity-Prefixed UUIDv7 Canonical IDs](architecture/adr/0009-prefixed-uuidv7-identifiers.md) |
| **D010** | One source object uses a database-unique four-part namespace and idempotent writes. | Prevents tenant collisions and duplicate SourceRecords during retries or concurrent processing. | [Use a Four-Part Source Identity and Idempotent Writes](architecture/adr/0010-four-part-source-identity.md) |
| **D011** | Resolution workflow, candidate evidence, and authoritative crosswalks are separate layers. | Keeps possible matches and scores from silently becoming accepted identity truth. | [Separate Resolution Cases, Candidate Evidence, and Crosswalks](architecture/adr/0011-separate-resolution-evidence-crosswalk.md) |
| **D012** | Corrections, merges, and unmerges preserve IDs, redirects, evidence, and audit history. | Makes mistakes traceable and recoverable without deleting source evidence. | [Preserve Identity and Audit History](architecture/adr/0012-audit-preserving-identity-changes.md) |
| **D013** | Python + SQLite serves as a transactional reference for identity invariants. | Proves constraints, concurrency, rollback, retry, and reconciliation before production deployment. | [Prove Identity Rules with a Transactional SQLite Reference](architecture/adr/0013-transactional-reference-identity-service.md) |
| **D014** | Preserve every available source payload field before standardization. | Keeps vendor evidence available when validation fails or later field needs emerge. | [Preserve Raw Payloads Before Standardization](architecture/adr/0014-preserve-raw-source-payloads.md) |
| **D015** | Append source versions and represent source deletion with a tombstone. | Preserves source history without deleting a durable canonical identity. | [Keep Source History and Represent Deletions as Tombstones](architecture/adr/0015-source-history-and-tombstones.md) |
| **D016** | Use one versioned source-event envelope for origin, identity, time, tracing, event type, checkpoint, and payload. | Gives Salesforce and HubSpot common operational metadata without flattening their payloads. | [Use One Standard Source-Event Envelope](architecture/adr/0016-standard-source-event-envelope.md) |
| **D017** | Standardize essential Salesforce and HubSpot objects and fields first while retaining full raw payloads. | Keeps the v1 model small and testable without losing unmodeled data. | [Standardize Essential Source Fields First](architecture/adr/0017-essential-source-fields-first.md) |
| **D018** | Advance checkpoints only after durable processing and replay with overlap plus idempotency. | Prevents gaps after failure and safely handles duplicates or late updates. | [Use Checkpoints, Overlap, Idempotency, and Safe Replay](architecture/adr/0018-checkpoint-overlap-and-safe-replay.md) |
| **D019** | Reuse the P1.2 source-identity interface and never auto-approve uncertain matches. | Preserves one identity authority and keeps ingestion separate from resolution truth. | [Reuse P1.2 Identity Control Without Automatic Approval](architecture/adr/0019-reuse-identity-interface.md) |
| **D020** | Assign source-of-truth ownership to individual canonical fields. | Prevents one system from controlling unrelated facts on an entire entity. | [Assign Source of Truth at the Field Level](architecture/adr/0020-field-level-source-of-truth.md) |
| **D021** | Preserve conflicting values and protect manually verified truth. | Prevents arrival order or automation from destroying reviewed evidence. | [Preserve Conflicts and Protect Manually Verified Values](architecture/adr/0021-preserve-conflicts-and-manual-truth.md) |
| **D022** | Give each business domain its own authoritative systems. | Keeps sales, marketing, usage, billing, payments, accounting, health, and consent ownership explicit. | [Give Each Business Domain Its Own Authoritative Systems](architecture/adr/0022-domain-specific-field-authority.md) |
| **D023** | Require explicit, auditable authorization before future write-back. | Prevents unrestricted synchronization loops and excessive automated authority. | [Authorize Write-Back Explicitly and Audit Every Decision](architecture/adr/0023-controlled-auditable-write-back.md) |
| **D024** | Assign human owners to conflicts and preserve their review history. | Makes escalation and final decisions accountable and explainable. | [Make People Accountable for Conflict Resolution](architecture/adr/0024-human-owned-conflict-resolution.md) |
| **D025** | Reserve future domain boundaries without implementing later projects. | Lets P4–P6 consume governed truth without redefining ownership or expanding P1.4 scope. | [Reserve Future Authority Boundaries Without Building Future Products](architecture/adr/0025-future-compatible-authority-boundaries.md) |

## What These Decisions Do Not Implement

The decisions define the architecture. They do not mean the following capabilities are running:

- Live Salesforce or HubSpot API ingestion and scheduled connector execution.
- Complete identity matching or artificial-intelligence scoring.
- Physical warehouse constraints and reconciliation jobs.
- Live field synchronization or write-back delivery.

The P1.2 identity, P1.3 source, and P1.4 field-authority mechanics are local references, not deployed services. P1.5 and later work require a separate approved scope.
