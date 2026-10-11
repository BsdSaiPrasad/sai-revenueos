# ADR-0008: Use an Auditable External-ID Crosswalk

- **Decision ID:** D008
- **Status:** Accepted
- **Scope:** P1 source-to-canonical identity

## 1. The Problem

One canonical entity can have records in several systems. Matches can also be wrong and require correction. Embedding external IDs directly in canonical entities makes both problems difficult to manage.

## 2. Connected Example

**Example:** Salesforce Account `SF-1001` and HubSpot Company `HS-502` both describe Globex Health, but a different HubSpot company is later mapped there by mistake.

**Problem:** Vendor columns on Account would not scale, and overwriting the bad match would erase evidence of what happened.

**Our Solution:** An effective-dated crosswalk maps each SourceRecord separately and corrects the mistake by closing the old mapping and appending a reviewed replacement.

## 3. Options We Considered

- Add one Salesforce ID, HubSpot ID, and other vendor columns to Account. This does not scale and assumes one record per source.
- Use a domain or external ID as the canonical Account ID. Source values can change and are not globally reliable.
- Store source records separately and use an effective-dated mapping table.

## 4. Our Decision

Use `ExternalIdentityCrosswalk` as a separate, auditable mapping from `SourceRecord` to a supported canonical entity. Support multiple source records, historical mappings, and future manual corrections.

## 5. How It Works Technically

- `source_record_id` identifies the source object.
- `canonical_entity_type` and `canonical_entity_id` identify the supported target.
- `mapping_status`, `mapping_method`, and `confidence` describe the mapping outcome, not the original source object.
- `valid_from` and `valid_to` preserve mapping intervals.
- `supersedes_crosswalk_id`, reviewer, and review time support correction lineage.
- One SourceRecord may have historical mappings but at most one active target at a time.

## 6. Why We Chose It

The crosswalk keeps canonical IDs vendor-independent, supports many source records per entity, and makes corrections explainable without rewriting history.

## 7. Tradeoffs and Limitations

The system needs mapping governance, temporal uniqueness, reconciliation, and manual review. P1.2 now implements those mechanics in a local transactional reference; production deployment and a complete matching engine remain deferred.

## 8. Interview Explanation

“I used an effective-dated crosswalk between source records and canonical entities. That supports many systems, preserves provenance, and lets us correct a bad match without deleting the old evidence.”
