import struct
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from device_service import parse_qemu_wifi_execution
from device_service_errors import ServiceError
from device_service_softap_peer import (
    ACL_OPERATION,
    PROVISION_ACL_OPERATION,
    PROFILE,
    STICKS3_PORTAL_PROFILE,
    STICKS3_PROVISION_PROFILE,
    STICKS3_PROFILE,
    PortalStationPeer,
    SoftAPPeer,
    _SAVE_MARKERS,
    _SAVE_REQUEST,
    _portal_http_body,
    require_softap_backend,
)
from network_fabric import _internet_checksum
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

    def test_sticks3_portal_profile_disallows_overrides(self):
        sticks = SimpleNamespace(id="sticks3", backend="qemu-esp32s3")
        selected = parse_qemu_wifi_execution(sticks, {"profile": STICKS3_PORTAL_PROFILE})
        self.assertEqual(selected["profile"], STICKS3_PORTAL_PROFILE)
        self.assertEqual(selected["net_mode"], "unix-socketpair")
        self.assertTrue(selected["capture_pcap"])
        self.assertFalse(selected["http_fixture"])
        for key in ("ssid", "path", "hostfwd", "policy"):
            with self.subTest(key=key), self.assertRaises(ServiceError) as raised:
                parse_qemu_wifi_execution(sticks, {"profile": STICKS3_PORTAL_PROFILE, key: "custom"})
            self.assertEqual(raised.exception.code, "invalid_network")
        other = SimpleNamespace(id="cardputer-adv", backend="qemu-esp32s3")
        with self.assertRaises(ServiceError) as raised:
            parse_qemu_wifi_execution(other, {"profile": STICKS3_PORTAL_PROFILE})
        self.assertEqual(raised.exception.code, "unsupported_network_profile")

    def test_portal_backend_requires_both_properties(self):
        with patch("device_service_softap_peer.subprocess.run") as run:
            run.return_value.stdout = "  open-softap-peer=<bool> - (default: false)"
            with self.assertRaises(ServiceError) as raised:
                require_softap_backend(Path("qemu"), portal=True)
            self.assertEqual(raised.exception.code, "softap_fixture_backend_unavailable")
            run.return_value.stdout += "\n  open-softap-sticks3-portal=<bool> - (default: false)"
            require_softap_backend(Path("qemu"), portal=True)

    def test_provisioning_requires_separate_grant_and_backend_property(self):
        sticks = SimpleNamespace(id="sticks3", backend="qemu-esp32s3")
        config = parse_qemu_wifi_execution(sticks, {"profile": STICKS3_PROVISION_PROFILE})
        self.assertEqual((config["wifi_ssid"], config["wifi_auth"]), ("fixturetest", "open"))
        for key in ("wifi_ssid", "path", "password", "hostfwd", "policy"):
            with self.subTest(key=key), self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(sticks, {"profile": STICKS3_PROVISION_PROFILE, key: "custom"})
        policy = RuntimeACL.from_document({"schema_version": 1, "devices": {
            "sticks3": {"allow": [ACL_OPERATION]},
        }})
        with self.assertRaises(RuntimeACLError):
            policy.check("sticks3", PROVISION_ACL_OPERATION)
        with patch("device_service_softap_peer.subprocess.run") as run:
            run.return_value.stdout = "open-softap-peer=<bool>\nopen-softap-sticks3-portal=<bool>\n"
            with self.assertRaises(ServiceError):
                require_softap_backend(Path("qemu"), station=True)
            run.return_value.stdout += "open-softap-sticks3-station=<bool>\n"
            require_softap_backend(Path("qemu"), station=True)

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

    def test_provisioned_reset_drains_old_frames_and_skips_portal(self):
        receipts = []
        peer = PortalStationPeer("02:00:00:00:00:01", "02:00:00:00:00:02", receipts.append)
        self.addCleanup(peer.close)
        peer.start()
        peer.invalidate_for_reset()
        peer._station_proven = True
        peer._input.extend(b"incomplete old frame")
        peer.child.sendall(b"obsolete socket bytes")
        delivered = Event()
        with patch.object(peer, "_await_station", side_effect=delivered.set):
            peer.start(capture_start_offset=2048)
            self.assertTrue(delivered.wait(2))
            self.assertFalse(peer._input)
            self.assertEqual(receipts[-1]["generation"], 2)
            self.assertTrue(receipts[-1]["station_reconnect"])
            self.assertEqual(receipts[-1]["capture_start_offset"], 2048)
            self.assertFalse(receipts[-1]["save_http"])
            self.assertIsNone(receipts[-1]["station_dhcp_xid"])
            peer.close()

class SoftAPPortalResponseTests(unittest.TestCase):
    def test_dropped_syn_retries_connection_before_sending_form_once(self):
        peer = SoftAPPeer("02:00:00:00:00:01", lambda receipt: None, portal=True)
        self.addCleanup(peer.close)
        lease, server = bytes([192, 168, 4, 2]), bytes([192, 168, 4, 1])
        gateway = bytes.fromhex("020000000005")
        body = b"Saving Credentials. Trying to connect ESP to network"
        response = (
            b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(body)).encode() + b"\r\n\r\n" + body
        )

        def packet(seq, ack, flags, data=b""):
            tcp = bytearray(struct.pack("!HHIIBBHHH", 80, 49152, seq, ack, 0x50, flags, 8192, 0, 0) + data)
            pseudo = server + lease + struct.pack("!BBH", 0, 6, len(tcp))
            struct.pack_into("!H", tcp, 16, _internet_checksum(pseudo + tcp))
            return peer.mac + gateway + b"\x08\0" + peer._ipv4(server, lease, 6, bytes(tcp))

        frames = [TimeoutError, packet(10, 8, 0x12), packet(11, 8 + len(_SAVE_REQUEST), 0x18, response)]
        with (
            patch("device_service_softap_peer.secrets.randbelow", return_value=0),
            patch("device_service_softap_peer.secrets.randbits", return_value=7),
            patch.object(peer, "_next_frame", side_effect=frames),
            patch.object(peer, "_send") as send,
        ):
            self.assertEqual(peer._http(lease, server, gateway, _SAVE_REQUEST, markers=_SAVE_MARKERS), body)
        packets = [call.args[0] for call in send.call_args_list]
        self.assertEqual(packets[:2], [packets[0]] * 2)
        self.assertEqual([frame[54:] for frame in packets if frame[54:]], [_SAVE_REQUEST])

    def test_requires_complete_expected_html(self):
        body = b"<h3>StickS3-Setup</h3><form action='/wifi'></form>"
        header = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=UTF-8\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
        )
        self.assertIsNone(_portal_http_body(header[:12]))
        self.assertIsNone(_portal_http_body(header + body[:-1]))
        self.assertEqual(_portal_http_body(header + body), body)
        for response in (
            header.replace(b"200 OK", b"302 Found") + body,
            header.replace(b"text/html", b"text/plain") + body,
            header + body + b"extra",
            header + body.replace(b"/wifi", b"/none"),
            header.replace(b"Content-Length:", b"Transfer-Encoding: chunked\r\nContent-Length:") + body,
            header.replace(b"Content-Length:", b"Content-Length: 1\r\nContent-Length:") + body,
            header.replace(str(len(body)).encode(), b"99999") + body,
            b"X" * 2049,
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                _portal_http_body(response)
