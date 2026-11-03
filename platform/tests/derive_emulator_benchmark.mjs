// Derive concise metrics without changing or rerunning original guest evidence.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {dirname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {summarizeEmulatorRun} from './emulator_performance_summary.mjs';

if(process.argv.includes('--self-test')){
  const r={start_ms:0,first_serial_ms:1,ready_ms:2,sample_start_ms:10,sample_end_ms:1010,
    frames:[{at_ms:9,digest:'a',nonblack_channels:1},{at_ms:810,digest:'b',observer_ms:1},{at_ms:910,digest:'b',observer_ms:1}],
    states:[],stats:[],serial_events:[{source:'uart0',data:'DAN',at_ms:5},{source:'uart1',data:'CE cue=999\n',at_ms:6},
      {source:'uart0',data:'CE cue=1\n',at_ms:25},{source:'uart0',data:'DANCE cue=2\n',at_ms:30}]};
  const summary=summarizeEmulatorRun(r);
  assert.equal(summary.steady.frame_gap_ms.max,801);
  assert.equal(summary.steady.pixel_change_frames,1);
  assert.equal(summary.steady.delivered_frames,2);
  assert.equal(summary.steady.dance_cue_count,2);
  assert.equal(summary.serial_cues[0].line,'DANCE cue=1');
  const movement=summarizeEmulatorRun({...r,states:[
    {at_ms:9,state:{packets:8,servos:[{id:1,present_position:460}]}},
    {at_ms:20,state:{packets:9,powered:true,servos:[{id:1,present_position:460,moving:true}]}},
    {at_ms:30,state:{packets:10,servos:[{id:1,present_position:461}]}},
    {at_ms:40,state:{packets:11,servos:[{id:1,present_position:461,moving:false}]}}
  ]});
  assert.equal(movement.steady.packet_delta,3);
  assert.equal(movement.steady.position_change_observations,1,'metadata-only and initial states are not movement');
  assert.equal(movement.steady.packet_window.baseline_source,'at-or-before-window');
  const other=summarizeEmulatorRun({...r,states:[
    {at_ms:15,state:{servos:[{id:'pan',positionDegrees:0},{id:'tilt',positionDegrees:45}]}},
    {at_ms:30,state:{supply:true,servos:[{id:'tilt',positionDegrees:45},{id:'pan',positionDegrees:0}]}},
    {at_ms:35,state:{servos:[{id:'pan',positionDegrees:1},{id:'tilt',positionDegrees:45}]}}
  ]});
  assert.equal(other.steady.packet_delta,null);
  assert.equal(other.steady.position_change_observations,1,'id order cannot invent movement');
  assert.equal(other.steady.packet_window.baseline_source,'first-in-window');
  const render=summarizeEmulatorRun({...r,render_poses:[
    {at_ms:20,dom:{known:'true'},yaw:{angleDeg:0,targetAngleDeg:90,transitioning:true},pitch:{angleDeg:0}},
    {at_ms:30,dom:{known:'true'},yaw:{angleDeg:0,targetAngleDeg:80,transitioning:true},pitch:{angleDeg:0}},
    {at_ms:40,dom:{known:'true'},yaw:{angleDeg:1,targetAngleDeg:80,transitioning:true},pitch:{angleDeg:0}},
    {at_ms:50,dom:{known:'false'},yaw:{angleDeg:99},pitch:{angleDeg:99}}
  ]});
  assert.equal(render.steady.rendered_joint_trace.observations,3);
  assert.equal(render.steady.rendered_joint_trace.actual_angle_changes,1,'Target-only changes do not invent actual rendered motion');
  assert.equal(render.steady.rendered_joint_trace.intermediate_observations,3);
  assert.equal(summary.steady.rendered_joint_trace,null,'Old raw files cannot invent unrecorded rendered pose evidence');
  console.log('EMULATOR_BENCHMARK_DERIVATION_OK: split UART, source isolation, crossing-window frame gap, distinct pixels and actual rendered angles');
  process.exit(0);
}
const [output,...inputs]=process.argv.slice(2);
assert.ok(output&&inputs.length,'Usage: node derive_emulator_benchmark.mjs .work/derived-summary.json .work/run/report.json [...]');
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),out=resolve(output);
assert.ok(out.startsWith(resolve(repo,'.work')+sep),'Derived raw-evidence summaries must remain in ignored .work');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const rows=[];
for(const input of inputs){
  const bytes=await readFile(input),report=JSON.parse(bytes);
  rows.push({input_sha256:hash(bytes),input_report:input,engine:report.engine,device:report.device??'stackchan',firmware:report.firmware,
    result:report.result,configuration:report.configuration,
    runs:report.runs.map(run=>({run:run.run,session_id:run.session_id,receipt:run.receipt,
      cleanup:run.worker_targets?.ok??null,input_observation:run.input_observation??null,
      guest_failure_observations:run.guest_failure_observations??null,summary:summarizeEmulatorRun(run)}))});
}
await mkdir(dirname(out),{recursive:true});
await writeFile(out,JSON.stringify({schema_version:1,kind:'derived-emulator-benchmark-summary',created_at:new Date().toISOString(),
  original_reports_modified:false,algorithm_sha256:hash(await readFile(new URL('./emulator_performance_summary.mjs',import.meta.url))),reports:rows},null,2)+'\n',{flag:'wx'});
console.log(out);
