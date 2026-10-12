"""Build deterministic fictional Salesforce, HubSpot, and canonical fixtures.

The generator creates connected business records, not production data. It uses
P1.2 UUIDv7 helpers for stable fixture identifiers and emits P1.3-compatible
source-event envelopes. Expected conflicts cite P1.4 field authority without
automatically resolving or merging any identity.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sai_revenueos_identity import PREFIX_REGISTRY, uuid7


CONTRACT_VERSION = "1.0.0"
DEFAULT_SEED = 42
BASE_TIME = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
MAX_COMPANIES = 100_000

_ADJECTIVES = (
    "Apex", "Bright", "Cedar", "Evergreen", "Harbor", "Lumen", "Meridian",
    "Nimbus", "Orchid", "Pioneer", "Redwood", "Summit", "Vertex", "Willow",
)
_NOUNS = (
    "Analytics", "Biotech", "Cloud", "Dynamics", "Health", "Logistics",
    "Networks", "Robotics", "Security", "Systems", "Technology", "Works",
)
_FIRST_NAMES = (
    "Aisha", "Alex", "Amara", "Daniel", "Elena", "Iris", "Jordan", "Luis",
    "Maya", "Nora", "Omar", "Priya", "Ravi", "Sofia", "Theo", "Zoe",
)
_LAST_NAMES = (
    "Brown", "Chen", "Garcia", "Johnson", "Khan", "Lee", "Martin", "Nguyen",
    "Patel", "Rivera", "Smith", "Taylor", "Walker", "Wilson",
)
_INDUSTRIES = ("Healthcare", "Life Sciences", "Software", "Manufacturing", "Financial Services")
_COUNTRIES = ("United States", "Canada", "United Kingdom", "Germany", "Australia")
_STAGES = ("Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won")


@dataclass(frozen=True)
class GenerationConfig:
    """Parameters that completely determine one generated dataset.

    ``company_count`` may be one of the documented presets (25, 250, or 2,500)
    or any custom value from 3 through 100,000. Three is the minimum because the
    core scenario always includes a parent, subsidiary, and acquired company.
    """

    company_count: int = 25
    seed: int = DEFAULT_SEED
    people_per_company: int = 2

    def __post_init__(self) -> None:
        if isinstance(self.company_count, bool) or not isinstance(self.company_count, int):
            raise ValueError("company_count must be an integer")
        if not 3 <= self.company_count <= MAX_COMPANIES:
            raise ValueError("company_count must be between 3 and %d" % MAX_COMPANIES)
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if self.people_per_company != 2:
            raise ValueError("P1.5 version 1 requires exactly two people per company")


@dataclass
class SyntheticDataset:
    """All generated records plus discoverable expected outcomes."""

    config: GenerationConfig
    companies: List[Dict[str, Any]]
    account_name_history: List[Dict[str, Any]]
    account_relationships: List[Dict[str, Any]]
    people: List[Dict[str, Any]]
    employment_history: List[Dict[str, Any]]
    opportunities: List[Dict[str, Any]]
    activities: List[Dict[str, Any]]
    salesforce_events: List[Dict[str, Any]]
    hubspot_events: List[Dict[str, Any]]
    quality_issues: List[Dict[str, Any]]
    expected_identity_outcomes: List[Dict[str, Any]]

    @property
    def source_events(self) -> List[Dict[str, Any]]:
        """Return events in deterministic source order without changing them."""
        return [*self.salesforce_events, *self.hubspot_events]

    def counts(self) -> Dict[str, int]:
        """Return stable record counts used by manifests, tests, and demos."""
        return {
            "companies": len(self.companies),
            "account_name_history": len(self.account_name_history),
            "account_relationships": len(self.account_relationships),
            "people": len(self.people),
            "employment_history": len(self.employment_history),
            "opportunities": len(self.opportunities),
            "activities": len(self.activities),
            "salesforce_events": len(self.salesforce_events),
            "hubspot_events": len(self.hubspot_events),
            "source_events": len(self.source_events),
            "quality_issues": len(self.quality_issues),
            "expected_identity_outcomes": len(self.expected_identity_outcomes),
        }

    def as_document(self) -> Dict[str, Any]:
        """Return the complete deterministic dataset as one JSON-ready object."""
        return {
            "contract_version": CONTRACT_VERSION,
            "synthetic": True,
            "config": {
                "company_count": self.config.company_count,
                "seed": self.config.seed,
                "people_per_company": self.config.people_per_company,
            },
            "records": {
                "companies": self.companies,
                "account_name_history": self.account_name_history,
                "account_relationships": self.account_relationships,
                "people": self.people,
                "employment_history": self.employment_history,
                "opportunities": self.opportunities,
                "activities": self.activities,
                "salesforce_events": self.salesforce_events,
                "hubspot_events": self.hubspot_events,
            },
            "quality_issues": self.quality_issues,
            "expected_identity_outcomes": self.expected_identity_outcomes,
        }

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint proving byte-independent determinism."""
        encoded = json.dumps(
            self.as_document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def manifest(self) -> Dict[str, Any]:
        """Describe scenarios, counts, issues, and expected identity behavior."""
        issue_counts = Counter(item["issue_type"] for item in self.quality_issues)
        return {
            "contract_name": "synthetic-gtm-scenario-manifest",
            "contract_version": CONTRACT_VERSION,
            "synthetic": True,
            "scenario_name": "P1.5 interconnected fictional B2B SaaS ecosystem",
            "generator": {
                "company_count": self.config.company_count,
                "seed": self.config.seed,
                "people_per_company": self.config.people_per_company,
                "deterministic": True,
            },
            "dataset_fingerprint_sha256": self.fingerprint(),
            "counts": self.counts(),
            "quality_issue_counts": dict(sorted(issue_counts.items())),
            "quality_issues": self.quality_issues,
            "identity_policy": {
                "default_state": "unresolved",
                "automatic_merge": False,
                "note": "Expected matches are evidence for review, never approved crosswalks.",
            },
            "expected_identity_outcomes": self.expected_identity_outcomes,
            "authority_expectations": {
                "Account.lifecycle_status": {
                    "authoritative_source": "salesforce",
                    "conflicting_source": "hubspot",
                    "expected_action": "preserve_both_and_open_review",
                },
                "Opportunity.stage": {
                    "authoritative_source": "salesforce",
                    "conflicting_source": "hubspot",
                    "expected_action": "preserve_both_and_open_review",
                },
            },
            "boundaries": {
                "live_vendor_data": False,
                "automatic_identity_approval": False,
                "live_write_back": False,
                "p5_workflows": False,
                "activity_rows": "canonical fixtures; P1.3 has no Activity source contract",
            },
            "files": [
                "synthetic-gtm-dataset.v1.json",
                "salesforce-events.v1.jsonl",
                "hubspot-events.v1.jsonl",
                "companies.csv",
                "account-name-history.csv",
                "account-relationships.csv",
                "people.csv",
                "employment-history.csv",
                "opportunities.csv",
                "activities.csv",
                "scenario-manifest.v1.json",
            ],
        }


class _StableIds:
    """Create deterministic, correctly prefixed UUIDv7 fixture identifiers."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.ordinal = 0

    def next(self, entity_type: str, logical_key: str) -> str:
        self.ordinal += 1
        digest = hashlib.sha256(
            ("%d:%s:%s" % (self.seed, entity_type, logical_key)).encode("utf-8")
        ).digest()
        random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
        identifier = uuid7(
            timestamp_ms=int(BASE_TIME.timestamp() * 1000) + self.ordinal,
            random_bits=random_bits,
        )
        return PREFIX_REGISTRY[entity_type] + str(identifier)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_id(prefix: str, index: int) -> str:
    """Return an 18-character Salesforce-style identifier."""
    return prefix + ("%015d" % (index + 1))


def _event(
    system: str,
    object_type: str,
    object_id: str,
    event_id: str,
    payload: Dict[str, Any],
    source_updated_at: datetime,
    observed_at: datetime,
    cursor: int,
    event_type: str = "upsert",
) -> Dict[str, Any]:
    """Wrap one source-native payload in the existing P1.3 envelope."""
    code = "sf" if system == "salesforce" else "hs"
    return {
        "contract_version": CONTRACT_VERSION,
        "event_id": event_id,
        "source": {
            "system": system,
            "tenant": "synthetic-%s-prod" % system,
            "object_type": object_type,
            "object_id": object_id,
        },
        "event_type": event_type,
        "timestamps": {
            "source_updated_at": _iso(source_updated_at),
            "observed_at": _iso(observed_at),
        },
        "tracing": {
            "trace_id": "trace-p15-%s-%06d" % (code, cursor),
            "extraction_id": "synthetic-p15-seed-run",
        },
        "checkpoint": {
            "stream_name": object_type,
            "cursor": "%s-%s-%06d" % (code, object_type.lower(), cursor),
            "high_watermark_at": _iso(observed_at + timedelta(seconds=5)),
        },
        "payload": payload,
    }


def _company_identity(index: int, rng: random.Random) -> Dict[str, str]:
    if index == 0:
        return {"name": "Globex Health", "domain": "globex.example", "industry": "Healthcare"}
    if index == 1:
        return {
            "name": "Globex Diagnostics",
            "domain": "diagnostics.globex.example",
            "industry": "Healthcare",
        }
    if index == 2:
        return {"name": "Northstar Labs", "domain": "northstar.example", "industry": "Life Sciences"}
    adjective = rng.choice(_ADJECTIVES)
    noun = rng.choice(_NOUNS)
    return {
        "name": "%s %s %04d" % (adjective, noun, index + 1),
        "domain": "%s-%s-%04d.example" % (adjective.lower(), noun.lower(), index + 1),
        "industry": rng.choice(_INDUSTRIES),
    }


def _person_identity(company_index: int, person_index: int, rng: random.Random) -> Dict[str, str]:
    if company_index == 0 and person_index == 0:
        return {"first_name": "Sarah", "last_name": "Kim", "title": "VP Revenue Operations"}
    if company_index == 0 and person_index == 1:
        return {"first_name": "John", "last_name": "Lee", "title": "Chief Financial Officer"}
    if company_index == 1 and person_index == 0:
        return {"first_name": "Maya", "last_name": "Chen", "title": "Director of Analytics"}
    return {
        "first_name": rng.choice(_FIRST_NAMES),
        "last_name": rng.choice(_LAST_NAMES),
        "title": rng.choice(("Director", "VP Operations", "Data Manager", "Finance Lead", "Analyst")),
    }


def generate_dataset(config: GenerationConfig = GenerationConfig()) -> SyntheticDataset:
    """Generate one connected and reproducible P1.5 dataset.

    Identical configurations produce identical records and fingerprints. Source
    events comply with the current P1.3 contracts, while intentional problems are
    limited to optional values, competing records, and business-level ambiguity.
    """
    rng = random.Random(config.seed)
    ids = _StableIds(config.seed)
    companies: List[Dict[str, Any]] = []
    account_name_history: List[Dict[str, Any]] = []
    account_relationships: List[Dict[str, Any]] = []
    people: List[Dict[str, Any]] = []
    employment_history: List[Dict[str, Any]] = []
    opportunities: List[Dict[str, Any]] = []
    activities: List[Dict[str, Any]] = []
    salesforce_events: List[Dict[str, Any]] = []
    hubspot_events: List[Dict[str, Any]] = []
    quality_issues: List[Dict[str, Any]] = []
    outcomes: List[Dict[str, Any]] = []
    sf_cursor = 0
    hs_cursor = 0

    for company_index in range(config.company_count):
        identity = _company_identity(company_index, rng)
        account_id = ids.next("Account", "company-%d" % company_index)
        sf_account_id = _source_id("001", company_index)
        hs_company_id = str(700_000 + company_index)
        country = rng.choice(_COUNTRIES)
        lifecycle = "customer" if company_index % 5 == 0 else "prospect"
        company = {
            "account_id": account_id,
            "name": identity["name"],
            "domain": identity["domain"],
            "industry": identity["industry"],
            "country": country,
            "lifecycle_status": lifecycle,
            "salesforce_account_id": sf_account_id,
            "hubspot_company_id": hs_company_id,
        }
        companies.append(company)
        account_name_history.append({
            "account_name_history_id": ids.next("AccountNameHistory", "name-%d-current" % company_index),
            "account_id": account_id,
            "name": identity["name"],
            "name_type": "official",
            "is_preferred": True,
            "valid_from": "2025-01-01",
            "valid_to": "",
        })

        event_time = BASE_TIME + timedelta(days=company_index % 180)
        sf_cursor += 1
        sf_name = "Northstar Research" if company_index == 2 else identity["name"]
        sf_payload: Dict[str, Any] = {
            "attributes": {"type": "Account"},
            "Id": sf_account_id,
            "Name": sf_name,
            "Industry": identity["industry"],
            "BillingCountry": country,
            "OwnerId": "005SYNTHETICOWNER",
            "LastModifiedDate": _iso(event_time),
            "IsDeleted": False,
            "Lifecycle_Status__c": lifecycle,
            "Synthetic_Account_Key__c": "company-%06d" % company_index,
        }
        if company_index % 7 != 6:
            sf_payload["Website"] = "https://%s" % identity["domain"]
        else:
            quality_issues.append({
                "issue_id": "missing-company-domain-%06d" % company_index,
                "issue_type": "missing_optional_field",
                "record_keys": ["salesforce:Account:%s" % sf_account_id],
                "description": "Salesforce Website is intentionally absent.",
                "expected_outcome": "preserve record; do not invent a domain",
            })
        sf_account_event = _event(
            "salesforce", "Account", sf_account_id,
            "p15-sf-account-%06d-v1" % company_index,
            sf_payload, event_time, event_time + timedelta(minutes=2), sf_cursor,
        )
        salesforce_events.append(sf_account_event)

        hs_cursor += 1
        hubspot_lifecycle = "marketingqualifiedlead" if company_index % 5 == 0 else lifecycle
        hs_properties: Dict[str, Any] = {
            "name": identity["name"],
            "industry": identity["industry"],
            "hubspot_owner_id": "hs-owner-01",
            "lifecyclestage": hubspot_lifecycle,
            "synthetic_account_key": "company-%06d" % company_index,
        }
        if company_index != 2:
            hs_properties["country"] = country
        else:
            quality_issues.append({
                "issue_id": "missing-northstar-country",
                "issue_type": "missing_optional_field",
                "record_keys": ["hubspot:Company:%s" % hs_company_id],
                "description": "HubSpot country is intentionally absent for Northstar Labs.",
                "expected_outcome": "preserve record; do not invent a country",
            })
        if company_index % 7 != 6:
            hs_properties["domain"] = identity["domain"]
        hs_payload = {
            "id": hs_company_id,
            "properties": hs_properties,
            "createdAt": _iso(event_time - timedelta(days=60)),
            "updatedAt": _iso(event_time + timedelta(minutes=1)),
            "archived": False,
        }
        hubspot_events.append(_event(
            "hubspot", "Company", hs_company_id,
            "p15-hs-company-%06d-v1" % company_index,
            hs_payload, event_time + timedelta(minutes=1), event_time + timedelta(minutes=3), hs_cursor,
        ))

        if lifecycle != hubspot_lifecycle:
            quality_issues.append({
                "issue_id": "account-lifecycle-conflict-%06d" % company_index,
                "issue_type": "conflicting_information",
                "record_keys": [
                    "salesforce:Account:%s" % sf_account_id,
                    "hubspot:Company:%s" % hs_company_id,
                ],
                "description": "Salesforce and HubSpot lifecycle values disagree.",
                "expected_outcome": "Salesforce value stays trusted; preserve HubSpot proposal for review",
            })

        opportunity_id = ids.next("Opportunity", "opportunity-%d" % company_index)
        sf_opportunity_id = _source_id("006", company_index)
        hs_deal_id = str(900_000 + company_index)
        stage = _STAGES[company_index % len(_STAGES)]
        amount = 25_000 + ((company_index * 7_500) % 250_000)
        close_date = (event_time + timedelta(days=90)).date().isoformat()
        opportunities.append({
            "opportunity_id": opportunity_id,
            "primary_account_id": account_id,
            "name": "%s Expansion" % identity["name"],
            "stage": stage,
            "amount": amount,
            "currency_code": "USD",
            "expected_close_date": close_date,
            "salesforce_opportunity_id": sf_opportunity_id,
            "hubspot_deal_id": hs_deal_id,
        })
        sf_cursor += 1
        sf_amount = None if company_index % 13 == 12 else amount
        sf_opp_payload = {
            "attributes": {"type": "Opportunity"},
            "Id": sf_opportunity_id,
            "Name": "%s Expansion" % identity["name"],
            "AccountId": sf_account_id,
            "StageName": stage,
            "Amount": sf_amount,
            "CurrencyIsoCode": "USD",
            "CloseDate": close_date,
            "IsClosed": stage == "Closed Won",
            "IsWon": stage == "Closed Won",
            "LastModifiedDate": _iso(event_time + timedelta(hours=1)),
            "IsDeleted": False,
        }
        salesforce_events.append(_event(
            "salesforce", "Opportunity", sf_opportunity_id,
            "p15-sf-opportunity-%06d-v1" % company_index,
            sf_opp_payload, event_time + timedelta(hours=1),
            event_time + timedelta(hours=1, minutes=2), sf_cursor,
        ))
        if sf_amount is None:
            quality_issues.append({
                "issue_id": "missing-opportunity-amount-%06d" % company_index,
                "issue_type": "missing_optional_field",
                "record_keys": ["salesforce:Opportunity:%s" % sf_opportunity_id],
                "description": "Salesforce Opportunity Amount is intentionally null.",
                "expected_outcome": "preserve null; do not fabricate pipeline value",
            })
        hs_cursor += 1
        hs_stage = "appointmentscheduled" if company_index % 6 == 0 else stage.casefold().replace(" ", "")
        hubspot_events.append(_event(
            "hubspot", "Deal", hs_deal_id,
            "p15-hs-deal-%06d-v1" % company_index,
            {
                "id": hs_deal_id,
                "properties": {
                    "dealname": "%s Expansion" % identity["name"],
                    "dealstage": hs_stage,
                    "amount": str(amount),
                    "closedate": close_date,
                    "hubspot_owner_id": "hs-owner-01",
                    "associatedcompanyid": hs_company_id,
                },
                "updatedAt": _iso(event_time + timedelta(hours=1, minutes=1)),
                "archived": False,
            },
            event_time + timedelta(hours=1, minutes=1),
            event_time + timedelta(hours=1, minutes=3), hs_cursor,
        ))
        if company_index % 6 == 0:
            quality_issues.append({
                "issue_id": "opportunity-stage-conflict-%06d" % company_index,
                "issue_type": "conflicting_information",
                "record_keys": [
                    "salesforce:Opportunity:%s" % sf_opportunity_id,
                    "hubspot:Deal:%s" % hs_deal_id,
                ],
                "description": "CRM stages intentionally disagree.",
                "expected_outcome": "Salesforce stage remains authoritative; preserve HubSpot stage for review",
            })

        for person_offset in range(config.people_per_company):
            person_number = company_index * config.people_per_company + person_offset
            person_identity = _person_identity(company_index, person_offset, rng)
            person_id = ids.next("Person", "person-%d" % person_number)
            email = "%s.%s@%s" % (
                person_identity["first_name"].lower(),
                person_identity["last_name"].lower(),
                identity["domain"],
            )
            if company_index != 0:
                email = "%s.%s.%d@%s" % (
                    person_identity["first_name"].lower(),
                    person_identity["last_name"].lower(),
                    person_number,
                    identity["domain"],
                )
            if person_number % 11 == 10:
                email = ""
            people.append({
                "person_id": person_id,
                "display_name": "%s %s" % (person_identity["first_name"], person_identity["last_name"]),
                "primary_email_normalized": email,
                "current_account_id": account_id,
                "job_title": person_identity["title"],
            })
            relationship_start = "2025-01-01"
            if company_index == 0 and person_offset == 0:
                employment_history.append({
                    "account_person_relationship_id": ids.next(
                        "AccountPersonRelationship", "sarah-northstar-history"
                    ),
                    "account_id": companies[2]["account_id"] if len(companies) > 2 else account_id,
                    "person_id": person_id,
                    "relationship_type": "employee",
                    "job_title": "Revenue Operations Director",
                    "valid_from": "2023-01-01",
                    "valid_to": "2025-01-01",
                    "is_primary": False,
                })
            employment_history.append({
                "account_person_relationship_id": ids.next(
                    "AccountPersonRelationship", "employment-%d-current" % person_number
                ),
                "account_id": account_id,
                "person_id": person_id,
                "relationship_type": "employee",
                "job_title": person_identity["title"],
                "valid_from": relationship_start,
                "valid_to": "",
                "is_primary": True,
            })

            sf_person_prefix = "003" if person_offset == 0 else "00Q"
            sf_person_type = "Contact" if person_offset == 0 else "Lead"
            sf_person_id = _source_id(sf_person_prefix, person_number)
            sf_cursor += 1
            sf_person_payload: Dict[str, Any] = {
                "attributes": {"type": sf_person_type},
                "Id": sf_person_id,
                "FirstName": person_identity["first_name"],
                "LastName": person_identity["last_name"],
                "LastModifiedDate": _iso(event_time + timedelta(hours=2, minutes=person_offset)),
                "IsDeleted": False,
            }
            if email:
                sf_person_payload["Email"] = email
            if sf_person_type == "Contact":
                sf_person_payload["AccountId"] = sf_account_id
                sf_person_payload["Title"] = person_identity["title"]
            else:
                sf_person_payload["Company"] = identity["name"]
                sf_person_payload["Status"] = "Working"
                sf_person_payload["ConvertedContactId"] = None
            salesforce_events.append(_event(
                "salesforce", sf_person_type, sf_person_id,
                "p15-sf-%s-%06d-v1" % (sf_person_type.lower(), person_number),
                sf_person_payload,
                event_time + timedelta(hours=2, minutes=person_offset),
                event_time + timedelta(hours=2, minutes=person_offset + 2), sf_cursor,
            ))

            hs_contact_id = str(800_000 + person_number)
            hs_title = "Former Revenue Operations Director" if person_number == 0 else person_identity["title"]
            hs_contact_company = (
                companies[2]["hubspot_company_id"]
                if person_number == 0 and len(companies) > 2
                else hs_company_id
            )
            hs_properties = {
                "firstname": person_identity["first_name"],
                "lastname": person_identity["last_name"],
                "associatedcompanyid": hs_contact_company,
                "jobtitle": hs_title,
            }
            if email:
                hs_properties["email"] = email
            hs_cursor += 1
            hubspot_events.append(_event(
                "hubspot", "Contact", hs_contact_id,
                "p15-hs-contact-%06d-v1" % person_number,
                {
                    "id": hs_contact_id,
                    "properties": hs_properties,
                    "updatedAt": _iso(event_time + timedelta(hours=2, minutes=person_offset + 1)),
                    "archived": False,
                },
                event_time + timedelta(hours=2, minutes=person_offset + 1),
                event_time + timedelta(hours=2, minutes=person_offset + 3), hs_cursor,
            ))
            if not email:
                quality_issues.append({
                    "issue_id": "missing-person-email-%06d" % person_number,
                    "issue_type": "missing_optional_field",
                    "record_keys": [
                        "salesforce:%s:%s" % (sf_person_type, sf_person_id),
                        "hubspot:Contact:%s" % hs_contact_id,
                    ],
                    "description": "Both source records intentionally omit email.",
                    "expected_outcome": "remain unresolved without fabricated contact data",
                })

            activity_id = ids.next("Activity", "activity-%d" % person_number)
            activities.append({
                "activity_id": activity_id,
                "activity_type": "meeting" if person_offset == 0 else "email",
                "occurred_at": _iso(event_time + timedelta(days=7, hours=person_offset)),
                "person_id": person_id,
                "account_id": account_id,
                "opportunity_id": opportunity_id,
                "campaign_id": "",
                "resolution_status": "resolved",
                "fixture_only": True,
            })

    # The fixed hierarchy and acquisition retain three separate Account identities.
    account_relationships.extend([
        {
            "account_hierarchy_relationship_id": ids.next("AccountHierarchyRelationship", "globex-subsidiary"),
            "parent_account_id": companies[0]["account_id"],
            "child_account_id": companies[1]["account_id"],
            "relationship_type": "subsidiary",
            "valid_from": "2024-01-01",
            "valid_to": "",
        },
        {
            "account_hierarchy_relationship_id": ids.next("AccountHierarchyRelationship", "globex-acquires-northstar"),
            "parent_account_id": companies[0]["account_id"],
            "child_account_id": companies[2]["account_id"],
            "relationship_type": "acquired_company",
            "valid_from": "2026-07-01",
            "valid_to": "",
        },
    ])
    # Sarah's stale HubSpot association and historical employment can reference
    # Northstar only after all fixed companies have been allocated.
    employment_history[0]["account_id"] = companies[2]["account_id"]
    sarah_hubspot = next(
        event for event in hubspot_events
        if event["source"]["object_type"] == "Contact"
        and event["source"]["object_id"] == "800000"
    )
    sarah_hubspot["payload"]["properties"]["associatedcompanyid"] = companies[2]["hubspot_company_id"]
    quality_issues.append({
        "issue_id": "acquisition-not-merge",
        "issue_type": "acquisition",
        "record_keys": ["canonical:Account:%s" % companies[2]["account_id"]],
        "description": "Globex Health acquired Northstar Labs.",
        "expected_outcome": "keep both Accounts; connect them with an effective-dated relationship",
    })

    # Northstar changes its name without receiving a new Account identity.
    account_name_history[2]["valid_from"] = "2026-03-01"
    account_name_history.insert(2, {
        "account_name_history_id": ids.next("AccountNameHistory", "northstar-old-name"),
        "account_id": companies[2]["account_id"],
        "name": "Northstar Research",
        "name_type": "official",
        "is_preferred": False,
        "valid_from": "2024-01-01",
        "valid_to": "2026-03-01",
    })
    northstar_initial = next(
        event for event in salesforce_events
        if event["source"]["object_type"] == "Account"
        and event["source"]["object_id"] == companies[2]["salesforce_account_id"]
    )
    northstar_update_time = datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc)
    sf_cursor += 1
    northstar_payload = dict(northstar_initial["payload"])
    northstar_payload["Name"] = "Northstar Labs"
    northstar_payload["LastModifiedDate"] = _iso(northstar_update_time)
    salesforce_events.append(_event(
        "salesforce", "Account", companies[2]["salesforce_account_id"],
        "p15-sf-account-000002-rebrand", northstar_payload,
        northstar_update_time, northstar_update_time + timedelta(minutes=3), sf_cursor,
    ))
    quality_issues.append({
        "issue_id": "northstar-rebrand",
        "issue_type": "company_rebrand",
        "record_keys": ["salesforce:Account:%s" % companies[2]["salesforce_account_id"]],
        "description": "Northstar Research became Northstar Labs.",
        "expected_outcome": "retain one Account ID and preserve both effective-dated names",
    })

    # Globex has a newer update followed by a late older event in arrival order.
    globex_initial = salesforce_events[0]
    globex_new_time = datetime(2026, 4, 20, 14, 0, tzinfo=timezone.utc)
    sf_cursor += 1
    globex_new_payload = dict(globex_initial["payload"])
    globex_new_payload["LastModifiedDate"] = _iso(globex_new_time)
    globex_new_payload["Employee_Count__c"] = 2400
    salesforce_events.append(_event(
        "salesforce", "Account", companies[0]["salesforce_account_id"],
        "p15-sf-account-000000-v2", globex_new_payload,
        globex_new_time, globex_new_time + timedelta(minutes=2), sf_cursor,
    ))
    globex_late_time = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
    sf_cursor += 1
    globex_late_payload = dict(globex_initial["payload"])
    globex_late_payload["LastModifiedDate"] = _iso(globex_late_time)
    globex_late_payload["Employee_Count__c"] = 2350
    salesforce_events.append(_event(
        "salesforce", "Account", companies[0]["salesforce_account_id"],
        "p15-sf-account-000000-late", globex_late_payload,
        globex_late_time, globex_new_time + timedelta(days=2), sf_cursor,
    ))
    quality_issues.append({
        "issue_id": "globex-late-account-update",
        "issue_type": "late_out_of_order_event",
        "record_keys": ["salesforce:Account:%s" % companies[0]["salesforce_account_id"]],
        "description": "An older Globex update arrives after a newer version.",
        "expected_outcome": "append history but keep the newer source state current",
    })

    # A second HubSpot Company shares Globex's domain and therefore stays ambiguous.
    duplicate_company_id = "799999"
    hs_cursor += 1
    duplicate_time = BASE_TIME + timedelta(days=20)
    hubspot_events.append(_event(
        "hubspot", "Company", duplicate_company_id,
        "p15-hs-company-globex-duplicate",
        {
            "id": duplicate_company_id,
            "properties": {
                "name": "Globex Healthcare",
                "domain": companies[0]["domain"],
                "industry": "Healthcare",
                "country": "United States",
                "hubspot_owner_id": "hs-owner-duplicate",
                "lifecyclestage": "lead",
            },
            "createdAt": _iso(duplicate_time - timedelta(days=90)),
            "updatedAt": _iso(duplicate_time),
            "archived": False,
        },
        duplicate_time, duplicate_time + timedelta(minutes=2), hs_cursor,
    ))
    quality_issues.append({
        "issue_id": "globex-duplicate-company",
        "issue_type": "duplicate_record",
        "record_keys": [
            "hubspot:Company:%s" % companies[0]["hubspot_company_id"],
            "hubspot:Company:%s" % duplicate_company_id,
        ],
        "description": "Two HubSpot companies share the Globex domain with different names.",
        "expected_outcome": "mark candidates ambiguous; require human review",
    })

    # An exact repeated event proves idempotent replay while remaining visible in JSONL.
    salesforce_events.append(json.loads(json.dumps(globex_initial)))
    quality_issues.append({
        "issue_id": "globex-exact-event-replay",
        "issue_type": "duplicate_event",
        "record_keys": [globex_initial["event_id"]],
        "description": "The identical Salesforce event appears twice.",
        "expected_outcome": "return the prior processing result without duplicate history",
    })

    quality_issues.append({
        "issue_id": "sarah-job-change",
        "issue_type": "employee_job_change",
        "record_keys": ["canonical:Person:%s" % people[0]["person_id"]],
        "description": (
            "Sarah Kim has stale Northstar employment in HubSpot and current Globex "
            "employment in Salesforce."
        ),
        "expected_outcome": "keep one Person candidate and preserve effective-dated employment evidence",
    })
    quality_issues.append({
        "issue_id": "sarah-ambiguous-identity",
        "issue_type": "ambiguous_identity_match",
        "record_keys": [
            "salesforce:Contact:%s" % _source_id("003", 0),
            "hubspot:Contact:800000",
        ],
        "description": "Email agrees but stale employer and title evidence conflict.",
        "expected_outcome": "open an ambiguous review case; never auto-merge",
    })

    outcomes.extend([
        {
            "scenario": "globex-cross-source-company",
            "source_records": [
                "salesforce:Account:%s" % companies[0]["salesforce_account_id"],
                "hubspot:Company:%s" % companies[0]["hubspot_company_id"],
            ],
            "expected_canonical_subject": companies[0]["account_id"],
            "expected_resolution": "review_required",
            "automatic_merge": False,
            "reason": "matching domain is candidate evidence, not approval",
        },
        {
            "scenario": "globex-duplicate-hubspot-company",
            "source_records": [
                "hubspot:Company:%s" % companies[0]["hubspot_company_id"],
                "hubspot:Company:%s" % duplicate_company_id,
            ],
            "expected_canonical_subject": companies[0]["account_id"],
            "expected_resolution": "ambiguous",
            "automatic_merge": False,
            "reason": "shared domain and conflicting names require stewardship",
        },
        {
            "scenario": "sarah-cross-source-person",
            "source_records": [
                "salesforce:Contact:%s" % _source_id("003", 0),
                "hubspot:Contact:800000",
            ],
            "expected_canonical_subject": people[0]["person_id"],
            "expected_resolution": "ambiguous",
            "automatic_merge": False,
            "reason": "email agrees while employer and title evidence conflict",
        },
        {
            "scenario": "northstar-acquisition",
            "source_records": [
                "salesforce:Account:%s" % companies[2]["salesforce_account_id"],
                "hubspot:Company:%s" % companies[2]["hubspot_company_id"],
            ],
            "expected_canonical_subject": companies[2]["account_id"],
            "expected_resolution": "keep_separate_account",
            "automatic_merge": False,
            "reason": "an acquisition creates a relationship, not an identity merge",
        },
    ])

    return SyntheticDataset(
        config=config,
        companies=companies,
        account_name_history=account_name_history,
        account_relationships=account_relationships,
        people=people,
        employment_history=employment_history,
        opportunities=opportunities,
        activities=activities,
        salesforce_events=salesforce_events,
        hubspot_events=hubspot_events,
        quality_issues=quality_issues,
        expected_identity_outcomes=outcomes,
    )
