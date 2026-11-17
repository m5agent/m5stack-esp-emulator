import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from device_service import parse_qemu_wifi_execution
from device_service_errors import ServiceError
from device_service_softap_peer import (
    ACL_OPERATION,
    PROFILE,
    STICKS3_PROFILE,
    SoftAPPeer,
    require_softap_backend,
)
from runtime_acl import RuntimeACL, RuntimeACLError


class SoftAPAdmissionTests(unittest.TestCase):
    def test_fixed_profile_and_capture(self):
        spec = SimpleNamespace(id="cardputer", backend="qemu-esp32s3")
        result = parse_qemu_wifi_execution(spec, {"profile": PROFILE})
        self.assertEqual(result["net_mode"], "unix-socketpair")
        self.assertTrue(result["capture_pcap"])
        self.assertFalse(result["http_fixture"])
        for settings in (
            {"capture_pcap": False}, {"net_mode": "user"}, {"http_fixture": True},
            {"policy": {}}, {"wifi_ssid": "alternate"}, {"hostfwd": []},
        ):
            with self.subTest(settings=settings), self.assertRaises(ServiceError) as raised:
                parse_qemu_wifi_execution(spec, {"profile": PROFILE, **settings})
            self.assertEqual(raised.exception.code, "invalid_network")
        other = SimpleNamespace(id="sticks3", backend="qemu-esp32s3")
        with self.assertRaises(ServiceError) as raised:
            parse_qemu_wifi_execution(other, {"profile": PROFILE})
        self.assertEqual(raised.exception.code, "unsupported_network_profile")

    def test_sticks3_profile_uses_same_isolated_transport(self):
        sticks = SimpleNamespace(id="sticks3", backend="qemu-esp32s3")
        admitted = parse_qemu_wifi_execution(sticks, {"profile": STICKS3_PROFILE})
        self.assertEqual(admitted["profile"], STICKS3_PROFILE)
        self.assertEqual(admitted["net_mode"], "unix-socketpair")
        self.assertTrue(admitted["capture_pcap"])
        for payload in (
            {"profile": PROFILE},
            {"profile": [STICKS3_PROFILE]},
            {"profile": STICKS3_PROFILE, "policy": {"egress": "native"}},
        ):
            with self.subTest(payload=payload), self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(sticks, payload)
        cardputer = SimpleNamespace(id="cardputer", backend="qemu-esp32s3")
        with self.assertRaises(ServiceError) as raised:
            parse_qemu_wifi_execution(cardputer, {"profile": STICKS3_PROFILE})
        self.assertEqual(raised.exception.code, "unsupported_network_profile")

    def test_backend_requires_explicit_property(self):
        with patch("device_service_softap_peer.subprocess.run") as run:
            run.return_value.stdout = "  open-softap-peer=<bool> - (default: false)"
            require_softap_backend(Path("qemu"))
            run.return_value.stdout = "  raw-fixture=<bool> - (default: false)"
            with self.assertRaises(ServiceError) as raised:
                require_softap_backend(Path("qemu"))
            self.assertEqual(raised.exception.code, "softap_fixture_backend_unavailable")

    def test_configured_acl_requires_explicit_permission(self):
        policy = RuntimeACL.from_document({"schema_version": 1, "devices": {
            "cardputer": {"allow": [ACL_OPERATION]},
            "cardputer-adv": {"allow": ["guest.reset"]},
        }})
        self.assertEqual(policy.check("cardputer", ACL_OPERATION), policy.policy_id)
        with self.assertRaises(RuntimeACLError):
            policy.check("cardputer-adv", ACL_OPERATION)


class SoftAPPeerLifecycleTests(unittest.TestCase):
    def test_reset_fences_a_generation_and_close_releases_descriptors(self):
        receipts = []
        peer = SoftAPPeer("02:00:00:00:00:01", receipts.append)
        self.addCleanup(peer.close)
        peer.start()
        self.assertEqual(receipts[-1]["generation"], 1)
        peer.invalidate_for_reset()
        self.assertEqual(receipts[-1]["status"], "INTERRUPTED")
        self.assertFalse(receipts[-1]["http"])
        peer.start()
        self.assertEqual(receipts[-1]["generation"], 2)
        peer.close()
        self.assertTrue(receipts[-1]["released"])
        self.assertEqual(peer.child.fileno(), -1)
        with self.assertRaises(RuntimeError):
            peer.start()
