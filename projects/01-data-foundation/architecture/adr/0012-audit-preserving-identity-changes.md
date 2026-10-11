# ADR-0012: Preserve Identity and Audit History Through Correction, Merge, and Unmerge

- **Decision ID:** D012 (P1.2 Decision D)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 stewardship

## Problem and example

Incorrect mappings and merges happen. If Northstar Labs is incorrectly merged into Globex Health, deleting rows cannot explain the mistake or restore stable downstream references.

## Options considered

- Delete and recreate identities, which breaks references and evidence.
- Rewrite mappings in place, which hides prior truth.
- Retire IDs with redirects and append correction/merge history.

## Decision and technical design

Corrections close a prior interval and create a superseding crosswalk. Merge retires the losing ID, creates a redirect, and records every moved mapping. Unmerge reactivates the original ID and restores mappings whose lineage is unchanged; uncertain records enter human review. Events and mapping lineage are immutable. A rebrand retains an Account ID, and acquisition never triggers automatic merge.

## Tradeoffs

History grows and consumers must understand redirects and effective dates. Unmerge can require manual review after later edits. Those costs buy explainability and recoverability.

## Interview explanation

“I never delete an identity mistake. I close history, redirect retired IDs, and retain enough lineage to reverse a bad merge safely.”
