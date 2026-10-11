# P1 — GTM Data Foundation & Customer Identity

## What Is P1?

Project 1 creates the shared identity and data foundation for SAI RevenueOS. It defines how companies, people, sales opportunities, commercial records, and source-system records fit together.

P1 is the foundation for Projects 2–7. Those projects should consume P1's shared identities rather than creating competing definitions.

## Why Do We Need It?

Synthetic company **Globex Health** may appear as a Salesforce Account, a HubSpot Company, and a billing customer. **Sarah Kim** may appear as a Lead, Contact, product user, and support requester.

Without P1, each system looks correct alone but combined reporting produces duplicate companies and people. P1 separates the stable business identity from each operational source record.

## How Does It Work?

1. `SourceRecord` preserves one object from one source system and tenant.
2. `ExternalIdentityCrosswalk` connects that source record to a canonical entity when resolved.
3. `Account` and `Person` provide stable, source-independent identities.
4. Relationship and history entities preserve employer, hierarchy, name, domain, and buying-role changes.
5. Revenue, engagement, product, support, and governance entities use the same canonical context.

Read the repository-wide [beginner walkthrough](../../docs/START_HERE.md) for the full Globex Health example.

## What Has Been Completed?

### P1.0 — Engineering Foundation

- Repository organization and configuration safety.
- Project continuity files and documentation responsibilities.
- Standard-library architecture validation.

### P1.1 — Canonical Business Model and ERD

- A machine-readable contract containing 23 entities and 31 declared relationships.
- A detailed canonical business model.
- A Mermaid Entity Relationship Diagram (ERD).
- Eight approved Architecture Decision Records (ADRs).
- Verified contract, relationship, documentation, and secret-filename checks.

### P1.2 — Canonical ID and Crosswalk Control

- Entity-prefixed UUIDv7 IDs under P1 write authority.
- Atomic four-part source identity and immutable observations.
- Separate resolution cases, candidate evidence, and authoritative crosswalks.
- History-preserving correction, merge, unmerge, redirects, and audit events.
- SQLite constraints, transactions, safe retries, rollback, concurrency protection, and reconciliation.
- Twenty-three executed acceptance scenarios using synthetic Globex Health and Northstar Labs data.

### P1.3 — Salesforce + HubSpot Source Model

- Versioned source-event, checkpoint, Salesforce, and HubSpot contracts.
- Raw-first source events, immutable source versions, current state, and deletion tombstones.
- Essential Salesforce Account, Lead, Contact, and Opportunity mappings.
- Essential HubSpot Company, Contact, and Deal mappings.
- Checkpoint overlap, idempotent replay, late-update handling, and transactional failure recovery.
- Reuse of the P1.2 source-identity interface without automatic identity approval.
- Thirteen executed source-model scenarios and a runnable synthetic Globex demonstration.

The [project state](PROJECT_STATE.md) is the authoritative source for current status.

## Key Documents

| Document | Use it for |
|---|---|
| [Canonical Business Model](architecture/CANONICAL_BUSINESS_MODEL.md) | Learn all 23 entities, relationships, history, and ERD notation. |
| [Mermaid ERD](architecture/diagrams/canonical-model.mmd) | Inspect the version-controlled visual model. |
| [P1.2 Identity Control Guide](architecture/IDENTITY_CONTROL.md) | Learn the implemented Decisions A–E and runtime flow. |
| [P1.2 Runtime ERD](architecture/diagrams/identity-control.mmd) | Inspect the operational reference tables. |
| [P1.3 Source Model Guide](architecture/SOURCE_MODEL.md) | Run and understand raw history, tombstones, checkpoints, replay, and identity integration. |
| [P1.3 Source Contracts](contracts/) | Inspect the versioned envelope, checkpoint, Salesforce, and HubSpot definitions. |
| [Decision Index](DECISIONS.md) | See all 19 approved decisions and open their ADRs. |
| [Shared Contract](../../shared/contracts/canonical-model.v1.json) | Inspect the machine-readable technical definition. |
| [Project State](PROJECT_STATE.md) | Confirm what works, what is deferred, and what comes next. |
| [Work Log](WORK_LOG.md) | Review chronological implementation and verification evidence. |
| [Glossary](../../docs/GLOSSARY.md) | Look up RevenueOS business and technical terms. |

## How to Read the Architecture

Start with the Canonical Business Model's ERD guide. Then explore entities in this order:

1. Account, Person, SourceRecord, and ExternalIdentityCrosswalk.
2. Account and Person history relationships.
3. Opportunity and OpportunityPersonRole.
4. Quote, Contract, Order, Subscription, and Invoice.
5. Activity, Campaign, ProductUser, SupportCase, Signal, Decision, and WorkflowRun.

## How to Verify It

From the repository root, using Python 3.9 or newer:

```bash
python3 projects/01-data-foundation/scripts/validate_architecture.py
python3 -m unittest discover -s projects/01-data-foundation/tests -v
python3 projects/01-data-foundation/scripts/demo_source_model.py
```

No credentials, package installation, warehouse, or external service is required.

## What Is Not Implemented?

- Live Salesforce/HubSpot API ingestion and a complete identity-matching engine.
- Survivorship and field-level source precedence.
- A deployed production identity service or Snowflake publication pipeline.
- Physical Snowflake tables and dbt transformations.
- Reverse Extract-Transform-Load (ETL), activation, scoring, routing, or forecasting.
- Production security policies, monitoring, or stewardship interfaces.

The future folders for those capabilities are intentionally absent until they contain working deliverables.

## What Comes Next?

Review the P1.3 implementation and demonstration before approving any P1.4 scope. No P1.4 work has started.
