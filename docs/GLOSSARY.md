# SAI RevenueOS Glossary

This glossary explains terms used in the repository. Definitions are specific to SAI RevenueOS rather than general textbook definitions.

| Term | Simple definition | RevenueOS example |
|---|---|---|
| **ADR — Architecture Decision Record** | A short document that records an important decision, alternatives, reasoning, and tradeoffs. | ADR-0001 explains why one human has one canonical Person. |
| **API — Application Programming Interface** | A defined way for software systems to exchange requests and responses. | A future connector may call a CRM API to retrieve Accounts. |
| **B2B SaaS — Business-to-Business Software as a Service** | Subscription software sold by one business to another. | Globex Health subscribes to a fictional analytics product. |
| **Canonical entity** | The shared, source-independent representation of a business concept. | One canonical Account represents Globex Health across Salesforce and HubSpot. |
| **Canonical identity** | A stable ID used for one real-world entity across systems and over time. | Sarah Kim keeps one Person ID after changing employers. |
| **Cardinality** | The allowed number of records on each side of a relationship. | One Account can have many Opportunities. |
| **Checkpoint** | The last source position known to be durably processed. | The Salesforce Account cursor advances only after its history row commits. |
| **Conflict review** | A human-owned case that preserves disagreeing values and evidence until an authorized person decides. | Sarah Kim reviews whether Globex Health's lifecycle should remain `prospect` or become `customer`. |
| **CRM — Customer Relationship Management** | Software used to manage companies, people, sales activity, and opportunities. | Salesforce is a possible CRM source. |
| **Crosswalk** | A mapping between a source-system record and a canonical entity. | Salesforce Account `SF-1001` maps to the canonical Globex Health Account. |
| **Data contract** | A versioned agreement about data meaning, structure, and allowed relationships. | `canonical-model.v1.json` defines the shared P1 logical model. |
| **Data lineage** | The path showing where data came from and how it changed. | An Activity links back to the source record that produced it. |
| **Entity** | A modeled business concept with its own identity and attributes. | Account, Person, and Subscription are entities. |
| **ERD — Entity Relationship Diagram** | A visual map of entities, attributes, and relationships. | The P1 ERD shows Account connected to Opportunity and Contract. |
| **Event** | A time-stamped fact that something happened. | An email Activity occurred at a specific time. |
| **FK — Foreign Key** | A field that refers to the primary key of another entity. | `Opportunity.primary_account_id` refers to `Account.account_id`. |
| **GTM — Go-To-Market** | The systems and processes used to attract, sell to, serve, and retain customers. | Marketing, sales, billing, product, and support are part of GTM. |
| **Idempotency** | Repeating the same operation produces the same result instead of a duplicate. | Reprocessing `SF-1001` must not create another SourceRecord. |
| **JSONL — JavaScript Object Notation Lines** | A text format containing one complete JSON record per line. | P1.5 writes one Salesforce or HubSpot source-event envelope per line. |
| **Identity resolution** | The process of deciding which source records represent the same real-world entity. | Determining whether Salesforce and HubSpot records both describe Globex Health. |
| **Many-to-many relationship** | Each side can relate to many records on the other side. A relationship table usually represents it. | Persons and Opportunities connect through OpportunityPersonRole. |
| **Overlap window** | A small period reread before a saved checkpoint to catch late source changes. | P1.3 starts a default replay five minutes before the saved high watermark. |
| **PK — Primary Key** | The field that uniquely identifies one entity record. | `person_id` uniquely identifies a Person. |
| **Provenance** | Evidence about the origin and authority of a fact or mapping. | A crosswalk records how and when a match was created. |
| **Reconciliation** | A check that compares records and finds missing, conflicting, or inconsistent states. | A future job may find two active mappings for one SourceRecord. |
| **ResolutionCase** | The workflow record that tracks whether one source identity is unresolved, a candidate, ambiguous, under review, resolved, or has no match. | Two plausible Northstar Labs Accounts make the case ambiguous. |
| **CandidateEvidence** | An append-oriented record of a possible canonical match, its evidence, confidence, policy, and review decision. | A verified Globex domain supports a proposed Account match. |
| **UUIDv7 — Universally Unique Identifier version 7** | A standards-based unique identifier whose leading bits preserve approximate creation-time order. | P1 combines UUIDv7 with `sai_acc_` for an Account ID. |
| **Reverse ETL — Reverse Extract, Transform, Load** | Sending prepared warehouse data back into operational tools. | A future process may send a canonical Account segment to a CRM. |
| **RevOps — Revenue Operations** | The people and processes that align marketing, sales, customer success, and revenue data. | RevOps needs one reliable view of an Account across tools. |
| **Rollback** | Undoing all changes in a failed transaction so partial data is not left behind. | If crosswalk creation fails, canonical creation should not remain half-finished. |
| **Raw payload** | The complete available source record before RevenueOS selects or renames fields. | The synthetic Globex Salesforce payload keeps custom fields outside the standardized subset. |
| **SCD Type 2 — Slowly Changing Dimension Type 2** | A history pattern that closes an old row and creates a new effective-dated row. | Globex Health's previous domain remains queryable after a domain change. |
| **Source of truth** | The system or governed dataset considered authoritative for a specific fact. | A contract system may be authoritative for signed contract dates. |
| **SourceRecord** | RevenueOS's stable reference to one object in one source system and tenant. | A Salesforce Lead and Contact are separate SourceRecords. |
| **Source event envelope** | Standard metadata wrapped around a vendor payload for identity, time, tracing, event type, and replay. | Salesforce and HubSpot payloads use the same P1.3 envelope. |
| **Survivorship** | Rules that choose which source value becomes the preferred canonical value. | P1.4 implements approved ownership and human review for selected fields; a complete enterprise ruleset remains later work. |
| **Synthetic data** | Fictional data created for learning or testing. | Globex Health and Sarah Kim are synthetic examples. |
| **Dataset fingerprint** | A repeatable hash that changes when generated dataset content changes. | Two P1.5 runs with the same count and seed have the same SHA-256 fingerprint. |
| **Random seed** | A starting number that makes pseudo-random generation repeatable. | Seed `42` recreates the same fictional P1.5 records. |
| **Scenario manifest** | A file that lists generated counts, deliberate problems, boundaries, and expected outcomes. | The P1.5 manifest explains why a duplicate Globex record must remain unresolved. |
| **Tombstone** | A retained marker that says a source record was deleted without erasing prior versions. | Deleting the synthetic Salesforce Globex Account appends a tombstone and leaves its canonical Account untouched. |
| **Transaction** | A group of changes that either all succeed or all fail. | Creating a canonical ID and its active mapping should be atomic. |
| **Upsert** | Insert a record if it does not exist, otherwise return or update the existing record. | Reprocessing a source identity should return its existing SourceRecord. |
| **Webhook** | A source-system message sent when an event happens. | A future CRM webhook may announce that an Account changed. |
| **Write authority** | The role or component allowed to propose, approve, or send a governed change. | P1.4 denies automatic HubSpot write-back but can record data-steward authorization. |
