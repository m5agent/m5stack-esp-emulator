"""Contract checks for the independent-guest ESP-NOW peer bridge."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0076-esp32-external-espnow-peer-bridge.patch"
)


class Esp32EspNowExternalPeerPatchTests(unittest.TestCase):
    def test_bridge_is_default_off_and_limited_to_action_frames(self):
        text = PATCH.read_text()
        required = (
            'getenv("M5SW_ESPNOW_PEER_LOCAL_PORT")',
            'getenv("M5SW_ESPNOW_PEER_REMOTE_PORT")',
            "if (!local_value && !remote_value) {",
            "frame->frame_control.type == IEEE80211_TYPE_MGT",
            "frame->frame_control.sub_type ==",
            "IEEE80211_TYPE_MGT_SUBTYPE_ACTION",
            "length >= IEEE80211_HEADER_SIZE",
            "length <= sizeof(*frame)",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_bridge_uses_normal_controller_tx_and_rx_data_planes(self):
        text = PATCH.read_text()
        self.assertIn("Esp32_ESPNow_peer_send(s, &frame);", text)
        self.assertEqual(text.count("Esp32_ESPNow_peer_send(s, &frame);"), 2)
        self.assertIn(
            "Esp32_sendFrame(s, &frame, length, -42);",
            text,
        )
        self.assertIn(
            "espnow_peer_trace(s, \"TX\", &forwarded, forwarded.frame_length);",
            text,
        )
        self.assertIn(
            "espnow_peer_trace(s, \"RX\", &frame, length);",
            text,
        )
        self.assertIn(
            "memcpy(forwarded.transmitter_address, s->macaddr,",
            text,
        )
        self.assertIn("!memcmp(filter0, zero_mac, sizeof(zero_mac))", text)
        self.assertIn("pkt->damatch1=1;", text)
        self.assertIn("pkt->bssidmatch1=1;", text)

    def test_peer_socket_is_loopback_only_and_cleaned_up(self):
        text = PATCH.read_text()
        self.assertGreaterEqual(
            text.count(".sin_addr.s_addr = htonl(INADDR_LOOPBACK)"),
            2,
        )
        self.assertIn("SOCK_DGRAM", text)
        self.assertIn("qemu_set_fd_handler(fd, espnow_peer_read, NULL, s);", text)
        self.assertIn(
            "qemu_set_fd_handler(s->espnow_peer_fd, NULL, NULL, NULL);",
            text,
        )
        self.assertEqual(text.count("dc->unrealize ="), 2)

    def test_bridge_rejects_mixed_loopback_and_invalid_port_pair(self):
        text = PATCH.read_text()
        self.assertIn(
            '"M5SW_ESPNOW_LOOPBACK cannot be combined with the "',
            text,
        )
        self.assertIn("local_port < 1024 || local_port > 65535", text)
        self.assertIn("remote_port < 1024 || remote_port > 65535", text)
        self.assertIn("local_port == remote_port", text)

    def test_service_and_runner_expose_only_plaintext_external_lane(self):
        text = PATCH.read_text()
        service = (ROOT / "platform/tools/device_service.py").read_text()
        runner = (ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py").read_text()
        for marker in (
            "M5SW_ESPNOW_PEER_LOCAL_PORT",
            "M5SW_ESPNOW_PEER_REMOTE_PORT",
            "M5SW_ESPNOW_PEER_TRACE",
            "set_esp32_efuse_mac",
            '"qemu-esp32lx6"',
        ):
            self.assertIn(marker, service)
        self.assertIn('choices=("plaintext",)', runner)
        self.assertIn("encrypt=False", runner)
        self.assertIn('"encryption": False', runner)
        self.assertIn('api="external_payload"', runner)
        self.assertIn('PEER_MAC = b"\\x02\\x00\\x00\\x00\\x00\\x43"', runner)
        self.assertNotIn('kind == "DISCOVERED"', runner)
        self.assertNotIn("encrypt=True", runner)
        self.assertNotIn("correct-pmk", runner)
        self.assertNotIn("[espnow-peer-data]", text)

    def test_patch_does_not_claim_encryption_or_rf(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("unencrypted external-guest", text)
        self.assertIn("does not model PMK/LMK encryption, CCMP", text)
        self.assertIn("loss/retry, RF, antenna or timing", text)
        self.assertNotIn("M5SW_ESPNOW_LMK", text)


if __name__ == "__main__":
    unittest.main()
