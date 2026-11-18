from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from device_service import DeviceSession
from device_service_specs import load_device_specs
from device_service_wifi_evidence import (
    captured_provision_station_dora, native_sta_capability, native_sta_data_plane,
)


def _transaction(**overrides):
    return {
        "xid": "01020304",
        "message_sequence": ["DISCOVER", "OFFER", "REQUEST", "ACK"],
        "client_address": "10.0.2.15",
        "requested_ip": "10.0.2.15",
        "server_id": "10.0.2.2",
        "lease_seconds": 86400,
        **overrides,
    }


def _pair(protocol, left, right, *, outgoing=1, incoming=1):
    return [
        {"protocol": protocol, "source": left, "destination": right, "payload_bytes": outgoing},
        {"protocol": protocol, "source": right, "destination": left, "payload_bytes": incoming},
    ]


def _capture(*, transactions=None, flows=None, **kwargs):
    return {
        "status": "PASS",
        "format": "pcap",
        "linktype": 1,
        "input": {"sha256": "a" * 64},
        "dhcp": {"transactions": [_transaction()] if transactions is None else transactions},
        "flows": [
            *_pair("TCP", "10.0.2.15:53000", "10.0.2.100:80"),
            *_pair("UDP", "10.0.2.15:53001", "10.0.2.100:53"),
        ] if flows is None else flows,
        **kwargs,
    }


class NativeStaDataPlaneTests(unittest.TestCase):
    def test_bound_same_lease_flows_without_application_verdict(self):
        receipt = native_sta_data_plane(_capture())
        self.assertEqual(receipt, {
            "schema_version": 1,
            "scope": "same-session-native-ipv4-transport",
            "source": "ethernet-pcap",
            "capture_state": "finalized",
            "capture_sha256": "a" * 64,
            "dhcpv4": {"completed_dora_transactions": 1, "leased_address_count": 1},
            "tcp": {"bidirectional_payload_flows": 1},
            "udp": {"bidirectional_payload_flows": 1},
        })
        self.assertNotIn("10.0.2", repr(receipt))

    def test_unbound_or_split_transaction_and_ack_without_lease_do_not_prove_ip(self):
        rejected = (
            [_transaction(message_sequence=["REQUEST", "ACK"])],
            [_transaction(message_sequence=["DISCOVER", "OFFER", "REQUEST"]),
             _transaction(xid="aabbccdd", message_sequence=["ACK"])],
            [_transaction(message_sequence=["DISCOVER", "OFFER", "REQUEST", "NAK", "ACK"])],
            [_transaction(requested_ip="10.0.2.23")],
            [_transaction(lease_seconds=0)],
        )
        for rows in rejected:
            with self.subTest(rows=rows):
                receipt = native_sta_data_plane(_capture(transactions=rows))
                self.assertEqual(receipt["dhcpv4"]["completed_dora_transactions"], 0)
                self.assertEqual(receipt["tcp"]["bidirectional_payload_flows"], 0)
                self.assertEqual(receipt["udp"]["bidirectional_payload_flows"], 0)

    def test_reverse_payload_and_known_lease_required(self):
        flows = [
            *_pair("TCP", "10.0.2.15:53000", "10.0.2.100:80", incoming=0),
            *_pair("TCP", "10.0.2.23:53000", "10.0.2.100:80"),
            *_pair("UDP", "10.0.2.15:68", "10.0.2.2:67"),
            *_pair("UDP", "2001:db8::1:11", "2001:db8::2:22"),
        ]
        receipt = native_sta_data_plane(_capture(flows=flows))
        self.assertEqual(receipt["dhcpv4"]["completed_dora_transactions"], 1)
        self.assertEqual(receipt["tcp"]["bidirectional_payload_flows"], 0)
        self.assertEqual(receipt["udp"]["bidirectional_payload_flows"], 0)

    def test_deduplicates_flow_and_lease_counts(self):
        pair = _pair("TCP", "10.0.2.15:53000", "10.0.2.100:80")
        receipt = native_sta_data_plane(_capture(
            transactions=[_transaction(), _transaction(xid="aabbccdd")],
            flows=pair + pair,
        ))
        self.assertEqual(receipt["dhcpv4"], {"completed_dora_transactions": 2, "leased_address_count": 1})
        self.assertEqual(receipt["tcp"]["bidirectional_payload_flows"], 1)

    def test_capturing_or_truncated_pcap_cannot_promote_observations(self):
        self.assertEqual(native_sta_data_plane({"status": "CAPTURING"})["capture_state"], "capturing")
        for override in (
            {"status": "FAIL"}, {"truncated_records": 1}, {"malformed_records": 1},
            {"flows_truncated": True}, {"dhcp": {"transactions_truncated": True}},
            {"input": {"sha256": None}}, {"linktype": 127},
        ):
            with self.subTest(override=override):
                receipt = native_sta_data_plane(_capture(**override))
                self.assertEqual(receipt["capture_state"], "unavailable")
                self.assertIsNone(receipt["capture_sha256"])
                self.assertEqual(receipt["dhcpv4"]["completed_dora_transactions"], 0)

    def test_provisioning_requires_generation_xid_and_exact_lease(self):
        self.assertTrue(captured_provision_station_dora(_capture(), "01020304"))
        self.assertFalse(captured_provision_station_dora(_capture(), "aabbccdd"))
        self.assertFalse(captured_provision_station_dora(_capture(), None))
        for capture in (
            _capture(transactions=[_transaction(server_id="10.0.2.23")]),
            _capture(transactions=[_transaction(client_address="10.0.2.23", requested_ip="10.0.2.23")]),
            _capture(transactions=[_transaction(message_sequence=["REQUEST", "ACK"])]),
            _capture(truncated_records=1),
        ):
            with self.subTest(capture=capture):
                self.assertFalse(captured_provision_station_dora(capture, "01020304"))


class NativeStaIntegrationTests(unittest.TestCase):
    def test_reconnect_cannot_pass_using_pre_reset_capture(self):
        historical = _capture()
        phase = _capture(record_start_offset=2048)
        session = SimpleNamespace(
            runtime="qemu-wifi", network_config={"profile": "sticks3-open-softap-provisioning"},
            network_result={},
            _build_network_evidence=lambda: {"status": "PARTIAL", "checks": {}},
            _network_capture_evidence=Mock(side_effect=[
                historical,
                {**historical, "station_reconnect": {**phase, "record_start_offset": 1024}},
                {**historical, "station_reconnect": phase},
            ]),
            _softap_receipt=lambda: {
                "status": "PASS", "station_reconnect": True, "station_dhcp": True,
                "station_arp": True, "station_dhcp_xid": "01020304", "capture_start_offset": 2048,
            },
            _persist_session=Mock(),
        )
        self.assertEqual(DeviceSession.network_evidence(session)["status"], "PARTIAL")
        self.assertEqual(DeviceSession.network_evidence(session)["status"], "PARTIAL")
        self.assertEqual(DeviceSession.network_evidence(session)["status"], "PASS")

    def test_native_transport_changes_are_persisted_without_promoting_marker_status(self):
        session = SimpleNamespace(
            runtime="qemu-wifi",
            network_config={},
            network_result={},
            _build_network_evidence=lambda: {"status": "PARTIAL", "checks": {}},
            _network_capture_evidence=Mock(side_effect=[{"status": "CAPTURING"}, _capture()]),
            _persist_session=Mock(),
        )
        live = DeviceSession.network_evidence(session)
        final = DeviceSession.network_evidence(session)
        self.assertEqual(live["native_data_plane"]["capture_state"], "capturing")
        self.assertEqual(final["native_data_plane"]["tcp"]["bidirectional_payload_flows"], 1)
        self.assertEqual(final["status"], "PARTIAL")
        self.assertEqual(final["checks"], {})
        self.assertEqual(session._persist_session.call_count, 2)

    def test_legacy_unified_evidence_shape_depends_on_its_existing_profile(self):
        session = SimpleNamespace(
            runtime="qemu-unified", network_config={}, network_result={},
            _build_network_evidence=lambda: {"status": "PASS", "checks": {}},
            _network_capture_evidence=lambda: _capture(), _persist_session=Mock(),
        )
        self.assertNotIn("native_data_plane", DeviceSession.network_evidence(session))


class NativeStaCapabilityTests(unittest.TestCase):
    def test_core2_offer_requires_exact_machine_and_radio_profile(self):
        core2 = replace(load_device_specs()["core2"], network_profiles=("core2-openmac",))
        expected = {"sta": {
            "runtime": "qemu-wifi", "profile": "core2-openmac", "operation_assertions": False,
            "http_fixture": True,
        }}
        self.assertEqual(native_sta_capability(core2, backend_ready=True), expected)
        self.assertEqual(native_sta_capability(core2, backend_ready=False), {})
        for wrong in (
            replace(core2, network_profiles=()),
            replace(core2, backend="qemu-esp32s3"),
            replace(core2, machine="m5stack"),
            replace(core2, id="atom-lite"),
        ):
            self.assertEqual(native_sta_capability(wrong, backend_ready=True), {})

    @patch("device_service_wifi_evidence.qemu_has_qom_property", return_value=False)
    def test_only_matched_ready_native_cardputer_projects_sta_capability(self, _property_probe):
        specs = load_device_specs()
        expected = {"sta": {
            "runtime": "qemu-wifi", "profile": "generic-observe", "operation_assertions": False,
            "http_post_fixture": True, "tcp_fixture": True,
        }}
        for name in ("cardputer", "cardputer-adv"):
            with self.subTest(name=name):
                spec = specs[name]
                observed = native_sta_capability(spec, backend_ready=True)
                if name == "cardputer-adv":
                    self.assertEqual(observed.pop("sta_time_fixture"), {
                        "runtime": "qemu-wifi", "profile": "cardputer-adv-local-time-fixture",
                        "host_ip_backends": 0, "scope": "local-dns-and-sntp",
                    })
                self.assertEqual(observed, expected)
                self.assertEqual(native_sta_capability(spec, backend_ready=False), {})
                for unsupported in (
                    replace(spec, supported=False),
                    replace(spec, machine="m5cores3"),
                    replace(spec, backend="qemu-esp32lx6"),
                    replace(spec, service_kind="tab5"),
                ):
                    self.assertEqual(native_sta_capability(unsupported, backend_ready=True), {})
        self.assertEqual(native_sta_capability(specs["sticks3"], backend_ready=True), {
            "portal_provisioning_fixture": {
                "runtime": "qemu-wifi", "profile": "sticks3-open-softap-provisioning",
                "host_ip_backends": 0, "scope": "portal-to-station",
            },
        })

    def test_fixed_softap_offer_requires_exact_board_machine_and_nic_property(self):
        specs = load_device_specs()
        for board, profile in (
            ("cardputer", "cardputer-open-softap-fixture"),
            ("cardputer-adv", "cardputer-open-softap-fixture"),
            ("sticks3", "sticks3-open-softap-fixture"),
        ):
            with self.subTest(board=board):
                spec = specs[board]
                with patch("device_service_wifi_evidence.qemu_has_qom_property", return_value=True) as probe:
                    result = native_sta_capability(spec, backend_ready=True)
                    self.assertEqual(result["open_softap_fixture"], {
                        "runtime": "qemu-wifi", "profile": profile, "host_ip_backends": 0,
                        "scope": "fixed-softap-http",
                    })
                    probe.assert_called_once_with(spec.qemu, "misc.esp32s3.wifi", "open-softap-peer", "bool")
                    probe.reset_mock()
                    self.assertEqual(native_sta_capability(spec, backend_ready=False), {})
                    self.assertEqual(native_sta_capability(replace(spec, machine="m5cores3"), backend_ready=True), {})
                    probe.assert_not_called()
                with patch("device_service_wifi_evidence.qemu_has_qom_property", return_value=False):
                    self.assertNotIn("open_softap_fixture", native_sta_capability(spec, backend_ready=True))
