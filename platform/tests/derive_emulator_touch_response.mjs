// Validate the exact c854 touch-triggered restart away from its automatic cycle.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {dirname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const [input,output,sourceFile]=process.argv.slice(2);
assert.ok(input&&output&&sourceFile,'Usage: node derive_emulator_touch_response.mjs report.json .work/touch-validation.json matching-source.ino');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),out=resolve(output);
assert.ok(out.startsWith(resolve(root,'.work')+sep),'Derived raw evidence must stay in ignored .work');
const hash=b=>createHash('sha256').update(b).digest('hex');
const [bytes,source]=await Promise.all([readFile(input),readFile(sourceFile)]);
const d=JSON.parse(bytes),firmwareSHA='c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542';
assert.equal(d.engine,'qemu');assert.equal(d.device,'stackchan');assert.equal(d.result,'PASS');
assert.equal(d.firmware.sha256,firmwareSHA);assert.equal(d.configuration.sample_ms,8000);assert.equal(d.runs.length,1);
assert.equal(hash(source),'7ee22ca570acd7f105d8205b3bc67ecc19e60ce11b1533f3481fc1288081bb9e');
assert.match(source.toString(),/kRoutineMs\s*=\s*16000\s*;/);
const r=d.runs[0],args=r.receipt.actualArguments;
assert.equal(r.receipt.firmwareSha256,firmwareSHA);assert.equal(r.receipt.clockDivisor,1);
assert.ok(Array.isArray(args)&&!args.includes('-icount')&&!args.includes('-smp'));
assert.equal(args.filter(a=>a==='-accel').length,1);assert.equal(args[args.indexOf('-accel')+1],'tcg,thread=multi,one-insn-per-tb=on');
assert.ok(r.cleanup.gracefulExit&&r.worker_targets.ok&&r.worker_targets.live.length===0);
assert.deepEqual(r.guest_failure_observations.panic_or_watchdog_markers,[]);assert.deepEqual(r.guest_failure_observations.reset_events,[]);
const observed=r.input_observation;assert.equal(observed.requested_hold_ms,500);assert.equal(observed.actual_controller_receipts,2);
const events=observed.after.dom_events;
const downs=events.filter(e=>e.type==='pointerdown'),ups=events.filter(e=>e.type==='pointerup');
assert.equal(downs.length,1);assert.equal(ups.length,1);
const down=downs[0],up=ups[0];
for(const e of [down,up]){assert.equal(e.isTrusted,true);assert.equal(e.target,'CANVAS');assert.ok(Math.abs(e.clientX-observed.pointer.x)<2&&Math.abs(e.clientY-observed.pointer.y)<2);}
assert.ok(up.at_ms-down.at_ms>=400&&up.at_ms-down.at_ms<=1000,'Observe the real requested 500ms hold');
assert.ok(down.at_ms-r.ready_ms>=8000&&up.at_ms+1500-r.ready_ms<16000,'Keep the complete response window before the first automatic 16s boundary');
assert.equal(observed.after.inputs[0].down,true);assert.equal(observed.after.inputs[1].down,false);
assert.equal(observed.after.inputs[0].result.source,'qemu-qom-readback');assert.equal(observed.after.inputs[0].result.touch_bits,48);
assert.equal(observed.after.inputs[1].result.source,'qemu-qom-readback');assert.equal(observed.after.inputs[1].result.touch_bits,0);
assert.ok(r.input_serial_events?.length,'Full serial event timing is required across the input');
const lines=[],partial=new Map();
for(const e of r.input_serial_events){
 if(e.source==='uart1'||e.source==='emulator')continue;
 let line=partial.get(e.source)||'';
 for(const c of e.data){if(c==='\n'){lines.push({source:e.source,at_ms:e.at_ms,line:line.replace(/\r$/,'')});line='';}else line+=c;}
 partial.set(e.source,line);
}
const markers=lines.filter(e=>e.line==='DANCE restart in 650 ms'&&e.at_ms>=r.ready_ms);
assert.equal(markers.filter(e=>e.at_ms<down.at_ms).length,0,'No earlier 650ms restart after ready may enter this first-cycle test');
assert.equal(markers.length,1,'Exactly one restart is observed before the automatic cycle can be reached');
const marker=markers[0];assert.ok(marker.at_ms>=down.at_ms&&marker.at_ms<=up.at_ms+1500,'The on-press marker may occur during the hold or within 1500ms of release');
const result={kind:'same-firmware-first-cycle-touch-response',result:'PASS',validation:'virtual-device validation',hardware_validation:'NOT RUN',
 firmware_sha256:firmwareSHA,firmware_source_sha256:hash(source),input_report_sha256:hash(bytes),session_id:r.session_id,
 observed_ready_ms:r.ready_ms,observed_pointer_down:down,observed_pointer_up:up,observed_marker:marker,
 actual_hold_ms:up.at_ms-down.at_ms,marker_latency_from_down_ms:marker.at_ms-down.at_ms,
 automatic_routine_ms:16000,response_window_ends_after_ready_ms:up.at_ms+1500-r.ready_ms,
 pre_input_restart_markers:0,actual_controller_receipts:observed.after.inputs,
 cleanup_verified:true,meaning:'Trusted model pointer input reached the controller and the same guest emitted its restart marker before the automatic-cycle boundary. This does not establish physical capacitive sensing.'};
await writeFile(out,JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result));
