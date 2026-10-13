# Start Here: Follow One Company Through RevenueOS

This walkthrough explains Project 1 through one continuous, synthetic example. Nothing below represents a real customer or production result.

## The Scenario

**Globex Health** appears in both Salesforce and HubSpot. **Sarah Kim** and **John Lee** work there. The company is evaluating a fictional analytics product, signs a contract, and starts a subscription.

The architecture and completed milestones are verified through P1.8. The live connectors passed mocked and authenticated acceptance for marked fictional CRM records; Snowflake/dbt passed authenticated RAW loading and staging checks; and P1.8 passed matching, manual-review, survivorship, replay, and stale-review checks. Write-back execution remains later work.

## Step 1 — Preserve the Source Records

Salesforce Account `SF-1001` and HubSpot Company `HS-502` are different system records, even when they describe the same company. RevenueOS represents each one as a `SourceRecord`.

**Implemented locally:** the stable four-part source identity, database uniqueness, atomic replay handling, immutable observations, complete raw payload history, standardized source versions, tombstones, and checkpoints.

**Important boundary:** P1.6 can now call the live APIs after local authentication. Checked-in examples and CI still use synthetic or mocked data and no credentials.

## Step 2 — Give the Company a Canonical Account

RevenueOS needs one durable `Account` for Globex Health. Reports and downstream workflows can use that Account even if a source record changes.

**Already designed:** the Account entity is independent of Salesforce and HubSpot identifiers.

**Implemented locally:** P1 generates an entity prefix plus UUIDv7, for example `sai_acc_<uuidv7>`. The ID survives rebrands and source-system changes.

## Step 3 — Connect Sources Through the Crosswalk

`ExternalIdentityCrosswalk` connects both source records to the same canonical Account when the match is confirmed.

```text
Salesforce SF-1001 ─┐
                    ├─> Canonical Globex Health Account
HubSpot HS-502 ─────┘
```

The source records are preserved; they are not replaced by the canonical Account.

**Implemented locally:** unresolved cases, deterministic Account/Person candidate evidence, version-locked steward review, authoritative active mappings, effective-dated correction history, idempotency, merge/unmerge controls, rollback, and reconciliation. Every new crosswalk requires human approval.

## Step 4 — Decide Which Source Owns Each Field

Salesforce owns Globex Health's sales lifecycle, while HubSpot owns marketing fields. If HubSpot proposes a different sales lifecycle, RevenueOS keeps the Salesforce value current and opens a human-owned conflict instead of overwriting it.

**Implemented locally:** a versioned field-level authority matrix, provenance and value history, manual-verification protection, assigned review cases, escalation, decisions, and write-back authorization without external delivery.

## Step 5 — Connect a Person to the Account

Sarah Kim has one canonical `Person` identity. Her employment at Globex Health is stored separately in `AccountPersonRelationship`.

If Sarah later joins **Northstar Labs**, her Person ID remains the same. One relationship closes and another begins. This preserves her employment history without treating her as a new human.

**Already designed:** Person is durable; employment is effective-dated.

**Implemented locally:** P1.8 compares normalized email, name, and mapped-employer evidence for Salesforce and HubSpot people. Ambiguous or weak evidence stays in human review; it never creates an automatic Person mapping.

## Step 6 — Create an Opportunity

Globex Health's potential purchase is an `Opportunity`. It has exactly one primary buying Account: Globex Health.

**Already designed:** Account has zero or many Opportunities; every Opportunity has one primary Account.

**Later:** source ingestion and stage-history transformations will populate and maintain these records.

## Step 7 — Add the Buying Committee

Sarah Kim is the champion and John Lee is the economic buyer. `OpportunityPersonRole` connects each Person to the Opportunity and records their role.

This relationship table is necessary because one Opportunity can involve many Persons, and one Person can participate in many Opportunities.

**Already designed:** the many-to-many business relationship and its effective-dated roles.

**Later:** CRM ingestion and future inference rules will supply the participants and roles.

## Step 8 — Preserve the Commercial Lifecycle

The accepted proposal becomes a `Quote`, then a `Contract`, `Order`, and `Subscription`. Future `Invoice` records represent billing demands.

These are separate entities because a company can sign several contracts, place several orders, or hold several subscriptions. Globex Health remains the same Account throughout.

**Already designed:** the logical commercial entities and their relationships.

**Later:** P5 will implement quote-to-cash workflows. Project 1 only provides the shared identity foundation.

## Step 9 — Keep History Instead of Overwriting It

Suppose Globex Health rebrands to **Helio Health** and changes its primary domain. RevenueOS keeps the same Account ID while adding effective-dated rows to `AccountNameHistory` and `AccountDomainHistory`.

If an identity mapping is wrong, the prior crosswalk row remains in history and a correction supersedes it. The approved architecture does not silently erase evidence.

**Already designed:** selective Slowly Changing Dimension Type 2 (SCD Type 2) history and append-oriented corrections.

**Implemented locally:** SQLite constraints and reconciliation prove these rules. A deployed database, scheduled jobs, and stewardship user interface remain later work.

## Step 10 — Generate a Complete Practice Dataset

P1.5 expands the Globex story into deterministic datasets containing 25, 250, 2,500, or a custom number of companies. The files include connected people, Leads, Contacts, Opportunities, Deals, Activities, hierarchy, rebrands, job changes, duplicates, missing values, conflicts, and late events.

**Implemented locally:** JSON, JSON Lines (JSONL), Comma-Separated Values (CSV), a scenario manifest, automated validation, and a concise runnable demonstration.

**Important boundary:** generated matches are expected evidence only. P1.5 never automatically approves a crosswalk or merges an unknown identity.

## Step 11 — Read the Marked Test Records from the Real CRMs

P1.6 connects to Salesforce Developer Edition and HubSpot Free with locally stored, ignored credentials. It performs one full read and later incremental polls, then sends every returned record through the same P1.3 raw-history and P1.2 source-identity interfaces.

**Implemented and verified:** OAuth/token handling, pagination, updates, deletion tombstones, retries, rate limits, deterministic replay, checkpoint protection, and safe Globex seeding.

**Authenticated acceptance passed:** both marked Globex records were retrieved and stored raw-first; Salesforce and HubSpot changes were captured incrementally; unchanged versions replayed without duplicates; checkpoints advanced only after durable processing; and both source identities remained unresolved.

## Step 12 — Normalize Source History in Snowflake

P1.7 copies the same immutable source events into Snowflake RAW. dbt Core extracts consistent company, person, and opportunity fields while retaining every source ID, event, timestamp, hash, and raw payload.

**Implemented and authenticated:** the idempotent loader, seven source-specific models, shared CRM company and people views, safe type conversions, late-arrival labels, 71 declared dbt tests, lineage metadata, cost-controlled setup, and isolated failure demonstration. The current build passes 68 production data tests plus 10 model builds and preserves the existing Globex history from RAW through staging.

## Step 13 — Resolve Identity with Human Approval

P1.8 reads the latest Account and Person rows from P1.7 staging. It produces deterministic feature evidence, such as an exact Globex domain, then opens a review instead of activating the proposed crosswalk.

**Implemented and verified:** Sarah Kim acting as an authorized identity steward can approve the proposed mapping; retries are idempotent, stale work cannot overwrite newer evidence, and the active mapping can be consumed by future P1.9 models. Governed field values still pass through P1.4, so conflicting values and their provenance remain available.

## Where to Go Next

1. Use the [glossary](GLOSSARY.md) for unfamiliar terms.
2. Read the [P1 overview](../projects/01-data-foundation/README.md).
3. Explore all entities in the [canonical business model](../projects/01-data-foundation/architecture/CANONICAL_BUSINESS_MODEL.md).
4. Read the [decision index](../projects/01-data-foundation/DECISIONS.md) and its ADRs.
5. Check [project state](../projects/01-data-foundation/PROJECT_STATE.md) before assuming a feature is implemented.
6. Read the [P1.2 identity-control guide](../projects/01-data-foundation/architecture/IDENTITY_CONTROL.md) for the executable workflow.
7. Run the [P1.3 source-model guide](../projects/01-data-foundation/architecture/SOURCE_MODEL.md) for raw history, replay, failure, and tombstone behavior.
8. Run the [P1.4 field-authority guide](../projects/01-data-foundation/architecture/FIELD_AUTHORITY.md) for ownership, conflict, review, and write-back policy.
9. Run the [P1.5 synthetic-data guide](../projects/01-data-foundation/architecture/SYNTHETIC_DATA.md) to create and inspect a connected fictional ecosystem.
10. Follow the [P1.6 live-ingestion guide](../projects/01-data-foundation/architecture/LIVE_INGESTION.md) for the mocked demo and secure real-account verification.
11. Follow the [P1.7 Snowflake + dbt guide](../projects/01-data-foundation/architecture/SNOWFLAKE_DBT.md) for RAW loading, staging, data tests, and lineage.
12. Run the [P1.8 identity-resolution guide](../projects/01-data-foundation/architecture/IDENTITY_RESOLUTION.md) for matching, review, approval, survivorship, and the P1.9 output boundary.
