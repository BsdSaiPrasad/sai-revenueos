# P1.4 Source of Truth and Write Authority

P1.4 is a local Python and SQLite reference built with **synthetic data**. It evaluates field ownership, preserves disagreements, controls human review, and records write-back permission. It does not call an external Application Programming Interface (API), send a write, or deploy a production master-data service.

## What It Proves

```text
P1.3 source event + P1.2 SourceRecord and canonical ID
  -> find the field's approved authority policy
  -> accept an authorized initial or same-source value
  -> otherwise preserve both values in a human-owned conflict
  -> append every verification and resolution to history
  -> authorize or deny future write-back without sending it
```

An unknown field is denied by default. An unauthorized system cannot replace trusted state. A manually verified value always requires human review before it changes.

## Versioned Source-of-Truth Matrix

[`field-authority-policy.v1.json`](../contracts/field-authority-policy.v1.json) is the executable policy. The implemented entries use real fields from the unchanged canonical v1 contract.

| Domain | Sources | Implemented field examples |
|---|---|---|
| Sales | Salesforce | `Account.lifecycle_status`, `Opportunity.stage`, `Opportunity.amount` |
| Marketing | HubSpot | `Campaign.status` |
| Enrichment | Clay, Apollo | `Person.display_name` |
| Usage | Product systems | `ProductUser.user_status`, `ProductUser.last_seen_at` |
| Billing | Billing system | `Subscription.status`, `Invoice.amount_due` |
| Payments | Stripe | `Invoice.amount_paid` |
| Accounting | Enterprise Resource Planning (ERP) | `Invoice.currency_code` |
| Customer health | Customer Success (CS) | `SupportCase.priority` |
| Consent | Verified consent registry | Reserved until consent entities and fields are approved; not implemented |

The matrix also names the allowed proposal roles, human review owner, manual-verification protection, and eligible write-back targets for each field.

## Decision Rules

1. The canonical entity and SourceRecord must already exist in P1.2.
2. The proposed field must exist in the canonical contract and policy matrix.
3. The source system and actor role must both be authorized.
4. A first authoritative value is accepted with provenance.
5. A changed value from the same source is accepted only when the current value is not manually verified.
6. A competing or protected value opens a conflict and leaves current truth unchanged.
7. Only the assigned review owner or a data steward can assign, escalate, approve, or reject the case.
8. Write-back requires current canonical truth, an approved target, data-steward authority, and a resolved conflict reference.
9. P1.4 records authorization only. No network delivery exists.

## Implementation Map

| Component | Start with | Responsibility |
|---|---|---|
| Policy loader | [`policy.py`](../src/sai_revenueos_authority/policy.py) | Validates the matrix against the canonical contract and provides default-deny lookup. |
| Policy engine | [`store.py`](../src/sai_revenueos_authority/store.py) | Evaluates proposals, protects trusted state, controls review, and evaluates write-back. |
| Local database rules | [`schema.sql`](../src/sai_revenueos_authority/schema.sql) | Stores current values and immutable value, review, request, and audit history. |
| P1.2 read boundary | [`IdentityStore.get_canonical_identity()`](../src/sai_revenueos_identity/store.py) | Confirms the target identity exists and is active. |
| P1.2 source boundary | [`IdentityStore.get_source_record()`](../src/sai_revenueos_identity/store.py) | Confirms provenance uses the existing four-part SourceRecord. |
| P1.3 evidence adapter | `FieldChange.from_source_event()` | Carries event ID, payload hash, trace ID, and SourceRecord into policy evaluation. |
| Acceptance scenarios | [`test_field_authority.py`](../tests/test_field_authority.py) | Proves ownership, conflicts, manual protection, review, audit, replay, and denied writes. |
| Runnable example | [`demo_field_authority.py`](../scripts/demo_field_authority.py) | Shows the complete synthetic Globex Health flow. |

## Run It

From the repository root:

```bash
python3 projects/01-data-foundation/scripts/demo_field_authority.py
```

Runs the synthetic Globex demonstration as a 14-line summary and removes its temporary databases afterward.

```bash
python3 projects/01-data-foundation/scripts/demo_field_authority.py --verbose
```

Shows the complete synthetic input, policy evaluations, conflicts, review history, and audit evidence.

```bash
PYTHONPATH=projects/01-data-foundation/src python3 -c "import inspect; from sai_revenueos_authority import AuthorityStore; print(inspect.getsource(AuthorityStore.apply_change))"
```

Prints the exact field-policy evaluation function used by the demonstration.

```bash
python3 -m unittest projects/01-data-foundation/tests/test_field_authority.py -v
```

Runs the P1.4 acceptance scenarios.

```bash
python3 -m unittest discover -s projects/01-data-foundation/tests -v
```

Runs every P1.2–P1.4 executable scenario.

## Small Exercise

Run the demo while keeping the manually verified Salesforce value:

```bash
python3 projects/01-data-foundation/scripts/demo_field_authority.py --salesforce-decision keep_current
```

Before reading the `Review decision` and `After` lines, predict the final `lifecycle_status`. Add `--verbose` to inspect the last `field_value_history.action` and full review history.

## Future Extension Points

- P4 Revenue Intelligence may read governed Opportunity fields; it does not own them automatically.
- P5 Quote to Cash may consume governed Contract, Subscription, Invoice, payment, and accounting fields. P1.4 does not build those workflows.
- P6 Customer 360 may consume product usage, support, health, and verified consent. New health-score or consent fields require explicit canonical modeling and policy approval first.
- A future delivery service may execute authorized write-back requests. It must preserve idempotency, rate-limit handling, vendor permissions, and delivery audit independently.

No **MASTER ARCHITECTURE DECISION NEEDED** change was required for P1.4. The 23 canonical entities, 31 relationships, and earlier accepted decisions remain unchanged.

## Boundaries

- All example companies, people, events, approvals, and outputs are synthetic.
- No live Salesforce, HubSpot, Clay, Apollo, Stripe, ERP, billing, product, Customer Success, or consent integration exists.
- SQLite is an executable specification, not a deployed production database.
- No P1.5 or P4–P6 workflow was implemented.
