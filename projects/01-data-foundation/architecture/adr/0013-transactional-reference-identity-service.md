# ADR-0013: Prove Identity Rules with a Transactional SQLite Reference

- **Decision ID:** D013 (P1.2 Decision E)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 operational reference behavior

## Problem and example

Application checks alone cannot prevent two workers from creating duplicates or a failure from leaving half a correction. Closing Globex's old mapping and creating its replacement must succeed or fail together.

## Options considered

- Documentation-only rules cannot prove behavior.
- In-memory objects do not prove database constraints or transactions.
- Deploying a production platform now would cross the P1.2 boundary.
- Python plus SQLite can demonstrate the rules locally with no service dependency.

## Decision and technical design

Use a standard-library Python service and SQLite schema with atomic transactions, unique constraints, state triggers, non-overlapping mapping intervals, immutable audit rows, idempotency claims, write serialization, rollback, and reconciliation. Tests exercise concurrent connections and injected partial failure.

## Tradeoffs

SQLite is not the production topology and its locking model is not a distributed-service design. A later operational service must preserve these semantics while adding authentication, deployment, observability, and reliable publication to Snowflake.

## Interview explanation

“I used SQLite as an executable specification: database constraints and transactions prove the identity invariants without pretending it is the production database.”
