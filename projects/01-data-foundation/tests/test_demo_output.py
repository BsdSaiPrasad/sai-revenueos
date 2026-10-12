"""Command-line acceptance tests for the P1.3 and P1.4 demonstrations."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SCRIPTS = PROJECT / "scripts"


class DemonstrationOutputTests(unittest.TestCase):
    """Keep default output concise while preserving complete verbose evidence."""

    def run_demo(self, script: str, *arguments: str) -> list[str]:
        """Run one demonstration exactly as a learner or CI would run it."""
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *arguments],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("", completed.stderr)
        return completed.stdout.splitlines()

    def test_p13_default_is_a_complete_summary_with_at_most_15_lines(self) -> None:
        """The source demo summarizes input, state changes, replay, failure, and deletion."""
        lines = self.run_demo("demo_source_model.py")
        output = "\n".join(lines)
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 15)
        for phrase in (
            "Input:", "Before:", "First process:", "Identity decision:", "Repeat:",
            "Simulated failure:", "Retry:", "Deletion:", "After deletion:", "Outcome:",
        ):
            self.assertIn(phrase, output)
        self.assertIn("overlap=300s", output)

    def test_p13_verbose_preserves_complete_technical_evidence(self) -> None:
        """Verbose mode retains the original event, recovery, tombstone, and replay detail."""
        lines = self.run_demo("demo_source_model.py", "--overlap-seconds", "120", "--verbose")
        output = "\n".join(lines)
        self.assertGreater(len(lines), 15)
        for heading in (
            "ACTUAL INPUT", "AFTER FIRST PROCESS", "REPEAT SAME EVENT", "SIMULATED FAILURE",
            "RETRY AFTER FAILURE", "SOURCE DELETION TOMBSTONE", "NEXT REPLAY WINDOW",
        ):
            self.assertIn(heading, output)
        self.assertIn('"overlap_seconds": 120', output)

    def test_p14_default_is_a_complete_summary_with_at_most_15_lines(self) -> None:
        """The authority demo summarizes values, conflicts, decisions, and write outcomes."""
        lines = self.run_demo("demo_field_authority.py")
        output = "\n".join(lines)
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 15)
        for phrase in (
            "Input:", "Before:", "Salesforce first value:", "Repeat:",
            "HubSpot conflict:", "Conflict decision:", "Salesforce conflict:",
            "Review decision:", "Automatic write-back:", "Steward write-back:",
            "After:", "Outcome:",
        ):
            self.assertIn(phrase, output)

    def test_p14_verbose_preserves_review_and_audit_evidence(self) -> None:
        """Verbose mode retains the alternate human decision and full audit-oriented output."""
        lines = self.run_demo(
            "demo_field_authority.py", "--salesforce-decision", "keep_current", "--verbose"
        )
        output = "\n".join(lines)
        self.assertGreater(len(lines), 15)
        for heading in (
            "ACTUAL INPUT", "AUTHORITATIVE SALESFORCE VALUE + SAFE REPLAY",
            "HUBSPOT CONFLICT", "HUMAN REVIEW DECISIONS",
            "CONTROLLED WRITE-BACK EVALUATION", "AFTER",
        ):
            self.assertIn(heading, output)
        self.assertIn('"action": "rejected"', output)
        self.assertIn('"proposed_value": "customer"', output)
        self.assertIn('"value": "prospect"', output)

    def test_p15_default_is_a_complete_summary_with_at_most_15_lines(self) -> None:
        """The data demo summarizes counts, relationships, issues, decisions, and outcomes."""
        lines = self.run_demo("demo_synthetic_data.py")
        output = "\n".join(lines)
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 15)
        for phrase in (
            "Generated:", "Source events:", "Relationships:", "History:",
            "Quality issues:", "Identity decision:", "Field conflict:",
            "Authority outcome:", "Expected identity:", "Outcome:",
        ):
            self.assertIn(phrase, output)

    def test_p15_verbose_preserves_records_and_contract_evidence(self) -> None:
        """Verbose mode exposes generated inputs, standardized values, and expected outcomes."""
        lines = self.run_demo("demo_synthetic_data.py", "--companies", "3", "--seed", "7", "--verbose")
        output = "\n".join(lines)
        self.assertGreater(len(lines), 15)
        for heading in (
            "GENERATED FILES", "GLOBEX CANONICAL FIXTURE", "SALESFORCE INPUT",
            "HUBSPOT INPUT", "STANDARDIZED SOURCE VALUES", "P1.2 IDENTITY CASES",
            "P1.4 AUTHORITY EVALUATION", "EXPECTED IDENTITY OUTCOMES", "SCENARIO MANIFEST",
        ):
            self.assertIn(heading, output)


if __name__ == "__main__":
    unittest.main()
