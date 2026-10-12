"""Validate P1.5 datasets against P1.2, P1.3, and P1.4 boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Set, Tuple

from sai_revenueos_authority import AuthorityPolicy
from sai_revenueos_identity import validate_prefixed_id
from sai_revenueos_sources import SourceEvent, standardize_event

from .generator import CONTRACT_VERSION, SyntheticDataset


@dataclass(frozen=True)
class ValidationReport:
    """Machine-readable validation result for one generated dataset."""

    errors: List[str]
    checked_source_events: int
    duplicate_event_replays: int
    late_event_streams: int

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("synthetic dataset validation failed: %s" % "; ".join(self.errors))


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_dataset(dataset: SyntheticDataset) -> ValidationReport:
    """Check determinism-relevant shape, relationships, contracts, and scenarios."""
    errors: List[str] = []
    if len(dataset.companies) != dataset.config.company_count:
        errors.append("company count does not match the generator configuration")
    if len(dataset.people) != dataset.config.company_count * dataset.config.people_per_company:
        errors.append("people count does not match the configured ecosystem")
    if len(dataset.opportunities) != dataset.config.company_count:
        errors.append("every company must have one opportunity fixture")
    if len(dataset.activities) != len(dataset.people):
        errors.append("every generated person must have one activity fixture")

    account_ids = {row["account_id"] for row in dataset.companies}
    person_ids = {row["person_id"] for row in dataset.people}
    opportunity_ids = {row["opportunity_id"] for row in dataset.opportunities}
    if len(account_ids) != len(dataset.companies):
        errors.append("canonical Account fixture identifiers are not unique")
    if len(person_ids) != len(dataset.people):
        errors.append("canonical Person fixture identifiers are not unique")
    if len(opportunity_ids) != len(dataset.opportunities):
        errors.append("canonical Opportunity fixture identifiers are not unique")
    identifier_groups = (
        ("Account", account_ids),
        ("Person", person_ids),
        ("Opportunity", opportunity_ids),
        ("Activity", {row["activity_id"] for row in dataset.activities}),
        (
            "AccountPersonRelationship",
            {row["account_person_relationship_id"] for row in dataset.employment_history},
        ),
        (
            "AccountHierarchyRelationship",
            {row["account_hierarchy_relationship_id"] for row in dataset.account_relationships},
        ),
        (
            "AccountNameHistory",
            {row["account_name_history_id"] for row in dataset.account_name_history},
        ),
    )
    for entity_type, values in identifier_groups:
        for value in values:
            try:
                validate_prefixed_id(entity_type, value)
            except Exception as exc:  # Validation errors are summarized with record context.
                errors.append("invalid %s fixture ID %s: %s" % (entity_type, value, exc))

    for relationship in dataset.account_relationships:
        parent = relationship["parent_account_id"]
        child = relationship["child_account_id"]
        if parent not in account_ids or child not in account_ids:
            errors.append("account relationship references an unknown Account")
        if parent == child:
            errors.append("account relationship cannot point to itself")
    for history in dataset.account_name_history:
        if history["account_id"] not in account_ids:
            errors.append("Account name history references an unknown Account")
        if history["valid_to"] and history["valid_from"] >= history["valid_to"]:
            errors.append("Account name history uses an invalid validity interval")
    for relationship in dataset.employment_history:
        if relationship["account_id"] not in account_ids or relationship["person_id"] not in person_ids:
            errors.append("employment history references an unknown Account or Person")
        if relationship["valid_to"] and relationship["valid_from"] >= relationship["valid_to"]:
            errors.append("employment history uses an invalid validity interval")
    for person in dataset.people:
        if person["current_account_id"] not in account_ids:
            errors.append("Person references an unknown current Account")
    for opportunity in dataset.opportunities:
        if opportunity["primary_account_id"] not in account_ids:
            errors.append("Opportunity lacks a known primary Account")
    for activity in dataset.activities:
        if activity["account_id"] not in account_ids:
            errors.append("Activity references an unknown Account")
        if activity["person_id"] not in person_ids:
            errors.append("Activity references an unknown Person")
        if activity["opportunity_id"] not in opportunity_ids:
            errors.append("Activity references an unknown Opportunity")

    event_contents: Dict[str, str] = {}
    duplicate_event_replays = 0
    last_source_time: Dict[Tuple[str, str, str, str], datetime] = {}
    late_streams: Set[Tuple[str, str, str, str]] = set()
    salesforce_accounts = {
        document["source"]["object_id"] for document in dataset.salesforce_events
        if document["source"]["object_type"] == "Account"
    }
    hubspot_companies = {
        document["source"]["object_id"] for document in dataset.hubspot_events
        if document["source"]["object_type"] == "Company"
    }
    for document in dataset.source_events:
        try:
            event = SourceEvent.from_dict(document)
            standardize_event(event)
        except Exception as exc:
            errors.append("source event failed P1.3 validation: %s" % exc)
            continue
        serialized = event.envelope_sha256
        prior = event_contents.get(event.event_id)
        if prior is not None:
            if prior != serialized:
                errors.append("one event ID has conflicting content")
            else:
                duplicate_event_replays += 1
        else:
            event_contents[event.event_id] = serialized
        key = (
            event.source_system,
            event.source_tenant,
            event.source_object_type,
            event.source_object_id,
        )
        current_time = _parse_time(event.source_updated_at)
        observed_time = _parse_time(event.observed_at)
        checkpoint_time = _parse_time(event.checkpoint_high_watermark_at)
        if observed_time < current_time:
            errors.append("source event was observed before its source update time")
        if checkpoint_time < observed_time:
            errors.append("checkpoint high watermark precedes event observation")
        if key in last_source_time and current_time < last_source_time[key]:
            late_streams.add(key)
        last_source_time[key] = max(current_time, last_source_time.get(key, current_time))
        payload = event.payload
        if event.source_system == "salesforce" and event.source_object_type in {"Contact", "Opportunity"}:
            related_account = payload.get("AccountId")
            if related_account and related_account not in salesforce_accounts:
                errors.append("Salesforce source relationship references an unknown Account")
        if event.source_system == "hubspot" and event.source_object_type in {"Contact", "Deal"}:
            related_company = payload.get("properties", {}).get("associatedcompanyid")
            if related_company and related_company not in hubspot_companies:
                errors.append("HubSpot source relationship references an unknown Company")

    required_issue_types = {
        "duplicate_record",
        "duplicate_event",
        "missing_optional_field",
        "conflicting_information",
        "acquisition",
        "company_rebrand",
        "employee_job_change",
        "ambiguous_identity_match",
        "late_out_of_order_event",
    }
    present_issue_types = {item.get("issue_type") for item in dataset.quality_issues}
    missing_issue_types = required_issue_types - present_issue_types
    if missing_issue_types:
        errors.append("required intentional issue types are missing: %s" % sorted(missing_issue_types))
    for issue in dataset.quality_issues:
        if set(issue) != {"issue_id", "issue_type", "record_keys", "description", "expected_outcome"}:
            errors.append("quality issue does not use the version 1 manifest shape")
    if duplicate_event_replays < 1:
        errors.append("dataset must contain an exact duplicate event replay")
    if not late_streams:
        errors.append("dataset must contain a late or out-of-order event")

    for outcome in dataset.expected_identity_outcomes:
        if outcome.get("automatic_merge") is not False:
            errors.append("expected identity outcomes must never enable automatic merge")
        if outcome.get("expected_resolution") not in {
            "review_required", "ambiguous", "keep_separate_account"
        }:
            errors.append("expected identity outcome uses an unsupported state")

    try:
        policy = AuthorityPolicy()
        if policy.field("Account", "lifecycle_status").authoritative_sources != frozenset({"salesforce"}):
            errors.append("P1.4 Account lifecycle authority changed")
        if policy.field("Opportunity", "stage").authoritative_sources != frozenset({"salesforce"}):
            errors.append("P1.4 Opportunity stage authority changed")
    except Exception as exc:
        errors.append("P1.4 authority policy could not validate generated conflicts: %s" % exc)

    manifest = dataset.manifest()
    required_manifest_keys = {
        "contract_name", "contract_version", "synthetic", "scenario_name", "generator",
        "dataset_fingerprint_sha256", "counts", "quality_issue_counts", "quality_issues",
        "identity_policy", "expected_identity_outcomes", "authority_expectations",
        "boundaries", "files",
    }
    if set(manifest) != required_manifest_keys:
        errors.append("scenario manifest does not use the version 1 shape")
    if manifest.get("contract_version") != CONTRACT_VERSION or manifest.get("synthetic") is not True:
        errors.append("scenario manifest must identify version 1 synthetic data")

    return ValidationReport(
        errors=errors,
        checked_source_events=len(dataset.source_events),
        duplicate_event_replays=duplicate_event_replays,
        late_event_streams=len(late_streams),
    )
