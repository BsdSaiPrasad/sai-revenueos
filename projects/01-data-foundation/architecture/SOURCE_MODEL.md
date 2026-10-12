# P1.3 Salesforce + HubSpot Source Model

P1.3 is a local Python and SQLite reference built from **synthetic records**. It does not call Salesforce or HubSpot Application Programming Interfaces (APIs), run a connector, or load Snowflake.

## What It Proves

```text
synthetic source envelope
  -> commit complete raw payload
  -> validate essential vendor fields
  -> reuse P1.2 source identity and observation
  -> append immutable source version
  -> update current source state if the event is newer
  -> advance checkpoint only after the transaction succeeds
```

A failed event keeps its raw payload and does not advance the checkpoint. A late event remains in history but does not replace newer current state. A delete event creates a tombstone and never deletes a canonical identity.

## Versioned Contracts

| Contract | Scope |
|---|---|
| [`source-event-envelope.v1.json`](../contracts/source-event-envelope.v1.json) | Origin, identifiers, event type, timestamps, tracing, checkpoint metadata, and full payload. |
| [`source-checkpoint.v1.json`](../contracts/source-checkpoint.v1.json) | Last durable cursor, high watermark, and overlap replay boundary. |
| [`salesforce-source.v1.json`](../contracts/salesforce-source.v1.json) | Essential Account, Lead, Contact, and Opportunity fields. |
| [`hubspot-source.v1.json`](../contracts/hubspot-source.v1.json) | Essential Company, Contact, and Deal fields. |

Unknown standard, custom, and nested payload fields remain in raw history even when they are not in the standardized v1 subset.

## Implementation Map

| Component | Start with | Responsibility |
|---|---|---|
| Envelope and field validation | [`contracts.py`](../src/sai_revenueos_sources/contracts.py) | Builds `SourceEvent` and standardizes only contracted fields. |
| Durable processing | [`store.py`](../src/sai_revenueos_sources/store.py) | Preserves raw events, history, current state, checkpoints, replay, and failure recovery. |
| Local database rules | [`schema.sql`](../src/sai_revenueos_sources/schema.sql) | Protects immutable raw events and versions. |
| P1.2 identity boundary | [`IdentityStore.get_or_create_source_record()`](../src/sai_revenueos_identity/store.py) | Reuses four-part source identity and immutable observations. |
| Acceptance scenarios | [`test_source_model.py`](../tests/test_source_model.py) | Proves duplicate, update, delete, malformed, late, failure, and replay behavior. |
| Runnable example | [`demo_source_model.py`](../scripts/demo_source_model.py) | Shows the complete Globex Health flow in a temporary database. |

P1.3 calls P1.2 with `SOURCE_WRITER` authority only. New SourceRecords remain unresolved; P1.3 never proposes or approves a crosswalk.

## Run It

From the repository root:

```bash
python3 projects/01-data-foundation/scripts/demo_source_model.py
```

Runs the synthetic Globex demonstration as a 13-line summary and removes its temporary databases afterward.

```bash
python3 projects/01-data-foundation/scripts/demo_source_model.py --verbose
```

Shows the complete synthetic input, stored records, checkpoints, failure evidence, and replay window.

```bash
PYTHONPATH=projects/01-data-foundation/src python3 -c "import inspect; from sai_revenueos_sources import SourceStore; print(inspect.getsource(SourceStore.process_event))"
```

Prints the exact processing function used by the demonstration.

```bash
python3 -m unittest projects/01-data-foundation/tests/test_source_model.py -v
```

Runs the 13 P1.3 source-model acceptance scenarios.

```bash
python3 -m unittest discover -s projects/01-data-foundation/tests -v
```

Runs all P1.2–P1.5 executable scenarios.

## Small Exercise

Run the demonstration with a two-minute overlap:

```bash
python3 projects/01-data-foundation/scripts/demo_source_model.py --overlap-seconds 120
```

Before reading the `Next replay` line, predict its start time and explain why replaying from that time cannot create duplicate history. Add `--verbose` if you want to inspect the complete replay-window record.

## Boundaries

- Payloads in `examples/p13/` are realistic but fictional.
- No OAuth, vendor pagination, rate-limit handling, webhook receiver, or live API client exists.
- No production object storage, queue, distributed transaction, scheduler, monitoring, or privacy policy exists.
- No Snowflake table, dbt model, automatic identity matching, or live connector exists.
- P1.4 consumes P1.3 evidence through a separate governed interface; P1.3 itself does not choose canonical field truth.
