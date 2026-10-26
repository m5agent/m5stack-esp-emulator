// Candidate shadow server and browser-only fixtures. No Device Service/API/QEMU.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {dirname, resolve, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const work = dirname(fileURLToPath(import.meta.url));
const root = resolve(work, '../..');
const require = createRequire(resolve(root, 'platform/tests/package.json'));
const {chromium} = require('playwright');
const output = resolve(work, process.env.M5_UNIT_ANNOTATION_OUT || 'browser-only-results');
await mkdir(output, {recursive: true});
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const hosts = JSON.parse(await readFile(resolve(root, 'platform/units/host-ports.json'), 'utf8'));
const archive = resolve(root, 'docs/evidence/2026-10-26-unit-host-web-gen9-a8fe');
const env = JSON.parse(await readFile(resolve(archive, 'controller/atoms3r/env-iii/result.json'), 'utf8')).unit_state.units[0];
const relay = JSON.parse(await readFile(resolve(archive, 'controller/atoms3r/relay/result.json'), 'utf8')).unit_state.units[0];
const report = {schema_version: 1, category: 'browser-only-candidate', status: 'FAIL',
  scope: 'Shadow files only. Browser fixtures/replayed values are not new controller, guest or hardware evidence.',
  firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN', promoted: false, checks: {}, errors: [], screenshots: []};
const harness = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/platform/web/app.css"><link rel="stylesheet" href="/platform/web/sessions.css"><link rel="stylesheet" href="/platform/web/three-device-viewer.css">
<link rel="stylesheet" href="/platform/web/unit-panel.css"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/m5-brand.css">
<style>html,body{margin:0;background:#fff;color:#434343}body{padding:16px;box-sizing:border-box}.session-card{max-width:1100px}h1{font:600 16px sans-serif;color:#0064c2}</style>
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
<h1>候选 · 浏览器回放（固件未执行）</h1><div class="session-card"><div id="host" class="session-visual is-three"></div><div class="session-body"><div id="panel"></div></div></div>`;
const mime = {'.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'};
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname === '/__candidate__') {res.setHeader('Content-Type','text/html');res.end(harness);return;}
  if (pathname.startsWith('/api/')) {res.writeHead(500);res.end('No Device Service');return;}
  try {
    const relative = '.' + decodeURIComponent(pathname);
    const real = resolve(root, relative), shadow = resolve(work, 'candidate', relative);
    assert.ok(real.startsWith(root + '/') && shadow.startsWith(resolve(work, 'candidate') + '/'));
    const data = await readFile(shadow).catch(() => readFile(real));
    res.setHeader('Content-Type',mime[extname(real)] || 'application/octet-stream');res.end(data);
  } catch {res.writeHead(404);res.end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('request', req => {if (req.method() !== 'GET') report.errors.push(`Unexpected ${req.method()} ${new URL(req.url()).pathname}`);});
  await page.goto(`http://127.0.0.1:${server.address().port}/__candidate__`);
  await page.evaluate(async ({catalog,hosts,env,relay}) => {
    const {createModelShell} = await import('/platform/web/model-shell.js');
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    const annotations = await import('/platform/web/unit-annotations.js');
    window.definitions = new Map(catalog.units.map(unit => [unit.id,unit]));
    window.annotations = annotations; window.THREE = await import('three');
    window.shell = await createModelShell(document.querySelector('#host'),{id:'cores3',name:'CoreS3'},{live:true});
    window.apiCalls = []; window.inputEcho = []; window.touchEcho = []; window.trustedPointers = [];
    shell.on('touch', event => touchEcho.push(event));
    shell.viewer.renderer.domElement.addEventListener('pointerdown', event => trustedPointers.push(event.isTrusted));
    shell.on('unit-input', event => inputEcho.push(event));
    window.mountFixture = async (unitId, properties) => {
      window.panel?.dispose?.(); shell.detachUnit('grove');
      const unit = {id:'external1',unit_id:unitId,port_id:'port-a',visual_port:'grove',available:true,properties,errors:{},source:'guest-qom'};
      window.session = {session_id:'browser-fixture',device_id:'cores3',state:'running',units:[unit]};
      window.payload = {session_id:'browser-fixture',state:'running',source:'live',units:[unit],definitions:[definitions.get(unitId)]};
      window.panel = await createUnitPanel(document.querySelector('#panel'),{session,shell,api:async (path,options={}) => {
        apiCalls.push({path,method:options.method || 'GET'});
        if (options.method) throw new Error('Annotation must never submit an input');
        return path.includes('/sessions/') ? structuredClone(payload) : {units:catalog.units,hosts:hosts.hosts.filter(host => host.device_id==='cores3')};
      }});
    };
    window.replay = {env:env.properties,relay:relay.properties};
    await mountFixture('env-iii',replay.env);
  },{catalog,hosts,env,relay});
  await page.waitForFunction(() => document.querySelector('[data-annotation-field="temperature-c"]'));
  const inspect = () => page.evaluate(() => {
    const host = document.querySelector('#host').getBoundingClientRect();
    return [...document.querySelectorAll('.unit-annotation:not([hidden])')].map(node => {
      const rect = node.getBoundingClientRect();
      return {text:node.textContent,anchor:node.dataset.annotationAnchor,port:node.dataset.annotationPort,
        bounds:[rect.left-host.left,rect.top-host.top,rect.right-host.left,rect.bottom-host.top],host:[host.width,host.height],
        pointer_events:getComputedStyle(node).pointerEvents,font_size:getComputedStyle(node.querySelector('dd')||node).fontSize,fields:[...node.querySelectorAll('[data-annotation-field]')].map(field => [field.dataset.annotationField,field.textContent])};
    });
  });
  const captureRail = async (prefix, count) => {
    const results = {};
    for (const width of [1440,1024,768,390]) {
      await page.setViewportSize({width,height:1000});
      await page.evaluate(() => {shell.viewer.resize();shell.viewer.fit({duration:0});});
      await page.waitForTimeout(100);
      const notes = await inspect(); assert.equal(notes.length,count);
      const geometry = await page.evaluate(() => {
        const canvas = shell.viewer.renderer.domElement.getBoundingClientRect();
        const rect = node => {const r=node.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom];};
        const cards=[...document.querySelectorAll('.unit-annotation')].map(node=>({bounds:rect(node),fields:node.querySelectorAll('dd').length,index:node.dataset.annotationIndex,title:node.querySelector('strong')?.textContent}));
        const protectedBoxes=[];
        for(const component of shell.model.list().filter(c=>!c.path.includes('/') && (c.kind==='display'||c.interactive))) {
          const box=new THREE.Box3().setFromObject(component.object3d);if(box.isEmpty())continue;
          const points=[];for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]) {
            const v=new THREE.Vector3(x,y,z).project(shell.viewer.camera);if(v.z>=-1&&v.z<=1)points.push([canvas.left+(v.x+1)*canvas.width/2,canvas.top+(1-v.y)*canvas.height/2]);
          }
          if(!points.length)continue;
          protectedBoxes.push({path:component.path,kind:component.kind,bounds:[Math.max(canvas.left,Math.min(...points.map(p=>p[0]))),Math.max(canvas.top,Math.min(...points.map(p=>p[1]))),Math.min(canvas.right,Math.max(...points.map(p=>p[0]))),Math.min(canvas.bottom,Math.max(...points.map(p=>p[1])))]});
        }
        return {canvas:[canvas.left,canvas.top,canvas.right,canvas.bottom],rail:rect(document.querySelector('.unit-readout-rail')),cards,protectedBoxes,
          leaderPointerEvents:getComputedStyle(document.querySelector('.unit-annotation-layer')).pointerEvents,
          markers:[...document.querySelectorAll('.unit-annotation-marker')].map(node=>({port:node.dataset.annotationPort,index:node.textContent,pointer:getComputedStyle(node).pointerEvents}))};
      });
      for(const note of notes){assert.ok(note.bounds[0]>=0 && note.bounds[1]>=0 && note.bounds[2]<=note.host[0] && note.bounds[3]<=note.host[1]);assert.equal(note.font_size,'16px');}
      assert.ok(geometry.rail[1]>=geometry.canvas[3]-0.5,'all values must be outside the canvas');
      assert.equal(geometry.leaderPointerEvents,'none');
      for(const card of geometry.cards){assert.ok(card.bounds[1]>=geometry.canvas[3],'readout card overlaps canvas');assert.ok(card.fields>0,'readouts cannot all be hidden to pass placement');}
      for(const a of geometry.cards)for(const b of geometry.protectedBoxes)assert.ok(a.bounds[2]<=b.bounds[0]||b.bounds[2]<=a.bounds[0]||a.bounds[3]<=b.bounds[1]||b.bounds[3]<=a.bounds[1],'readout covers a display/control projection');
      for(const a of geometry.cards)for(const b of geometry.cards)if(a!==b)assert.ok(a.bounds[2]<=b.bounds[0]||b.bounds[2]<=a.bounds[0]||a.bounds[3]<=b.bounds[1]||b.bounds[3]<=a.bounds[1],'readout cards overlap');
      assert.ok(geometry.markers.every(marker=>marker.pointer==='none'));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
      const file=`${prefix}-${width}.png`;await page.screenshot({path:resolve(output,file),fullPage:true});report.screenshots.push(file);results[width]={notes,geometry};
    }
    return results;
  };
  let notes = await inspect();
  assert.deepEqual(notes[0].fields,[['temperature-c','18.75 °C'],['humidity-pct','45.5 %RH'],['pressure-pa','103200 Pa']]);
  assert.ok(notes[0].text.includes('模拟输入') && !notes[0].text.includes('固件输出'));
  assert.equal(notes[0].anchor,'grove/sensor');
  report.checks.exact_present_readback_and_direction = true;
  report.viewport_notes = await captureRail('env',1);
  report.checks.responsive_1440_1024_768_390 = true;
  report.checks.canvas_display_controls_not_occluded = true;
  const before = await page.locator('.unit-annotation-marker').evaluate(node => [node.style.left,node.style.top]);
  await page.evaluate(() => shell.viewer.setView('right',{duration:0}));await page.waitForTimeout(100);
  const after = await page.locator('.unit-annotation-marker').evaluate(node => [node.style.left,node.style.top]);
  assert.notDeepEqual(before,after);report.checks.follows_real_anchor_rotation = true;
  await page.evaluate(() => shell.viewer.setView('front',{duration:0}));
  // The public setView(0) still settles on the next viewer render. Do not fit
  // a newly attached module against the previous orientation's narrow box.
  await page.waitForTimeout(100);
  const pure = await page.evaluate(() => {
    const definition = definitions.get('env-iii');
    const read = properties => annotations.annotationReadback({unit_id:'env-iii',available:true,source:'guest-qom',properties},definition,{running:true,source:'live',frozenDefinitions:true});
    return {missing:read({}).groups,invalid:read({'temperature-c':NaN}).groups,
      persisted:annotations.annotationReadback(payload.units[0],definition,{running:true,source:'persisted',frozenDefinitions:true}).groups,
      range:read({'temperature-c':999,'humidity-pct':101,'pressure-pa':-1}).groups,
      unitPersisted:annotations.annotationReadback({...payload.units[0],source:'persisted'},definition,{running:true,source:'live',frozenDefinitions:true}).groups,
      unitMissingSource:annotations.annotationReadback({...payload.units[0],source:undefined},definition,{running:true,source:'live',frozenDefinitions:true}).groups,
      inventory:annotations.annotationReadback(payload.units[0],definition,{running:true,source:'live',frozenDefinitions:false}).groups,
      thermal:annotations.annotationReadback({unit_id:'thermal',source:'guest-qom',available:true,properties:{'control-word':7,'raw-fixture-ready':true}},definitions.get('thermal'),{running:true,source:'live',frozenDefinitions:true}).groups.map(group=>({label:group.label,values:group.rows.map(row=>row.value)}))};
  });
  assert.deepEqual(pure,{missing:[],invalid:[],persisted:[],range:[],unitPersisted:[],unitMissingSource:[],inventory:[],thermal:[{label:'控制寄存器状态',values:['7']},{label:'模型状态',values:['true']}]});
  report.checks.no_defaults_invalid_values_or_persisted_live_readings = true;
  report.checks.schema_range_and_double_source_contract_fail_closed = true;
  report.checks.thermal_register_and_derived_model_origins = true;
  await page.evaluate(() => {payload.units[0].available=false;panel.apply(payload);});
  assert.equal(await page.locator('.unit-annotation dd').count(),0);report.checks.unavailable_clears_values = true;
  await page.evaluate(() => {payload.units[0].available=true;panel.apply(payload);panel.updateSession({...session,state:'stopped'});});
  assert.equal(await page.locator('.unit-annotation dd').count(),0);report.checks.terminal_clears_values = true;
  await page.evaluate(async () => mountFixture('relay',replay.relay));
  await page.waitForSelector('.unit-annotation:not([hidden])');
  notes = await inspect();assert.deepEqual(notes[0].fields,[['output-level',String(relay.properties['output-level'])]]);
  assert.ok(notes[0].text.includes('固件输出') && !notes[0].text.includes('模拟输入'));
  const physical = await page.evaluate(() => {
    const before = shell.model.list().map(c => [c.path,c.kind,c.getState?.()]);
    for(let i=0;i<20;i++) shell.updateUnitAnnotation(payload.units[0],{port:'grove',definition:definitions.get('relay'),running:true,source:'live',frozenDefinitions:true});
    return {same:JSON.stringify(before)===JSON.stringify(shell.model.list().map(c => [c.path,c.kind,c.getState?.()])),inputs:inputEcho.length,posts:apiCalls.filter(c=>c.method!=='GET').length};
  });
  assert.deepEqual(physical,{same:true,inputs:0,posts:0});report.checks.relay_annotation_does_not_create_actuator_or_echo = true;
  report.relay_viewports = await captureRail('relay',1);
  const interaction = await page.evaluate(() => {
    const display=shell.model.find('lcd','display'),point=display.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera);
    const canvas=shell.viewer.renderer.domElement,rect=canvas.getBoundingClientRect();
    const x=rect.left+(point.x+1)*rect.width/2,y=rect.top+(1-point.y)*rect.height/2;
    return {x,y,canvasHit:document.elementFromPoint(x,y)===canvas,touches:touchEcho.length};
  });
  assert.equal(interaction.canvasHit,true);
  await page.mouse.click(interaction.x,interaction.y);
  const received=await page.evaluate(()=>({touches:touchEcho.map(event=>event.down),trusted:trustedPointers.at(-1)}));
  assert.deepEqual(received.touches.slice(interaction.touches),[true,false]);assert.equal(received.trusted,true);
  report.trusted_canvas_interaction=received;report.checks.trusted_display_touch_survives_readout_rail=true;
  const anchors = await page.evaluate(async () => {
    panel.dispose();const found=[];
    for(const id of annotations.ANNOTATED_UNITS) {await shell.attachUnit(id);const sensor=shell.model.find('grove/sensor');found.push({id,path:sensor?.path,role:sensor?.meta?.role});shell.detachUnit();}
    return found;
  });
  assert.equal(anchors.length,12);assert.ok(anchors.every(a=>a.path==='grove/sensor'&&a.role==='visual-anchor'));report.anchor_inventory=anchors;
  report.checks.twelve_real_sensor_anchors = true;
  await page.evaluate(async () => {
    await shell.attachUnit('hub');
    for(const [i,id] of ['env-iii','tof','color'].entries()) {
      const port=`grove/grove-${i+1}`;await shell.attachUnit(id,{port});
      const properties=id==='env-iii'?replay.env:id==='tof'?{'distance-mm':382}:{'clear-raw':1700,'red-raw':430,'green-raw':530,'blue-raw':740};
      shell.updateUnitAnnotation({unit_id:id,available:true,source:'guest-qom',properties},{port,definition:definitions.get(id),running:true,source:'live',frozenDefinitions:true});
    }
    // An unsupported parent annotation must not erase its children.
    shell.updateUnitAnnotation({unit_id:'hub',available:true,source:'guest-qom',properties:{}},{port:'grove',definition:definitions.get('hub'),running:true,source:'live',frozenDefinitions:true});
    shell.viewer.resize();shell.viewer.fit({duration:0});
  });
  await page.waitForTimeout(100);notes = await inspect();assert.equal(notes.length,3);
  report.nested_notes=await captureRail('nested',3);
  report.checks.nested_real_paths_and_nonoverlap=true;
  report.checks.all_nested_values_remain_visible_in_rail=true;
  await page.evaluate(() => shell.detachUnit());assert.equal(await page.locator('.unit-annotation').count(),0);
  await page.evaluate(() => shell.dispose());assert.equal(await page.locator('.unit-annotation-layer').count(),0);
  report.checks.detach_dispose_remove_notes = true;
  assert.deepEqual(report.errors,[]);report.status='PASS';
} catch(error) {
  report.error=error.stack;
  const page=browser?.contexts()[0]?.pages()[0];
  if(page) {
    report.failure_dom=await page.evaluate(() => ({annotations:[...document.querySelectorAll('.unit-annotation')].map(n=>({text:n.textContent,hidden:n.hidden})),items:window.shell?.unitAnnotations?.items.size,mounted:window.panel?.mounted?.size,source:window.panel?.stateSource})).catch(()=>null);
    await page.screenshot({path:resolve(output,'failure.png'),fullPage:true}).catch(()=>{});
    report.screenshots.push('failure.png');
  }
}
finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
report.screenshot_sha256 = Object.fromEntries(await Promise.all(report.screenshots.map(async name => [name,createHash('sha256').update(await readFile(resolve(output,name))).digest('hex')])));
await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,checks:report.checks,error:report.error,screenshots:report.screenshots},null,2));
process.exitCode=report.status==='PASS'?0:1;
