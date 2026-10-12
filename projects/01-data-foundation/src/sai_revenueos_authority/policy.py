"""Load and validate the versioned P1.4 field-authority policy.

The policy names the source systems allowed to establish each canonical field,
the human role that owns conflicts, and the systems eligible for controlled
write-back. It validates every implemented field against the unchanged canonical
model so configuration cannot silently invent a new entity or attribute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from sai_revenueos_identity.errors import NotFoundError, ValidationError


CONTRACT_VERSION = "1.0.0"
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = PROJECT_DIR / "contracts/field-authority-policy.v1.json"
CANONICAL_CONTRACT_PATH = PROJECT_DIR.parents[1] / "shared/contracts/canonical-model.v1.json"
APPROVED_SOURCE_DOMAINS = {
    "sales": ["salesforce"],
    "marketing": ["hubspot"],
    "enrichment": ["clay", "apollo"],
    "usage": ["product"],
    "billing": ["billing"],
    "payments": ["stripe"],
    "accounting": ["erp"],
    "customer_health": ["customer_success"],
    "consent": ["consent_registry"],
}


@dataclass(frozen=True)
class FieldPolicy:
    """One executable source-of-truth rule for one canonical field."""

    entity_type: str
    field_name: str
    domain: str
    authoritative_sources: FrozenSet[str]
    allowed_writer_roles: FrozenSet[str]
    review_owner_role: str
    protect_manual_verification: bool
    write_back_targets: FrozenSet[str]


class AuthorityPolicy:
    """Validated field ownership, conflict ownership, and write-back rules."""

    def __init__(
        self,
        policy_path: Path = DEFAULT_POLICY_PATH,
        canonical_contract_path: Path = CANONICAL_CONTRACT_PATH,
    ) -> None:
        try:
            document = json.loads(policy_path.read_text(encoding="utf-8"))
            canonical = json.loads(canonical_contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError("field-authority policy could not be loaded") from exc
        self._document = document
        self._validate(document, canonical)
        self.contract_version = document["contract_version"]
        self.default_action = document["default_action"]
        self.source_domains: Dict[str, FrozenSet[str]] = {
            domain: frozenset(systems) for domain, systems in document["source_domains"].items()
        }
        self.write_back_authorized_roles = frozenset(
            document["write_back_policy"]["authorized_roles"]
        )
        self.requires_resolved_conflict = bool(
            document["write_back_policy"]["requires_resolved_conflict"]
        )
        self.network_delivery = bool(document["write_back_policy"]["network_delivery"])
        self._fields: Dict[Tuple[str, str], FieldPolicy] = {}
        for item in document["field_policies"]:
            field = FieldPolicy(
                entity_type=item["entity_type"],
                field_name=item["field_name"],
                domain=item["domain"],
                authoritative_sources=frozenset(item["authoritative_sources"]),
                allowed_writer_roles=frozenset(item["allowed_writer_roles"]),
                review_owner_role=item["review_owner_role"],
                protect_manual_verification=item["protect_manual_verification"],
                write_back_targets=frozenset(item["write_back_targets"]),
            )
            self._fields[(field.entity_type, field.field_name)] = field

    @staticmethod
    def _validate(document: Mapping[str, Any], canonical: Mapping[str, Any]) -> None:
        """Reject incomplete policy or references outside the canonical contract."""
        required = {
            "contract_name", "contract_version", "description", "default_action",
            "source_domains", "field_policies", "write_back_policy", "future_extension_points",
        }
        if set(document) != required:
            raise ValidationError("field-authority policy has unexpected or missing top-level fields")
        if document["contract_name"] != "field-authority-policy":
            raise ValidationError("unexpected field-authority contract name")
        if document["contract_version"] != CONTRACT_VERSION:
            raise ValidationError("unsupported field-authority contract version")
        if document["default_action"] != "deny":
            raise ValidationError("field-authority policy must default to deny")
        domains = document["source_domains"]
        if not isinstance(domains, dict) or not domains:
            raise ValidationError("source_domains must be a non-empty object")
        if domains != APPROVED_SOURCE_DOMAINS:
            raise ValidationError("source_domains do not match the approved P1.4 decision")
        all_systems = set()
        for domain, systems in domains.items():
            if not isinstance(domain, str) or not domain or not isinstance(systems, list) or not systems:
                raise ValidationError("each source domain requires named systems")
            if any(not isinstance(system, str) or not system for system in systems):
                raise ValidationError("source system names must be non-empty strings")
            overlap = all_systems.intersection(systems)
            if overlap:
                raise ValidationError("source systems cannot belong to multiple domains")
            all_systems.update(systems)

        entities = canonical.get("entities", {})
        seen = set()
        fields = document["field_policies"]
        if not isinstance(fields, list) or not fields:
            raise ValidationError("field_policies must be a non-empty array")
        field_keys = {
            "entity_type", "field_name", "domain", "authoritative_sources",
            "allowed_writer_roles", "review_owner_role", "protect_manual_verification",
            "write_back_targets",
        }
        for item in fields:
            if not isinstance(item, dict) or set(item) != field_keys:
                raise ValidationError("each field policy must use the version 1 shape")
            key = (item["entity_type"], item["field_name"])
            if key in seen:
                raise ValidationError("field policy is duplicated: %s.%s" % key)
            seen.add(key)
            entity = entities.get(item["entity_type"])
            if entity is None or item["field_name"] not in entity.get("important_attributes", []):
                raise ValidationError("field policy is outside the canonical contract: %s.%s" % key)
            domain = item["domain"]
            if domain not in domains:
                raise ValidationError("field policy uses an unknown domain")
            authorities = item["authoritative_sources"]
            if not isinstance(authorities, list) or not authorities:
                raise ValidationError("field policy requires an authoritative source")
            if not set(authorities).issubset(set(domains[domain])):
                raise ValidationError("field authority must belong to the field's domain")
            if not isinstance(item["allowed_writer_roles"], list) or not item["allowed_writer_roles"]:
                raise ValidationError("field policy requires writer roles")
            if not isinstance(item["review_owner_role"], str) or not item["review_owner_role"]:
                raise ValidationError("field policy requires a conflict owner")
            if not isinstance(item["protect_manual_verification"], bool):
                raise ValidationError("protect_manual_verification must be boolean")
            targets = item["write_back_targets"]
            if not isinstance(targets, list) or not set(targets).issubset(all_systems):
                raise ValidationError("write-back targets must be registered source systems")

        write_back = document["write_back_policy"]
        if set(write_back) != {
            "mode", "authorized_roles", "requires_resolved_conflict", "network_delivery"
        }:
            raise ValidationError("write_back_policy must use the version 1 shape")
        if write_back["mode"] != "authorization_only" or write_back["network_delivery"] is not False:
            raise ValidationError("P1.4 cannot enable network write-back")
        if not isinstance(write_back["authorized_roles"], list) or not write_back["authorized_roles"]:
            raise ValidationError("write-back requires authorized roles")
        if write_back["requires_resolved_conflict"] is not True:
            raise ValidationError("write-back must require a resolved conflict")

    def field(self, entity_type: str, field_name: str) -> FieldPolicy:
        """Return the rule for a governed field or reject default-deny access."""
        try:
            return self._fields[(entity_type, field_name)]
        except KeyError as exc:
            raise NotFoundError("field has no approved source-of-truth policy") from exc

    def source_domain(self, source_system: str) -> Optional[str]:
        """Return the approved business domain for a source system, if registered."""
        normalized = source_system.casefold()
        for domain, systems in self.source_domains.items():
            if normalized in systems:
                return domain
        return None

    def as_dict(self) -> Dict[str, Any]:
        """Return an independent copy for demonstrations and diagnostics."""
        return json.loads(json.dumps(self._document))


__all__ = ["AuthorityPolicy", "CONTRACT_VERSION", "FieldPolicy"]
