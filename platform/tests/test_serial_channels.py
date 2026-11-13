"""Separate real retained logs, existing ACLs and actual HTTP channel routing."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import shutil
import subprocess
import unittest
from http.server import ThreadingHTTPServer
from device_service import DeviceService, DeviceSession, ServiceError, NANOC6_HCI_BLE_PROFILE
from observation_store import display_projection
from runtime_acl import RuntimeACL
from serve import Handler


class SerialChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = DeviceService(state_dir=Path(self.tmp.name))
        firmware = Path(self.tmp.name) / 'fixture.bin'; firmware.write_bytes(b'\xff' * 1024)
        self.session = DeviceSession(self.service, session_id='a'*32, spec=self.service.specs['nanoc6'],
            firmware_id='b'*64, firmware_path=firmware, firmware_sha='b'*64, firmware_source='uploaded',
            source_artifacts=[], ttl_seconds=60, ready_marker=None, ready_timeout=10, ready_conditions=None,
            initial_state='stopped', persist=False)
        self.session.serial0.write_bytes(b'ROM\n')
        self.usb = self.session.dir / 'usb-serial-jtag.log'; self.usb.write_bytes('USB 中文\n'.encode())
        self.service._sessions[self.session.id] = self.session

    def tearDown(self):
        self.service.close_all(); self.tmp.cleanup()

    def test_separate_logs_offsets_truncation_and_retained_history(self):
        default = self.session.serial_read()
        self.assertEqual(default['data'], 'ROM\n'); self.assertEqual(default['channel'], 'console')
        usb = self.session.serial_read(4, 3, channel='usb-serial-jtag')
        self.assertEqual(usb['data'], '中'); self.assertEqual(usb['next_offset'], 7)
        self.assertEqual(self.session.serial_read(4)['data'], '')
        self.usb.write_bytes(b'x')
        self.assertEqual(self.session.serial_read(7, channel='usb-serial-jtag')['next_offset'], 1)
        self.assertEqual(self.session.serial0.read_bytes(), b'ROM\n')
        self.session._persist_session()
        self.service.close_all()
        self.service = DeviceService(state_dir=Path(self.tmp.name))
        restored = self.service.get_session(self.session.id)
        self.assertEqual(restored.serial_read(channel='usb-serial-jtag')['data'], 'x')
        self.assertEqual([x['channel'] for x in restored.snapshot()['serial_channels']], ['console', 'usb-serial-jtag'])

    @unittest.skipUnless(shutil.which("node"), "Node is required for the actual frontend cursor control")
    def test_truncated_backend_response_rewinds_frontend_and_reads_new_prefix(self):
        self.session.serial0.write_bytes(b"x" * 100)
        first = self.session.serial_read()
        self.session.serial0.write_bytes(b"new")
        truncated = self.session.serial_read(100)
        self.assertEqual((truncated["offset"], truncated["next_offset"], truncated["data"]), (3, 3, ""))
        fresh = self.session.serial_read(0)
        module = (Path(__file__).resolve().parents[1] / "web/serial-channel-state.js").as_uri()
        javascript = f"""
import {{SerialChannelState}} from {json.dumps(module)};
import assert from 'node:assert/strict';
let input='';for await(const chunk of process.stdin)input+=chunk;
const [first,truncated,fresh]=JSON.parse(input), state=new SerialChannelState(first.session_id);
state.accept(state.request(),first);assert.equal(state.view().bytes,100);
state.accept(state.request(),truncated);assert.equal(state.request().offset,0);assert.equal(state.view().text,'');
state.accept(state.request(),fresh);assert.equal(state.view().text,'new');assert.equal(state.view().bytes,3);
"""
        result = subprocess.run(["node", "--input-type=module", "-e", javascript],
            input=json.dumps([first, truncated, fresh]), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_identity_labels_do_not_call_hci_usb_console_uart0(self):
        self.session.network_config = {'profile': NANOC6_HCI_BLE_PROFILE}
        self.assertEqual(self.session.serial_channels(), [{'channel':'console','transport':'usb-serial-jtag','bytes':4}])
        with self.assertRaises(ServiceError) as error:self.session.serial_read(channel='usb-serial-jtag')
        self.assertEqual(error.exception.code, 'serial_channel_unavailable')

    def test_acl_precedes_channel_and_advertisement_and_journal_has_no_paths(self):
        projected = display_projection({'serial_channels': self.session.serial_channels() + [
            {'channel':'console','transport':'console','bytes':12,'path':'private-path','data':'private-log'}]})
        self.assertNotIn('private', json.dumps(projected))
        self.service.runtime_acl = RuntimeACL.from_document({'schema_version':1,'devices':{'nanoc6':{'allow':['program.read']}}})
        self.assertEqual(self.session.serial_channels(), [])
        for channel in ('console','usb-serial-jtag','../../secret'):
            with self.subTest(channel=channel), self.assertRaises(ServiceError) as error:
                self.session.serial_read(channel=channel)
            self.assertEqual(error.exception.status, 403)

    def test_actual_http_query_auth_unknown_and_unavailable(self):
        class LocalHandler(Handler):
            api_token='test-only-serial'; previous_api_token=None
            def log_message(self,*args):pass
        LocalHandler.service=self.service
        server=ThreadingHTTPServer(('127.0.0.1',0), LocalHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def get(query='',authenticated=True):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request('GET','/api/v1/sessions/'+self.session.id+'/serial'+query,
                    headers={'Authorization':'Bearer test-only-serial'} if authenticated else {})
                response=client.getresponse();return response.status,json.loads(response.read())
            finally:client.close()
        try:
            self.assertEqual(get()[1]['data'],'ROM\n')
            status,payload=get('?channel=usb-serial-jtag&offset=4&limit=3')
            self.assertEqual((status,payload['data'],payload['channel']),(200,'中','usb-serial-jtag'))
            self.assertEqual(get('?channel=usb-serial-jtag',False)[0],401)
            self.assertEqual(get('?channel=unknown')[0],400)
            self.usb.unlink(); self.assertEqual(get('?channel=usb-serial-jtag')[0],409)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
