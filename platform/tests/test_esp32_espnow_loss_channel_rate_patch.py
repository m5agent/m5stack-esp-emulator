"""Contract checks for ESP-NOW loss/retry and channel/rate validation."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0084-esp32-espnow-loss-channel-rate.patch"
)
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"
SERVICE = ROOT / "platform/tools/device_service.py"


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowLossChannelRatePatchTests(unittest.TestCase):
    def test_wire_metadata_records_channel_and_rate(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "typedef struct QEMU_PACKED Esp32EspNowPeerWireHeader",
            "ESPNOW_PEER_WIRE_VERSION",
            "packet.header.channel = s->espnow_peer_channel",
            "packet.header.rate = s->espnow_peer_tx_rate",
            '"[espnow-peer] RX drop: channel mismatch "',
            '"[espnow-peer] delivered channel=%u rate=%u len=%u\\n"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_rx_metadata_uses_wire_channel_and_rate(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            ".rate=s->espnow_peer_rx_rate ? s->espnow_peer_rx_rate : 11",
            ".rate = s->espnow_peer_rx_rate ? s->espnow_peer_rx_rate : 11",
            ".channel=s->espnow_peer_rx_channel",
            ".channel = s->espnow_peer_rx_channel",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_runner_covers_loss_channel_and_rate_paths(self):
        runner = RUNNER.read_text()
        for marker in (
            "class LossProxy:",
            "receiver = bytes(frame[4:10])",
            '"loss-retry"',
            '"channel-match"',
            '"channel-mismatch"',
            '"rate-mixed"',
            '"soak"',
            "SOAK_SOURCE",
            "ESPNOW_SOAK_DONE",
            "row.get(\"duplicate_payloads\") == 0",
            "proxy_stats[\"dropped\"][\"left_to_right\"] == 2",
            '"channel_drops": text.count(',
            '"tx_channel_rates": [',
            '"delivered_channel_rates": [',
            'peer_channels = {"A": 6, "B": 6}',
            'peer_rates = {"A": 11, "B": 24}',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_service_rejects_orphan_and_unsupported_values(self):
        service = SERVICE.read_text()
        for marker in (
            '"M5SW_ESPNOW_PEER_CHANNEL"',
            '"M5SW_ESPNOW_PEER_TX_RATE"',
            "ESPNOW_PEER_TX_RATES = frozenset({",
            "requires the external ",
            "an integer from 1 to 14",
            "a supported 802.11 Mbps ",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)

    def test_scope_is_virtual_link_metadata(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("bounded fault proxy", text)
        self.assertIn("does not model RF propagation", text)
        self.assertIn("does not prove physical controller", text)


if __name__ == "__main__":
    unittest.main()
