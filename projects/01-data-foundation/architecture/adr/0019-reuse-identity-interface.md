# ADR-0019: Reuse P1.2 Identity Control Without Automatic Approval

- **Decision ID:** D019 (P1.3 Decision F)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 source-to-identity boundary

## The Problem

P1.3 needs stable SourceRecords, but creating a second identity interface would weaken the four-part key, observation history, and approval controls already proven in P1.2. A connector also lacks authority to declare an uncertain company or person match as truth.

## Visual Diagram

The solid arrow registers source identity; the guarded path to a crosswalk remains a separate P1.2 process.

```mermaid
flowchart LR
    E[P1.3 source event] -->|get_or_create_source_record| S[P1.2 SourceRecord]
    S --> U[Unresolved ResolutionCase]
    U -.->|evidence and explicit approval| X[Active Crosswalk]
```

## Simple Example

Synthetic Salesforce and HubSpot records both contain the Globex name and domain. P1.3 registers each through P1.2 and leaves both cases unresolved. It does not map either record to a canonical Account. Evidence and authorized approval remain separate actions.

## How We Implement It

| Component | Responsibility |
|---|---|
| `IdentityStore.get_or_create_source_record()` | Provides the existing atomic four-part source identity interface. |
| `SOURCE_WRITER` | Limits P1.3 to source-registration authority. |
| `event_id` observation key | Connects replay-safe P1.3 processing to immutable P1.2 observations. |
| `ResolutionCase` | Starts unresolved when a SourceRecord is first registered. |
| P1.2 steward operations | Remain the only path to candidate approval and active crosswalk creation. |

## Why This Design

- **Rejected alternative:** Build connector-specific identity tables or auto-map records from name and domain similarity.
- **Why rejected:** Duplicate interfaces create conflicting identity truth, while automatic approval can merge unrelated customers.
- **Why this is better:** One governed identity boundary preserves P1.2 guarantees and keeps ingestion separate from resolution authority.
- **Tradeoff:** Source records can remain unresolved and require later evidence, policy, or human review.
