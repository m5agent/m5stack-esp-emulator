"""Contract checks for fail-closed ESP-NOW CCMP PN exhaustion."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0083-esp32-espnow-ccmp-pn-exhaustion.patch"
)
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowCcmpPnExhaustionPatchTests(unittest.TestCase):
    def test_48_bit_pn_is_not_wrapped(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "ESPNOW_PEER_CCMP_PN_MAX         0xffffffffffffULL",
            "if (*pn_counter >= ESPNOW_PEER_CCMP_PN_MAX)",
            '"[espnow-peer] TX drop: CCMP PN exhausted\\n"',
            "pn = ++*pn_counter;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_seed_applies_once_before_rekey(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "M5SW_ESPNOW_PEER_TX_PN_START",
            "espnow_peer_guest_tx_pn_seed_consumed[slot]",
            "s->espnow_peer_guest_tx_pn_seed_consumed[guest_slot] = true",
            "s->espnow_peer_guest_tx_pn[slot] =",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_runner_burns_pn_then_rekeys_and_resumes(self):
        runner = RUNNER.read_text()
        for marker in (
            '"guest-key-pn-rekey"',
            '"guest-key-pn-stale-rekey"',
            "GUEST_KEY_PN_REKEY_SOURCE",
            "for _ in range(128):",
            'node.send(PEER_MAC, ("BURN:" + ROLE).encode(), False)',
            "node.mod_peer(",
            'api="fabric_pn_rekey"',
            'api="fabric_pn_post"',
            'runtime_env["M5SW_ESPNOW_PEER_TX_PN_START"]',
            '"pn_exhaustions": text.count(',
            '"same guest LMK rejected after CCMP PN exhaustion"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_service_validates_seed_without_claiming_hardware(self):
        service = (ROOT / "platform/tools/device_service.py").read_text()
        for marker in (
            '"M5SW_ESPNOW_PEER_TX_PN_START"',
            "must fit in 48 bits",
            "external ESP-NOW peer bridge and a decimal CCMP PN",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)
        text = " ".join(PATCH.read_text().split())
        self.assertIn("allow a new guest LMK installation", text)
        self.assertNotIn("hardware PASS", text)


if __name__ == "__main__":
    unittest.main()
