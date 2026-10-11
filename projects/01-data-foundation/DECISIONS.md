# P1 Architecture Decision Index

## What Is This File?

This is the index of Project 1's approved architecture decisions. An Architecture Decision Record (ADR) explains the problem, alternatives, decision, technical design, and tradeoffs.

All 13 decisions below are **Accepted**. D001–D008 remain unchanged; D009–D013 implement the five approved P1.2 decisions. A future change requires a new superseding ADR. A change that affects Projects 2–7 must be labeled **MASTER ARCHITECTURE DECISION NEEDED** before implementation.

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

## What These Decisions Do Not Implement

The decisions define the architecture. They do not mean the following capabilities are running:

- Source-system ingestion.
- Complete identity matching or artificial-intelligence scoring.
- Survivorship or field-level source precedence.
- Physical warehouse constraints and reconciliation jobs.

The P1.2 mechanics are implemented as a local reference, not a deployed service. The immediate next milestone is **P1.3 — Salesforce + HubSpot Source Model**.
