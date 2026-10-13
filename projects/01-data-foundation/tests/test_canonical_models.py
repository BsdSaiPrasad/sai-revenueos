"""Acceptance scenarios for P1.9 canonical warehouse models."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_canonical import (  # noqa: E402
    IdentityMappingPublisher,
    PublicationConflictError,
)


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.result: Optional[Tuple[Any, ...]] = None

    def execute(self, sql: str, parameters: Tuple[Any, ...] = ()) -> None:
        self.connection.sql.append(sql)
        if sql.startswith("SELECT MAPPING_SET_SHA256"):
            self.result = self.connection.publications.get(str(parameters[0]))
        elif "INSERT INTO" in sql and "MAPPING_SET_SHA256" in sql:
            publication_id, _, digest, _, count = parameters
            self.connection.publications[str(publication_id)] = (str(digest), int(count))

    def executemany(self, sql: str, rows: List[Tuple[Any, ...]]) -> None:
        self.connection.sql.append(sql)
        self.connection.mapping_rows.extend(rows)

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self.result

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.publications: Dict[str, Tuple[str, int]] = {}
        self.mapping_rows: List[Tuple[Any, ...]] = []
        self.sql: List[str] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _output(status: str = "active") -> Dict[str, Any]:
    return {
        "contract_name": "identity-resolution-output",
        "contract_version": "1.0.0",
        "generated_at": "2026-10-13T23:00:00Z",
        "mappings": [{
            "external_identity_crosswalk_id": "sai_xid_0199",
            "source_record_id": "sai_src_0199",
            "canonical_entity_type": "Account",
            "canonical_entity_id": "sai_acc_0199",
            "mapping_status": status,
            "mapping_method": "deterministic_feature_evidence",
            "confidence": 1.0,
            "valid_from": "2026-10-13T23:00:00Z",
            "valid_to": None,
            "reviewed_by": "sarah-kim",
            "reviewed_at": "2026-10-13T23:00:00Z"
        }],
    }


class CanonicalModelTests(unittest.TestCase):
    """Protect the approved-only, governed, history-preserving P1.9 boundary."""

    def test_01_publication_is_idempotent(self) -> None:
        """An unchanged P1.8 mapping set creates one Snowflake publication."""
        connection = _Connection()
        publisher = IdentityMappingPublisher(connection)
        first = publisher.publish(_output())
        second = publisher.publish(_output())
        self.assertTrue(first.inserted)
        self.assertTrue(second.replayed)
        self.assertEqual(first.publication_id, second.publication_id)
        self.assertEqual(1, len(connection.publications))
        self.assertEqual(1, len(connection.mapping_rows))

    def test_02_unapproved_mapping_cannot_be_published(self) -> None:
        """Proposed or revoked mappings never reach canonical dbt models."""
        connection = _Connection()
        with self.assertRaises(ValueError):
            IdentityMappingPublisher(connection).publish(_output("proposed"))
        self.assertEqual({}, connection.publications)

    def test_03_conflicting_publication_rolls_back(self) -> None:
        """A corrupted prior publication is rejected instead of overwritten."""
        connection = _Connection()
        publisher = IdentityMappingPublisher(connection)
        first = publisher.publish(_output())
        connection.publications[first.publication_id] = ("different", 1)
        with self.assertRaises(PublicationConflictError):
            publisher.publish(_output())
        self.assertEqual(1, connection.rollbacks)

    def test_04_contract_reuses_p18_and_p14_without_new_owners(self) -> None:
        """The versioned contract accepts active mappings and preserves field authority."""
        path = PROJECT / "contracts/canonical-warehouse-models.v1.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("1.0.0", contract["contract_version"])
        self.assertEqual("active", contract["identity_input"]["accepted_mapping_status"])
        self.assertFalse(contract["identity_input"]["automatic_merge"])
        self.assertFalse(contract["authority_input"]["invent_unowned_field_authority"])
        self.assertEqual(["salesforce"], contract["authority_input"]["implemented_fields"][0]["authoritative_sources"])

    def test_05_canonical_models_cover_identity_history_and_relationship_inputs(self) -> None:
        """P1.9 publishes its nine promised source-neutral model boundaries."""
        models = PROJECT / "warehouse/dbt/models/canonical"
        expected = {
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
        self.assertTrue(expected.issubset({path.name for path in models.glob("*.sql")}))

    def test_06_account_values_use_salesforce_authority(self) -> None:
        """Lifecycle promotion follows P1.4 while source names remain evidence."""
        sql = (PROJECT / "warehouse/dbt/models/canonical/canonical_accounts.sql").read_text()
        self.assertIn("source_system = 'salesforce'", sql)
        self.assertIn("governed_account_name", sql)
        self.assertIn("cast(null as varchar) as governed_account_name", sql)
        conflict = (PROJECT / "warehouse/dbt/models/canonical/canonical_field_conflict_evidence.sql").read_text()
        self.assertIn("competing_value", conflict)
        self.assertIn("open_evidence", conflict)

    def test_07_opportunities_do_not_receive_invented_canonical_ids(self) -> None:
        """Account links can resolve while Opportunity stays explicitly unresolved."""
        sql = (PROJECT / "warehouse/dbt/models/canonical/canonical_opportunity_inputs.sql").read_text()
        self.assertIn("cast(null as varchar) as opportunity_id", sql)
        self.assertIn("unresolved_opportunity", sql)
        self.assertIn("account_mapping.canonical_entity_id as primary_account_id", sql)

    def test_08_demo_summary_is_complete_and_concise(self) -> None:
        """The default real-data walkthrough stays within the 10–15 line limit."""
        script = PROJECT / "scripts/demo_canonical_models.py"
        spec = importlib.util.spec_from_file_location("demo_canonical_models", script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        result = {
            "sources": [
                {"source_system": "salesforce", "source_object_id": "SF-1"},
                {"source_system": "hubspot", "source_object_id": "HS-1"},
            ],
            "account": {"account_id": "sai_acc_1", "lifecycle_status": "customer"},
            "conflicts": [{"field_name": "lifecycle_status"}],
            "history_count": 4,
            "unresolved": {"source_object_id": "SF-UNRESOLVED"},
            "publication_count": 1,
        }
        lines = module.summary_lines(result)
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 15)
        self.assertTrue(any("canonical ID" in line for line in lines))
        self.assertTrue(any("Unresolved" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
