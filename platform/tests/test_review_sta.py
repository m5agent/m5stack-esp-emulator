"""Host-side contracts for the portable review-sta profile (#238).

These drive the peer over the same framed Ethernet stream QEMU uses. They
prove request parsing, peer protocol behavior and verdict semantics; guest
execution is covered by tests/network/review_sta_controls.
"""
import socket
import struct
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from device_service_errors import ServiceError  # noqa: E402
from network_fabric import _internet_checksum  # noqa: E402
import review_sta_config as config_mod  # noqa: E402
from review_sta_config import capability, parse_review_sta  # noqa: E402
from review_sta_peer import PEER_MAC, ReviewStaPeer  # noqa: E402
from review_sta_verdict import evaluate, firmware_has_wifi_stack, wifi_auth_events  # noqa: E402

STATION = "02:11:22:33:44:55"
STA = bytes.fromhex(STATION.replace(":", ""))
LEASE = socket.inet_aton("10.0.2.15")
GW = socket.inet_aton("10.0.2.2")
NIC = "misc.esp32s3.wifi"


def _config(**network):
    return parse_review_sta({"profile": "review-sta", **network}, nic=NIC)


def _ip(src, dst, proto, payload):
    header = bytearray(struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), 0, 0, 64, proto, 0, src, dst))
    struct.pack_into("!H", header, 10, _internet_checksum(bytes(header)))
    return bytes(header) + payload


def _udp(src, dst, sport, dport, payload):
    udp = struct.pack("!HHHH", sport, dport, 8 + len(payload), 0) + payload
    return PEER_MAC + STA + b"\x08\x00" + _ip(src, dst, 17, udp)


def _tcp(dport, seq, ack, flags, payload=b"", sport=40000, dst=GW):
    tcp = bytearray(struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 0x50, flags, 8192, 0, 0) + payload)
    pseudo = LEASE + dst + struct.pack("!BBH", 0, 6, len(tcp))
    struct.pack_into("!H", tcp, 16, _internet_checksum(pseudo + bytes(tcp)))
    return PEER_MAC + STA + b"\x08\x00" + _ip(LEASE, dst, 6, bytes(tcp))


def _dhcp(kind, xid=b"\x01\x02\x03\x04", requested=None):
    packet = bytearray(240)
    packet[:4] = b"\x01\x01\x06\x00"
    packet[4:8] = xid
    packet[28:34] = STA
    packet[236:240] = b"\x63\x82\x53\x63"
    options = bytes([53, 1, kind]) + (bytes([50, 4]) + requested if requested else b"") + b"\xff"
    bootp = bytes(packet) + options
    return (b"\xff" * 6 + STA + b"\x08\x00"
            + _ip(b"\0" * 4, b"\xff" * 4, 17, struct.pack("!HHHH", 68, 67, 8 + len(bootp), 0) + bootp))


def _dns_query(name, ident=0x1234):
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0\0\x01\0\x01"
    return struct.pack("!HHHHHH", ident, 0x0100, 1, 0, 0, 0) + q


class PeerHarness:
    """Plays QEMU's side of the framed socketpair."""

    def __init__(self, cfg):
        self.receipts = []
        self.peer = ReviewStaPeer(STATION, cfg, lambda r: self.receipts.append(r))
        self.qemu = self.peer.child
        self.qemu.settimeout(2)
        self.buffer = bytearray()
        self.peer.start()

    def send(self, frame):
        self.qemu.sendall(struct.pack("!I", len(frame)) + frame)

    def recv(self, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.buffer) >= 4:
                size = int.from_bytes(self.buffer[:4], "big")
                if len(self.buffer) >= 4 + size:
                    frame = bytes(self.buffer[4:4 + size])
                    del self.buffer[:4 + size]
                    return frame
            try:
                chunk = self.qemu.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                break
            self.buffer.extend(chunk)
        raise AssertionError("peer did not answer")

    def quiet(self, timeout=0.4):
        try:
            self.recv(timeout)
        except AssertionError:
            return True
        return False

    def lease(self):
        self.send(_dhcp(1))
        offer = self.recv()
        assert offer[42 + 16:42 + 20] == LEASE, offer[58:62]
        self.send(_dhcp(3, requested=LEASE))
        self.recv()

    def tcp_session(self, port, request):
        self.send(_tcp(port, 1000, 0, 0x02))
        synack = self.recv()
        tcp = synack[34:]
        server_seq = struct.unpack_from("!I", tcp, 4)[0]
        flags = tcp[13]
        if flags & 0x04:
            return None
        self.send(_tcp(port, 1001, server_seq + 1, 0x10))
        self.send(_tcp(port, 1001, server_seq + 1, 0x18, request))
        data = bytearray()
        while True:
            try:
                frame = self.recv(1.0)
            except AssertionError:
                break
            seg = frame[34:]
            data.extend(seg[(seg[12] >> 4) * 4:])
            if seg[13] & 0x01:
                break
        return bytes(data)

    def events(self):
        return self.receipts[-1]["events"] if self.receipts else []

    def close(self):
        self.peer.close()


FULL = {
    "security": "wpa2-psk", "password": "review-pass-v1",
    "fixtures": {
        "dns": {"A": {"review.test": "10.0.2.2"}},
        "http": {"routes": [{"method": "GET", "path": "/api/status", "status": 200, "body": "OK"}]},
        "tcp": {"port": 19193, "request_hex": "52455649455700ff", "response_hex": "41434b00ff"},
        "udp": {"port": 19090, "request_hex": "5544500001", "response_hex": "41434b5544500001"},
        "mqtt": {"topics": ["review/#"]},
    },
    "assertions": [
        {"type": "wifi_auth"}, {"type": "dhcp_lease"}, {"type": "dns_query", "name": "review.test"},
        {"type": "http_request", "method": "GET", "path": "/api/status", "status": 200},
        {"type": "tcp_connect", "port": 19193}, {"type": "udp_exchange", "port": 19090},
        {"type": "mqtt_publish", "topic": "review/ctrl"},
    ],
}


class ReviewStaConfigTests(unittest.TestCase):
    def test_defaults_are_open_dhcp_only(self):
        cfg = _config()
        self.assertEqual(cfg["wifi_auth"], "open")
        self.assertEqual(cfg["fixtures"], {"dhcp": True})
        self.assertEqual(cfg["isolation"], "userspace-fixture-only")
        self.assertEqual(cfg["host_egress"], "deny")
        self.assertTrue(cfg["capture_pcap"])

    def test_rejects_non_gateway_dns_answer_and_port_collisions(self):
        with self.assertRaises(ServiceError) as raised:
            _config(fixtures={"dns": {"A": {"evil.test": "8.8.8.8"}}})
        self.assertEqual(raised.exception.code, "fixture_rejected")
        with self.assertRaises(ServiceError) as raised:
            _config(fixtures={"http": {"port": 1883, "routes": [{"path": "/"}]}, "mqtt": True})
        self.assertEqual(raised.exception.code, "fixture_rejected")

    def test_wpa2_requires_passphrase_and_rejects_wpa3(self):
        with self.assertRaises(ServiceError):
            _config(security="wpa2-psk", password="short")
        with self.assertRaises(ServiceError) as raised:
            _config(security="wpa3-sae", password="long-enough")
        self.assertEqual(raised.exception.code, "unsupported_wifi_security")

    def test_assertion_requires_matching_fixture(self):
        with self.assertRaises(ServiceError):
            _config(assertions=[{"type": "http_request"}])

    def test_capability_no_namespace_and_unsupported_board(self):
        spec = SimpleNamespace(id="cardputer", machine="m5cardputer", service_kind="qemu",
                               backend="qemu-esp32s3", supported=True)
        cap = capability(spec, backend_ready=True)
        self.assertEqual(cap["network"], "supported")
        self.assertFalse(cap["review_sta"]["requires_linux_namespace"])
        self.assertEqual(cap["review_sta"]["network_isolation"], "userspace-fixture-only")
        tab5 = SimpleNamespace(id="tab5", machine="", service_kind="tab5", backend="esp-emulator-native",
                               supported=True)
        cap = capability(tab5, backend_ready=True)
        self.assertEqual(cap["network"], "unsupported")
        self.assertIn("lora_peer", cap["external_dependencies"])
        wrong_machine = SimpleNamespace(**{**vars(spec), "machine": "m5stopwatch"})
        self.assertEqual(capability(wrong_machine, backend_ready=True)["network"], "unsupported")


class ReviewStaPeerTests(unittest.TestCase):
    def setUp(self):
        self.h = PeerHarness(_config(**FULL))

    def tearDown(self):
        self.h.close()

    def test_full_fixture_chain_produces_pass_verdict(self):
        h = self.h
        h.lease()
        h.send(_udp(LEASE, GW, 5353, 53, _dns_query("review.test")))
        answer = h.recv()
        self.assertEqual(answer[-4:], GW)
        h.send(_udp(LEASE, GW, 5354, 53, _dns_query("absent.test", 0x2222)))
        self.assertEqual(h.recv()[42 + 3] & 0xF, 3)
        body = h.tcp_session(80, b"GET /api/status HTTP/1.1\r\nHost: review.test\r\nConnection: close\r\n\r\n")
        self.assertIn(b"200 OK", body)
        self.assertTrue(body.endswith(b"\r\n\r\nOK"))
        self.assertEqual(h.tcp_session(19193, bytes.fromhex("52455649455700ff")), bytes.fromhex("41434b00ff"))
        h.send(_udp(LEASE, GW, 5000, 19090, bytes.fromhex("5544500001")))
        self.assertEqual(h.recv()[42:], bytes.fromhex("41434b5544500001"))
        connect = (b"\x10\x1a\x00\x04MQTT\x04\x02\x00\x1e\x00\x0em5-review-ctrl")
        publish = b"\x30\x10\x00\x0breview/ctrlhello"
        reply = h.tcp_session(1883, connect + publish + b"\xe0\x00")
        self.assertTrue(reply.startswith(b"\x20\x02\x00\x00"))
        types = [e["type"] for e in h.events()]
        for kind in ("dhcp_lease", "dns_query", "tcp_connect", "http_request", "tcp_exchange",
                     "udp_exchange", "mqtt_connect", "mqtt_publish"):
            self.assertIn(kind, types)
        trace = "[esp32s3-wifi] WPA: EAPOL 4/4 verified; WPA2-PSK ready\n"
        verdict = evaluate(h.peer._config, h.receipts[-1], stderr_text=trace, capture={},
                           window_closed=False, firmware_wifi_stack=True)
        self.assertEqual(verdict["status"], "PASS", verdict["assertions"])
        self.assertEqual(verdict["data_plane"], "PASS")

    def test_unknown_port_is_refused_and_egress_is_dropped(self):
        h = self.h
        h.lease()
        self.assertIsNone(h.tcp_session(8080, b"x"))
        h.send(_tcp(443, 1, 0, 0x02, dst=socket.inet_aton("93.184.216.34")))
        self.assertTrue(h.quiet())
        codes = {e.get("code") for e in h.events()}
        self.assertIn("tcp_refused", codes)
        self.assertIn("host_egress_denied", codes)
        self.assertGreaterEqual(h.receipts[-1]["dropped_egress_frames"], 1)

    def test_http_unknown_route_is_http_status_failure(self):
        h = self.h
        h.lease()
        body = h.tcp_session(80, b"GET /missing HTTP/1.0\r\n\r\n")
        self.assertIn(b"404", body)
        event = [e for e in h.events() if e["type"] == "http_request"][-1]
        self.assertEqual(event["code"], "http_status")

    def test_event_accepts_kind_field_without_collision(self):
        self.h.peer.event("setup_input", step=0, input_kind="button", kind="button", status="PASS")
        row = self.h.events()[-1]
        self.assertEqual(row["type"], "setup_input")
        self.assertEqual(row["kind"], "button")

    def test_frames_from_other_station_are_ignored(self):
        other = bytearray(_dhcp(1))
        other[6:12] = bytes.fromhex("02aabbccddee")
        self.h.send(bytes(other))
        self.assertTrue(self.h.quiet())


class ReviewStaEnvironmentTests(unittest.TestCase):
    def test_classic_review_sta_enables_shared_wpa_trace(self):
        from device_service_qemu_wifi import apply_qemu_wifi_environment
        env = {}
        apply_qemu_wifi_environment(env, "misc.esp32_wifi", parse_review_sta(
            {"profile": "review-sta", "security": "wpa2-psk", "password": "review-pass-v1"},
            nic="misc.esp32_wifi"))
        self.assertEqual(env["M5SW_S3_WIFI_TRACE"], "1")
        self.assertEqual(env["M5SW_WIFI_AUTH"], "wpa2-psk")
        other = {}
        apply_qemu_wifi_environment(other, "misc.esp32_wifi", {"profile": "core2-openmac",
                                                               "wifi_auth": "wpa2-psk"})
        self.assertNotIn("M5SW_S3_WIFI_TRACE", other)


class ReviewStaVerdictTests(unittest.TestCase):
    def test_wrong_password_is_fail_not_partial(self):
        cfg = _config(security="wpa2-psk", password="review-pass-v1",
                      assertions=[{"type": "wifi_auth"}, {"type": "dhcp_lease"}])
        trace = "[esp32s3-wifi] WPA: EAPOL 2/4 MIC mismatch\n" * 3
        verdict = evaluate(cfg, {"events": []}, stderr_text=trace, capture={},
                           window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertEqual(verdict["failure_codes"][0], "wifi_auth_failed")
        self.assertEqual(verdict["events"][0]["attempts"], 3)

    def test_no_activity_is_partial_with_stack_and_not_used_without(self):
        cfg = _config()
        partial = evaluate(cfg, {"events": []}, stderr_text="", capture={},
                           window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(partial["failure_codes"], ["no_network_activity"])
        unused = evaluate(cfg, {"events": []}, stderr_text="", capture={},
                          window_closed=True, firmware_wifi_stack=False)
        self.assertEqual(unused["status"], "NOT_USED")
        declared = evaluate(_config(network_code="absent"), {"events": []}, stderr_text="", capture={},
                            window_closed=True, firmware_wifi_stack=None)
        self.assertEqual(declared["status"], "NOT_USED")

    def test_open_window_without_events_is_running(self):
        verdict = evaluate(_config(), {"events": []}, stderr_text="", capture={},
                           window_closed=False, firmware_wifi_stack=True)
        self.assertEqual(verdict["status"], "RUNNING")

    def test_lease_without_required_http_fails_after_window(self):
        cfg = _config(fixtures={"http": {"routes": [{"path": "/x"}]}},
                      assertions=[{"type": "dhcp_lease"}, {"type": "http_request", "path": "/x"}])
        verdict = evaluate(cfg, {"events": [{"type": "dhcp_lease", "status": "PASS"}]},
                           stderr_text="", capture={}, window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("http_status", verdict["failure_codes"])

    def test_attempt_without_lease_is_dhcp_timeout(self):
        verdict = evaluate(_config(), {"events": [{"type": "dhcp_discover"}]}, stderr_text="",
                           capture={}, window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("dhcp_timeout", verdict["failure_codes"])

    def test_pcap_with_non_fixture_address_fails_isolation(self):
        capture = {"status": "PASS", "input": {"sha256": "0" * 64},
                   "flows": [{"source": "10.0.2.15:1", "destination": "1.1.1.1:53"}]}
        verdict = evaluate(_config(), {"events": [{"type": "dhcp_lease", "status": "PASS"}]},
                           stderr_text="", capture=capture, window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(verdict["pcap_isolation"]["status"], "FAIL")
        self.assertEqual(verdict["status"], "FAIL")

    def test_guest_softap_multicast_is_local_not_egress(self):
        capture = {"status": "PASS", "input": {"sha256": "0" * 64}, "flows": [
            {"source": "192.168.4.1", "destination": "224.0.0.251"},
            {"source": "192.168.4.1:5353", "destination": "224.0.0.251:5353"},
            {"source": "0.0.0.0:68", "destination": "255.255.255.255:67"},
        ]}
        verdict = evaluate(_config(), {"events": []}, stderr_text="", capture=capture,
                           window_closed=True, firmware_wifi_stack=True)
        self.assertEqual(verdict["pcap_isolation"]["status"], "PASS")
        self.assertEqual(verdict["pcap_isolation"]["guest_local_sources"], ["192.168.4.1"])
        self.assertEqual(verdict["status"], "PARTIAL")

    def test_scan_only_is_partial_and_join_without_lease_is_dhcp_timeout(self):
        scan = "QEMU: Received probe request!\n" * 4
        verdict = evaluate(_config(), {"events": []}, stderr_text="", capture={},
                           window_closed=True, firmware_wifi_stack=True, stdout_text=scan)
        self.assertEqual(verdict["status"], "PARTIAL")
        self.assertEqual(verdict["failure_codes"], ["no_network_activity", "wifi_scan_only"])
        joined = scan + "QEMU: Received authentication request!\nQEMU: Received association request!\n"
        verdict = evaluate(_config(), {"events": []}, stderr_text="", capture={},
                           window_closed=True, firmware_wifi_stack=True, stdout_text=joined)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("dhcp_timeout", verdict["failure_codes"])

    def test_auth_events_come_only_from_controller_trace(self):
        self.assertEqual(wifi_auth_events("WPA2-PSK ready", "wpa2-psk", True), [])
        self.assertTrue(firmware_has_wifi_stack(b"..net80211.."))
        self.assertFalse(firmware_has_wifi_stack(b"plain app"))


if __name__ == "__main__":
    unittest.main()
