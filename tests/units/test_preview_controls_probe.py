"""Host-only managed control probe/source/observation rejection contracts."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preview_controls_probe as probe

NODE = '/opt/homebrew/bin/node'
ROOT = Path(__file__).resolve().parents[2]
RUNNER = 'platform/tests/test_live_preview_controls_service_browser.mjs'


class PreviewControlsProbeTests(unittest.TestCase):
    nonce = 'a' * 32
    execution = 'b' * 32

    def sample(self):
        return {'kind': 'sample', 'nonce': self.nonce, 'phase': 'A', 'sequence': 1, 'resource_hex': probe.RESOURCE.hex(),
                'encoder': {'counter': 0, 'pressed': True}, 'eight': {'counters': [0] * 8, 'pressed': [False] * 8, 'switch_on': False},
                'joystick': {'x_raw': 128, 'y_raw': 128, 'button_raw': 0}, 'written': {'encoder': [0xFF0000] * 2, 'eight': [0] * 9}}

    def window(self, row=None, *, ready=True, execution=None):
        rows = [dict(kind='ready', nonce=self.nonce, phase='A', scan=[64, 65, 82], resource_hex=probe.RESOURCE.hex())] if ready else []
        rows.append(row or self.sample())
        return '\x01\x04\x04__M5_EXEC_' + (execution or self.execution) + '__:START\r\n' + ''.join(probe.PREFIX + json.dumps(value) + '\r\n' for value in rows)

    def test_four_plans_are_offline_and_host_ports_not_inherited(self):
        for device in probe.DEVICES:
            plan = probe.plan(device)
            self.assertFalse(plan['api_contacted']); self.assertEqual(plan['guests_started'], 0)
            self.assertEqual(plan['status'], 'NOT RUN')
            self.assertEqual(plan['attachments'][0]['port_id'], probe.PORTS[device])
            self.assertEqual(plan['addresses'], [64, 65, 82])
        with self.assertRaises(ValueError): probe.plan('tab5')

    def test_generated_source_uses_real_drivers_and_resources(self):
        payload = probe.build_package(self.nonce, {'white': 1, 'yellow': 2})
        source = payload['files']['main.py']['data']
        for phase in ('', "_preview_phase='B'\n", "_preview_phase='C'\n"):
            compile(phase + source, 'main.py', 'exec')
        compile(payload['files']['logic.py']['data'], 'logic.py', 'exec')
        compile(probe.seed_package(self.nonce)['files']['main.py']['data'], 'seed.py', 'exec')
        self.assertIn('from unit import EncoderUnit, Encoder8Unit, JoystickUnit', source)
        self.assertIn('encoder.fill_color', source); self.assertIn('eight.write_reg_data(0x88', source)
        self.assertIn('scl=Pin(1), sda=Pin(2)', source); self.assertIn(probe.nonce_path(self.nonce), source)
        self.assertNotIn('rotation', source); self.assertEqual(len(payload['files']), 4)
        self.assertEqual(probe.seed_package(self.nonce)['source_kind'], 'uiflow2-package')

    def test_bad_pin_and_nonce_inputs_do_not_generate_source(self):
        for pins in ({'white': 1, 'yellow': 1}, {'white': True, 'yellow': 2}, {'white': 49, 'yellow': 2}, {'white': 1}):
            with self.subTest(pins=pins), self.assertRaises(ValueError): probe.build_package(self.nonce, pins)
        with self.assertRaises(ValueError): probe.seed_package('unquoted nonce')

    def test_node_default_all_hosts_never_reads_token_or_creates_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'must-not-exist'
            for device in probe.DEVICES:
                result = subprocess.run([NODE, RUNNER, '--device', device, '--out-dir', str(output),
                                         '--token-file', str(Path(directory) / 'missing-token'), '--base-url', 'invalid://offline'],
                                        cwd=ROOT, env={**os.environ, 'M5_PREVIEW_PYTHON': sys.executable},
                                        capture_output=True, text=True, check=True, timeout=20)
                self.assertEqual(json.loads(result.stdout), probe.plan(device)); self.assertEqual(result.stderr, '')
                self.assertFalse(output.exists())

    def test_current_start_raw_paste_prefix_and_typed_ready_are_required(self):
        parsed = probe.parse_window(self.window(), self.execution, self.nonce, 'A', require_ready=True)
        self.assertTrue(parsed['ready']); self.assertEqual(parsed['sample'], self.sample())
        self.assertIsNone(probe.parse_window(self.window(execution='c' * 32), self.execution, self.nonce, 'A'))
        self.assertIsNone(probe.parse_window(self.window(ready=False), self.execution, self.nonce, 'A', require_ready=True))
        text = probe.PREFIX + json.dumps(self.sample()) + '\n__M5_EXEC_' + self.execution + '__:START\n'
        self.assertIsNone(probe.parse_window(text, self.execution, self.nonce, 'A'))

    def test_old_phase_wrong_nonce_and_incomplete_json_never_count(self):
        for field, value in [('phase', 'B'), ('nonce', 'c' * 32)]:
            row = self.sample(); row[field] = value
            self.assertIsNone(probe.parse_window(self.window(row), self.execution, self.nonce, 'A'))
        self.assertIsNone(probe.parse_window(self.window().rstrip(), self.execution, self.nonce, 'A'))
        marker = '__M5_EXEC_' + self.execution + '__:START'
        self.assertIsNone(probe.parse_window(self.window().replace(marker, marker + '_other'), self.execution, self.nonce, 'A'))
        self.assertIsNone(probe.parse_window(marker, self.execution, self.nonce, 'A'))

    def test_fresh_action_window_does_not_borrow_old_matching_sample(self):
        old = self.window(); row = self.sample(); row['encoder']['pressed'] = False; row['written']['encoder'] = [0, 0]; row['sequence'] = 2
        parsed = probe.parse_window(old, self.execution, self.nonce, 'A', require_ready=True, fresh_text=probe.PREFIX + json.dumps(row) + '\n')
        self.assertFalse(parsed['sample']['encoder']['pressed']); self.assertEqual(parsed['sample']['sequence'], 2)
        self.assertIsNone(probe.parse_window(old, self.execution, self.nonce, 'A', fresh_text=''))

    def test_sample_types_ranges_and_uniform_output_cannot_be_spoofed(self):
        changes = [lambda r: r.update(sequence=True), lambda r: r['encoder'].update(counter=False),
                   lambda r: r['encoder'].update(pressed=1), lambda r: r['eight']['counters'].__setitem__(0, 2**31),
                   lambda r: r['eight']['pressed'].__setitem__(0, 0), lambda r: r['joystick'].update(x_raw=True),
                   lambda r: r['joystick'].update(button_raw=2), lambda r: r['written']['encoder'].__setitem__(0, 0),
                   lambda r: r.update(resource_hex='00')]
        for change in changes:
            row = self.sample(); change(row)
            with self.subTest(row=row), self.assertRaises(ValueError): probe.typed_sample(row, self.nonce, 'A')
        with self.assertRaises(ValueError): probe.typed_sample(self.sample(), self.nonce, 'unknown')

    def test_unknown_creation_recovery_and_cleanup_are_owned_and_fail_closed(self):
        # Import the actual live runner lifecycle without CLI execution. All
        # injected transports are in-memory; even an accidental fetch fails.
        script = r'''
import assert from 'node:assert/strict';
globalThis.fetch = () => { throw new Error('offline contract attempted HTTP'); };
const {createOwnedPreview,closeOwnedPreview} = await import('./platform/tests/test_live_preview_controls_service_browser.mjs');
const receipt={preview_id:'a'.repeat(32),owner_epoch:'b'.repeat(32),session_id:'owned'};
const intent={key:'one-original-intent',body:{device_id:'cores3',runtime:'qemu',ttl_seconds:900,units:[{id:'hub1'}]}};
const session={session_id:'owned',pid:42,state:'running'};
const capacity={active_sessions:0,worker:{active_lease_count:0}};
async function scenario({failure,zipFails=false,readFails=false,closeLost=false,late=false,recoverFails=false}={}) {
 const state={},calls=[];let creates=0,closed=false,verifyCount=0;
 const send=async(path,method='GET',body=null,key=null)=>{
  calls.push({path,method,body:structuredClone(body),key});
  if(path==='previews') {creates++;assert.deepEqual(body,intent.body);assert.equal(key,intent.key);
   if(creates===1&&failure)throw failure;
   if(creates>1&&recoverFails)throw new Error('recovery unavailable');
   return {...receipt,session_id:late?null:'owned'};}
  if(path===`previews/${receipt.preview_id}/close`) {
   assert.deepEqual(body,{expected_owner_epoch:receipt.owner_epoch});closed=true;
   if(closeLost)throw new Error('close receipt lost');return {state:'closing'};}
  if(path===`previews/${receipt.preview_id}`) {
   if(readFails&&!closed)throw new Error('preview read unavailable');
   return {...receipt,session_id:late&&!closed?null:'owned',state:closed?'closed':'ready'};}
  if(path==='sessions/owned') {
   if(readFails&&!closed)throw new Error('session read unavailable');
   return {...session,state:closed?'stopped':'running',flash_retained:false};}
  if(path==='capacity')return capacity;
  throw new Error('unowned or unexpected operation '+path);
 };
 let original;
 try {await createOwnedPreview(state,intent,send);}catch(error){original=error;}
 let result,cleanupError;
 try {result=await closeOwnedPreview(state,{send,wait:async(read,predicate)=>{const value=await read();assert.ok(predicate(value));return value;},
  captureZip:async(id)=>{assert.equal(id,'owned');assert.equal(closed,false);calls.push({path:'zip-before-close'});if(zipFails)throw new Error('ZIP unavailable');},
  pidGone:async(pid)=>{assert.equal(pid,42);assert.equal(closed,true);return true;},
  verify:value=>{verifyCount++;assert.equal(value.preview.state,'closed');assert.equal(value.session.state,'stopped');assert.equal(value.session.flash_retained,false);
   assert.equal(value.pid_gone,true);assert.equal(value.zip_before_close,true);assert.deepEqual(value.capacity,capacity);return {status:'PASS'};}
 });}catch(error){cleanupError=error;}
 return {state,calls,creates,closed,verifyCount,original,result,cleanupError};
}
for(const failure of [new Error('creation receipt lost'),Object.assign(new Error('HTTP 500'),{status:500,responseComplete:true}),
 Object.assign(new Error('HTTP 408'),{status:408,responseComplete:true})]) {
 const row=await scenario({failure});assert.equal(row.original,failure);assert.equal(row.creates,2);assert.equal(row.closed,true);
 assert.equal(row.result.contract.status,'PASS');assert.equal(row.state.creation.recovered_for_cleanup,true);
 assert.deepEqual(row.calls.filter(c=>c.path==='previews'),[0,1].map(()=>({path:'previews',method:'POST',body:intent.body,key:intent.key})));
 assert.ok(row.calls.findIndex(c=>c.path==='zip-before-close')<row.calls.findIndex(c=>c.path.endsWith('/close')));
}
const rejected=await scenario({failure:Object.assign(new Error('known rejection'),{status:409,responseComplete:true})});
assert.equal(rejected.creates,1);assert.equal(rejected.closed,false);assert.equal(rejected.result,null);
const zip=await scenario({zipFails:true});assert.equal(zip.closed,true);assert.ok(zip.cleanupError);assert.equal(zip.state.zipBeforeClose,undefined);
const read=await scenario({readFails:true});assert.equal(read.closed,true);assert.ok(read.cleanupError);assert.equal(read.state.session,undefined);
const lost=await scenario({closeLost:true});assert.equal(lost.result.contract.status,'PASS');assert.equal(lost.calls.filter(c=>c.path.endsWith('/close')).length,1);
const late=await scenario({late:true});assert.equal(late.closed,true);assert.ok(late.cleanupError);assert.equal(late.verifyCount,1);
const unavailable=await scenario({failure:new Error('creation receipt lost'),recoverFails:true});
assert.ok(unavailable.cleanupError);assert.equal(unavailable.closed,false);assert.equal(unavailable.creates,2);
assert.ok(unavailable.calls.every(c=>c.path==='previews'));
console.log(JSON.stringify({status:'PASS',network_calls:0,guest_starts:0,scenarios:9}));
'''
        result = subprocess.run([NODE, '--input-type=module', '-e', script], cwd=ROOT,
                                capture_output=True, text=True, check=True, timeout=20)
        self.assertEqual(json.loads(result.stdout), {'status': 'PASS', 'network_calls': 0, 'guest_starts': 0, 'scenarios': 9})
        self.assertEqual(result.stderr, '')

    def cleanup(self):
        return {'preview': {'state': 'closed', 'session_id': 'owned'}, 'session': {'state': 'stopped', 'session_id': 'owned', 'flash_retained': False},
                'capacity': {'active_sessions': 0, 'worker': {'active_lease_count': 0}}, 'session_id': 'owned', 'pid_gone': True, 'zip_before_close': True}

    def test_cleanup_requires_literal_observed_evidence(self):
        self.assertEqual(probe.cleanup_contract(self.cleanup())['status'], 'PASS')
        changes = [lambda r: r['preview'].update(state='closing'), lambda r: r['session'].update(flash_retained=None),
                   lambda r: r['session'].update(state='running'), lambda r: r.update(pid_gone=False), lambda r: r.update(zip_before_close=False),
                   lambda r: r['capacity'].update(active_sessions=False), lambda r: r['capacity']['worker'].update(active_lease_count=1),
                   lambda r: r['session'].update(session_id='somebody-else'), lambda r: r['capacity'].update(worker=None),
                   lambda r: (r['session'].update(session_id=None), r['preview'].update(session_id=None), r.update(session_id=None))]
        for change in changes:
            row = self.cleanup(); change(row)
            with self.subTest(row=row), self.assertRaises(ValueError): probe.cleanup_contract(row)

    def archive(self, *, bad_hash=False, missing_execution=False):
        expected = {'session_id': 'owned', 'device_id': 'cores3', 'firmware_sha256': 'c' * 64, 'pid': 42,
                    'runs': [{'execution_id': self.execution, 'revision_id': 'd' * 64}]}
        execution = {**expected['runs'][0], 'pid': 42, 'firmware_sha256': 'c' * 64}
        members = {} if missing_execution else {f'programs/{self.execution}.json': json.dumps(execution).encode()}
        members['serial.log'] = b'actual retained serial'
        manifest = {'session': {k: v for k, v in expected.items() if k != 'runs'},
                    'files': {name: {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()} for name, value in members.items()}}
        if bad_hash: manifest['files']['serial.log']['sha256'] = '0' * 64
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, value in members.items(): archive.writestr(name, value)
            archive.writestr('manifest.json', json.dumps(manifest))
        return output.getvalue(), expected

    def test_zip_identity_crc_manifest_and_execution_gate(self):
        data, expected = self.archive(); self.assertEqual(probe.inspect_zip(data, expected)['status'], 'PASS')
        with self.assertRaises(ValueError): probe.inspect_zip(data, {**expected, 'pid': 100})
        with self.assertRaises(ValueError): probe.inspect_zip(*self.archive(bad_hash=True))
        with self.assertRaises(KeyError): probe.inspect_zip(*self.archive(missing_execution=True))


if __name__ == '__main__':
    unittest.main()
