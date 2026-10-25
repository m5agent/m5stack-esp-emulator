#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsContractBase(unittest.TestCase):
    def _platform_test_count(self) -> int:
        suite = unittest.TestLoader().discover(
            str(ROOT / "platform" / "tests"),
            pattern="test_*.py",
        )
        return suite.countTestCases()
