"""Contract checks for key-bound CCMP on the external ESP-NOW bridge."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0077-esp32-espnow-external-ccmp.patch"
)


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowExternalCcmpPatchTests(unittest.TestCase):
    def test_patch_extends_existing_external_bridge(self):
        text = PATCH.read_text()
        for marker in (
            "espnow_peer_encrypted",
            "espnow_peer_pmk[16]",
            "espnow_peer_wrapped_lmk[16]",
            "espnow_peer_tx_pn",
            "Esp32_WLAN_ccmp_encrypt_payload",
            "Esp32_WLAN_ccmp_decrypt_payload",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_pmk_wraps_lmk_without_retaining_plaintext_key(self):
        text = added_lines(PATCH.read_text())
        self.assertIn(
            "static bool espnow_peer_unwrap_lmk(Esp32WifiState *s, "
            "uint8_t lmk[16])",
            text,
        )
        self.assertIn(
            "espnow_peer_aes_ecb(\n"
            "                    s->espnow_peer_pmk, true, lmk,",
            text,
        )
        self.assertIn(
            "s->espnow_peer_wrapped_lmk, unwrapped",
            text,
        )
        self.assertIn("memcmp(lmk, unwrapped, sizeof(lmk))", text)
        self.assertIn("memset(lmk, 0, sizeof(lmk));", text)
        self.assertNotIn("espnow_peer_lmk[16]", text)
        self.assertNotIn("espnow_peer_plaintext_lmk", text)

    def test_tx_replaces_guest_envelope_with_key_bound_ccmp(self):
        text = added_lines(PATCH.read_text())
        function = text.split(
            "static bool espnow_peer_encrypt_guest_frame", 1
        )[1].split("static bool espnow_peer_ccmp_pn", 1)[0]
        self.assertIn(
            "memmove(frame->data_and_fcs, frame->data_and_fcs + 8, "
            "plain_length);",
            function,
        )
        self.assertIn(
            "Esp32_WLAN_ccmp_encrypt_payload(\n"
            "        key, frame, ++s->espnow_peer_tx_pn",
            function,
        )
        self.assertIn("memset(key, 0, sizeof(key));", function)

    def test_rx_drops_authentication_failure_before_guest_dma(self):
        text = added_lines(PATCH.read_text())
        block = text.split("if (s->espnow_peer_encrypted)", 1)[1].split(
            "frame.frame_length = length;", 1
        )[0]
        self.assertIn("Esp32_WLAN_ccmp_decrypt_payload", block)
        self.assertIn(
            '"[espnow-peer] RX drop: encrypted CCMP validation failed',
            block,
        )
        self.assertIn("continue;", block)
        self.assertNotIn("Esp32_sendFrame", block)

    def test_ccmp_uses_actual_authentication_and_not_a_python_callback(self):
        text = PATCH.read_text()
        for marker in (
            "aes_ccm_encrypt(",
            "aes_ccm_decrypt(",
            "ccmp_header_aad_nonce(header, ccmp, aad, nonce);",
            "ccmp[3] = 0x20;",
            "ccmp + 8 + plain_len",
            "ccmp[3] & 0x40",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertNotIn("python", text.lower())
        self.assertNotIn("recv_callback", text)

    def test_service_keys_are_validated_and_redacted(self):
        service = (ROOT / "platform/tools/device_service.py").read_text()
        for marker in (
            '"M5SW_ESPNOW_PEER_PMK"',
            '"M5SW_ESPNOW_PEER_LMK"',
            "must be set together",
            "require the external peer bridge",
            "must contain exactly 32 hexadecimal",
            "PRIVATE_RUNTIME_ENV",
            "redacted_runtime_env(self.runtime_env)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)

    def test_runner_covers_positive_and_negative_key_cases(self):
        runner = (
            ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"
        ).read_text()
        for marker in (
            '"plaintext",',
            '"encrypted",',
            '"wrong-lmk",',
            '"wrong-pmk",',
            "node.set_pmk(PMK)",
            "node.add_peer(PEER_MAC, lmk=LMK",
            "encrypt=True",
            'args.scenario == "wrong-lmk"',
            'args.scenario == "wrong-pmk"',
            "bytes(value ^ 0xff for value in right_lmk)",
            "expected_drop = args.scenario == \"wrong-lmk\"",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_scope_does_not_claim_key_lifecycle_or_physical_behavior(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("not guest key-state programming", text)
        self.assertIn("replay windows", text)
        self.assertIn("RF, timing or physical hardware", text)


if __name__ == "__main__":
    unittest.main()
