"""Contract checks for the three-guest ESP-NOW fabric bridge."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0081-esp32-espnow-peer-fabric.patch"
)
PATCH_CHAIN = [
    "0076-esp32-external-espnow-peer-bridge.patch",
    "0077-esp32-espnow-external-ccmp.patch",
    "0078-esp32-espnow-external-ccmp-replay.patch",
    "0079-esp32-espnow-external-ccmp-window.patch",
    "0080-esp32-espnow-guest-key-state.patch",
    "0081-esp32-espnow-peer-fabric.patch",
]
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def patch_hunk(text: str, marker: str) -> str:
    hunks = re.split(r"(?m)^@@.*\n", text)[1:]
    return next(hunk for hunk in hunks if marker in hunk)


def hunk_after(text: str, marker: str) -> str:
    return "\n".join(
        line[1:] if line.startswith(("+", " ")) else line
        for line in patch_hunk(text, marker).splitlines()
        if not line.startswith("-")
    )


def hunk_added(text: str, marker: str) -> str:
    return "\n".join(
        line[1:]
        for line in patch_hunk(text, marker).splitlines()
        if line.startswith("+")
    )


class Esp32EspNowPeerFabricPatchTests(unittest.TestCase):
    def test_replay_window_is_keyed_by_source_peer(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "Esp32EspNowPeerReplayState",
            "espnow_peer_replay[ESPNOW_PEER_REPLAY_SLOTS]",
            "state->valid && !memcmp(state->peer, peer, 6)",
            "memcpy(free_state->peer, peer, 6);",
            "s, frame.transmitter_address, pn",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_mic_validation_precedes_peer_window(self):
        text = "\n".join(
            added_lines(
                (
                    ROOT
                    / "patches/qemu-m5stack-peripherals"
                    / patch_name
                ).read_text()
            )
            for patch_name in PATCH_CHAIN
        )
        decrypt = text.index("Esp32_WLAN_ccmp_decrypt_payload")
        accept = text.index("espnow_peer_accept_rx_pn(\n                    s, frame.transmitter_address")
        self.assertLess(decrypt, accept)
        self.assertIn(
            '"[espnow-peer] RX drop: CCMP PN replay\\n"',
            text,
        )

    def test_each_reset_path_clears_all_peer_windows(self):
        text = added_lines(PATCH.read_text())
        self.assertIn(
            "memset(s->espnow_peer_replay, 0,",
            text,
        )
        self.assertGreaterEqual(
            text.count("espnow_peer_reset_replay(s);"),
            4,
        )

    def test_public_mac_is_used_before_ccmp_and_preserved_on_rx(self):
        patch = PATCH.read_text()
        send = hunk_after(
            patch,
            "memcpy(&forwarded, frame, sizeof(forwarded));",
        )
        self.assertIn("s->espnow_peer_public_mac_valid", send)
        self.assertIn("s->espnow_peer_public_mac", send)
        self.assertIn("espnow_peer_encrypt_guest_frame", send)
        self.assertNotIn(
            "memcpy(forwarded.transmitter_address,\n"
            "                   (uint8_t[]){0x02, 0, 0, 0, 0, 0x43}, 6);",
            send,
        )
        self.assertNotIn(
            "memcpy(frame.transmitter_address",
            hunk_added(
                patch,
                "if (s->espnow_peer_fabric) {",
            ),
        )
        receive = hunk_after(
            patch,
            "if (s->espnow_peer_fabric) {",
        )
        self.assertIn(
            "memcpy(frame.receiver_address, local_mac, 6);",
            receive,
        )

    def test_service_gates_fabric_and_synthetic_identity(self):
        service = (ROOT / "platform/tools/device_service.py").read_text()
        for marker in (
            '"M5SW_ESPNOW_PEER_FABRIC"',
            '"M5SW_ESPNOW_PEER_PUBLIC_MAC"',
            "M5SW_ESPNOW_PEER_FABRIC requires the external",
            "M5SW_ESPNOW_PEER_PUBLIC_MAC requires the ",
            "ESP-NOW peer fabric and exactly 12 hexadecimal ",
            "PRIVATE_RUNTIME_ENV",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)

    def test_runner_builds_three_guest_fabric(self):
        runner = RUNNER.read_text()
        for marker in (
            "THREE_PEER_SOURCE",
            "class PeerFabric:",
            '"fabric",',
            '"fabric-replay",',
            'runtime_env["M5SW_ESPNOW_PEER_FABRIC"] = "1"',
            '"M5SW_ESPNOW_PEER_PUBLIC_MAC"',
            "peer_count == [len(PEER_MACS), len(PEER_MACS)]",
            "node.send(peer_mac, (\"READY:\" + ROLE).encode(), False)",
            "self._duplicate_sent = True",
            "results_by_role[\"B\"][\"trace\"][\"replay_drops\"] == 1",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_scope_is_shared_lmk_and_not_multi_key_routing(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("shared-LMK test lane", text)
        runner = RUNNER.read_text()
        self.assertIn(
            "shared LMK; per-peer key routing NOT RUN",
            runner,
        )


if __name__ == "__main__":
    unittest.main()
