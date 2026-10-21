#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
from symbolize_core2_panic import extract_addresses


class Core2PanicSymbolizerTests(unittest.TestCase):
    def test_extracts_pc_and_backtrace_without_duplicates(self):
        log = """
Guru Meditation Error: Core 0 panic'ed
PC      : 0x40081234  PS      : 0x00060030
Backtrace:0x40081235:0x3ffb1234 0x40081234:0x3ffb1250
"""
        self.assertEqual(
            extract_addresses(log),
            ["0x40081234", "0x40081235", "0x3ffb1234", "0x3ffb1250"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
