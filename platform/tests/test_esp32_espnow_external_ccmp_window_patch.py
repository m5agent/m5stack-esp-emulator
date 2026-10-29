"""Contract checks for the external ESP-NOW CCMP replay window."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0079-esp32-espnow-external-ccmp-window.patch"
)


def added_lines(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


class Esp32EspNowExternalCcmpWindowPatchTests(unittest.TestCase):
    def test_window_state_is_controller_local(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "uint64_t espnow_peer_rx_pn_bitmap;",
            "s->espnow_peer_rx_pn_bitmap = 0;",
            "static bool espnow_peer_accept_rx_pn(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertGreaterEqual(
            text.count("s->espnow_peer_rx_pn_bitmap = 0;"),
            2,
        )

    def test_newer_pn_shifts_a_64_frame_bitmap(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "if (pn > s->espnow_peer_last_rx_pn) {",
            "delta = pn - s->espnow_peer_last_rx_pn;",
            "delta >= 64 ? 0 : s->espnow_peer_rx_pn_bitmap << delta",
            "s->espnow_peer_rx_pn_bitmap |= 1;",
            "s->espnow_peer_last_rx_pn = pn;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_older_pn_must_fall_inside_unseen_window(self):
        text = added_lines(PATCH.read_text())
        for marker in (
            "s->espnow_peer_last_rx_pn - pn >= 64",
            "bit = 1ULL << (s->espnow_peer_last_rx_pn - pn);",
            "if (s->espnow_peer_rx_pn_bitmap & bit) {",
            "s->espnow_peer_rx_pn_bitmap |= bit;",
            "return true;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_authenticated_receive_uses_window(self):
        text = added_lines(PATCH.read_text())
        self.assertIn(
            "if (!espnow_peer_accept_rx_pn(s, pn)) {",
            text,
        )
        self.assertNotIn(
            "pn <= s->espnow_peer_last_rx_pn",
            text,
        )

    def test_runner_reorders_real_forwarded_frames(self):
        runner = (
            ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"
        ).read_text()
        for marker in (
            "class ReorderProxy:",
            '"reorder",',
            "self._held = data",
            "self._right_socket.sendto(data, self._right_service)",
            "self._right_socket.sendto(\n                            self._held, self._right_service\n                        )",
            "self._reordered = True",
            '"reordered": self._reordered',
            "proxy_stats[\"reordered\"] is True",
            "result[\"trace\"][\"replay_drops\"] == 0",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, runner)

    def test_scope_remains_single_peer(self):
        text = " ".join(PATCH.read_text().split())
        self.assertIn("current single external peer", text)
        self.assertIn("Multi-peer replay windows remain separate", text)


if __name__ == "__main__":
    unittest.main()
