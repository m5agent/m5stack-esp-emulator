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
            "node.mod_peer(PEER_MAC, lmk=ROTATED_LMK, channel=0",
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
            "node.mod_peer(PEER_MAC, lmk=ROTATED_LMK, channel=0, ifidx=0, "
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
            "native_lifecycle = args.scenario in {",
            "parse_lifecycle_records(serial)",
            "external_peer_lifecycle",
            "ESPNOW_LIFECYCLE_DONE ",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)

    def test_m5espnow_wrapper_uses_documented_api(self):
        for marker in (
            "M5ESPNOW_LIFECYCLE_SOURCE",
            "from m5espnow import M5ESPNow",
            "node = M5ESPNow(0)",
            "node.set_pmk_encrypt(PMK)",
            "node.set_add_peer(PEER_MAC_HEX, 1, 0, True, LMK)",
            "node.set_delete_peer(1)",
            "node.get_peer_list(1)",
            "node.send_data(1, own)",
            "node.recv_data(timeout_ms)",
            "node.deinit()",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)

    def test_m5espnow_requires_empty_delete_and_restored_peer_list(self):
        for marker in (
            "deleted_peer_list_empty=deleted_peers == []",
            "send_after_delete_noop = True",
            "peer_list_restored = (",
            "row.get(\"deleted_peer_list_empty\") is True",
            "row.get(\"send_after_delete_noop\") is True",
            "row.get(\"peer_list_restored\") is True",
            '"external_peer_lifecycle_m5espnow"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner)


if __name__ == "__main__":
    unittest.main()
