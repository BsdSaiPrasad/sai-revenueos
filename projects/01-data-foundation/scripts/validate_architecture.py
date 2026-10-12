#!/usr/bin/env python3
"""Validate P1 architecture and reference artifacts without external packages.

This script checks the shared JavaScript Object Notation (JSON) contract, canonical
Entity Relationship Diagram (ERD), Architecture Decision Records (ADRs), required
P1.2 through P1.5 artifacts, schema enforcement names, continuity documents, and
secret-like filenames. It validates repository consistency; it does not execute
runtime tests or claim that a production service is deployed.
"""

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
SOURCE_GUIDE_PATH = PROJECT_DIR / "architecture/SOURCE_MODEL.md"
SOURCE_SCHEMA_PATH = PROJECT_DIR / "src/sai_revenueos_sources/schema.sql"
SOURCE_TEST_PATH = PROJECT_DIR / "tests/test_source_model.py"
SOURCE_DEMO_PATH = PROJECT_DIR / "scripts/demo_source_model.py"
SOURCE_CONTRACT_DIR = PROJECT_DIR / "contracts"
AUTHORITY_GUIDE_PATH = PROJECT_DIR / "architecture/FIELD_AUTHORITY.md"
AUTHORITY_SCHEMA_PATH = PROJECT_DIR / "src/sai_revenueos_authority/schema.sql"
AUTHORITY_TEST_PATH = PROJECT_DIR / "tests/test_field_authority.py"
AUTHORITY_DEMO_PATH = PROJECT_DIR / "scripts/demo_field_authority.py"
AUTHORITY_POLICY_PATH = PROJECT_DIR / "contracts/field-authority-policy.v1.json"
AUTHORITY_EXAMPLE_PATH = PROJECT_DIR / "examples/p14/globex-field-authority-demo.v1.json"
SYNTHETIC_GUIDE_PATH = PROJECT_DIR / "architecture/SYNTHETIC_DATA.md"
SYNTHETIC_CONTRACT_PATH = PROJECT_DIR / "contracts/synthetic-dataset-manifest.v1.json"
SYNTHETIC_PACKAGE_DIR = PROJECT_DIR / "src/sai_revenueos_synthetic"
SYNTHETIC_TEST_PATH = PROJECT_DIR / "tests/test_synthetic_data.py"
SYNTHETIC_DEMO_PATH = PROJECT_DIR / "scripts/demo_synthetic_data.py"
SYNTHETIC_GENERATOR_PATH = PROJECT_DIR / "scripts/generate_synthetic_gtm_data.py"
DECISION_COUNT = 30

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
    """Collect a validation problem so the user sees all findings in one run."""
    errors.append(message)


def load_contract(errors: list[str]) -> dict:
    """Load the canonical JSON contract or record a readable failure."""
    try:
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"contract cannot be loaded: {exc}")
        return {}


def validate_contract(contract: dict, errors: list[str]) -> None:
    """Check entity definitions, relationships, temporal fields, and P1 invariants."""
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
    """Confirm the canonical Mermaid ERD covers the contract's entities and links."""
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
    """Check that every approved ADR and the project continuity documents are present."""
    missing_files = [name for name in REQUIRED_CONTINUITY_FILES if not (PROJECT_DIR / name).is_file()]
    if missing_files:
        fail(errors, f"missing continuity files: {', '.join(sorted(missing_files))}")

    decisions_path = PROJECT_DIR / "DECISIONS.md"
    if not decisions_path.exists():
        return
    decisions = decisions_path.read_text(encoding="utf-8")
    for number in range(1, DECISION_COUNT + 1):
        decision_id = f"D{number:03d}"
        adr_path = PROJECT_DIR / f"architecture/adr/{number:04d}-"
        if decision_id not in decisions:
            fail(errors, f"DECISIONS.md is missing {decision_id}")
        if not any(adr_path.parent.glob(f"{number:04d}-*.md")):
            fail(errors, f"missing ADR for {decision_id}")


def validate_p12_reference(errors: list[str]) -> None:
    """Check that P1.2 teaching, test, diagram, and schema artifacts remain present."""
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


def validate_p13_reference(errors: list[str]) -> None:
    """Check P1.3 contracts, examples, source schema, tests, guide, and demo."""
    contract_names = (
        "source-event-envelope.v1.json",
        "source-checkpoint.v1.json",
        "salesforce-source.v1.json",
        "hubspot-source.v1.json",
    )
    example_names = (
        "globex-salesforce-account-created.json",
        "globex-salesforce-account-updated.json",
        "globex-salesforce-account-deleted.json",
        "globex-hubspot-company.json",
    )
    required = [
        SOURCE_GUIDE_PATH,
        SOURCE_SCHEMA_PATH,
        SOURCE_TEST_PATH,
        SOURCE_DEMO_PATH,
        *(SOURCE_CONTRACT_DIR / name for name in contract_names),
        *(PROJECT_DIR / "examples/p13" / name for name in example_names),
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.3 reference artifacts: {', '.join(missing)}")
        return

    for name in contract_names:
        path = SOURCE_CONTRACT_DIR / name
        try:
            contract = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(errors, f"P1.3 contract cannot be loaded ({name}): {exc}")
            continue
        serialized = json.dumps(contract, sort_keys=True)
        if "1.0.0" not in serialized:
            fail(errors, f"P1.3 contract does not declare version 1.0.0: {name}")

    schema = SOURCE_SCHEMA_PATH.read_text(encoding="utf-8")
    for table in ("source_event", "source_record_version", "source_current_state", "connector_checkpoint"):
        if f"CREATE TABLE IF NOT EXISTS {table}" not in schema:
            fail(errors, f"P1.3 schema is missing {table}")
    for enforcement in ("source_event_immutable_envelope", "source_event_no_delete", "source_record_version_immutable"):
        if enforcement not in schema:
            fail(errors, f"P1.3 schema is missing enforcement rule {enforcement}")


def validate_p14_reference(contract: dict, errors: list[str]) -> None:
    """Check P1.4 policy, reference schema, tests, guide, example, and demo."""
    required = (
        AUTHORITY_GUIDE_PATH,
        AUTHORITY_SCHEMA_PATH,
        AUTHORITY_TEST_PATH,
        AUTHORITY_DEMO_PATH,
        AUTHORITY_POLICY_PATH,
        AUTHORITY_EXAMPLE_PATH,
    )
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.4 reference artifacts: {', '.join(missing)}")
        return

    try:
        policy = json.loads(AUTHORITY_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.4 authority policy cannot be loaded: {exc}")
        return
    if policy.get("contract_version") != "1.0.0":
        fail(errors, "P1.4 authority policy must declare version 1.0.0")
    if policy.get("default_action") != "deny":
        fail(errors, "P1.4 authority policy must default to deny")
    write_back = policy.get("write_back_policy", {})
    if write_back.get("mode") != "authorization_only" or write_back.get("network_delivery") is not False:
        fail(errors, "P1.4 write-back must remain authorization-only")

    approved_domains = {
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
    domains = policy.get("source_domains", {})
    if domains != approved_domains:
        fail(errors, "P1.4 source domains do not match the approved decision")
    entities = contract.get("entities", {})
    seen_fields = set()
    for field in policy.get("field_policies", []):
        key = (field.get("entity_type"), field.get("field_name"))
        if key in seen_fields:
            fail(errors, f"P1.4 field policy is duplicated: {key}")
        seen_fields.add(key)
        entity = entities.get(key[0], {})
        if key[1] not in entity.get("important_attributes", []):
            fail(errors, f"P1.4 field policy is outside the canonical contract: {key}")
        if field.get("domain") not in domains:
            fail(errors, f"P1.4 field policy uses unknown domain: {key}")
        if not set(field.get("authoritative_sources", [])).issubset(
            set(domains.get(field.get("domain"), []))
        ):
            fail(errors, f"P1.4 field policy uses a source outside its domain: {key}")

    schema = AUTHORITY_SCHEMA_PATH.read_text(encoding="utf-8")
    for table in (
        "canonical_field_state", "field_value_history", "field_conflict",
        "conflict_review_event", "field_change_attempt", "write_back_request",
        "authority_audit_event",
    ):
        if f"CREATE TABLE IF NOT EXISTS {table}" not in schema:
            fail(errors, f"P1.4 schema is missing {table}")
    for enforcement in (
        "field_value_history_immutable", "field_conflict_evidence_immutable",
        "conflict_review_event_immutable", "conflict_review_event_no_delete",
        "field_change_attempt_immutable", "write_back_request_immutable",
        "authority_audit_event_no_delete",
    ):
        if enforcement not in schema:
            fail(errors, f"P1.4 schema is missing enforcement rule {enforcement}")


def validate_p15_reference(errors: list[str]) -> None:
    """Check P1.5 generator, manifest contract, validation, tests, guide, and demo."""
    required = (
        SYNTHETIC_GUIDE_PATH,
        SYNTHETIC_CONTRACT_PATH,
        SYNTHETIC_PACKAGE_DIR / "__init__.py",
        SYNTHETIC_PACKAGE_DIR / "generator.py",
        SYNTHETIC_PACKAGE_DIR / "validation.py",
        SYNTHETIC_PACKAGE_DIR / "writer.py",
        SYNTHETIC_TEST_PATH,
        SYNTHETIC_DEMO_PATH,
        SYNTHETIC_GENERATOR_PATH,
    )
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.5 reference artifacts: {', '.join(missing)}")
        return

    try:
        contract = json.loads(SYNTHETIC_CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.5 manifest contract cannot be loaded: {exc}")
        return
    if contract.get("properties", {}).get("contract_version", {}).get("const") != "1.0.0":
        fail(errors, "P1.5 scenario manifest must declare version 1.0.0")
    required_manifest_fields = {
        "contract_name", "contract_version", "synthetic", "scenario_name", "generator",
        "dataset_fingerprint_sha256", "counts", "quality_issue_counts", "quality_issues",
        "identity_policy", "expected_identity_outcomes", "authority_expectations",
        "boundaries", "files",
    }
    if set(contract.get("required", [])) != required_manifest_fields:
        fail(errors, "P1.5 manifest contract does not require the approved version 1 fields")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    if "generated-data/" not in gitignore:
        fail(errors, "P1.5 generated-data output directory is not ignored")
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "generated-data"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(errors, f"cannot inspect generated P1.5 files: {exc}")
    else:
        if tracked:
            fail(errors, "generated P1.5 bulk data must not be tracked in Git")


def validate_no_tracked_secrets(errors: list[str]) -> None:
    """Flag secret-like filenames among tracked and candidate repository files."""
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
    """Run every architecture check and return a shell-friendly status code."""
    errors: list[str] = []
    contract = load_contract(errors)
    if contract:
        validate_contract(contract, errors)
        validate_erd(contract, errors)
    validate_decisions_and_continuity(errors)
    validate_p12_reference(errors)
    validate_p13_reference(errors)
    validate_p14_reference(contract, errors)
    validate_p15_reference(errors)
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
        f"{DECISION_COUNT} decisions, ERD coverage, P1.2–P1.5 reference artifacts, "
        "continuity files, and secret filename checks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
