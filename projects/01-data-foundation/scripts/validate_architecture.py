#!/usr/bin/env python3
"""Validate P1 architecture and reference artifacts without external packages.

This script checks the shared JavaScript Object Notation (JSON) contract, canonical
Entity Relationship Diagram (ERD), Architecture Decision Records (ADRs), required
P1.2 through P1.9 artifacts, schema enforcement names, continuity documents, and
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
LIVE_GUIDE_PATH = PROJECT_DIR / "architecture/LIVE_INGESTION.md"
LIVE_POLICY_PATH = PROJECT_DIR / "contracts/live-ingestion-policy.v1.json"
LIVE_PACKAGE_DIR = PROJECT_DIR / "src/sai_revenueos_connectors"
LIVE_TEST_PATH = PROJECT_DIR / "tests/test_live_connectors.py"
LIVE_DEMO_PATH = PROJECT_DIR / "scripts/demo_live_ingestion.py"
LIVE_RUNNER_PATH = PROJECT_DIR / "scripts/run_live_ingestion.py"
LIVE_AUTH_PATH = PROJECT_DIR / "scripts/configure_live_auth.py"
WAREHOUSE_GUIDE_PATH = PROJECT_DIR / "architecture/SNOWFLAKE_DBT.md"
WAREHOUSE_POLICY_PATH = PROJECT_DIR / "contracts/warehouse-normalization-policy.v1.json"
WAREHOUSE_PACKAGE_DIR = PROJECT_DIR / "src/sai_revenueos_warehouse"
WAREHOUSE_TEST_PATH = PROJECT_DIR / "tests/test_warehouse_staging.py"
WAREHOUSE_LOADER_PATH = PROJECT_DIR / "scripts/load_source_events_to_snowflake.py"
WAREHOUSE_DEMO_PATH = PROJECT_DIR / "scripts/demo_snowflake_dbt.py"
WAREHOUSE_FAILURE_DEMO_PATH = PROJECT_DIR / "scripts/demo_dbt_failure.py"
WAREHOUSE_VALIDATOR_PATH = PROJECT_DIR / "scripts/validate_dbt_project.py"
WAREHOUSE_DBT_DIR = PROJECT_DIR / "warehouse/dbt"
WAREHOUSE_BOOTSTRAP_PATH = PROJECT_DIR / "warehouse/snowflake/bootstrap.sql"
RESOLUTION_GUIDE_PATH = PROJECT_DIR / "architecture/IDENTITY_RESOLUTION.md"
RESOLUTION_POLICY_PATH = PROJECT_DIR / "contracts/identity-resolution-policy.v1.json"
RESOLUTION_OUTPUT_PATH = PROJECT_DIR / "contracts/identity-resolution-output.v1.json"
RESOLUTION_PACKAGE_DIR = PROJECT_DIR / "src/sai_revenueos_resolution"
RESOLUTION_TEST_PATH = PROJECT_DIR / "tests/test_identity_resolution.py"
RESOLUTION_DEMO_PATH = PROJECT_DIR / "scripts/demo_identity_resolution.py"
RESOLUTION_SNOWFLAKE_PATH = PROJECT_DIR / "scripts/verify_identity_resolution_snowflake.py"
CANONICAL_POLICY_PATH = PROJECT_DIR / "contracts/canonical-warehouse-models.v1.json"
CANONICAL_PACKAGE_DIR = PROJECT_DIR / "src/sai_revenueos_canonical"
CANONICAL_TEST_PATH = PROJECT_DIR / "tests/test_canonical_models.py"
CANONICAL_DEMO_PATH = PROJECT_DIR / "scripts/demo_canonical_models.py"
CANONICAL_PREPARE_PATH = PROJECT_DIR / "scripts/prepare_p19_globex_approval.py"
CANONICAL_PUBLISH_PATH = PROJECT_DIR / "scripts/publish_identity_mappings_to_snowflake.py"
CANONICAL_DBT_DIR = WAREHOUSE_DBT_DIR / "models/canonical"
DECISION_COUNT = 47

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


def validate_p16_reference(errors: list[str]) -> None:
    """Check P1.6 connectors, policy, tests, authentication helper, guide, and demo."""
    required = (
        LIVE_GUIDE_PATH,
        LIVE_POLICY_PATH,
        LIVE_PACKAGE_DIR / "__init__.py",
        LIVE_PACKAGE_DIR / "http.py",
        LIVE_PACKAGE_DIR / "models.py",
        LIVE_PACKAGE_DIR / "runner.py",
        LIVE_PACKAGE_DIR / "salesforce.py",
        LIVE_PACKAGE_DIR / "hubspot.py",
        LIVE_TEST_PATH,
        LIVE_DEMO_PATH,
        LIVE_RUNNER_PATH,
        LIVE_AUTH_PATH,
    )
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.6 reference artifacts: {', '.join(missing)}")
        return
    try:
        policy = json.loads(LIVE_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.6 ingestion policy cannot be loaded: {exc}")
        return
    if policy.get("contract_version") != "1.0.0":
        fail(errors, "P1.6 ingestion policy must declare version 1.0.0")
    connectors = policy.get("connectors", {})
    if set(connectors) != {"salesforce", "hubspot"}:
        fail(errors, "P1.6 policy must define Salesforce and HubSpot connectors")
    if connectors.get("salesforce", {}).get("objects") != ["Account", "Lead", "Contact", "Opportunity"]:
        fail(errors, "P1.6 Salesforce objects do not match the approved P1.3 boundary")
    if connectors.get("hubspot", {}).get("objects") != ["Company", "Contact", "Deal"]:
        fail(errors, "P1.6 HubSpot objects do not match the approved P1.3 boundary")
    reliability = policy.get("reliability", {})
    for rule in (
        "honor_retry_after", "checkpoint_after_durable_processing_only",
        "deterministic_event_ids", "stop_failed_stream_before_checkpoint_gap",
    ):
        if reliability.get(rule) is not True:
            fail(errors, f"P1.6 reliability rule must remain enabled: {rule}")
    boundaries = policy.get("boundaries", {})
    if any(value is not False for value in boundaries.values()):
        fail(errors, "P1.6 deferred boundaries must remain disabled")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    if "generated-data/" not in gitignore:
        fail(errors, "P1.6 local credentials and databases are not excluded by generated-data/")


def validate_p17_reference(errors: list[str]) -> None:
    """Check P1.7 Snowflake loader, dbt project, tests, policy, guide, and demos."""
    required = (
        WAREHOUSE_GUIDE_PATH,
        WAREHOUSE_POLICY_PATH,
        WAREHOUSE_PACKAGE_DIR / "__init__.py",
        WAREHOUSE_PACKAGE_DIR / "connection.py",
        WAREHOUSE_PACKAGE_DIR / "loader.py",
        WAREHOUSE_TEST_PATH,
        WAREHOUSE_LOADER_PATH,
        WAREHOUSE_DEMO_PATH,
        WAREHOUSE_FAILURE_DEMO_PATH,
        WAREHOUSE_VALIDATOR_PATH,
        WAREHOUSE_BOOTSTRAP_PATH,
        WAREHOUSE_DBT_DIR / "dbt_project.yml",
        WAREHOUSE_DBT_DIR / "profiles.yml",
        WAREHOUSE_DBT_DIR / "models/sources.yml",
        WAREHOUSE_DBT_DIR / "models/staging/staging.yml",
        WAREHOUSE_DBT_DIR / "models/staging/shared/stg_source_events.sql",
        WAREHOUSE_DBT_DIR / "models/staging/shared/stg_crm_companies.sql",
        WAREHOUSE_DBT_DIR / "models/staging/shared/stg_crm_people.sql",
        WAREHOUSE_DBT_DIR / "seeds/p17_invalid_globex.csv",
    )
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.7 reference artifacts: {', '.join(missing)}")
        return
    try:
        policy = json.loads(WAREHOUSE_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.7 warehouse policy cannot be loaded: {exc}")
        return
    if policy.get("contract_version") != "1.0.0":
        fail(errors, "P1.7 warehouse policy must declare version 1.0.0")
    platform = policy.get("platform", {})
    if platform.get("warehouse") != "snowflake" or platform.get("transformation") != "dbt-core":
        fail(errors, "P1.7 must use Snowflake and dbt Core")
    if platform.get("local_substitute_allowed") is not False:
        fail(errors, "P1.7 cannot permit a local warehouse substitute")
    objects = policy.get("staging", {}).get("essential_objects", {})
    if objects.get("salesforce") != ["Account", "Lead", "Contact", "Opportunity"]:
        fail(errors, "P1.7 Salesforce staging objects do not match P1.3")
    if objects.get("hubspot") != ["Company", "Contact", "Deal"]:
        fail(errors, "P1.7 HubSpot staging objects do not match P1.3")
    safeguards = policy.get("cost_safeguards", {})
    if safeguards.get("warehouse_size") != "XSMALL" or safeguards.get("auto_suspend_seconds") != 60:
        fail(errors, "P1.7 X-Small warehouse and 60-second auto-suspend must remain configured")
    if safeguards.get("max_cluster_count") != 1 or safeguards.get("monthly_credit_quota") != 1:
        fail(errors, "P1.7 cluster and monthly credit caps must remain configured")
    completion = policy.get("completion_gate", {})
    if not all(completion.values()):
        fail(errors, "P1.7 completion must require static, authenticated, query, and failure evidence")
    if any(value is not False for value in policy.get("boundaries", {}).values()):
        fail(errors, "P1.7 deferred boundaries must remain disabled")
    expected_models = {
        "stg_salesforce_accounts.sql", "stg_salesforce_leads.sql",
        "stg_salesforce_contacts.sql", "stg_salesforce_opportunities.sql",
        "stg_hubspot_companies.sql", "stg_hubspot_contacts.sql", "stg_hubspot_deals.sql",
    }
    found_models = {path.name for path in (WAREHOUSE_DBT_DIR / "models/staging").rglob("*.sql")}
    if not expected_models.issubset(found_models):
        fail(errors, "P1.7 dbt project does not cover every P1.3 source object")
    bootstrap = WAREHOUSE_BOOTSTRAP_PATH.read_text(encoding="utf-8").upper()
    for safeguard in ("WAREHOUSE_SIZE = XSMALL", "AUTO_SUSPEND = 60", "CREDIT_QUOTA = 1"):
        if safeguard not in bootstrap:
            fail(errors, f"P1.7 Snowflake bootstrap is missing safeguard: {safeguard}")


def validate_p18_reference(errors: list[str]) -> None:
    """Check P1.8 matching, manual review, survivorship, and P1.7 integration."""
    required = (
        RESOLUTION_GUIDE_PATH,
        RESOLUTION_POLICY_PATH,
        RESOLUTION_OUTPUT_PATH,
        RESOLUTION_PACKAGE_DIR / "__init__.py",
        RESOLUTION_PACKAGE_DIR / "matcher.py",
        RESOLUTION_PACKAGE_DIR / "normalization.py",
        RESOLUTION_PACKAGE_DIR / "policy.py",
        RESOLUTION_PACKAGE_DIR / "schema.sql",
        RESOLUTION_PACKAGE_DIR / "service.py",
        RESOLUTION_PACKAGE_DIR / "staging.py",
        RESOLUTION_PACKAGE_DIR / "store.py",
        RESOLUTION_TEST_PATH,
        RESOLUTION_DEMO_PATH,
        RESOLUTION_SNOWFLAKE_PATH,
        WAREHOUSE_DBT_DIR / "models/staging/shared/stg_crm_people.sql",
    )
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(errors, f"missing P1.8 reference artifacts: {', '.join(missing)}")
        return
    try:
        policy = json.loads(RESOLUTION_POLICY_PATH.read_text(encoding="utf-8"))
        output = json.loads(RESOLUTION_OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.8 contracts cannot be loaded: {exc}")
        return
    if policy.get("contract_version") != "1.0.0":
        fail(errors, "P1.8 resolution policy must declare version 1.0.0")
    if set(policy.get("matching", {})) != {"Account", "Person"}:
        fail(errors, "P1.8 matching must remain limited to Account and Person")
    decision = policy.get("decision_policy", {})
    if not decision.get("human_approval_required_for_every_new_crosswalk"):
        fail(errors, "P1.8 must require human approval for every new crosswalk")
    if decision.get("automatic_merge") or decision.get("automatic_crosswalk_activation"):
        fail(errors, "P1.8 cannot automatically merge or activate identities")
    survivorship = policy.get("survivorship", {})
    if survivorship.get("authority_contract") != "field-authority-policy.v1.json":
        fail(errors, "P1.8 survivorship must reuse the P1.4 authority contract")
    if survivorship.get("matching_score_selects_field_value"):
        fail(errors, "P1.8 match scores cannot select canonical field values")
    if output.get("properties", {}).get("mapping_status", {}).get("const") == "proposed":
        fail(errors, "P1.8 output cannot publish proposed mappings")
    output_text = RESOLUTION_OUTPUT_PATH.read_text(encoding="utf-8")
    if '"mapping_status": {"const": "active"}' not in output_text:
        fail(errors, "P1.8 output contract must publish active mappings only")
    staging_text = (RESOLUTION_PACKAGE_DIR / "staging.py").read_text(encoding="utf-8")
    if "STG_CRM_COMPANIES" not in staging_text or "STG_CRM_PEOPLE" not in staging_text:
        fail(errors, "P1.8 is not connected to both P1.7 identity staging views")


def validate_p19_reference(errors: list[str]) -> None:
    """Check approved identity, governed values, history, and dbt publication."""
    required = (
        CANONICAL_POLICY_PATH,
        CANONICAL_PACKAGE_DIR / "__init__.py",
        CANONICAL_PACKAGE_DIR / "publisher.py",
        CANONICAL_TEST_PATH,
        CANONICAL_DEMO_PATH,
        CANONICAL_PREPARE_PATH,
        CANONICAL_PUBLISH_PATH,
        CANONICAL_DBT_DIR / "canonical.yml",
    )
    expected_models = {
        "int_active_identity_mappings.sql",
        "canonical_identity_crosswalks.sql",
        "canonical_accounts.sql",
        "canonical_people.sql",
        "canonical_account_source_history.sql",
        "canonical_person_source_history.sql",
        "canonical_field_conflict_evidence.sql",
        "unresolved_identity_records.sql",
        "resolved_person_account_relationship_inputs.sql",
        "canonical_opportunity_inputs.sql",
    }
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    found_models = {path.name for path in CANONICAL_DBT_DIR.glob("*.sql")}
    missing_models = sorted(expected_models - found_models)
    if missing or missing_models:
        fail(errors, "missing P1.9 artifacts: %s" % ", ".join(missing + missing_models))
        return
    try:
        policy = json.loads(CANONICAL_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"P1.9 canonical contract cannot be loaded: {exc}")
        return
    if policy.get("contract_version") != "1.0.0":
        fail(errors, "P1.9 canonical contract must declare version 1.0.0")
    identity = policy.get("identity_input", {})
    if identity.get("accepted_mapping_status") != "active" or identity.get("automatic_merge"):
        fail(errors, "P1.9 must consume active approved mappings without automatic merge")
    if set(identity.get("approved_entity_types", [])) != {"Account", "Person"}:
        fail(errors, "P1.9 canonical identity scope must remain Account and Person")
    authority = policy.get("authority_input", {})
    if authority.get("invent_unowned_field_authority") is not False:
        fail(errors, "P1.9 cannot invent field owners outside P1.4")
    history = policy.get("history_policy", {})
    for rule in ("preserve_all_staged_versions", "preserve_deletions", "preserve_late_arrivals"):
        if history.get(rule) is not True:
            fail(errors, f"P1.9 history policy must keep {rule}")
    boundaries = policy.get("downstream_boundary", {})
    if boundaries.get("p1_10_implemented") or boundaries.get("live_write_back"):
        fail(errors, "P1.9 cannot implement P1.10 or live write-back")
    account_sql = (CANONICAL_DBT_DIR / "canonical_accounts.sql").read_text(encoding="utf-8")
    if "source_system = 'salesforce'" not in account_sql:
        fail(errors, "P1.9 Account lifecycle must reuse Salesforce P1.4 authority")
    if "cast(null as varchar) as governed_account_name" not in account_sql:
        fail(errors, "P1.9 cannot promote an unowned Account name")
    opportunity_sql = (CANONICAL_DBT_DIR / "canonical_opportunity_inputs.sql").read_text(encoding="utf-8")
    if "cast(null as varchar) as opportunity_id" not in opportunity_sql:
        fail(errors, "P1.9 cannot invent canonical Opportunity IDs")


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
    validate_p16_reference(errors)
    validate_p17_reference(errors)
    validate_p18_reference(errors)
    validate_p19_reference(errors)
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
        f"{DECISION_COUNT} decisions, ERD coverage, P1.2–P1.9 reference artifacts, "
        "continuity files, and secret filename checks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
