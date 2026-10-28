"""Contract checks for the opt-in ESP-NOW controller loopback fixture."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0067-esp32-espnow-controlled-peer-loopback.patch"
)


class Esp32EspNowLoopbackPatchTests(unittest.TestCase):
    def test_loopback_is_explicit_and_limited_to_management_action_frames(self):
        text = PATCH.read_text()
        required = (
            'getenv("M5SW_ESPNOW_LOOPBACK")',
            "frame->frame_control.type != IEEE80211_TYPE_MGT",
            "frame->frame_control.sub_type != "
            "IEEE80211_TYPE_MGT_SUBTYPE_ACTION",
            "frame->frame_length < IEEE80211_HEADER_SIZE",
            "frame->frame_length > sizeof(frame->data_and_fcs)",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_echo_uses_controller_tx_and_rx_paths(self):
        text = PATCH.read_text()
        self.assertIn(
            "memcpy(echo->receiver_address, source, sizeof(source));",
            text,
        )
        self.assertIn(
            "broadcast ? loopback_peer : frame->receiver_address",
            text,
        )
        self.assertIn(
            "Esp32_sendFrame(s, echo, echo->frame_length, -42);",
            text,
        )
        self.assertIn(
            "Esp32_S3_sendFrame(s, echo, echo->frame_length, -42);",
            text,
        )
        self.assertEqual(
            text.count("Esp32_WLAN_handle_frame(s, &frame);"),
            2,
        )
        self.assertEqual(
            text.count("esp32_wifi_loopback_espnow(s, &frame);"),
            1,
        )
        self.assertEqual(
            text.count("esp32s3_wifi_loopback_espnow(s, &frame);"),
            1,
        )

    def test_service_and_runner_share_the_explicit_gate(self):
        service = (ROOT / "platform/tools/device_service.py").read_text()
        runner = (ROOT / "tests/uiflow2/api_sweep/run_protocols.py").read_text()
        self.assertIn('"M5SW_ESPNOW_LOOPBACK"', service)
        self.assertIn(
            'runtime_env.get("M5SW_ESPNOW_LOOPBACK")',
            runner,
        )
        self.assertIn(
            '"scope":"controller DMA TX to same-guest RX DMA echo; '
            'not an external ESP-NOW peer"',
            runner,
        )


if __name__ == "__main__":
    unittest.main()
