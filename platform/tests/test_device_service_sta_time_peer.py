import socket
import struct
from types import SimpleNamespace
import unittest

from device_service import parse_qemu_wifi_execution
from device_service_errors import ServiceError
from device_service_sta_time_peer import ACL_OPERATION, NTP_SECONDS, PROFILE, StationTimePeer
from network_sandbox import ControlledDns
from runtime_acl import RuntimeACL, RuntimeACLError


class StationTimePeerTests(unittest.TestCase):
    def test_only_fixed_profile_on_native_adv(self):
        adv = SimpleNamespace(id="cardputer-adv", backend="qemu-esp32s3")
        settings = parse_qemu_wifi_execution(adv, {"profile": PROFILE, "withhold_ntp": True})
        self.assertEqual(settings["net_mode"], "unix-socketpair")
        self.assertTrue(settings["capture_pcap"])
        self.assertTrue(settings["withhold_ntp"])
        self.assertEqual(settings["wifi_ssid"], "fixturetest")
        for value in (
            {"wifi_ssid": "external"}, {"policy": {}}, {"hostfwd": []},
            {"http_fixture": True}, {"capture_pcap": False}, {"withhold_ntp": 1},
        ):
            with self.subTest(value=value), self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(adv, {"profile": PROFILE, **value})
        for device in ("cardputer", "sticks3"):
            with self.subTest(device=device), self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(SimpleNamespace(id=device, backend="qemu-esp32s3"), {"profile": PROFILE})

    def test_time_peer_permission_is_separate_from_softap(self):
        policy = RuntimeACL.from_document({"schema_version": 1, "devices": {
            "cardputer-adv": {"allow": ["network.softap.probe"]},
        }})
        with self.assertRaises(RuntimeACLError):
            policy.check("cardputer-adv", ACL_OPERATION)

    def test_fixed_endpoint_and_dns_denial_after_replies(self):
        receipts = []
        peer = StationTimePeer("02:00:00:00:00:02", receipts.append)
        self.addCleanup(peer.close)
        peer.start()
        self.assertEqual(peer.child.family, socket.AF_UNIX)

        def query(name):
            header = bytes.fromhex("456701000001000000000000")
            return header + ControlledDns.encode_name(name) + bytes.fromhex("00010001")

        positive = peer._reply_dns(query("pool.ntp.org"))
        negative = peer._reply_dns(query("unrelated.test"))
        self.assertEqual(positive[2:8], bytes.fromhex("818000010001"))
        self.assertEqual(positive[-4:], socket.inet_aton("10.0.2.2"))
        self.assertEqual(negative[2:8], bytes.fromhex("818300010000"))
        raw = bytearray(48)
        raw[0] = 0x23
        raw[40:48] = b"origin!!"
        reply = peer._reply_ntp(bytes(raw))
        self.assertEqual(reply[24:32], b"origin!!")
        self.assertEqual(struct.unpack_from("!I", reply, 40)[0], NTP_SECONDS)
        self.assertEqual(receipts[-1]["ntp_replies"], 1)
        peer.invalidate_for_reset()
        self.assertEqual(receipts[-1]["ntp_replies"], 0)
        self.assertIsNone(receipts[-1]["last_ntp_response_sha256"])
        peer.start()
        self.assertEqual(receipts[-1]["generation"], 2)
        self.assertFalse(receipts[-1]["dhcp"])
        peer.close()
        self.assertTrue(receipts[-1]["released"])
        self.assertEqual(peer.child.fileno(), -1)

    def test_withholding_response_counts_request_only(self):
        receipts = []
        peer = StationTimePeer("02:00:00:00:00:02", receipts.append, withhold_ntp=True)
        self.addCleanup(peer.close)
        peer.start()
        self.assertIsNone(peer._reply_ntp(bytes([0x23]) + bytes(47)))
        self.assertEqual(receipts[-1]["ntp_requests"], 1)
        self.assertEqual(receipts[-1]["ntp_replies"], 0)
