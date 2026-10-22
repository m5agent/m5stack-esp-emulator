#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from qemu_network_preflight import has_slirp_define, has_user_netdev  # noqa: E402


class QemuNetworkPreflightTests(unittest.TestCase):
    def test_accepts_enabled_slirp_define(self):
        self.assertTrue(has_slirp_define("#define CONFIG_SLIRP\n"))
        self.assertTrue(has_slirp_define("#define CONFIG_SLIRP 1\n"))

    def test_rejects_undef_or_similar_symbol(self):
        self.assertFalse(has_slirp_define("#undef CONFIG_SLIRP\n"))
        self.assertFalse(has_slirp_define("#define CONFIG_SLIRP_DISABLED\n"))

    def test_detects_user_netdev_without_prefix_false_positives(self):
        help_text = (
            "Available netdev backend types:\n"
            "socket\n"
            "user\n"
            "vhost-user\n"
        )
        self.assertTrue(has_user_netdev(help_text))
        self.assertFalse(has_user_netdev("vhost-user\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
