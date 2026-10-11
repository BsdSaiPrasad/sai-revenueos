# ADR-0007: Keep Activity, Campaign, and ProductUser Distinct

- **Decision ID:** D007
- **Status:** Accepted
- **Scope:** P1 engagement model

## 1. The Problem

A marketing initiative, an individual interaction, and a product login describe different things. Combining them produces unclear metrics and weak provenance.

## 2. Connected Example

**Example:** Globex Health joins the “2026 Analytics Readiness” Campaign, Sarah Kim attends its webinar, and later she signs in through a ProductUser profile.

**Problem:** Combining the initiative, attendance event, and product profile into one generic record would blur their different meanings and lifecycles.

**Our Solution:** Campaign, Activity, and ProductUser stay separate while linking to the same canonical Person and Account when resolved.

## 3. Options We Considered

- Store every item as one generic engagement record. This is flexible but hides important differences.
- Put campaign and product fields directly on Activity. This creates sparse, confusing records.
- Model each concept separately and connect it to canonical context when known.

## 4. Our Decision

`Activity`, `Campaign`, and `ProductUser` are distinct entities. They link to Person, Account, Opportunity, and source context where relevant, while supporting unresolved identity.

## 5. How It Works Technically

- Campaign represents the initiative.
- Activity represents a time-stamped interaction and can reference Campaign, Person, Account, Opportunity, and SourceRecord.
- ProductUser represents a product-system profile and can reference Person, Account, and SourceRecord.
- Optional canonical links remain null until identity is resolved; `resolution_status` records that condition.

## 6. Why We Chose It

The model supports clear campaign attribution, interaction history, and product usage without pretending they share one lifecycle or identity.

## 7. Tradeoffs and Limitations

Analysis requires explicit joins, and consumers must handle unresolved records. Later matching and ingestion work must update links without dropping early-arriving interactions.

## 8. Interview Explanation

“I separated campaigns, individual activities, and product profiles because they have different meanings and lifecycles. Each can still connect to the same canonical customer context.”
