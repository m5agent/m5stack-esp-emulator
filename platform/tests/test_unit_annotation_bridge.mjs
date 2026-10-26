// Offline oracle and transport branch checks. No API/browser/guest is started;
// transport snapshots below are explicitly synthetic fixtures, never evidence.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {AnnotationBridge, ANNOTATION_CONTRACT, claimAnnotationPhase,
  validateAnnotationSemantics, validateExpectedScalars} from './unit_annotation_bridge.mjs';
import {UnitWebBridge} from './unit_web_bridge.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const catalog = JSON.parse(await readFile(resolve(root,'platform/units/catalog.json'),'utf8'));
const annotationSource = await readFile(resolve(root,'platform/web/unit-annotations.js'),'utf8');
const annotationReadback = new Function(annotationSource.replace(/^import[^\n]*\n/gm,'').replace(/^export /gm,'')
  + '\nreturn annotationReadback;')();
const vectors = {
  'env-iii': {'temperature-c':18.75,'humidity-pct':45.5,'pressure-pa':103200},
  pir:{motion:true},'ultrasonic-i2c':{'distance-mm':432.25},
  color:{'clear-raw':1000,'red-raw':2000,'green-raw':3000,'blue-raw':4000},
  tof:{'distance-mm':321},light:{'analog-mv':1250.5,'digital-level':false},
  relay:{'output-level':true},ncir:{'ambient-c':21.5,'object-c':32.25},
  heart:{'ir-sample':1234,'red-sample':4567},thermal:{'control-word':6400,'raw-fixture-ready':true},
  tvoc:{'eco2-ppm':1234,'tvoc-ppb':567,'raw-h2':10000,'raw-ethanol':20000},
  buzzer:{'frequency-hz':1200.192,'duty-pct':24.9878},
};

function fixture(unitId) {
  const definition=structuredClone(catalog.units.find(unit=>unit.id===unitId));
  const readback={id:'external1',unit_id:unitId,source:'guest-qom',available:true,errors:{},properties:structuredClone(vectors[unitId])};
  const result=annotationReadback(readback,definition,{running:true,source:'live',frozenDefinitions:true});
  const groups=result.groups.map(group=>({label:group.label,fields:group.rows.map(row=>({field:row.field,label:row.label,
    text:row.value+(row.unit ? ` ${row.unit}` : '')}))}));
  return {at:'synthetic-offline-fixture',session_state:'running',panel_state:'running',state_source:'live',
    frozen_definitions:true,definition,readback,mounted_port:'grove',anchor:'grove/sensor',anchor_role:'visual-anchor',
    note:{fields:groups.flatMap(group=>group.fields.map(({field,text})=>({field,text}))),labels:groups.map(group=>group.label),groups,
      hidden:false,display:'block',bounds:{left:0,right:100,top:200,bottom:300,width:100,height:100},
      in_readout_rail:true,inside_canvas_subtree:false,inside_interactive_stage:false},
    canvas_bounds:{left:0,right:100,top:0,bottom:100,width:100,height:100},
    protected_projection_bounds:[{path:'lcd',bounds:{left:20,right:80,top:20,bottom:80}}],horizontal_overflow:false};
}

const cases=[];
async function test(name,run) {
  try {await run();cases.push({name,status:'PASS'});}
  catch(error) {cases.push({name,status:'FAIL',error:error.stack});}
}

await test('oracle-exactly-covers-current-twelve-annotated-units',()=>{
  assert.equal(Object.keys(ANNOTATION_CONTRACT).length,12);
  assert.deepEqual(Object.keys(ANNOTATION_CONTRACT).sort(),Object.keys(vectors).sort());
  assert.equal(Object.hasOwn(ANNOTATION_CONTRACT,'angle'),false);
});
for (const id of Object.keys(vectors)) {
  await test(`${id}-actual-product-semantics-match-explicit-source-and-field-contract`,()=>{
    const snapshot=fixture(id),result=validateAnnotationSemantics(snapshot,vectors[id]);
    assert.equal(result.rows.length,Object.keys(vectors[id]).length);
    assert.deepEqual(snapshot.note.fields,result.rows.map(({field,text})=>({field,text})));
  });
  await test(`${id}-wrong-source-label-is-rejected`,()=>{
    const snapshot=fixture(id);
    snapshot.note.labels[0]=snapshot.note.labels[0]==='固件输出' ? '模拟输入' : '固件输出';
    assert.throws(()=>validateAnnotationSemantics(snapshot,vectors[id]),/source labels differ/);
  });
}
await test('thermal-register-and-readiness-retain-distinct-directions-and-labels',()=>{
  const result=validateAnnotationSemantics(fixture('thermal'),vectors.thermal);
  assert.deepEqual(result.groups.map(group=>[group.label,group.fields.map(row=>row.field)]),[
    ['控制寄存器状态',['control-word']],['模型状态',['raw-fixture-ready']],
  ]);
  assert.deepEqual(result.rows.map(row=>row.direction),['inputs','outputs']);
});
await test('buzzer-quantized-live-values-are-not-rounded-to-requested-values',()=>{
  const snapshot=fixture('buzzer');
  assert.equal(validateAnnotationSemantics(snapshot,vectors.buzzer).rows[0].text,'1200.192 Hz');
  assert.throws(()=>validateAnnotationSemantics(snapshot,{'frequency-hz':1200}),/expected live/);
});
await test('expected-fields-reject-strings-arrays-counters-prototype-names-and-unknown-units',()=>{
  for (const expected of [{},[],{'eeprom-hex':'00'},{transactions:1},{'control-word':1.5},{constructor:1},{toString:1}]) {
    assert.throws(()=>validateExpectedScalars('thermal',expected));
  }
  for (const id of ['angle','button','constructor','toString']) assert.throws(()=>validateExpectedScalars(id,{motion:true}));
  for (const value of [NaN,Infinity,-Infinity,'1200',true,null]) assert.throws(()=>validateExpectedScalars('buzzer',{'frequency-hz':value}));
});
await test('frozen-definition-direction-type-unit-and-membership-cannot-drift',()=>{
  const changes=[
    snapshot=>{snapshot.definition.outputs['temperature-c']=snapshot.definition.inputs['temperature-c'];delete snapshot.definition.inputs['temperature-c'];},
    snapshot=>{snapshot.definition.inputs['temperature-c'].type='integer';},
    snapshot=>{snapshot.definition.inputs['temperature-c'].unit='WRONG';},
    snapshot=>{delete snapshot.definition.inputs['temperature-c'];},
    snapshot=>{snapshot.definition.inputs.unreviewed={type:'number'};snapshot.readback.properties.unreviewed=1;},
  ];
  for (const mutate of changes) {const snapshot=fixture('env-iii');mutate(snapshot);assert.throws(()=>validateAnnotationSemantics(snapshot,vectors['env-iii']));}
});
await test('missing-fields-invalid-values-ranges-and-enums-never-become-a-live-pass',()=>{
  const changes=[
    snapshot=>{delete snapshot.readback.properties['humidity-pct'];},
    snapshot=>{snapshot.readback.properties['humidity-pct']=101;},
    snapshot=>{snapshot.readback.properties['temperature-c']=NaN;},
    snapshot=>{snapshot.readback.properties['temperature-c']='18.75';},
    snapshot=>{snapshot.definition.inputs['temperature-c'].enum=[20];},
  ];
  for (const mutate of changes) {const snapshot=fixture('env-iii');mutate(snapshot);assert.throws(()=>validateAnnotationSemantics(snapshot,{'pressure-pa':103200}));}
});
await test('live-source-frozen-contract-and-running-state-are-required',()=>{
  const changes=[
    snapshot=>{snapshot.session_state='stopped';},snapshot=>{snapshot.panel_state='failed';},
    snapshot=>{snapshot.state_source='persisted';},snapshot=>{snapshot.frozen_definitions=false;},
    snapshot=>{snapshot.readback.source='pending-input';},snapshot=>{snapshot.readback.available=false;},
    snapshot=>{snapshot.readback.errors={qom:'unavailable'};},snapshot=>{snapshot.definition.id='another-unit';},
  ];
  for (const mutate of changes) {const snapshot=fixture('pir');mutate(snapshot);assert.throws(()=>validateAnnotationSemantics(snapshot,vectors.pir));}
});
await test('DOM-groups-labels-units-values-and-field-completeness-are-all-checked',()=>{
  const changes=[
    snapshot=>{snapshot.note.groups[0].fields[0].label='wrong field name';},
    snapshot=>{snapshot.note.groups[0].label='固件输出';},
    snapshot=>{snapshot.note.fields[0].text='1 Pa';},
    snapshot=>{snapshot.note.fields.pop();},
    snapshot=>{snapshot.note.fields.push({field:'invented',text:'1'});},
  ];
  for (const mutate of changes) {const snapshot=fixture('env-iii');mutate(snapshot);assert.throws(()=>validateAnnotationSemantics(snapshot,vectors['env-iii']));}
});
await test('unique-safe-phases-preserve-multiple-stage-evidence',()=>{
  const item={};
  for (const phase of ['buzzer-state-1','buzzer-once','buzzer-off']) claimAnnotationPhase(item,phase);
  assert.equal(item.annotationPhases.size,3);
  assert.throws(()=>claimAnnotationPhase(item,'buzzer-state-1'),/already recorded/);
  for (const phase of ['../escape','a/b','a\nb','',null]) assert.throws(()=>claimAnnotationPhase(item,phase));
});

function transportFixture({gestureMutation='',fresh=true,staleTimestamp=false}={}) {
  const snapshot=fixture('buzzer'),http={source:'live',contract_status:'frozen',units:[snapshot.readback],definitions:[snapshot.definition]};
  const calls={capture:0,evaluate:0,gesture:0,screenshots:0,save:0};
  const oldAt=new Date(Date.now()-1000).toISOString();
  const record={attachments:[{id:'external1',unit_id:'buzzer'}],posts:[],readbacks:[{at:oldAt,status:200,response:http}],
    annotation_snapshots:[],annotation_mutation_requests:[],annotation_http_bodies:[{at:oldAt,status:200,response:http,body_sha256:'synthetic-fixture-only'}]};
  const readout={async scrollIntoViewIfNeeded(){},async dblclick(){calls.gesture++;
    if (gestureMutation==='unit') record.posts.push({synthetic:true});
    if (gestureMutation==='other') record.annotation_mutation_requests.push({synthetic:true});},
    async evaluate(){return {inside_readout:true,selection:'fixture',selection_anchor_inside:true};},async click(){}};
  const note={locator(){return {first:()=>readout};},async screenshot(){calls.screenshots++;}};
  const item={record,responseTasks:new Set(),directory:'/synthetic-offline-only',annotationAssets:[],card:{locator(){return note;}},
    page:{async evaluate(_fn,arg){if(arg){
      calls.evaluate++;
      if(fresh) {
        const at=staleTimestamp ? oldAt : new Date().toISOString();
        record.readbacks.push({at,status:200,response:http});
        record.annotation_http_bodies.push({at,status:200,response:http,body_sha256:'synthetic-fresh-fixture-only'});
      }
      return {...structuredClone(snapshot),at:new Date().toISOString()};
    }},async waitForTimeout(){},async screenshot(){calls.screenshots++;}}};
  const bridge=Object.create(AnnotationBridge.prototype);
  bridge.sessions=new Map([['offline',item]]);
  bridge.save=async()=>{calls.save++;};
  return {bridge,item,calls};
}
await test('state-mode-keeps-strict-live-alignment-and-geometry-without-capture-gesture-or-image',async()=>{
  const {bridge,item,calls}=transportFixture();
  const previous=UnitWebBridge.prototype.capture;
  UnitWebBridge.prototype.capture=async()=>{calls.capture++;throw Error('state mode must not capture');};
  try {
    const snapshot=await bridge.observe('offline','buzzer-state-1',vectors.buzzer,'external1','state');
    assert.equal(snapshot.evidence_scope,'live-state-observation');
    assert.equal(snapshot.exact_http_controller_dom_alignment,true);
    assert.equal(snapshot.readout_outside_interactive_canvas,true);
    assert.equal(snapshot.phase_entry.readbacks_index,1);assert.equal(snapshot.phase_entry.http_bodies_index,1);
    assert.ok(snapshot.http_event_index>=snapshot.phase_entry.readbacks_index);
    assert.ok(snapshot.http_body_event_index>=snapshot.phase_entry.http_bodies_index);
    assert.ok(snapshot.http_observation.at>=snapshot.phase_entry.at);
    assert.equal(snapshot.screenshot,undefined);assert.equal(snapshot.readout_gesture,undefined);
    assert.equal(item.record.annotation_snapshots.length,1);
    assert.deepEqual(calls,{capture:0,evaluate:1,gesture:0,screenshots:0,save:1});
  } finally {UnitWebBridge.prototype.capture=previous;}
});
await test('state-and-full-phases-cannot-reuse-an-old-identical-GET-and-body',async()=>{
  const previous=UnitWebBridge.prototype.capture;
  UnitWebBridge.prototype.capture=async()=>{};
  try {
    for(const mode of ['state','full']) {
      const {bridge,item}=transportFixture({fresh:false});
      await assert.rejects(bridge.observe('offline','must-observe-new-GET',vectors.buzzer,'external1',mode),/fresh real product GET/);
      assert.equal(item.record.annotation_snapshots.length,0);
    }
  } finally {UnitWebBridge.prototype.capture=previous;}
});
await test('late-appended-prephase-response-timestamp-is-not-new-phase-evidence',async()=>{
  const {bridge,item}=transportFixture({staleTimestamp:true});
  await assert.rejects(bridge.observe('offline','late-old-response',vectors.buzzer,'external1','state'),/fresh real product GET/);
  assert.equal(item.record.annotation_snapshots.length,0);
});
await test('default-full-mode-retains-gesture-zero-post-and-readout-plus-page-images',async()=>{
  const {bridge,item,calls}=transportFixture(),previous=UnitWebBridge.prototype.capture;
  UnitWebBridge.prototype.capture=async()=>{calls.capture++;};
  try {
    const snapshot=await bridge.observe('offline','buzzer-off',vectors.buzzer);
    assert.equal(snapshot.evidence_mode,'full');assert.equal(calls.capture,1);
    assert.equal(calls.gesture,1);assert.equal(calls.screenshots,2);
    assert.equal(snapshot.readout_gesture.unit_post_delta,0);assert.equal(snapshot.readout_gesture.all_mutation_delta,0);
    assert.equal(item.record.annotation_snapshots.length,1);
  } finally {UnitWebBridge.prototype.capture=previous;}
});
await test('full-mode-rejects-unit-input-and-other-API-mutations-from-text-gesture',async()=>{
  const previous=UnitWebBridge.prototype.capture;
  UnitWebBridge.prototype.capture=async()=>{};
  try {
    for (const gestureMutation of ['unit','other']) {
      const {bridge,item}=transportFixture({gestureMutation});
      await assert.rejects(bridge.observe('offline','gesture-must-not-write',vectors.buzzer));
      assert.equal(item.record.annotation_snapshots.length,0);
    }
  } finally {UnitWebBridge.prototype.capture=previous;}
});
await test('unsupported-evidence-mode-is-rejected-before-observation',async()=>{
  const {bridge,calls}=transportFixture();
  await assert.rejects(bridge.observe('offline','bad-mode',vectors.buzzer,'external1','screenshot-only'),/unsupported annotation evidence mode/);
  assert.equal(calls.evaluate,0);assert.equal(calls.capture,0);
});

const sources=['platform/tests/unit_annotation_bridge.mjs','platform/tests/test_unit_annotation_bridge.mjs',
  'platform/web/unit-annotations.js','platform/units/catalog.json'];
const report={schema_version:1,category:'offline-annotation-bridge-oracle-and-transport-fixtures',
  status:cases.every(row=>row.status==='PASS') ? 'PASS' : 'FAIL',cases,
  source_sha256:Object.fromEntries(await Promise.all(sources.map(async path=>[path,createHash('sha256').update(await readFile(resolve(root,path))).digest('hex')]))),
  browser_execution:'NOT RUN',firmware_execution:'NOT RUN',hardware_execution:'NOT RUN',
  api_contacted:false,sessions_started:0,fixture_scope:'Synthetic in-memory DOM/HTTP snapshots only; no live evidence is produced.'};
if(process.argv[2]) await writeFile(resolve(process.argv[2]),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(report,null,2));
process.exitCode=report.status==='PASS' ? 0 : 1;
