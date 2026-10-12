# SAI RevenueOS

[![Project status: P1.0 through P1.5 complete](https://img.shields.io/badge/status-P1.0%E2%80%93P1.5%20complete-2f855a)](projects/01-data-foundation/PROJECT_STATE.md)
[![CI](https://github.com/BsdSaiPrasad/sai-revenueos/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/BsdSaiPrasad/sai-revenueos/actions/workflows/ci.yml)

## What Is SAI RevenueOS?

SAI RevenueOS is a learning and portfolio project that models how an enterprise business can connect its Go-To-Market (GTM) systems. It creates a consistent view of companies, people, sales opportunities, contracts, subscriptions, and customer activity across disconnected tools. The platform is designed around realistic Business-to-Business Software-as-a-Service (B2B SaaS) scenarios, but every company, person, and data example is synthetic.

The repository contains the completed architecture foundation plus tested local references for P1.2 identity control, P1.3 Salesforce/HubSpot source history, P1.4 field authority, P1.5 deterministic synthetic data, and a P1.6 live-connector implementation. P1.6 passes mocked verification but remains incomplete until both authenticated test accounts pass. This is not a deployed production platform.

## What Business Problem Are We Solving?

Imagine that synthetic company **Globex Health** exists as an Account in Salesforce and as a Company in HubSpot. **Sarah Kim** appears as a Salesforce Contact, a HubSpot contact, and a product user.

Without a shared identity layer, reports may count two Globex companies and three Sarahs. Sales, marketing, billing, and support teams may disagree about who the customer is.

RevenueOS gives each real-world business concept one durable canonical identity while preserving every source-system record and its history.

## How Does RevenueOS Work?

```mermaid
flowchart LR
  A[CRM, marketing, product, billing, support] --> B[Source records]
  B --> C[Identity crosswalk]
  C --> D[Canonical Accounts and Persons]
  D --> E[Revenue and customer relationships]
  E -. future projects .-> F[Analytics, automation, and activation]
```

1. A source record identifies an object in one source system and tenant.
2. An external-ID crosswalk connects that record to a canonical identity when the match is known.
3. Canonical entities provide stable Accounts, Persons, Opportunities, and commercial records.
4. Effective-dated history preserves changes such as a new company name, domain, parent, or employer.
5. Future projects will use these shared identities for GTM workflows and analysis.

Start with the [beginner walkthrough](docs/START_HERE.md). Use the [glossary](docs/GLOSSARY.md) whenever a term is unfamiliar.

## The Seven Projects

| Project | Purpose | Status |
|---|---|---|
| **P1 — Data Foundation & Customer Identity** | Build shared identities, source mappings, and historical business relationships. | P1.0–P1.5 complete |
| **P2 — Inbound** | Connect future marketing demand, scoring, and routing processes. | Planned |
| **P3 — Outbound** | Support future prospecting and outbound engagement workflows. | Planned |
| **P4 — Revenue Intelligence** | Support future pipeline, forecasting, and revenue analysis. | Planned |
| **P5 — Quote to Cash** | Connect future quoting, contracting, ordering, billing, and payment processes. | Planned |
| **P6 — Customer 360** | Create a future view of adoption, support, health, renewal, and lifecycle. | Planned |
| **P7 — Reliability** | Add future data quality, observability, recovery, and governance controls. | Planned |

## Current Progress

**Completed**

- P1.0 — Engineering and documentation foundation.
- P1.1 — Canonical business model, shared contract, Entity Relationship Diagram (ERD), eight Architecture Decision Records (ADRs), and architecture validation.
- P1.2 — Prefixed UUIDv7 IDs, source idempotency, governed crosswalk lifecycle, reversible merge/unmerge, transactions, recovery, and reconciliation.
- P1.3 — Versioned Salesforce/HubSpot source contracts, raw history, tombstones, safe replay, checkpoints, and P1.2 integration.
- P1.4 — Field-level source of truth, conflict review, provenance history, and controlled write-back authorization.
- P1.5 — Deterministic synthetic GTM ecosystems, deliberate quality scenarios, portable files, and automated validation.
- P1.6 — Salesforce and HubSpot connector code, safe authentication helpers, polling, retries, and mocked API verification; real-account verification pending.
- Repository readability and learning-documentation improvement.

**Planned next**

- Authenticate and verify both P1.6 test accounts; do not start P1.7.

See the authoritative [progress tracker](PROGRESS.md) and [P1 project state](projects/01-data-foundation/PROJECT_STATE.md) for exact status and limitations.

## Repository Structure

```text
.
├── docs/
│   ├── START_HERE.md              # Guided learning path
│   ├── GLOSSARY.md                # RevenueOS terminology
│   └── MASTER_ARCHITECTURE.md     # Seven-project boundaries
├── shared/contracts/
│   └── canonical-model.v1.json    # Machine-readable shared model
└── projects/01-data-foundation/
    ├── README.md                  # P1 overview and navigation
    ├── PROJECT_STATE.md           # Current, authoritative status
    ├── DECISIONS.md               # Approved decision index
    ├── WORK_LOG.md                # Chronological evidence log
    ├── contracts/                 # P1.3–P1.6 versioned contracts and policy
    ├── examples/                  # Synthetic P1.3/P1.4 inputs
    ├── architecture/              # Model, ERD, and ADRs
    ├── scripts/                   # Validation and runnable demonstration
    ├── src/                       # P1.2–P1.6 Python + SQLite references
    └── tests/                     # P1.2–P1.6 executable acceptance scenarios
```

Future project folders are intentionally absent until they contain real work.

## How to Explore This Repository

1. [Start Here](docs/START_HERE.md) — follow one synthetic company through the model.
2. [P1 README](projects/01-data-foundation/README.md) — understand Project 1's scope.
3. [Canonical Business Model](projects/01-data-foundation/architecture/CANONICAL_BUSINESS_MODEL.md) — learn all 23 entities and the ERD.
4. [Decision Index](projects/01-data-foundation/DECISIONS.md) — see what was decided and open the ADRs to learn why.
5. [Shared Contract](shared/contracts/canonical-model.v1.json) — inspect the machine-readable technical definition.
6. [P1.3 Source Model](projects/01-data-foundation/architecture/SOURCE_MODEL.md) — run the synthetic source history and recovery demonstration.
7. [P1.4 Field Authority](projects/01-data-foundation/architecture/FIELD_AUTHORITY.md) — inspect field ownership, conflicts, reviews, and write-back authorization.
8. [P1.5 Synthetic Data](projects/01-data-foundation/architecture/SYNTHETIC_DATA.md) — generate reproducible connected fixtures and inspect expected data-quality outcomes.
9. [P1.6 Live Ingestion](projects/01-data-foundation/architecture/LIVE_INGESTION.md) — understand connector behavior and securely run real-account verification.
10. [Project State](projects/01-data-foundation/PROJECT_STATE.md) — confirm what is actually working and what remains unverified.
11. [Progress](PROGRESS.md) — see the milestone-based completion calculation.

## How to Verify the Current Implementation

Requirements: Python 3.9 or newer. The validator uses only the Python standard library.

```bash
python3 projects/01-data-foundation/scripts/validate_architecture.py
python3 -m unittest discover -s projects/01-data-foundation/tests -v
python3 projects/01-data-foundation/scripts/demo_source_model.py
python3 projects/01-data-foundation/scripts/demo_field_authority.py
python3 projects/01-data-foundation/scripts/demo_synthetic_data.py
python3 projects/01-data-foundation/scripts/demo_live_ingestion.py
```

These commands check the unchanged 23 entities and 31 relationships, 36 approved decisions, required reference artifacts, 90 P1.2–P1.6 scenarios, and all four Globex demonstrations. The P1.6 demo uses scripted API responses; follow its guide for authenticated checks. Add `--verbose` to a demonstration command for complete technical evidence.

## Important Limitations

- The P1.2–P1.6 runtimes are local reference implementations, not deployed services or a data platform.
- Live connector code exists, but both real-account checks remain unverified. There is no scheduler, webhook receiver, write-back delivery, production Snowflake schema, complete identity-matching engine, reverse Extract-Transform-Load (ETL), or workflow service.
- The shared JSON contract describes intended meaning and relationships; it does not prove that source data has been loaded.
- P2–P7 are planned boundaries, not implemented capabilities.

Repository: [BsdSaiPrasad/sai-revenueos](https://github.com/BsdSaiPrasad/sai-revenueos)
