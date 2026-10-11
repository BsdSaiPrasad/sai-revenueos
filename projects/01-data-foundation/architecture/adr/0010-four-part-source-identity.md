# ADR-0010: Use a Four-Part Source Identity and Idempotent Writes

- **Decision ID:** D010 (P1.2 Decision B)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 source identity

## Problem and example

An object ID is not globally unique. Salesforce ID `001ABC` in the Globex sandbox and production tenants may refer to different objects, while replaying the production record must not create a duplicate.

## Options considered

- Object ID alone is ambiguous.
- System plus object ID still conflates tenants and object types.
- A generated SourceRecord with no natural-key constraint cannot stop duplicates.
- A four-part key captures the actual vendor namespace.

## Decision and technical design

Uniquely identify a source object by `source_system`, `source_tenant`, `source_object_type`, and `source_object_id`. Preserve originals, normalize only under documented vendor rules, enforce the normalized tuple in SQLite, and perform lookup/insert inside one write transaction. Immutable observations record reprocessing. Governed commands also use request-bound idempotency keys.

## Tradeoffs

Every connector must supply tenant and object type consistently. Normalization changes require care because the key is permanent. In return, retries and multiple tenants are safe.

## Interview explanation

“I modeled the complete vendor namespace and enforced it in the database, so concurrent replays return one SourceRecord while every observation remains auditable.”
