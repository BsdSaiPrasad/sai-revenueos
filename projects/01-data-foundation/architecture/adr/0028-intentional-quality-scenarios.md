# ADR-0028: Make Intentional Data Problems Explicit

- **Decision ID:** D028 (P1.5 Decision C)
- **Status:** Accepted and implemented in the synthetic generator
- **Scope:** P1 data-quality and identity fixtures

## The Problem

A perfectly clean dataset cannot test duplicate handling, missing values, conflicting sources, or ambiguous identity evidence. Deliberate problems become confusing, however, if users cannot distinguish them from generator bugs.

## Visual Diagram

```mermaid
flowchart LR
    R[Generated records] --> Q[Intentional quality issue]
    Q --> M[Manifest entry]
    M --> E[Expected outcome]
    E -. review only .-> I[Identity or authority decision]
```

## Simple Example

HubSpot contains two Globex company records with the same domain and different names. The manifest labels the duplicate and says the expected identity state is ambiguous. RevenueOS keeps both source records unresolved. It never turns the shared domain into an automatic merge.

## How We Implement It

| Component | Responsibility |
|---|---|
| `quality_issues` | Names every deliberate duplicate, gap, conflict, rebrand, job change, or late event. |
| `expected_identity_outcomes` | Records review expectations with `automatic_merge: false`. |
| P1.2 interfaces | Prove generated source records begin unresolved with no active mapping. |
| P1.4 expectations | Identify the existing authoritative source for conflicting governed fields. |

## Why This Design

- **Rejected alternative:** Hide test anomalies inside payloads or automatically resolve obvious-looking matches.
- **Why rejected:** Hidden anomalies look accidental, and automatic merges can create false identity truth.
- **Why this is better:** Every problem is discoverable, testable, and paired with an explicit safe outcome.
- **Tradeoff:** Manifest maintenance is part of every new scenario and can become large at high scale.
