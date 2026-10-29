"""Contract checks for guest-programmed external ESP-NOW controller keys."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0080-esp32-espnow-guest-key-state.patch"
)
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowGuestKeyPatchTests(unittest.TestCase):
    def test_patch_maps_both_crypto_windows(self):
        text = PATCH.read_text()
        for marker in (
            "ESP32_WIFI_CRYPTO_CONTROL_BASE  0x3ff73800",
            "ESP32_WIFI_CRYPTO_KEY_BASE      0x3ff74400",
            "ESP32S3_WIFI_CRYPTO_CONTROL_BASE 0x60033800",
            "ESP32S3_WIFI_CRYPTO_KEY_BASE    0x60034400",
            "sysbus_mmio_get_region(sbd, 1)",
            "sysbus_mmio_get_region(sbd, 2)",
            "sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 1)",
            "sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 2)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_key_slot_tracks_all_25_extended_entries(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "ESP32_WIFI_CRYPTO_KEY_SIZE      0x3e8",
            "ESP32_WIFI_CRYPTO_KEY_SLOTS     25",
            "ESP32_WIFI_CRYPTO_KEY_STRIDE    40",
            "slot_offset == ESP32_WIFI_CRYPTO_KEY_OFFSET",
            "s->espnow_crypto_key_written[slot] == 0xffff",
            "slot >= ESP32_WIFI_CRYPTO_KEY_SLOTS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_guest_key_requires_controller_valid_bit(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "uint32_t valid = s->espnow_crypto_control[0x14 / 4];",
            "(valid & (1u << slot))",
            "s->espnow_peer_use_guest_key = true;",
            "s->espnow_peer_guest_key_valid = true;",
            "memcpy(s->espnow_peer_guest_lmk, key, 16);",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_replacement_and_clear_reset_replay_state(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "static void espnow_peer_clear_guest_key(",
            "s->espnow_peer_tx_pn = 0;",
            "s->espnow_peer_rx_pn_valid = false;",
            "s->espnow_peer_rx_pn_bitmap = 0;",
            "memset(s->espnow_crypto_key_bytes, 0,",
            "memset(s->espnow_crypto_key_written, 0,",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_bridge_uses_guest_lmk_without_plaintext_logging(self):
        text = added_lines(PATCH.read_text())
        block = PATCH.read_text().split(
            "static bool espnow_peer_unwrap_lmk", 1
        )[1].split("static bool espnow_peer_encrypt_guest_frame", 1)[0]
        self.assertIn(
            "memcpy(lmk, s->espnow_peer_guest_lmk, 16);",
            block,
        )
        self.assertIn("guest-key state=ready slot=%u", text)
        self.assertNotIn("espnow_peer_guest_lmk[%", text)
        self.assertNotIn("guest-key", block)

    def test_runner_omits_runtime_env_keys_for_guest_key_cases(self):
        runner = RUNNER.read_text()
        for marker in (
            '"guest-key",',
            '"guest-key-wrong-lmk",',
            '"guest-key-rotation",',
            "if encrypt and not guest_key:",
            '"M5SW_ESPNOW_PEER_PMK": pmk.hex(),',
            '"guest-controller-key-store"',
            "result[\"trace\"][\"guest_key_ready\"]",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_runner_rotates_the_guest_lmk_after_readd(self):
        runner = RUNNER.read_text()
        for marker in (
            "ROTATED_LMK = __ROTATED_LMK__",
            "node.add_peer(PEER_MAC, lmk=LMK",
            "node.mod_peer(PEER_MAC, lmk=ROTATED_LMK",
            "rotated_lmk = b\"fedcba9876543211\"",
            ">= (2 if args.scenario == \"guest-key-rotation\" else 1)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)


if __name__ == "__main__":
    unittest.main()
