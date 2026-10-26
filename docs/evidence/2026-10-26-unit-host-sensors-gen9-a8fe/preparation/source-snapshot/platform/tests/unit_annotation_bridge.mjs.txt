// Annotation test adapter. Product behavior and the common bridge are unchanged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {UnitWebBridge} from './unit_web_bridge.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const {chromium} = createRequire(resolve(root, 'platform/tests/package.json'))('playwright');
const hash = data => createHash('sha256').update(data).digest('hex');
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const extraAssets = ['platform/web/unit-annotations.js', 'platform/web/unit-panel.js',
  'platform/web/unit-panel.css', 'platform/web/model-shell.js', 'platform/web/unit-assembly-layout.js'];

// Independent test oracle for the current twelve readouts. Schema direction
// alone never decides origin: Thermal's input is a controller register and its
// output is fixture readiness. Unknown scalar fields require explicit review.
const input = (type, unit = '') => ['inputs', '模拟输入', type, unit];
const output = (type, unit = '') => ['outputs', '固件输出', type, unit];
export const ANNOTATION_CONTRACT = Object.freeze({
  'env-iii': {'temperature-c':input('number','degC'),'humidity-pct':input('number','%RH'),'pressure-pa':input('number','Pa')},
  pir: {motion:input('boolean')},
  'ultrasonic-i2c': {'distance-mm':input('number','mm')},
  color: {'clear-raw':input('integer','raw16'),'red-raw':input('integer','raw16'),'green-raw':input('integer','raw16'),'blue-raw':input('integer','raw16')},
  tof: {'distance-mm':input('integer','mm')},
  light: {'analog-mv':input('number','mV'),'digital-level':input('boolean')},
  relay: {'output-level':output('boolean')},
  ncir: {'ambient-c':input('number','degC'),'object-c':input('number','degC')},
  heart: {'ir-sample':input('integer','raw16'),'red-sample':input('integer','raw16')},
  thermal: {'control-word':['inputs','控制寄存器状态','integer',''],'raw-fixture-ready':['outputs','模型状态','boolean','']},
  tvoc: {'eco2-ppm':input('integer','ppm'),'tvoc-ppb':input('integer','ppb'),'raw-h2':input('integer','raw16'),'raw-ethanol':input('integer','raw16')},
  buzzer: {'frequency-hz':output('number','Hz'),'duty-pct':output('number','%')},
});

export function validateExpectedScalars(unitId, expected) {
  const contract = Object.hasOwn(ANNOTATION_CONTRACT,unitId) ? ANNOTATION_CONTRACT[unitId] : null;
  assert.ok(contract, `no annotation contract for ${unitId}`);
  assert.ok(expected && typeof expected === 'object' && !Array.isArray(expected) && Object.keys(expected).length, 'expected scalar fields are required');
  for (const [field,value] of Object.entries(expected)) {
    const descriptor = Object.hasOwn(contract,field) ? contract[field] : null;
    assert.ok(descriptor, `not an annotation scalar: ${unitId}.${field}`);
    assert.equal(typeof value, descriptor[2] === 'boolean' ? 'boolean' : 'number', `expected scalar type: ${field}`);
    if (typeof value === 'number') assert.ok(Number.isFinite(value) && (descriptor[2] !== 'integer' || Number.isInteger(value)), `expected finite scalar: ${field}`);
  }
  return contract;
}

export function validateAnnotationSemantics(snapshot, expected) {
  const unit = snapshot.readback, definition = snapshot.definition;
  const contract = validateExpectedScalars(unit?.unit_id, expected);
  assert.equal(snapshot.session_state, 'running');
  assert.equal(snapshot.panel_state, 'running');
  assert.equal(snapshot.state_source, 'live');
  assert.equal(snapshot.frozen_definitions, true);
  assert.equal(unit.available, true);
  assert.equal(unit.source, 'guest-qom');
  assert.deepEqual(unit.errors || {}, {});
  assert.equal(definition?.id, unit.unit_id, 'frozen definition identity differs');
  const groups = new Map(), rows = [], found = new Set();
  for (const direction of ['inputs','outputs']) {
    for (const [field,schema] of Object.entries(definition[direction] || {})) {
      if (!['boolean','number','integer'].includes(schema.type)) continue;
      const descriptor = Object.hasOwn(contract,field) ? contract[field] : null;
      assert.ok(descriptor, `unreviewed annotation scalar: ${unit.unit_id}.${field}`);
      assert.deepEqual([direction,schema.type,schema.unit || ''], [descriptor[0],descriptor[2],descriptor[3]], `annotation field semantics differ: ${field}`);
      assert.ok(!found.has(field), `duplicate annotation scalar: ${field}`);
      found.add(field);
      assert.ok(Object.hasOwn(unit.properties || {},field), `missing controller scalar: ${field}`);
      const value = unit.properties[field];
      assert.equal(typeof value,schema.type === 'boolean' ? 'boolean' : 'number', `controller scalar type: ${field}`);
      if (typeof value === 'number') assert.ok(Number.isFinite(value) && (schema.type !== 'integer' || Number.isInteger(value)), `controller finite scalar: ${field}`);
      assert.ok((schema.minimum === undefined || value >= schema.minimum) && (schema.maximum === undefined || value <= schema.maximum)
        && (!schema.enum || schema.enum.includes(value)), `controller scalar range: ${field}`);
      const unitText = schema.unit === 'degC' ? '°C' : schema.unit || '';
      const row = {field,direction,value,text:String(value)+(unitText ? ` ${unitText}` : '')};
      rows.push(row);
      if (!groups.has(descriptor[1])) groups.set(descriptor[1], {label:descriptor[1],fields:[]});
      groups.get(descriptor[1]).fields.push({field,label:schema.label || field,text:row.text});
    }
  }
  assert.deepEqual([...found].sort(),Object.keys(contract).sort(),'annotation scalar schema is incomplete');
  for (const [field,value] of Object.entries(expected)) assert.equal(unit.properties[field],value,`expected live ${field}`);
  assert.deepEqual(snapshot.note?.fields,rows.map(({field,text})=>({field,text})),'DOM scalar fields differ from the controller');
  assert.deepEqual(snapshot.note?.labels,[...groups.keys()],'DOM source labels differ');
  assert.deepEqual(snapshot.note?.groups,[...groups.values()],'DOM field labels or source grouping differ');
  return {rows,groups:[...groups.values()]};
}

export function claimAnnotationPhase(item, phase) {
  assert.equal(typeof phase,'string');
  assert.match(phase,/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/,'unsafe annotation phase');
  item.annotationPhases ||= new Set();
  assert.ok(!item.annotationPhases.has(phase),'annotation phase already recorded or attempted');
  item.annotationPhases.add(phase);
}

export class AnnotationBridge extends UnitWebBridge {
  async prepare() {
    if (this.prepared) return super.prepare();
    const expected = Object.fromEntries(await Promise.all(extraAssets.map(async name => [name,hash(await readFile(resolve(root,name)))])));
    if (!this.browser) this.browser = await chromium.launch({
      executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'],
    });
    const page = await this.browser.newPage({viewport:{width:1440,height:1100},hasTouch:true});
    const assets = [], assetErrors = [], mutations = [];
    page.on('request', request => {
      if (!['GET','HEAD','OPTIONS'].includes(request.method())) mutations.push({at:new Date().toISOString(),
        method:request.method(),path:new URL(request.url()).pathname,body:request.postData()});
    });
    // Observe the actual served bytes before executing them. No content changes.
    await page.route(url => extraAssets.includes(new URL(url).pathname.slice(1)), async route => {
      const name = new URL(route.request().url()).pathname.slice(1);
      try {
        const response = await route.fetch();
        const sha256 = hash(await response.body());
        assert.equal(sha256, expected[name], `served source drift: ${name}`);
        assert.equal(response.ok(), true, `served asset unavailable: ${name}`);
        assets.push({file:name,sha256,status:response.status(),verification:'actual HTTP body before application execution'});
        await route.fulfill({response});
      } catch(error) {assetErrors.push({file:name,error:String(error.message)});await route.abort();}
    });
    // Feed the already-instrumented page to the inherited prepare; its original
    // source export and navigation remain unchanged. Only test browser creation
    // is adapted, never a product function, HTTP body, controller or fixture.
    const createPage = this.browser.newPage;
    this.browser.newPage = async () => page;
    let result;
    try {result = await super.prepare();}
    finally {this.browser.newPage = createPage;}
    Object.assign(this.prepared.source_sha256,expected);
    this.prepared.annotationAssets=assets;
    this.prepared.annotationAssetErrors=assetErrors;
    this.prepared.annotationMutations=mutations;
    return result;
  }

  async open(session) {
    if (this.sessions.has(session.session_id)) return super.open(session);
    await this.prepare();
    const prepared = this.prepared;
    const result = await super.open(session);
    const item = this.item(session.session_id);
    item.annotationAssets = prepared.annotationAssets;
    item.record.annotation_asset_errors = prepared.annotationAssetErrors;
    item.record.annotation_mutation_requests = prepared.annotationMutations;
    item.record.annotation_snapshots = [];
    item.record.annotation_http_bodies = [];
    item.annotationBodyIndex = 0;
    item.page.on('response', response => {
      const path = new URL(response.url()).pathname;
      if (response.request().method() !== 'GET' || path !== `/api/v1/sessions/${session.session_id}/units`) return;
      const name = `annotation-http-${String(++item.annotationBodyIndex).padStart(4,'0')}.json`;
      const task = (async () => {
        try {
          const body = await response.body();
          await writeFile(resolve(item.directory,name),body,{flag:'wx'});
          item.record.annotation_http_bodies.push({at:new Date().toISOString(),method:'GET',path,status:response.status(),
            body_file:name,body_bytes:body.length,body_sha256:hash(body),response:JSON.parse(body.toString('utf8'))});
        } catch(error) {item.record.errors.push(`annotation HTTP body: ${error.message}`);}
      })();
      item.responseTasks.add(task);
      task.finally(()=>item.responseTasks.delete(task));
    });
    item.record.annotation_transport = 'Test subclass of unchanged UnitWebBridge; observe-only evaluate, actual product controls, unmodified HTTP assets and live API responses.';
    return result;
  }

  async observe(id, phase, expected, instance = 'external1', evidenceMode = 'full') {
    const item = this.item(id);
    assert.ok(['state','full'].includes(evidenceMode),'unsupported annotation evidence mode');
    claimAnnotationPhase(item,phase);
    const attachment = item.record.attachments.find(unit=>unit.id===instance);
    validateExpectedScalars(attachment?.unit_id,expected);
    const phaseEntry={at:new Date().toISOString(),readbacks_index:item.record.readbacks.length,
      http_bodies_index:item.record.annotation_http_bodies.length};
    if (evidenceMode === 'full') await super.capture(id, 'observed-units', false);
    let snapshot, match, bodyMatch, semantics;
    for (let attempt = 0; attempt < 80; attempt++) {
      snapshot = await item.page.evaluate(async ({id,instance}) => {
        const {Box3,Vector3} = await import('/platform/web/vendor/three/three.module.js');
        const visual = window.__unitWebBridgeProbe?.state.visuals.get(id);
        const panel = visual?.unitPanel;
        const state = panel?.states.get(instance);
        const mounted = panel?.mounted.get(instance);
        const definition = panel?.definitions.get(state?.unit_id);
        const card = document.querySelector(`[data-session-id="${id}"]`);
        const note = [...(card?.querySelectorAll('.unit-annotation[data-annotation-port]') || [])].find(note => note.dataset.annotationPort === mounted?.port);
        const rect = node => {const r = node?.getBoundingClientRect(); return r ? {x:r.x,y:r.y,left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height} : null;};
        const canvas = visual?.shell?.viewer?.renderer?.domElement;
        const canvasBounds = rect(canvas);
        const protectedBoxes = [];
        for (const component of visual?.shell?.model?.list() || []) {
          if (!(component.interactive || component.kind === 'display')) continue;
          let visible = true;
          for (let object=component.object3d;object;object=object.parent) if (!object.visible) visible=false;
          if (!visible) continue;
          const box = new Box3().setFromObject(component.object3d);
          if (box.isEmpty() || !canvasBounds) continue;
          const points = [];
          for (const x of [box.min.x,box.max.x]) for (const y of [box.min.y,box.max.y]) for (const z of [box.min.z,box.max.z]) {
            const point = new Vector3(x,y,z).project(visual.shell.viewer.camera);
            if (point.z>=-1 && point.z<=1) points.push([canvasBounds.left+(point.x+1)*canvasBounds.width/2,canvasBounds.top+(1-point.y)*canvasBounds.height/2]);
          }
          if (!points.length) continue;
          const bounds = {left:Math.max(canvasBounds.left,Math.min(...points.map(p=>p[0]))),
            top:Math.max(canvasBounds.top,Math.min(...points.map(p=>p[1]))),
            right:Math.min(canvasBounds.right,Math.max(...points.map(p=>p[0]))),
            bottom:Math.min(canvasBounds.bottom,Math.max(...points.map(p=>p[1])))};
          if (bounds.left<=bounds.right && bounds.top<=bounds.bottom) protectedBoxes.push({path:component.path,kind:component.kind,interactive:component.interactive,bounds});
        }
        return {at:new Date().toISOString(), session_state:visual?.session?.state, panel_state:panel?.session?.state,
          state_source:panel?.stateSource, readback:state, mounted_port:mounted?.port,
          definition,frozen_definitions:panel?.frozenDefinitions,
          anchor:note?.dataset.annotationAnchor, anchor_role:visual?.shell?.model?.find(`${mounted?.port}/sensor`)?.meta?.role,
          note:note ? {text:note.textContent, hidden:note.hidden, display:getComputedStyle(note).display,
            labels:[...note.querySelectorAll('.unit-annotation-source')].map(n=>n.textContent),
            fields:[...note.querySelectorAll('[data-annotation-field]')].map(n=>({field:n.dataset.annotationField,text:n.textContent})),
            groups:[...note.querySelectorAll('.unit-annotation-values')].map(list=>({label:list.previousElementSibling?.textContent,
              fields:[...list.querySelectorAll('[data-annotation-field]')].map(n=>({field:n.dataset.annotationField,label:n.previousElementSibling?.textContent,text:n.textContent}))})),
            pointer_events:getComputedStyle(note).pointerEvents,user_select:getComputedStyle(note).userSelect,
            in_readout_rail:!!note.closest('.unit-readout-rail'),inside_canvas_subtree:canvas?.contains(note),
            inside_interactive_stage:!!note.closest('.three-device-stage'),bounds:rect(note)} : null,
          canvas_bounds:canvasBounds, protected_projection_bounds:protectedBoxes,
          horizontal_overflow:document.documentElement.scrollWidth > innerWidth};
      }, {id,instance});
      await Promise.all([...item.responseTasks]);
      match = item.record.readbacks.slice(phaseEntry.readbacks_index).reverse().find(event => event.status === 200
        && event.at >= phaseEntry.at && event.at <= snapshot.at && event.response.source === 'live'
        && event.response.contract_status === 'frozen'
        && event.response.units?.some(unit => unit.id === instance && equal(unit, snapshot.readback))
        && equal(event.response.definitions?.find(unit=>unit.id===snapshot.readback?.unit_id),snapshot.definition));
      bodyMatch = match && item.record.annotation_http_bodies.slice(phaseEntry.http_bodies_index).find(event => event.status === 200
        && event.at >= phaseEntry.at && equal(event.response,match.response));
      try {semantics=validateAnnotationSemantics(snapshot,expected);} catch {semantics=null;}
      if (semantics && match && bodyMatch) break;
      await item.page.waitForTimeout(50);
    }
    semantics=validateAnnotationSemantics(snapshot,expected);
    assert.equal(snapshot.session_state, 'running');
    assert.equal(snapshot.panel_state, 'running');
    assert.equal(snapshot.state_source, 'live');
    assert.equal(snapshot.readback?.available, true);
    assert.equal(snapshot.readback?.source, 'guest-qom');
    assert.deepEqual(snapshot.readback.errors || {}, {});
    for (const [field,value] of Object.entries(expected)) assert.equal(snapshot.readback.properties[field], value, `expected live ${field}`);
    assert.ok(match, 'annotation readback must equal a fresh real product GET after phase entry');
    assert.ok(bodyMatch,'annotation GET must have its fresh actual raw HTTP body and hash after phase entry');
    assert.equal(snapshot.anchor, `${snapshot.mounted_port}/sensor`);
    assert.equal(snapshot.anchor_role, 'visual-anchor');
    assert.equal(snapshot.note?.hidden, false);
    assert.notEqual(snapshot.note.display, 'none');
    assert.ok(snapshot.note.bounds.width > 0 && snapshot.note.bounds.height > 0);
    assert.equal(snapshot.note.in_readout_rail,true);
    assert.equal(snapshot.note.inside_canvas_subtree,false);
    assert.equal(snapshot.note.inside_interactive_stage,false);
    const separate = (a,b) => a.right<=b.left || b.right<=a.left || a.bottom<=b.top || b.bottom<=a.top;
    assert.ok(snapshot.canvas_bounds?.width>0 && snapshot.canvas_bounds?.height>0,'actual canvas bounds required');
    assert.ok(separate(snapshot.note.bounds,snapshot.canvas_bounds),'readout must not cover the actual canvas');
    assert.ok(snapshot.protected_projection_bounds.length>0,'actual display/control projection must be observed');
    for (const component of snapshot.protected_projection_bounds) assert.ok(separate(snapshot.note.bounds,component.bounds),`readout covers actual ${component.path} projection`);
    snapshot.readout_outside_interactive_canvas = true;
    assert.equal(snapshot.horizontal_overflow, false);
    snapshot.expected_scalar_rows=semantics.rows;
    snapshot.expected_source_groups=semantics.groups;
    snapshot.phase = phase;
    snapshot.phase_entry=phaseEntry;
    snapshot.phase_verified_at=new Date().toISOString();
    snapshot.instance_id = instance;
    snapshot.http_event_index = item.record.readbacks.indexOf(match);
    snapshot.http_body_event_index=item.record.annotation_http_bodies.indexOf(bodyMatch);
    snapshot.http_observation = match;
    snapshot.http_body_observation = bodyMatch;
    snapshot.exact_http_controller_dom_alignment = true;
    snapshot.evidence_mode = evidenceMode;
    snapshot.evidence_scope = evidenceMode === 'state' ? 'live-state-observation' : 'live-state-observation-with-subsequent-gesture-and-screenshots';
    if (evidenceMode === 'state') {
      // Fast guest phases retain exact state/DOM/HTTP and geometry evidence.
      // Screenshots and gestures belong only to a later explicit full phase.
      item.record.annotation_snapshots.push(snapshot);
      item.record.annotation_served_assets = item.annotationAssets;
      await this.save(item);
      return snapshot;
    }
    const count = item.record.posts.length;
    const mutations = item.record.annotation_mutation_requests.length;
    const noteLocator = item.card.locator(`.unit-annotation[data-annotation-port=${JSON.stringify(snapshot.mounted_port)}]`);
    const readout = noteLocator.locator('[data-annotation-field]').first();
    await readout.scrollIntoViewIfNeeded();
    // Locator actionability prevents a sticky header from receiving the gesture.
    // pointer-events alone does not decide whether this ordinary DOM path works.
    await readout.dblclick({delay:20});
    const hitTest = await readout.evaluate(node => {
      const r=node.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
      const hit=document.elementFromPoint(x,y),selection=getSelection();
      return {x,y,inside_readout:hit===node || node.contains(hit),selection:selection?.toString() || '',
        selection_anchor_inside:!!selection?.anchorNode && node.contains(selection.anchorNode)};
    });
    assert.equal(hitTest.inside_readout,true,'the actual browser hit must remain in the readout');
    await item.page.waitForTimeout(100);
    await Promise.all([...item.responseTasks]);
    assert.equal(item.record.posts.length, count, 'annotation must not produce an input POST');
    assert.equal(item.record.annotation_mutation_requests.length,mutations,'readout text gesture must not mutate any API endpoint');
    snapshot.readout_gesture={kind:'actionable-locator-double-click',unit_post_delta:0,all_mutation_delta:0,hit_test:hitTest};
    await readout.click({trial:true});
    const small = `annotation-${phase}-readout.png`;
    await noteLocator.screenshot({path:resolve(item.directory,small),timeout:30000});
    snapshot.readout_screenshot=small;
    await item.page.evaluate(() => window.scrollTo({top:0,left:0,behavior:'instant'}));
    const name = `annotation-${phase}.png`;
    await item.page.screenshot({path:resolve(item.directory,name),fullPage:true});
    snapshot.screenshot = name;
    item.record.annotation_snapshots.push(snapshot);
    item.record.annotation_served_assets = item.annotationAssets;
    await this.save(item);
    return snapshot;
  }

  async terminal(id) {
    const item = this.item(id);
    const responsePromise = item.page.waitForResponse(response => response.request().method()==='GET'
      && new URL(response.url()).pathname==='/api/v1/sessions', {timeout:30000});
    responsePromise.catch(()=>{});
    await item.page.locator('#refreshBtn').click();
    const response = await responsePromise;
    assert.equal(response.ok(),true);
    const terminalBody=await response.body();
    await writeFile(resolve(item.directory,'annotation-terminal-sessions.json'),terminalBody,{flag:'wx'});
    const httpSession = JSON.parse(terminalBody.toString('utf8')).sessions.find(session=>session.session_id===id);
    assert.ok(['stopped','failed'].includes(httpSession?.state));
    await item.page.waitForFunction(id => {
      const visual = window.__unitWebBridgeProbe?.state.visuals.get(id);
      const card = document.querySelector(`[data-session-id="${id}"]`);
      return ['stopped','failed'].includes(visual?.session?.state) && !!card?.querySelector('.unit-annotation[data-annotation-port]')
        && card.querySelectorAll('[data-annotation-field]').length === 0;
    }, id, {timeout:30000});
    const terminal = await item.page.evaluate(id => {
      const visual = window.__unitWebBridgeProbe?.state.visuals.get(id);
      const card = document.querySelector(`[data-session-id="${id}"]`);
      return {at:new Date().toISOString(),session_state:visual.session.state,panel_state:visual.unitPanel.session.state,
        live_annotation_fields:card.querySelectorAll('[data-annotation-field]').length,
        notes:[...card.querySelectorAll('.unit-annotation[data-annotation-port]')].map(note=>({port:note.dataset.annotationPort,text:note.textContent})),
        controls_disabled:[...card.querySelectorAll('[data-unit-id] input,[data-unit-id] button')].every(control=>control.disabled)};
    }, id);
    assert.ok(['stopped','failed'].includes(terminal.panel_state));
    assert.equal(terminal.live_annotation_fields,0);
    assert.equal(terminal.controls_disabled,true);
    assert.ok(terminal.notes.every(note=>/停止|结束|终止|不可用|未运行/.test(note.text)));
    terminal.http_session_state=httpSession.state;
    terminal.http_body={file:'annotation-terminal-sessions.json',sha256:hash(terminalBody),bytes:terminalBody.length};
    const note = item.card.locator('.unit-annotation[data-annotation-port]').first();
    await note.click({trial:true});
    terminal.readout_hit_test=await note.evaluate(node=>{
      const r=node.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
      return {inside_readout:hit===node || node.contains(hit)};
    });
    assert.equal(terminal.readout_hit_test.inside_readout,true);
    await note.screenshot({path:resolve(item.directory,'annotation-terminal-readout.png'),timeout:30000});
    terminal.readout_screenshot='annotation-terminal-readout.png';
    await item.page.screenshot({path:resolve(item.directory,'annotation-terminal.png'),fullPage:true});
    terminal.screenshot='annotation-terminal.png';
    item.record.annotation_terminal=terminal;
    item.record.annotation_served_assets=item.annotationAssets;
    await this.save(item);
    return terminal;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
const bridge = new AnnotationBridge(process.argv[2], process.argv[3]);
await mkdir(bridge.output,{recursive:true});
for await (const line of createInterface({input:process.stdin,crlfDelay:Infinity})) {
  let watchdog;
  try {
    const {command,...input}=JSON.parse(line);
    watchdog=setTimeout(()=>{
      setTimeout(()=>process.exit(2),5000).unref();
      bridge.shutdown().finally(()=>process.exit(2));
    },150000);
    let result;
    if(command==='prepare') result=await bridge.prepare();
    else if(command==='open') result=await bridge.open(input.session);
    else if(command==='input') result=await bridge.input(input.session_id,input.payload);
    else if(command==='capture') result=await bridge.capture(input.session_id,input.phase,input.screenshot);
    else if(command==='annotation') result=await bridge.observe(input.session_id,input.phase,input.expected,input.instance,input.evidence_mode);
    else if(command==='terminal') result=await bridge.terminal(input.session_id);
    else if(command==='close') result=await bridge.closeSession(input.session_id);
    else if(command==='shutdown') await bridge.shutdown();
    else throw new Error(`Unknown command: ${command}`);
    process.stdout.write(JSON.stringify({ok:true,result})+'\n');
    if(command==='shutdown') break;
  } catch(error) {
    process.stdout.write(JSON.stringify({ok:false,error:String(error.stack||error).replaceAll(root,'<workspace>')})+'\n');
  } finally {clearTimeout(watchdog);}
}
await bridge.shutdown();
}
