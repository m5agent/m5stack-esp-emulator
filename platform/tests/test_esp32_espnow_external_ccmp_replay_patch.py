"""Contract checks for external ESP-NOW CCMP replay rejection."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0078-esp32-espnow-external-ccmp-replay.patch"
)
PREVIOUS_PATCH = (
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


class Esp32EspNowExternalCcmpReplayPatchTests(unittest.TestCase):
    def test_replay_state_is_controller_local(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "bool espnow_peer_rx_pn_valid;",
            "uint64_t espnow_peer_last_rx_pn;",
            "s->espnow_peer_rx_pn_valid = false;",
            "s->espnow_peer_last_rx_pn = 0;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertGreaterEqual(
            text.count("s->espnow_peer_rx_pn_valid = false;"),
            2,
        )

    def test_equal_or_older_authenticated_pn_is_dropped(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "s->espnow_peer_rx_pn_valid &&",
            "pn <= s->espnow_peer_last_rx_pn",
            '"[espnow-peer] RX drop: CCMP PN replay\\n"',
            "s->espnow_peer_rx_pn_valid = true;",
            "s->espnow_peer_last_rx_pn = pn;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        replay = text.index("pn <= s->espnow_peer_last_rx_pn")
        update = text.index("s->espnow_peer_last_rx_pn = pn;")
        self.assertLess(replay, update)

    def test_unauthenticated_frame_cannot_advance_counter(self):
        text = "\n".join(
            (
                added_lines(PREVIOUS_PATCH.read_text()),
                added_lines(PATCH.read_text()),
            )
        )
        validation = text.index(
            "[espnow-peer] RX drop: encrypted CCMP validation failed"
        )
        replay = text.index("pn <= s->espnow_peer_last_rx_pn")
        self.assertLess(validation, replay)
        self.assertIn("continue;", text[validation:replay])

    def test_runner_replays_a_real_forwarded_datagram(self):
        runner = (
            ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"
        ).read_text()
        for marker in (
            "class ReplayProxy:",
            '"replay"',
            "self._right_socket.sendto(data, self._right_service)",
            "self._forwarded[\"left_to_right\"] >= 2",
            "self._forwarded[\"right_to_left\"] > 0",
            "self._replay_sent = True",
            '"replay_drops"',
            "RX drop: CCMP PN replay",
            'args.scenario != "replay"',
            'proxy_stats["replay_sent"] is True',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_scope_is_single_peer_replay_only(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("single external ESP-NOW peer", text)
        self.assertIn("not a multi-peer replay", text)
        self.assertIn("key-rotation lifecycle", text)


if __name__ == "__main__":
    unittest.main()
