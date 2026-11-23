"""Fixed S3-watch protocol admission and bounded read-only response parsing."""
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from device_service import parse_qemu_wifi_execution, redacted_network_config
from device_service_errors import ServiceError
from device_service_specs import load_device_specs
from device_service_s3_watch_peer import PROFILE, REQUEST, parse_config, require_backend, state_body, controller_state, controller_checks, CONTROLLER_COUNTERS


def response(value=None, body=None):
    if body is None:
        value = value or {'t':'12:34:56','bt':'ADV','n':0,'name':'fixture','theme':0,
                          'h24':'1','secs':'1','scan':'1','brt':80,'net':'','ssid':'',
                          'ble':'1','sleep':60,'web':'1'}
        body = json.dumps(value).encode()
    return b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body


class S3WatchAdmissionTests(unittest.TestCase):
    def test_fixed_ssid_and_no_open_or_host_network_fallback(self):
        value={'profile':PROFILE,'wifi_ssid':'fixturetest','wifi_password':'fixture-password'}
        with patch('device_service_s3_watch_peer.SSID_SHA256',hashlib.sha256(b'fixturetest').hexdigest()):
            config=parse_config(value)
            self.assertEqual(config['net_mode'],'unix-socketpair')
            self.assertEqual(config['wifi_auth'],'wpa2-psk')
            self.assertFalse(config['http_fixture'])
            for override in ({'wifi_ssid':'other'},{'wifi_password':'short'},{'wifi_password':'x'*64},
                             {'wifi_password':'\ud800'},{'wifi_password':'12345678\0'},{'wifi_auth':'open'},{'capture_pcap':False},
                             {'net_mode':'user'},{'hostfwd':[]},{'http_fixture':True},{'policy':{}}):
                with self.subTest(override=list(override)),self.assertRaises(ServiceError):
                    parse_config({**value,**override})
            self.assertNotIn('fixture-password',json.dumps(redacted_network_config(config)))

    def test_board_admission_is_exact(self):
        spec=load_device_specs()['sticks3']
        value={'profile':PROFILE,'wifi_ssid':'fixturetest','wifi_password':'fixture-password'}
        with patch('device_service_s3_watch_peer.SSID_SHA256',hashlib.sha256(b'fixturetest').hexdigest()):
            self.assertEqual(parse_qemu_wifi_execution(spec,value)['profile'],PROFILE)
            for other in (replace(spec,id='stopwatch'),replace(spec,machine='m5stopwatch'),
                          replace(spec,backend='qemu-esp32lx6'),replace(spec,service_kind='tab5')):
                with self.subTest(other=other),self.assertRaises(ServiceError):parse_qemu_wifi_execution(other,value)

    @patch('device_service_s3_watch_peer.subprocess.run')
    def test_open_peer_does_not_satisfy_secure_backend(self, run):
        run.return_value.stdout='open-softap-peer=<bool>\n'
        with self.assertRaises(ServiceError):require_backend(Path('qemu'))
        run.return_value.stdout+='wpa2-softap-peer=<bool>\n'
        require_backend(Path('qemu'))


class S3WatchProtocolTests(unittest.TestCase):
    def test_only_read_only_application_endpoint(self):
        self.assertEqual(REQUEST.split(b'\r\n',1)[0],b'GET /api/state HTTP/1.0')
        self.assertNotIn(b'/time',REQUEST)

    def test_bounded_complete_json_and_partial_response(self):
        wire=response()
        self.assertIsNone(state_body(wire[:-1]))
        self.assertEqual(json.loads(state_body(wire))['web'],'1')
        unset=json.loads(state_body(wire));unset['t']='--:--:--'
        self.assertEqual(json.loads(state_body(response(unset)))['t'],'--:--:--')
        for invalid in (wire+b'x',wire.replace(b'200 OK',b'302 Found'),
                        wire.replace(b'Content-Length:',b'Content-Length: 1\r\nContent-Length:'),
                        wire.replace(b'Content-Length:',b'Transfer-Encoding: chunked\r\nContent-Length:'),
                        wire.replace(b'application/json',b'text/html'),b'x'*2049,response(body=b'x'*4097)):
            with self.subTest(invalid=invalid[:50]),self.assertRaises(ValueError):state_body(invalid)

    def test_listener_and_types_cannot_be_forged_by_truthiness(self):
        good=json.loads(state_body(response()))
        for key,value in (('web','0'),('n',False),('theme','0'),('bt',[]),('bt','other'),('t','ready')):
            with self.subTest(key=key),self.assertRaises(ValueError):state_body(response({**good,key:value}))
        with self.assertRaises(ValueError):state_body(response({**good,'extra':True}))
        duplicate=json.dumps(good).encode().replace(b'"n": 0',b'"n": 0, "n": 1')
        with self.assertRaises(ValueError):state_body(response(body=duplicate))

class S3WatchControllerTests(unittest.TestCase):
    def test_wpa2_gate_requires_real_current_handshake_and_both_protected_directions(self):
        state={'ready':True,**{key:1 for key in CONTROLLER_COUNTERS}}
        good=controller_state(json.dumps(state))
        self.assertTrue(all(controller_checks({'status':'OBSERVED','state':good}).values()))
        for key,value in (('ready',False),('m3',0),('m4',0),('protected_tx',0),('protected_rx',0)):
            with self.subTest(key=key):
                self.assertFalse(all(controller_checks({'status':'OBSERVED','state':{**good,key:value}}).values()))
        self.assertFalse(any(controller_checks({'status':'UNAVAILABLE','state':good}).values()))
        for bad in ({**state,'m1':True},{**state,'m2':-1},{**state,'ready':1},{**state,'extra':0}):
            with self.assertRaises(ValueError):controller_state(json.dumps(bad))

if __name__ == '__main__':unittest.main()
