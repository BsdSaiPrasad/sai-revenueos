#!/usr/bin/env python3
"""Validate the P1 logical architecture and P1.2 reference artifacts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_DIR.parents[1]
CONTRACT_PATH = REPO_ROOT / "shared/contracts/canonical-model.v1.json"
ERD_PATH = PROJECT_DIR / "architecture/diagrams/canonical-model.mmd"
IDENTITY_ERD_PATH = PROJECT_DIR / "architecture/diagrams/identity-control.mmd"
IDENTITY_GUIDE_PATH = PROJECT_DIR / "architecture/IDENTITY_CONTROL.md"
SCHEMA_PATH = PROJECT_DIR / "src/sai_revenueos_identity/schema.sql"
TEST_PATH = PROJECT_DIR / "tests/test_identity_reference.py"

REQUIRED_ENTITIES = {
    "Account",
    "Person",
    "AccountPersonRelationship",
    "Opportunity",
    "OpportunityPersonRole",
    "Activity",
    "Campaign",
    "Quote",
    "Contract",
    "Order",
    "Subscription",
    "Invoice",
    "ProductUser",
    "SupportCase",
    "Signal",
    "EnrichmentSnapshot",
    "Decision",
    "WorkflowRun",
    "ExternalIdentityCrosswalk",
    "SourceRecord",
    "AccountHierarchyRelationship",
    "AccountNameHistory",
    "AccountDomainHistory",
}

TEMPORAL_ENTITIES = {
    "AccountPersonRelationship",
    "OpportunityPersonRole",
    "ExternalIdentityCrosswalk",
    "AccountHierarchyRelationship",
    "AccountNameHistory",
    "AccountDomainHistory",
}

REQUIRED_ENTITY_FIELDS = {
    "definition",
    "purpose",
    "primary_key",
    "important_attributes",
    "foreign_keys",
    "history",
    "source_relationship",
    "consumers",
}

REQUIRED_CONTINUITY_FILES = {
    "README.md",
    "PROJECT_STATE.md",
    "DECISIONS.md",
    "WORK_LOG.md",
}


def mermaid_name(entity_name: str) -> str:
    """Convert CamelCase contract names to ERD_STYLE names."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", entity_name).upper()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_contract(errors: list[str]) -> dict:
    try:
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"contract cannot be loaded: {exc}")
        return {}


def validate_contract(contract: dict, errors: list[str]) -> None:
    if contract.get("contract_version") != "1.0.0":
        fail(errors, "contract_version must be 1.0.0 for the P1.1 contract")
    if contract.get("owner") != "P1 Data Foundation & Customer Identity":
        fail(errors, "contract owner is missing or unexpected")

    entities = contract.get("entities")
    if not isinstance(entities, dict):
        fail(errors, "entities must be an object")
        return

    missing = REQUIRED_ENTITIES - set(entities)
    extra = set(entities) - REQUIRED_ENTITIES
    if missing:
        fail(errors, f"missing required entities: {', '.join(sorted(missing))}")
    if extra:
        fail(errors, f"unreviewed entities in v1 contract: {', '.join(sorted(extra))}")

    for name, entity in entities.items():
        absent_fields = REQUIRED_ENTITY_FIELDS - set(entity)
        if absent_fields:
            fail(errors, f"{name} missing documentation fields: {', '.join(sorted(absent_fields))}")
            continue
        pk = entity["primary_key"]
        attributes = entity["important_attributes"]
        if pk not in attributes:
            fail(errors, f"{name} primary key {pk!r} is absent from important_attributes")
        if not entity["definition"].strip() or not entity["purpose"].strip():
            fail(errors, f"{name} requires a non-empty definition and purpose")
        if name in TEMPORAL_ENTITIES:
            for temporal_field in ("valid_from", "valid_to"):
                if temporal_field not in attributes:
                    fail(errors, f"{name} must include {temporal_field}")
        for foreign_key in entity["foreign_keys"]:
            match = re.fullmatch(r"([a-z0-9_]+) -> ([A-Za-z]+)\.([a-z0-9_]+)", foreign_key)
            if not match:
                fail(errors, f"{name} has malformed foreign key: {foreign_key}")
                continue
            local_field, target_entity, target_field = match.groups()
            if local_field not in attributes:
                fail(errors, f"{name} foreign-key field {local_field} is not documented as important")
            if target_entity not in entities:
                fail(errors, f"{name} foreign key targets unknown entity {target_entity}")
            elif target_field != entities[target_entity]["primary_key"]:
                fail(errors, f"{name} foreign key targets non-primary field {foreign_key}")

    relationships = contract.get("relationships")
    if not isinstance(relationships, list) or not relationships:
        fail(errors, "relationships must be a non-empty array")
    else:
        allowed_cardinality = {
            "one-to-many",
            "one-to-many-as-parent-or-child",
            "one-to-many-over-time",
        }
        for index, relationship in enumerate(relationships):
            prefix = f"relationship[{index}]"
            if relationship.get("from") not in entities:
                fail(errors, f"{prefix} has unknown from endpoint")
            if relationship.get("to") not in entities:
                fail(errors, f"{prefix} has unknown to endpoint")
            if relationship.get("cardinality") not in allowed_cardinality:
                fail(errors, f"{prefix} has unsupported cardinality")
            if not isinstance(relationship.get("required"), bool):
                fail(errors, f"{prefix} required must be boolean")

    allowed_targets = set(entities)
    for owner, targets in contract.get("polymorphic_subjects", {}).items():
        if owner not in entities:
            fail(errors, f"polymorphic subject owner {owner} is unknown")
        unknown_targets = set(targets) - allowed_targets
        if unknown_targets:
            fail(errors, f"{owner} has unknown polymorphic targets: {sorted(unknown_targets)}")

    invariants = " ".join(contract.get("invariants", [])).lower()
    for phrase in ("lead and contact", "exactly one primary buying account", "customer status"):
        if phrase not in invariants:
            fail(errors, f"contract invariants do not encode approved rule: {phrase}")


def validate_erd(contract: dict, errors: list[str]) -> None:
    try:
        erd = ERD_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        fail(errors, f"ERD cannot be loaded: {exc}")
        return

    if not erd.lstrip().startswith("erDiagram"):
        fail(errors, "Mermaid ERD must start with erDiagram")

    declared = set(re.findall(r"^\s{4}([A-Z][A-Z_]*)\s+\{$", erd, re.MULTILINE))
    expected = {mermaid_name(name) for name in contract.get("entities", {})}
    missing = expected - declared
    extra = declared - expected
    if missing:
        fail(errors, f"ERD is missing entities: {', '.join(sorted(missing))}")
    if extra:
        fail(errors, f"ERD has entities outside the contract: {', '.join(sorted(extra))}")

    relation_pattern = re.compile(
        r'^\s*([A-Z][A-Z_]*)\s+[|o}{]+--[|o}{]+\s+([A-Z][A-Z_]*)\s+:',
        re.MULTILINE,
    )
    erd_pairs = {frozenset(pair) for pair in relation_pattern.findall(erd)}
    for relationship in contract.get("relationships", []):
        pair = frozenset(
            {
                mermaid_name(relationship["from"]),
                mermaid_name(relationship["to"]),
            }
        )
        if pair not in erd_pairs:
            fail(
                errors,
                "ERD lacks contract relationship "
                f"{relationship['from']} -> {relationship['to']}",
            )


def validate_decisions_and_continuity(errors: list[str]) -> None:
    missing_files = [name for name in REQUIRED_CONTINUITY_FILES if not (PROJECT_DIR / name).is_file()]
    if missing_files:
        fail(errors, f"missing continuity files: {', '.join(sorted(missing_files))}")

    decisions_path = PROJECT_DIR / "DECISIONS.md"
    if not decisions_path.exists():
        return
    decisions = decisions_path.read_text(encoding="utf-8")
    for number in range(1, 14):
        decision_id = f"D{number:03d}"
        adr_path = PROJECT_DIR / f"architecture/adr/{number:04d}-"
        if decision_id not in decisions:
            fail(errors, f"DECISIONS.md is missing {decision_id}")
        if not any(adr_path.parent.glob(f"{number:04d}-*.md")):
            fail(errors, f"missing ADR for {decision_id}")


def validate_p12_reference(errors: list[str]) -> None:
    required = (IDENTITY_ERD_PATH, IDENTITY_GUIDE_PATH, SCHEMA_PATH, TEST_PATH, REPO_ROOT / "PROGRESS.md")
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.2 reference artifacts: {', '.join(missing)}")
        return
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    for table in (
        "canonical_identity", "source_record", "source_observation", "resolution_case",
        "candidate_evidence", "external_identity_crosswalk", "identity_merge_event",
        "audit_event", "idempotency_operation",
    ):
        if f"CREATE TABLE IF NOT EXISTS {table}" not in schema:
            fail(errors, f"P1.2 schema is missing {table}")
    for enforcement in (
        "one_active_mapping_per_source", "crosswalk_no_overlap_insert",
        "canonical_identity_no_delete", "source_observation_immutable",
    ):
        if enforcement not in schema:
            fail(errors, f"P1.2 schema is missing enforcement rule {enforcement}")


def validate_no_tracked_secrets(errors: list[str]) -> None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(errors, f"cannot inspect Git file set: {exc}")
        return

    risky_names = re.compile(r"(^|/)(\.env($|\.)|id_rsa$|id_ed25519$|.*\.(pem|p12|pfx|key)$)", re.IGNORECASE)
    for filename in result.stdout.splitlines():
        if filename == ".env.example":
            continue
        if risky_names.search(filename):
            fail(errors, f"secret-like filename is not ignored: {filename}")


def main() -> int:
    errors: list[str] = []
    contract = load_contract(errors)
    if contract:
        validate_contract(contract, errors)
        validate_erd(contract, errors)
    validate_decisions_and_continuity(errors)
    validate_p12_reference(errors)
    validate_no_tracked_secrets(errors)

    if errors:
        print(f"P1 architecture validation FAILED ({len(errors)} issue(s)):")
        for error in errors:
            print(f"  - {error}")
        return 1

    entity_count = len(contract["entities"])
    relationship_count = len(contract["relationships"])
    print(
        "P1 architecture validation PASSED: "
        f"{entity_count} entities, {relationship_count} relationships, "
        "13 decisions, ERD coverage, P1.2 reference artifacts, continuity files, and secret filename checks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
