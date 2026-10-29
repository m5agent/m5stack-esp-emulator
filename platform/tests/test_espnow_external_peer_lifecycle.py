"""Contract checks for the external ESP-NOW peer lifecycle scenario."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/api_sweep/run_espnow_pair.py"


class EspNowExternalPeerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.runner = RUNNER.read_text()

    def test_lifecycle_uses_documented_native_espnow_methods(self):
        for marker in (
            "node.set_pmk(PMK)",
            "node.add_peer(PEER_MAC, lmk=LMK",
            "node.add_peer(PEER_MAC, lmk=LMK, channel=0",
            "node.del_peer(PEER_MAC)",
            "node.mod_peer(PEER_MAC, lmk=LMK, channel=0",
            "node.get_peer(PEER_MAC)",
            "list(node.peer_count())",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)

    def test_delete_is_checked_before_readd(self):
        text = self.runner.split("LIFECYCLE_SOURCE = r'''", 1)[1].split(
            "'''", 1
        )[0]
        deleted = text.index("node.del_peer(PEER_MAC)")
        rejected = text.index("node.send(PEER_MAC, b\"AFTER_DELETE\"")
        readded = text.index(
            "node.add_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, "
            "encrypt=True)",
            rejected,
        )
        self.assertLess(deleted, rejected)
        self.assertLess(rejected, readded)
        block = text[deleted:readded]
        self.assertIn("deleted_count == [0, 0]", text)
        self.assertIn("get_peer_not_found", block)
        self.assertIn("send_rejected", block)

    def test_modify_and_post_readd_delivery_are_required(self):
        for marker in (
            "node.mod_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, "
            "encrypt=True)",
            "modified = (",
            'b"POST", b"POST:" + other_role.encode(), 12000',
            "row.get(\"readded_count\") == [1, 1]",
            "row.get(\"modified\") is True",
            "row.get(\"post_resumed\") is True",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)

    def test_lifecycle_is_a_separate_encrypted_scenario(self):
        for marker in (
            '"replay",',
            '"lifecycle",',
            'args.scenario == "lifecycle"',
            "parse_lifecycle_records(serial)",
            "external_peer_lifecycle",
            "ESPNOW_LIFECYCLE_DONE ",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)


if __name__ == "__main__":
    unittest.main()
