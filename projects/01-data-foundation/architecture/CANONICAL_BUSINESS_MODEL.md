# P1 Canonical Business Model

## 1. What Is This Model?

The canonical business model is the shared vocabulary for SAI RevenueOS. It defines what an Account, Person, Opportunity, Contract, and other important business concepts mean independently of any source system.

The model contains 23 entities. The machine-readable contract is [`canonical-model.v1.json`](../../../shared/contracts/canonical-model.v1.json), and the visual Entity Relationship Diagram (ERD) is [`canonical-model.mmd`](diagrams/canonical-model.mmd). This document explains them in plain English without changing their technical names.

All examples use synthetic companies and people. They are not real customers.

## 2. Why Do We Need a Canonical Model?

Salesforce, HubSpot, a product application, a billing platform, and a support tool can all describe the same company differently. If every source definition flows directly into reporting, Revenue Operations (RevOps) teams may count duplicate companies, lose history, or connect revenue to the wrong people.

The canonical model preserves every source record while giving shared business concepts durable identities and explicit relationships.

## 3. How to Read the ERD

An ERD is a visual map of entities and their relationships.

### Entities and attributes

Each box is an entity. The rows inside are attributes.

```text
ACCOUNT
  account_id       PK
  account_type
  lifecycle_status
```

`account_id` is the Primary Key (PK): it uniquely identifies one Account.

### Foreign keys

A Foreign Key (FK) points to another entity's primary key. For example, `Opportunity.primary_account_id` points to `Account.account_id`. This means every Opportunity has one primary buying Account.

### One-to-many relationships

One Account can have many Opportunities:

```text
Account 1 ─── 0..many Opportunities
```

An Account can exist before it has an Opportunity, so the minimum on the Opportunity side is zero.

### Many-to-many relationships

One Opportunity can involve many Persons, and one Person can join many Opportunities. `OpportunityPersonRole` resolves this many-to-many relationship and records each person's role.

```text
Person ──< OpportunityPersonRole >── Opportunity
```

Sarah Kim can be the champion while John Lee is the economic buyer. A direct Person field on Opportunity could not represent that buying committee cleanly.

### Historical relationships

Some relationships change over time. These entities contain `valid_from` and `valid_to`:

- `AccountPersonRelationship` preserves employer history.
- `AccountHierarchyRelationship` preserves parent-company history.
- `AccountNameHistory` and `AccountDomainHistory` preserve company identity evidence.
- `OpportunityPersonRole` preserves changing buying roles.
- `ExternalIdentityCrosswalk` preserves mapping corrections.

The interval is half-open: `valid_from` is included, `valid_to` is excluded, and a null `valid_to` means the row is current.

## 4. Core Modeling Rules

### Stable identity

Canonical primary keys are opaque and source-independent. They never contain a Salesforce ID, email address, domain, or another mutable business value. P1.2 implements the approved entity-prefixed UUIDv7 method in its local reference layer.

### Selective history

Slowly Changing Dimension Type 2 (SCD Type 2) history is used only where the business needs an as-of view. We do not apply history tables to every attribute automatically.

### Safe unresolved records

An Activity or ProductUser can arrive before RevenueOS knows the correct Person or Account. The source record and resolution status remain available while canonical links are null. The system must not invent a match.

### Controlled polymorphic references

`Signal`, `EnrichmentSnapshot`, and `Decision` can refer to several allowed entity types through a type-and-ID pair. `ExternalIdentityCrosswalk` uses the same pattern for supported canonical targets. The shared contract lists allowed targets; a future physical implementation must enforce them.

## 5. Customer and Organization Identity

| Entity and PK | Plain-English meaning and example | Important relationships | Why it exists |
|---|---|---|---|
| **Account** (`account_id`) | One durable organization identity. Globex Health stays the same Account if it rebrands. Customer is an Account lifecycle status, not another company entity. | Has names, domains, hierarchy edges, people, Opportunities, and commercial records. | Gives all projects one company identity without merging parents and subsidiaries. |
| **Person** (`person_id`) | One durable human identity. Sarah Kim remains the same Person across Salesforce, HubSpot, the product, and employer changes. | Has Account affiliations, Opportunity roles, Activities, product profiles, and cases. | Prevents Lead, Contact, and product profiles from becoming duplicate humans. |
| **AccountPersonRelationship** (`account_person_relationship_id`) | An effective-dated link between a Person and Account. Sarah works at Globex Health, then later Northstar Labs. | Each row belongs to one Account and one Person; both can have many rows. | Preserves employment, title, department, and other affiliation history outside Person. |
| **AccountHierarchyRelationship** (`account_hierarchy_relationship_id`) | An effective-dated parent/child link between two separate Accounts. Helio Systems can be the parent of Globex Health. | Each row has one parent Account and one child Account. Self-links and cycles are invalid. | Supports company rollups without collapsing subsidiaries into parents. |
| **AccountNameHistory** (`account_name_history_id`) | An official name, trade name, or alias during a time period. Globex Health later uses the preferred name Helio Health. | One Account has one or more name rows; only one preferred name should be active. | Keeps rebrands and aliases without changing Account identity. |
| **AccountDomainHistory** (`account_domain_history_id`) | A normalized internet domain associated with an Account during a time period. | One Account can have zero or many domains. | A domain can change or move, so it is useful identity evidence but not the Account ID. |
| **SourceRecord** (`source_record_id`) | One object in one source system and tenant. Salesforce Account `SF-1001` and HubSpot Company `HS-502` are separate SourceRecords. | Can have historical crosswalk mappings and provide provenance to other entities. | Preserves the original system identity even before a canonical match exists. Lead and Contact are source object types here. |
| **ExternalIdentityCrosswalk** (`external_identity_crosswalk_id`) | An auditable, effective-dated mapping from a SourceRecord to one supported canonical entity. | One SourceRecord can have multiple non-overlapping historical mappings but at most one active target at a time. | Connects vendor IDs to canonical IDs and allows correction without deleting prior evidence. |

### Example identity flow

```text
Salesforce Account SF-1001 ─┐
                            ├─> Account: Globex Health
HubSpot Company HS-502 ─────┘
```

The two source records remain separate. The Account is the shared identity.

## 6. Sales and Revenue

| Entity and PK | Plain-English meaning and example | Important relationships | Why it exists |
|---|---|---|---|
| **Opportunity** (`opportunity_id`) | A potential commercial transaction, such as Globex Health's analytics expansion. | Has exactly one primary Account and zero or many people, Activities, Quotes, and Contracts. | Gives the sales process a source-independent identity and clear buyer. |
| **OpportunityPersonRole** (`opportunity_person_role_id`) | A Person's role in one Opportunity. Sarah is the champion; John Lee is the economic buyer. | Each row links exactly one Opportunity and one Person and is effective-dated. | Represents buying committees and changing roles instead of adding fixed contact columns. |
| **Quote** (`quote_id`) | A versioned priced proposal for an Opportunity and Account. Version 2 can replace an earlier proposal. | Belongs to one Opportunity and Account; can lead to Orders. | Keeps proposal revisions separate from the sales Opportunity and signed agreement. |
| **Contract** (`contract_id`) | A legally binding agreement with an Account. | Belongs to an Account, may come from an Opportunity, and may govern Orders and Subscriptions. | Preserves signed terms independently of customer status and service entitlement. |
| **Order** (`order_id`) | An accepted request to fulfill purchased products or services. | Belongs to an Account and may reference a Quote and Contract; can provision Subscriptions. | Separates accepted fulfillment instructions from the proposal and agreement. |
| **Subscription** (`subscription_id`) | A time-bounded recurring product or service entitlement for an Account. | Belongs to an Account and may reference a Contract and Order; can have Invoices and SupportCases. | Tracks recurring service independently of the Contract and Account lifecycle label. |
| **Invoice** (`invoice_id`) | A billing demand issued to an Account, optionally for a Subscription. | Belongs to one Account and may belong to one Subscription. | Gives billing obligations, credits, voids, and payment state their own auditable identity. |

Customer status remains an Account attribute. Contract, Order, Subscription, and Invoice are not collapsed into Account because one company can have many of each.

## 7. Marketing and Engagement

| Entity and PK | Plain-English meaning and example | Important relationships | Why it exists |
|---|---|---|---|
| **Campaign** (`campaign_id`) | A coordinated marketing or outreach initiative, such as the synthetic “2026 Analytics Readiness” campaign. | Groups zero or many Activities. | Separates the initiative from individual interactions and supports future attribution. |
| **Activity** (`activity_id`) | A time-stamped interaction such as an email, meeting, call, or form submission. | May reference a Person, Account, Opportunity, Campaign, and SourceRecord. | Creates one interaction envelope while preserving unresolved records and source provenance. |

A Campaign is not an Activity. The campaign is the initiative; Sarah Kim's webinar attendance is one Activity connected to it.

## 8. Product, Support, and Governance

| Entity and PK | Plain-English meaning and example | Important relationships | Why it exists |
|---|---|---|---|
| **ProductUser** (`product_user_id`) | A profile inside a product tenant. Sarah's product login can resolve to her Person and Globex Health Account. | Has one SourceRecord and may reference one Person and Account. | Keeps product-system identity separate from the human's canonical Person. |
| **SupportCase** (`support_case_id`) | A customer support request or incident. | Belongs to an Account and may reference a Person and Subscription. | Connects service experience to customer context without treating a case as an Activity or Signal. |
| **Signal** (`signal_id`) | A derived observation such as engagement, intent, risk, or data-quality state. | Refers to one allowed canonical subject through `subject_entity_type` and `subject_entity_id`. | Stores explainable observations without overwriting the subject entity. |
| **EnrichmentSnapshot** (`enrichment_snapshot_id`) | An immutable point-in-time response from an enrichment provider or internal process. | Refers to one Account or Person subject. | Preserves what a provider reported, when it reported it, and under which schema. |
| **Decision** (`decision_id`) | An auditable human or machine decision, such as assigning an Account for manual review. | Refers to one allowed subject and may come from a WorkflowRun. | Records outcomes, reasons, policy versions, and actors separately from workflow code. |
| **WorkflowRun** (`workflow_run_id`) | One execution attempt of an automated or human-assisted workflow. | Can produce Decisions and reference a prior run when retried. | Provides idempotency, execution history, failure context, and recovery lineage. |

Signals, enrichment, decisions, and workflow runs describe evidence and processing around business entities. They do not replace Account, Person, or Opportunity.

## 9. Source-System and History Rules

The SourceRecord uniqueness scope is:

```text
source_system + source_tenant + source_object_type + source_object_id
```

Example: a Salesforce Lead and its converted Contact are two SourceRecords. They may both map to Sarah Kim's Person. Lead conversion changes the source representation, not the human.

Rules that a future physical model must enforce:

- `valid_from` must be earlier than `valid_to` when `valid_to` exists.
- Current preferred or primary history rows must not conflict.
- An active crosswalk target type must be allowed by the shared contract.
- A canonical target must exist before a mapping becomes active.
- Parent and child Account IDs must differ, and the active hierarchy must be acyclic.
- Every monetary value must include `currency_code`.
- Physical timestamps will use Coordinated Universal Time (UTC); business dates remain dates.

## 10. What Could Go Wrong?

- A common company name or domain could cause an incorrect merge.
- Two active crosswalk rows could map one SourceRecord to different canonical targets.
- A correction could overwrite the old row and destroy audit history.
- A parent/subsidiary hierarchy could contain a cycle.
- Personal data in Person or Activity could be exposed too broadly.
- A retry could create duplicate records if operations are not idempotent.

The architecture requires provenance, effective dates, append-oriented correction, and unresolved states. Later phases must implement database constraints, access controls, reconciliation, and failure recovery.

## 11. What Comes Next?

P1.2 defines and locally implements canonical ID generation, crosswalk lifecycle, correction, merge/unmerge, idempotency, and recovery semantics. P1.3 adds synthetic Salesforce/HubSpot source events, raw history, tombstones, and safe replay. Neither phase builds the full matching or survivorship engines.

The following remain deliberately deferred: source ingestion, physical Snowflake design, dbt transformations, customer-status derivation, field survivorship, workflow deployment, and reverse Extract-Transform-Load (ETL).
