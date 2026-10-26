#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsContractBase(unittest.TestCase):
    def _assert_recorded_tool_hash(self, group: str, relative: str, expected: str) -> None:
        """Audit immutable evidence against its pinned source, not today's code.

        Missing history fails explicitly. In particular, do not silently accept a
        changed source tree or overwrite a historical run's hashes to turn green.
        """
        provenance = json.loads((
            ROOT / "platform/tests/fixtures/historical_tool_provenance.json"
        ).read_text())
        commit = provenance["groups"][group]["source_snapshot_commit"]
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        result = subprocess.run(
            ["git", "cat-file", "blob", f"{commit}:{relative}"],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            f"historical source unavailable: {commit}:{relative}; "
            "fetch repository history before running evidence contracts",
        )
        self.assertEqual(hashlib.sha256(result.stdout).hexdigest(), expected)

    def _platform_test_count(self) -> int:
        suite = unittest.TestLoader().discover(
            str(ROOT / "platform" / "tests"),
            pattern="test_*.py",
        )
        return suite.countTestCases()
