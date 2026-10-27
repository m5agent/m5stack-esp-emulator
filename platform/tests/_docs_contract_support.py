#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsContractBase(unittest.TestCase):
    def _assert_recorded_tool_hash(self, group: str, relative: str, expected: str) -> None:
        """Check a historical digest index, without claiming source verification.

        Ordinary CI needs only the source branch. Full source-blob verification
        is explicit: tests/units/verify_historical_tool_provenance.py fails closed
        when the pinned historical source is unavailable or differs.
        """
        provenance = json.loads((
            ROOT / "platform/tests/fixtures/historical_tool_provenance.json"
        ).read_text())
        record = provenance["groups"][group]
        commit = record["source_snapshot_commit"]
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertEqual(record["storage"], "external")
        self.assertEqual(
            record["source_url"],
            f"https://github.com/m5agent/m5stack-esp-emulator/tree/{commit}",
        )
        self.assertFalse(Path(relative).is_absolute())
        self.assertNotIn("..", Path(relative).parts)
        self.assertRegex(expected, r"^[0-9a-f]{64}$")
        self.assertEqual(record["recorded_tool_hashes"][relative], expected)

    def _platform_test_count(self) -> int:
        suite = unittest.TestLoader().discover(
            str(ROOT / "platform" / "tests"),
            pattern="test_*.py",
        )
        return suite.countTestCases()
