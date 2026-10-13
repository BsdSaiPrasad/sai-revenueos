# P1.8 Identity Resolution, Survivorship, and Manual Review

P1.8 turns P1.7 staged Account and Person records into explainable P1.2 candidates. Every new crosswalk still requires a human identity steward. After approval, governed fields pass through the unchanged P1.4 authority engine.

```text
P1.7 STG_CRM_COMPANIES / STG_CRM_PEOPLE
  -> deterministic Account or Person features
  -> P1.2 CandidateEvidence
  -> version-locked human review
  -> active P1.2 ExternalIdentityCrosswalk
  -> P1.4 field authority and conflict history
  -> versioned active-mapping output consumed by P1.9
```

## What Is Implemented

| Component | Responsibility |
|---|---|
| [`identity-resolution-policy.v1.json`](../contracts/identity-resolution-policy.v1.json) | Defines P1.7 inputs, Account/Person weights, thresholds, human gate, survivorship, and boundaries. |
| [`stg_crm_people.sql`](../warehouse/dbt/models/staging/shared/stg_crm_people.sql) | Aligns Salesforce Leads/Contacts and HubSpot Contacts without merging source identities. |
| [`staging.py`](../src/sai_revenueos_resolution/staging.py) | Reads latest P1.7 company and people rows through a read-only Snowflake connection. |
| [`matcher.py`](../src/sai_revenueos_resolution/matcher.py) | Blocks candidates and records positive and negative feature evidence. |
| [`service.py`](../src/sai_revenueos_resolution/service.py) | Reuses P1.2 proposals, review, decisions, activation, and P1.4 survivorship. |
| [`schema.sql`](../src/sai_revenueos_resolution/schema.sql) | Stores immutable runs, candidate results, versioned review work, and audit events. |
| [`identity-resolution-output.v1.json`](../contracts/identity-resolution-output.v1.json) | Publishes active Account/Person mappings for P1.9 consumption. |

## Matching Rules

Accounts use normalized domain, company name, and country. Persons use normalized email, name, and mapped employer evidence. Normalization affects comparison only; raw and staged values stay unchanged.

Blocking reduces comparisons to records sharing a useful normalized key. The matcher groups already-mapped P1.7 source rows by their active P1.2 canonical target. It records each feature result and versioned score, but never activates the result.

One candidate and multiple candidates both enter `pending_review`. Missing evidence also enters review without inventing a canonical identity. Merges are never automatic.

## Human Review and Failure Recovery

Each work item stores the P1.2 case version seen when review opened. New evidence creates another run and makes older pending work stale. Only `p1_identity_steward` can accept a candidate and activate its crosswalk.

Candidate decision and crosswalk activation use deterministic operation keys. If execution stops between them, retry completes the same decision without adding another candidate or mapping.

## Survivorship

P1.8 does not use a match score to choose field values. It sends latest mapped values to P1.4, where manually verified truth, authoritative sources, history, and human conflict review remain in control. Fields without an approved P1.4 policy remain evidence only.

## Run the Demonstration

```bash
python3 projects/01-data-foundation/scripts/demo_identity_resolution.py
```

The default 14-line demonstration shows staged Globex input, the before state, feature evidence, pending review, explicit approval, the active crosswalk, survivorship, and the P1.9 output boundary. Add `--verbose` for complete records and audit history.

Run the automated scenarios:

```bash
python3 -m unittest projects/01-data-foundation/tests/test_identity_resolution.py -v
```

## Verify the Real Snowflake Boundary

First build the added people view with the existing restricted dbt role:

```bash
.venv/bin/python projects/01-data-foundation/scripts/run_snowflake_dbt.py build --exclude tag:failure_demo
```

Then run the authenticated, read-only P1.7-to-P1.8 check:

```bash
.venv/bin/python projects/01-data-foundation/scripts/verify_identity_resolution_snowflake.py
```

The command reads actual P1.7 staged Globex rows. It performs identity writes only in a temporary copy of the ignored local P1.6 identity database and deletes that copy afterward. It does not write to Snowflake, Salesforce, or HubSpot.

## Boundaries

- This is a Python and SQLite reference, not a deployed matching service or user interface.
- Only Account and Person matching is implemented.
- There is no automatic crosswalk activation, merge, canonical-field invention, or external write-back.
- P1.9 now consumes the output contract; P1.8 still does not build canonical warehouse models itself.
