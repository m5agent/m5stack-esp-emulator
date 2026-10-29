"""Contract checks for stock ESP-NOW per-peer LMK routing."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0082-esp32-espnow-per-peer-key-routing.patch"
)
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowPerPeerKeyPatchTests(unittest.TestCase):
    def test_stock_key_metadata_is_captured(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "ESP32_WIFI_CRYPTO_KEY_META_LENGTH 8",
            "espnow_crypto_key_meta[",
            "espnow_crypto_key_meta_written[",
            "s->espnow_crypto_key_meta[slot][slot_offset]",
            "s->espnow_crypto_key_meta_written[slot] == 0xff",
            "Stock hal_crypto_set_key_entry stores the peer MAC",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_peer_mac_selects_guest_key_slot(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "espnow_peer_guest_key_slot_for_peer(",
            "s->espnow_peer_fabric || !peer",
            "memcmp(s->espnow_crypto_key_meta[slot], peer, 6)",
            "s, frame->receiver_address, key, &guest_slot",
            "s, frame.transmitter_address, key, &guest_slot",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_tx_pn_is_scoped_to_peer_key_slot(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "espnow_peer_guest_tx_pn[ESP32_WIFI_CRYPTO_KEY_SLOTS]",
            "++s->espnow_peer_guest_tx_pn[guest_slot]",
            "s->espnow_peer_guest_tx_pn[slot] = 0",
            "memset(s->espnow_peer_guest_tx_pn, 0,",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_runner_covers_pairwise_keys_and_cross_wire_negative(self):
        runner = RUNNER.read_text()
        for marker in (
            "PEER_LMKS = __PEER_LMKS__",
            "lmk=PEER_LMKS[peer_role]",
            '"fabric-per-peer-key"',
            '"fabric-per-peer-key-negative"',
            'role_lmks["B"]["A"] = pair_lmks[frozenset(("B", "C"))]',
            'expected_links["A-B"] = False',
            "return expected_links[link_name(role, peer)]",
            '"pairwise LMK"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_scope_is_guest_controller_keys_not_host_fixture(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("peer MAC in entry bytes 0..5", text)
        self.assertIn("per-peer LMK routing", text)
        runner = RUNNER.read_text()
        self.assertIn('"pairwise LMK; role B/A intentionally cross-wired"', runner)


if __name__ == "__main__":
    unittest.main()
