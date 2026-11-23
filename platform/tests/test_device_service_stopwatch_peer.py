"""StopWatch's original JSON portal has a distinct submit/exit/STA contract."""
import struct
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from device_service import parse_qemu_wifi_execution
from device_service_errors import ServiceError
from device_service_specs import load_device_specs
from device_service_softap_peer import (
    STOPWATCH_PROVISION_PROFILE, SoftAPPeer, require_softap_backend,
    PROVISION_STATION_GATEWAY, PROVISION_STATION_LEASE, _ARP_HEADER,
    _STATION_GATEWAY_MAC,
)
from device_service_stopwatch_peer import StopWatchProvisionPeer, _body
from network_fabric import _dhcp_options


def response(body, content_type=b'text/html'):
    return b'HTTP/1.1 200 OK\r\nContent-Type: '+content_type+b'\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body


class StopWatchAdmissionTests(unittest.TestCase):
    def test_exact_native_board_and_fixed_authorized_payload(self):
        spec=load_device_specs()['stopwatch']
        config=parse_qemu_wifi_execution(spec, {'profile': STOPWATCH_PROVISION_PROFILE})
        self.assertEqual(config['net_mode'], 'unix-socketpair')
        self.assertTrue(config['capture_pcap'])
        self.assertEqual(config['wifi_auth'], 'open')
        for other in (replace(spec,id='paperdiy'), replace(spec,machine='m5sticks3'),
                      replace(spec,service_kind='tab5'), replace(spec,backend='qemu-esp32lx6')):
            with self.subTest(other=other),self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(other, {'profile':STOPWATCH_PROVISION_PROFILE})
        for override in ({'capture_pcap':False},{'wifi_ssid':'elsewhere'},{'wifi_password':'x'},
                         {'policy':{}},{'net_mode':'user'},{'http_fixture':False}):
            with self.subTest(override=override),self.assertRaises(ServiceError):
                parse_qemu_wifi_execution(spec, {'profile':STOPWATCH_PROVISION_PROFILE,**override})

    @patch('device_service_softap_peer.subprocess.run')
    def test_backend_requires_independent_property(self, run):
        run.return_value.stdout='open-softap-peer=<bool>\nopen-softap-sticks3-portal=<bool>\nopen-softap-sticks3-station=<bool>\n'
        with self.assertRaises(ServiceError):require_softap_backend(Path('qemu'),stopwatch=True)
        run.return_value.stdout+='open-softap-stopwatch-provisioning=<bool>\n'
        require_softap_backend(Path('qemu'),stopwatch=True)


class StopWatchProtocolTests(unittest.TestCase):
    def test_bounded_page_and_exact_json_success(self):
        html=b'<script>fetch("/submit"); let ssid; let password;</script>'
        wire=response(html)
        self.assertIsNone(_body(wire[:-1]))
        self.assertEqual(_body(wire),html)
        self.assertEqual(_body(response(b'/exit'),done=True),b'/exit')
        self.assertEqual(_body(response(b'{"success":true}',b'application/json'),submit=True),b'{"success":true}')
        for invalid in (wire+b'x',wire.replace(b'200 OK',b'302 Found'),
                        wire.replace(b'Content-Length:',b'Transfer-Encoding: chunked\r\nContent-Length:'),
                        wire.replace(b'Content-Length:',b'Content-Length: 1\r\nContent-Length:'),
                        response(b'wrong'),response(b'x'*65537),b'x'*2049):
            with self.subTest(invalid=invalid[:80]),self.assertRaises(ValueError):_body(invalid)
        for body in (b'{"success":false}',b'{"success":1}',b'{"success":true,"extra":1}'):
            with self.subTest(body=body),self.assertRaises(ValueError):
                _body(response(body,b'application/json'),submit=True)

    def test_bound_station_dhcp_is_pumped_while_ap_tcp_waits(self):
        receipts=[];station='02:00:00:00:00:02'
        peer=StopWatchProvisionPeer('02:00:00:00:00:01',station,receipts.append)
        guest=SoftAPPeer(station,lambda _:None);foreign=SoftAPPeer('02:00:00:00:00:03',lambda _:None)
        for item in (peer,guest,foreign):self.addCleanup(item.close)
        frames=[]
        with patch.object(foreign,'_send',side_effect=frames.append):foreign._dhcp_request(b'othr',b'\x35\x01\x01')
        with patch.object(guest,'_send',side_effect=frames.append):
            guest._dhcp_request(b'good',b'\x35\x01\x01')
            guest._dhcp_request(b'good',b'\x35\x01\x03\x32\x04'+PROVISION_STATION_LEASE.packed+b'\x36\x04'+PROVISION_STATION_GATEWAY.packed)
        sent=[]
        with patch.object(peer,'_send',side_effect=sent.append):
            peer._station_frame(frames[0]);self.assertFalse(sent)
            peer._exit_response_received=True
            for frame in frames[1:]:peer._station_frame(frame)
        replies=[f[42:] for f in sent if f[12:14]==b'\x08\0']
        self.assertEqual([_dhcp_options(p).get(53) for p in replies],[b'\x02',b'\x05'])
        self.assertTrue(peer._station_dhcp_after_exit)
        self.assertEqual(peer._acknowledged_xid,b'good'.hex())
        arp=(_STATION_GATEWAY_MAC+peer._station_mac+_ARP_HEADER+b'\0\x02'
             +peer._station_mac+PROVISION_STATION_LEASE.packed+_STATION_GATEWAY_MAC+PROVISION_STATION_GATEWAY.packed)
        peer._station_frame(arp);self.assertTrue(peer._station_arp_seen)
        self.assertTrue(receipts[-1]['station_arp'])
