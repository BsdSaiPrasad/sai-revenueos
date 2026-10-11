# ADR-0011: Separate Resolution Cases, Candidate Evidence, and Crosswalks

- **Decision ID:** D011 (P1.2 Decision C)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 identity resolution lifecycle

## Problem and example

A possible match must not become business truth automatically. If a Northstar Labs source record has two plausible Accounts, RevenueOS needs to show ambiguity and require a decision.

## Options considered

- Put scores directly on the crosswalk, which mixes guesses with approved truth.
- Overwrite one status row, which loses evidence and reviewer history.
- Separate workflow state, evidence, and authoritative mappings.

## Decision and technical design

`ResolutionCase` tracks `unresolved`, `candidate`, `ambiguous`, `pending_review`, `resolved`, or `no_match`. `CandidateEvidence` records possible targets, evidence, confidence, policy, and a review disposition. Only an approved `active` `ExternalIdentityCrosswalk` is authoritative; earlier rows become `superseded` or `revoked`.

## Tradeoffs

More tables and explicit transitions create operational work, but they prevent a heuristic from silently changing identity. Complete matching and artificial-intelligence scoring remain deferred.

## Interview explanation

“I separated what we are investigating, why we think it matches, and what the business has approved. Only the approved active crosswalk is truth.”
