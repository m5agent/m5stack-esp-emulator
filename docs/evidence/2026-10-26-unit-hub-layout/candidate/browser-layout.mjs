// Isolated browser geometry / fixture tests. Never calls Device Service.
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
const output = resolve(work, process.env.M5_HUB_LAYOUT_OUT || 'results-r1');
await mkdir(output, {recursive:true});
const catalog = JSON.parse(await readFile(resolve(work,'base/platform/units/catalog.json'),'utf8'));
const report = {schema_version:1,status:'FAIL',category:'browser-only-hub-layout-candidate',
  scope:'CoreS3 with one direct HUB and three compact Units. Fixture values are replayed browser inputs, not guest/controller proof.',
  firmware_execution:'NOT RUN',device_service_execution:'NOT RUN',hardware_execution:'NOT RUN',promoted:false,
  captured_at:new Date().toISOString(),checks:{},screenshots:[],variants:{},errors:[]};
const digest=data=>createHash('sha256').update(data).digest('hex');
const namedSources=['candidate/platform/web/model-shell.js','candidate/platform/web/unit-assembly-layout.js','browser-layout.mjs','frozen-web-sha256.json'];
const sourceHashes=async()=>Object.fromEntries(await Promise.all(namedSources.map(async name=>[name,digest(await readFile(resolve(work,name)))])));
report.source_sha256=await sourceHashes();
const frozen=JSON.parse(await readFile(resolve(work,'frozen-web-sha256.json'),'utf8'));
for(const[name,sha]of Object.entries(frozen))assert.equal(digest(await readFile(resolve(work,'base',name))),sha,'baseline freeze drift: '+name);
const harness=`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/platform/web/app.css"><link rel="stylesheet" href="/platform/web/sessions.css"><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><link rel="stylesheet" href="/platform/web/unit-panel.css"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/m5-brand.css">
<style>html,body{margin:0;background:#fff;color:#434343}body{padding:16px;box-sizing:border-box}.session-card{max-width:1100px}h1{font:600 16px sans-serif;color:#0064c2}</style>
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
<h1>HUB 装配候选 · 浏览器夹具（固件未执行）</h1><div class="session-card"><div id="host" class="session-visual is-three"></div></div>`;
const mime={'.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'};
let browser;
async function startServer(variant){
  const server=createServer(async(req,res)=>{
    const path=new URL(req.url,'http://localhost').pathname;
    if(path==='/__fixture__'){res.setHeader('Content-Type','text/html');res.end(harness);return;}
    if(path.startsWith('/api/')){report.errors.push('Forbidden API call '+path);res.writeHead(500);res.end();return;}
    try{
      const relative='.'+decodeURIComponent(path);
      const base=resolve(work,'base',relative),candidate=resolve(work,'candidate',relative);
      assert.ok(base.startsWith(resolve(work,'base')+'/')&&candidate.startsWith(resolve(work,'candidate')+'/'));
      const data=variant==='after'?await readFile(candidate).catch(()=>readFile(base)):await readFile(base);
      res.setHeader('Content-Type',mime[extname(base)]||'application/octet-stream');res.end(data);
    }catch{res.writeHead(404);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));return server;
}
async function inspect(page){return page.evaluate(()=>{
  const rect=node=>{const r=node.getBoundingClientRect();return[r.left,r.top,r.right,r.bottom];};
  const canvas=shell.viewer.renderer.domElement.getBoundingClientRect();
  const excludeFor=host=>new Set(host.list('port').filter(port=>port.host===host&&port.module).map(port=>port.module.root));
  const physicalMeshes=host=>{
    const result=[],excluded=excludeFor(host),frame=host.find('unitFrame')?.object3d||host.body;
    const visit=object=>{if(excluded.has(object)||!object.visible)return;
      if(object.isMesh&&![object.material].flat().every(material=>material.transparent&&material.opacity===0))result.push(object);
      object.children.forEach(visit);};visit(frame);return result;
  };
  const bounds=meshes=>{const b=new THREE.Box3();for(const mesh of meshes){mesh.geometry.computeBoundingBox();b.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));}return b;};
  const projected=box=>{
    if(box.isEmpty())return null;const p=[];
    for(const x of[box.min.x,box.max.x])for(const y of[box.min.y,box.max.y])for(const z of[box.min.z,box.max.z]){
      const v=new THREE.Vector3(x,y,z).project(shell.viewer.camera);p.push([canvas.left+(v.x+1)*canvas.width/2,canvas.top+(1-v.y)*canvas.height/2]);}
    return[Math.min(...p.map(p=>p[0])),Math.min(...p.map(p=>p[1])),Math.max(...p.map(p=>p[0])),Math.max(...p.map(p=>p[1]))];
  };
  shell.model.root.updateWorldMatrix(true,true);
  const owners=[{id:'host',host:shell.model},...shell.model.list('port').filter(p=>p.module).map(p=>({id:p.path,host:p.module}))];
  const housings=owners.map(({id,host})=>{
    const meshes=physicalMeshes(host),box=bounds(meshes),frame=host.find('unitFrame')?.object3d||host.body;
    const local=box.clone().applyMatrix4(frame.matrixWorld.clone().invert());
    return{id,bounds:projected(box),world:[box.min.toArray(),box.max.toArray()],local:[local.min.toArray(),local.max.toArray()],
      scale:frame.scale.toArray(),pose:host.find('unitFrame')?.getState(),meshCount:meshes.length,hiddenMeshes:meshes.filter(o=>!o.visible).length};
  });
  const protectedBoxes=shell.model.list().filter(c=>c.kind==='display'||c.interactive||c.kind==='port').map(c=>{
    const own=[];const visit=object=>{if(object===c.module?.root)return;if(object.isMesh)own.push(object);object.children.forEach(visit);};visit(c.object3d);
    return{path:c.path,kind:c.kind,interactive:c.interactive,method:'own component geometry; excludes attached module subtree',bounds:projected(bounds(own))};
  }).filter(c=>c.bounds);
  const anchors=shell.model.list().filter(c=>c.meta?.role==='visual-anchor').map(c=>{
    const p=c.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera);return{path:c.path,point:[canvas.left+(p.x+1)*canvas.width/2,canvas.top+(1-p.y)*canvas.height/2]};});
  const cableResults=shell.model.list('cable').map(c=>{
    const state=c.getState(),source=c.source.getWorldPosition(new THREE.Vector3()),target=c.target.getWorldPosition(new THREE.Vector3());
    const a=c.sourcePlug.getWorldPosition(new THREE.Vector3()),b=c.targetPlug.getWorldPosition(new THREE.Vector3());
    const sourceQ=c.source.getWorldQuaternion(new THREE.Quaternion()),targetQ=c.target.getWorldQuaternion(new THREE.Quaternion());
    const targets=protectedBoxes.filter(component=>!component.path.includes('/')&&(component.kind==='display'||component.interactive));
    const screen=v=>{v.project(shell.viewer.camera);return[canvas.left+(v.x+1)*canvas.width/2,canvas.top+(1-v.y)*canvas.height/2];};
    const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    const edge=(a,b,c,d)=>cross(a,b,c)*cross(a,b,d)<=0&&cross(c,d,a)*cross(c,d,b)<=0
      &&Math.max(Math.min(a[0],b[0]),Math.min(c[0],d[0]))<=Math.min(Math.max(a[0],b[0]),Math.max(c[0],d[0]))
      &&Math.max(Math.min(a[1],b[1]),Math.min(c[1],d[1]))<=Math.min(Math.max(a[1],b[1]),Math.max(c[1],d[1]));
    const insideTriangle=(p,a,b,c)=>{const d=[cross(a,b,p),cross(b,c,p),cross(c,a,p)];return d.every(n=>n>=0)||d.every(n=>n<=0);};
    const coveredComponents={};
    for(const target of targets){
      const lcd=target.bounds;let displayTriangles=0;
      const corners=[[lcd[0],lcd[1]],[lcd[2],lcd[1]],[lcd[2],lcd[3]],[lcd[0],lcd[3]]];
      const inRect=p=>p[0]>=lcd[0]&&p[0]<=lcd[2]&&p[1]>=lcd[1]&&p[1]<=lcd[3];
      for(const wire of c.wires){const g=wire.geometry,attr=g.attributes.position,idx=g.index;
        for(let i=0;i<idx.count;i+=3){const p=[0,1,2].map(j=>screen(new THREE.Vector3().fromBufferAttribute(attr,idx.getX(i+j)).applyMatrix4(wire.matrixWorld)));
          if(p.some(inRect)||corners.some(corner=>insideTriangle(corner,...p))||p.some((a,j)=>corners.some((c,k)=>edge(a,p[(j+1)%3],c,corners[(k+1)%4]))))displayTriangles++;
        }
      }
      coveredComponents[target.path]=displayTriangles;
    }
    return{path:c.path,state,sourceErrorMm:source.distanceTo(a),targetErrorMm:target.distanceTo(b),displayTriangles:coveredComponents.lcd,coveredComponents,
      sourceAngleRad:sourceQ.angleTo(c.sourcePlug.getWorldQuaternion(new THREE.Quaternion())),targetAngleRad:targetQ.angleTo(c.targetPlug.getWorldQuaternion(new THREE.Quaternion())),
      wireBounds:projected(bounds(c.wires))};
  });
  const cards=[...document.querySelectorAll('.unit-annotation:not([hidden])')].map(node=>({port:node.dataset.annotationPort,anchor:node.dataset.annotationAnchor,bounds:rect(node),fields:[...node.querySelectorAll('dd')].map(n=>({field:n.dataset.annotationField,text:n.textContent,font:getComputedStyle(n).fontSize}))}));
  const markerBoxes=[...document.querySelectorAll('.unit-annotation-marker')].map(node=>({port:node.dataset.annotationPort,bounds:rect(node),pointer:getComputedStyle(node).pointerEvents}));
  return{canvas:[canvas.left,canvas.top,canvas.right,canvas.bottom],housings,protectedBoxes,anchors,cables:cableResults,
    rail:rect(document.querySelector('.unit-readout-rail')),cards,markerBoxes,horizontalOverflow:document.documentElement.scrollWidth>innerWidth};
});}
function overlap(a,b){return Math.min(a[2],b[2])-Math.max(a[0],b[0])>0.5&&Math.min(a[3],b[3])-Math.max(a[1],b[1])>0.5;}
function pairs(items){const result=[];for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++)if(overlap(items[i].bounds,items[j].bounds))result.push([items[i].id,items[j].id]);return result;}
try{
  browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  report.browser_version=browser.version();
  for(const variant of['before','after']){
    const server=await startServer(variant);const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',error=>report.errors.push(variant+': '+error.message));
    page.on('request',req=>{if(req.method()!=='GET')report.errors.push('Unexpected '+req.method()+' '+new URL(req.url()).pathname);});
    try{
      await page.goto(`http://127.0.0.1:${server.address().port}/__fixture__`);
      await page.evaluate(async catalog=>{
        window.THREE=await import('three');const{createModelShell}=await import('/platform/web/model-shell.js');
        window.shell=await createModelShell(document.querySelector('#host'),{id:'cores3',name:'CoreS3'},{live:true});
        window.events=[];window.trusted=[];shell.on('unit-input',e=>events.push(e));shell.on('touch',e=>events.push(e));
        shell.viewer.renderer.domElement.addEventListener('pointerdown',e=>trusted.push(e.isTrusted));
        window.definitions=new Map(catalog.units.map(u=>[u.id,u]));
        await shell.attachUnit('hub');
        for(const[index,id]of['env-iii','tof','color'].entries()){
          const port=`grove/grove-${index+1}`;await shell.attachUnit(id,{port});
          const properties=id==='env-iii'?{'temperature-c':18.75,'humidity-pct':45.5,'pressure-pa':103200}:id==='tof'?{'distance-mm':382}:{'clear-raw':1700,'red-raw':430,'green-raw':530,'blue-raw':740};
          shell.updateUnitAnnotation({unit_id:id,available:true,source:'guest-qom',properties},{port,definition:definitions.get(id),running:true,source:'live',frozenDefinitions:true});
        }
        shell.viewer.setView('front',{duration:0});
      },catalog);
      await page.waitForTimeout(100);const runs={};report.variants[variant]=runs;
      for(const width of[1440,1024,768,390]){
        await page.setViewportSize({width,height:1000});await page.evaluate(()=>{shell.viewer.resize();shell.viewer.fit({padding:1.15,duration:0});});await page.waitForTimeout(120);
        const geometry=await inspect(page);geometry.housingOverlaps=pairs(geometry.housings);
        const file=`${variant}-${width}.png`;await page.screenshot({path:resolve(output,file),fullPage:true});report.screenshots.push(file);runs[width]=geometry;
        if(variant==='after'){
          assert.deepEqual(geometry.housingOverlaps,[],`${width}: housing overlap`);assert.equal(geometry.horizontalOverflow,false);
          assert.equal(geometry.cards.length,3);assert.ok(geometry.cards.every(c=>c.fields.length>0&&c.fields.every(f=>f.font==='16px')));
          assert.ok(geometry.cards.every(c=>c.bounds[1]>=geometry.canvas[3]-0.5));
          assert.ok(geometry.housings.every(h=>h.scale.every(x=>x===1)&&h.meshCount>0));
          assert.deepEqual(geometry.housings.map(h=>[h.id,h.meshCount]),report.variants.before[width].housings.map(h=>[h.id,h.meshCount]),'layout removed rendered housing meshes');
          for(const h of geometry.housings){assert.ok(h.bounds[0]>=geometry.canvas[0]&&h.bounds[1]>=geometry.canvas[1]&&h.bounds[2]<=geometry.canvas[2]&&h.bounds[3]<=geometry.canvas[3],`${h.id}: housing clipped`);}
          assert.ok(geometry.housings.filter(h=>h.id.includes('grove-')).every(h=>Math.min(h.bounds[2]-h.bounds[0],h.bounds[3]-h.bounds[1])>=24),'compact Unit projected size below24px');
          const lcd=geometry.protectedBoxes.find(c=>c.path==='lcd');assert.ok(lcd);
          assert.ok(geometry.housings.filter(h=>h.id!=='host').every(h=>!overlap(h.bounds,lcd.bounds)),'Unit covers LCD');
          assert.ok(geometry.protectedBoxes.filter(c=>!c.path.includes('/')&&c.interactive).every(c=>geometry.housings.filter(h=>h.id!=='host').every(h=>!overlap(h.bounds,c.bounds))),'Unit covers host control');
          assert.ok(geometry.cables.every(c=>Object.values(c.coveredComponents).every(n=>n===0)),'rendered cable triangle covers host display/control');
          assert.ok(geometry.cables.every(c=>c.sourceErrorMm<1e-6&&c.targetErrorMm<1e-6&&c.sourceAngleRad<1e-6&&c.targetAngleRad<1e-6&&c.state.faceDistanceMm>=12));
          for(const card of geometry.cards){assert.ok(!geometry.housings.some(h=>overlap(card.bounds,h.bounds)));const anchor=geometry.anchors.find(a=>a.path===card.anchor);assert.ok(anchor);}
        }
      }
      report.variants[variant]=runs;
      if(variant==='after'){
        report.checks.four_viewport_full_size_housings_separated=true;report.checks.four_viewport_display_readouts_and_cables_clear=true;report.checks.actual_mating_frames_preserved=true;
        report.cable_surface_sampling=await page.evaluate(()=>{
          window.sampleCableSurfaces=()=>{
          // Sample the actual rendered tube's8 surface rails every2 rings.
          // This is a geometry regression sample, not a general collision solver.
          const excluded=new Set(shell.model.list('cable').flatMap(c=>[c.object3d]));
          const meshes=[];const visit=o=>{if(excluded.has(o)||!o.visible)return;if(o.isMesh&&![o.material].flat().every(m=>m.transparent&&m.opacity===0)){o.geometry.computeBoundingBox();meshes.push({o,box:o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld)});}o.children.forEach(visit);};
          visit(shell.model.body);const ray=new THREE.Raycaster(),hits=[];let segments=0,candidates=0;
          for(const cable of shell.model.list('cable'))for(const wire of cable.wires){
            const attr=wire.geometry.attributes.position,rings=attr.count/9;
            for(let rail=0;rail<8;rail++)for(let i=0;i<rings-2;i+=2){
              const a=new THREE.Vector3().fromBufferAttribute(attr,i*9+rail).applyMatrix4(wire.matrixWorld),b=new THREE.Vector3().fromBufferAttribute(attr,(i+2)*9+rail).applyMatrix4(wire.matrixWorld);
              const segmentBox=new THREE.Box3().setFromPoints([a,b]),delta=b.clone().sub(a),length=delta.length();if(length<1e-9)continue;segments++;
              const possible=meshes.filter(m=>m.box.intersectsBox(segmentBox)).map(m=>m.o);if(!possible.length)continue;candidates+=possible.length;
              const dir=delta.normalize();for(const[start,direction]of[[a,dir],[b,dir.clone().negate()]]){ray.set(start,direction);ray.near=1e-5;ray.far=length-1e-5;const intersections=ray.intersectObjects(possible,false);for(const hit of intersections)hits.push({cable:cable.path,wire:wire.name,ring:i,rail,mesh:hit.object.name,point:hit.point.toArray()});}
            }
          }
          return{method:'rendered TubeGeometry8rails, every2rings, bidirectional segment/triangle raycast',segments,candidates,hits};
          };return sampleCableSurfaces();
        });
        assert.equal(report.cable_surface_sampling.hits.length,0,'sampled wire/shell intersection (full hits in report)');report.checks.sampled_rendered_wire_surface_shell_clear=true;
        report.cable_surface_negative_control=await page.evaluate(()=>{
          const cable=shell.model.get('grove/cable'),before=cable.getState(),space=shell.model.body;
          const direction=new THREE.Vector3(-1,-0.2,0.2).transformDirection(space.matrixWorld).transformDirection(cable.host.body.matrixWorld.clone().invert()).toArray();
          cable.setOptions({slack:10,bend:direction});const negative=sampleCableSurfaces();
          cable.setOptions({slack:before.slack,bend:before.bend});const restored=sampleCableSurfaces();
          return{deliberately_bad_route:{slack:10,bendInControllerSpace:[-1,-0.2,0.2]},negative,restored};
        });
        assert.ok(report.cable_surface_negative_control.negative.hits.length>0);assert.equal(report.cable_surface_negative_control.restored.hits.length,0);
        report.checks.cable_surface_sampler_detects_deliberate_shell_crossing=true;
        // Trust a real browser pointer through the unchanged host LCD hitbox.
        const lcd=await page.evaluate(()=>{const p=shell.display.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera),r=shell.viewer.renderer.domElement.getBoundingClientRect();return{x:r.left+(p.x+1)*r.width/2,y:r.top+(1-p.y)*r.height/2};});
        const prior=await page.evaluate(()=>events.length);await page.mouse.click(lcd.x,lcd.y);
        assert.deepEqual(await page.evaluate(prior=>events.slice(prior).map(e=>e.down),prior),[true,false]);
        assert.equal(await page.evaluate(()=>trusted.at(-1)),true);report.checks.trusted_lcd_touch_survives=true;
        // Replace a real nested model with a Button and exercise its actual hitbox.
        await page.evaluate(async()=>{await shell.attachUnit('button',{port:'grove/grove-1'});shell.viewer.fit({padding:1.15,duration:0});});await page.waitForTimeout(120);
        const button=await page.evaluate(()=>{
          const c=shell.model.button('grove/grove-1/press'),box=new THREE.Box3().setFromObject(c.object3d),points=[];
          for(const x of[box.min.x,box.max.x])for(const y of[box.min.y,box.max.y])for(const z of[box.min.z,box.max.z]){const v=new THREE.Vector3(x,y,z).project(shell.viewer.camera);points.push(v);}
          const r=shell.viewer.renderer.domElement.getBoundingClientRect(),bounds=[r.left+(Math.min(...points.map(p=>p.x))+1)*r.width/2,r.top+(1-Math.max(...points.map(p=>p.y)))*r.height/2,r.left+(Math.max(...points.map(p=>p.x))+1)*r.width/2,r.top+(1-Math.min(...points.map(p=>p.y)))*r.height/2];
          const center=c.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera),x=r.left+(center.x+1)*r.width/2,y=r.top+(1-center.y)*r.height/2;
          return{path:c.path,bounds,x,y,pick:shell.viewer.pick({clientX:x,clientY:y})?.component?.path,prior:events.length};
        });
        report.nested_button_hitbox=button;
        assert.equal(button.pick,button.path);await page.mouse.click(button.x,button.y);
        const nestedEvents=await page.evaluate(prior=>events.slice(prior).filter(e=>e.kind==='button').map(e=>({id:e.id,action:e.action,source:e.source})),button.prior);
        assert.deepEqual(nestedEvents.filter(e=>['down','up'].includes(e.action)).map(e=>[e.id,e.action]),[[button.path,'down'],[button.path,'up']]);
        const buttonShot='after-button-hitbox-390.png';await page.screenshot({path:resolve(output,buttonShot),fullPage:true});report.screenshots.push(buttonShot);
        report.nested_button_hitbox={...button,events:nestedEvents};report.checks.trusted_nested_button_path_preserved=true;
        // The native flex pad is physically10.6x8.8mm. Record its overview
        // size honestly; focus uses the existing public viewer API without
        // changing its mesh, scale, picking volume or component address.
        await page.evaluate(()=>shell.viewer.focus('grove/grove-1/press',{distance:70,duration:0}));await page.waitForTimeout(100);
        const focus=await page.evaluate(()=>{
          const c=shell.model.button('grove/grove-1/press'),box=new THREE.Box3().setFromObject(c.object3d),r=shell.viewer.renderer.domElement.getBoundingClientRect(),points=[];
          for(const x of[box.min.x,box.max.x])for(const y of[box.min.y,box.max.y])for(const z of[box.min.z,box.max.z])points.push(new THREE.Vector3(x,y,z).project(shell.viewer.camera));
          const bounds=[r.left+(Math.min(...points.map(p=>p.x))+1)*r.width/2,r.top+(1-Math.max(...points.map(p=>p.y)))*r.height/2,r.left+(Math.max(...points.map(p=>p.x))+1)*r.width/2,r.top+(1-Math.min(...points.map(p=>p.y)))*r.height/2];
          const p=c.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera);return{bounds,x:r.left+(p.x+1)*r.width/2,y:r.top+(1-p.y)*r.height/2,prior:events.length,scale:c.object3d.scale.toArray()};
        });
        assert.ok(Math.min(focus.bounds[2]-focus.bounds[0],focus.bounds[3]-focus.bounds[1])>=24);assert.deepEqual(focus.scale,[1,1,1]);
        await page.mouse.click(focus.x,focus.y);focus.events=await page.evaluate(prior=>events.slice(prior).filter(e=>e.kind==='button').map(e=>({id:e.id,action:e.action,source:e.source})),focus.prior);
        assert.deepEqual(focus.events.filter(e=>['down','up'].includes(e.action)).map(e=>[e.id,e.action]),[[button.path,'down'],[button.path,'up']]);
        const focusShot='after-button-focus-390.png';await page.screenshot({path:resolve(output,focusShot),fullPage:true});report.screenshots.push(focusShot);
        report.nested_button_hitbox.focus=focus;report.nested_button_hitbox.overview_touch_comfort='NOT PROVEN; native small flex pad, use existing zoom/focus for inspection';
        report.checks.existing_public_focus_keeps_native_nested_hitbox_operable=true;
        await page.evaluate(()=>shell.viewer.fit({padding:1.15,duration:0}));await page.waitForTimeout(100);
        report.lifecycle=await page.evaluate(async()=>{
          const hub=shell.model.port('grove').module,old=shell.model.port('grove/grove-1').module,geometries=old.get('cable').wires.map(w=>w.geometry);let disposed=0;geometries.forEach(g=>g.addEventListener('dispose',()=>disposed++));
          shell.detachUnit('grove/grove-1');const childDisposed=old.components.size===0&&disposed===4;
          const siblingPaths=shell.model.list().filter(c=>c.path.startsWith('grove/grove-2/')||c.path.startsWith('grove/grove-3/')).map(c=>c.path);
          await shell.attachUnit('env-iii',{port:'grove/grove-1'});
          const before=shell.model.get('grove/grove-1/sensor').object3d.getWorldPosition(new THREE.Vector3()).toArray();
          const saved=shell.model.port('grove').detach({dispose:false});shell.model.port('grove').attach(saved);
          const after=shell.model.get('grove/grove-1/sensor').object3d.getWorldPosition(new THREE.Vector3()).toArray();
          const reused=saved===hub&&saved.parentHost===shell.model&&before.every((v,i)=>Math.abs(v-after[i])<1e-8);
          const pending= shell.attachUnit('env-iii',{port:'grove/grove-2'});shell.detachUnit('grove/grove-2');const stale=await pending;
          const staleCancelled=stale===null&&!shell.model.port('grove/grove-2').module;
          await shell.attachUnit('tof',{port:'grove/grove-2'});
          const children=['grove-1','grove-2','grove-3'].map(id=>hub.port(id).module);
          shell.detachUnit('grove');const parentDisposed=hub.components.size===0&&children.every(c=>c.components.size===0);
          shell.dispose();return{childDisposed,siblingPaths,reused,staleCancelled,parentDisposed,remainingNotes:document.querySelectorAll('.unit-annotation').length,remainingCanvases:document.querySelectorAll('canvas').length,remainingLayers:document.querySelectorAll('.unit-annotation-layer').length};
        });
        assert.equal(report.lifecycle.childDisposed,true);assert.equal(report.lifecycle.reused,true);assert.equal(report.lifecycle.staleCancelled,true);assert.equal(report.lifecycle.parentDisposed,true);assert.equal(report.lifecycle.remainingNotes,0);assert.equal(report.lifecycle.remainingCanvases,0);assert.equal(report.lifecycle.remainingLayers,0);
        report.checks.nested_replace_detach_reuse_stale_attach_and_dispose=true;
        report.scope_and_rollback=await page.evaluate(async()=>{
          const{loadModel,loadGroveModule}=await import('/platform/web/vendor/m5stack-models/src/loaders.js');
          const{layoutHubAttachments}=await import('/platform/web/unit-assembly-layout.js');
          const state=model=>model.list('unit-frame').map(frame=>({path:frame.path,pose:frame.getState(),cable:(()=>{const c=frame.host.get('cable').getState();return{slack:c.slack,bend:c.bend};})()}));
          const prepare=async(id='cores3',options={},hubOptions={},childOptions={})=>{
            const model=await loadModel(id,options),hub=await loadGroveModule('hub',hubOptions);model.port('grove').attach(hub);
            for(const[index,id]of['env-iii','tof','color'].entries())hub.port(`grove-${index+1}`).attach(await loadGroveModule(id,childOptions));return model;
          };
          const unchanged=[];
          for(const[id,options,hubOptions,childOptions]of[
            ['atoms3r',{}, {},{}],['cores3',{dinBase:true},{},{}],
            ['cores3',{}, {unitPose:{position:[0,70,0]}},{}],['cores3',{}, {},{unitPose:{position:[0,70,0]}}],
          ]){const model=await prepare(id,options,hubOptions,childOptions),before=state(model),result=layoutHubAttachments(model);unchanged.push({id,options,customHub:!!hubOptions.unitPose,customChild:!!childOptions.unitPose,unchanged:JSON.stringify(before)===JSON.stringify(state(model)),result});model.dispose();}
          const model=await prepare(),original=state(model),hub=model.port('grove').module;
          const first=layoutHubAttachments(model),changed=JSON.stringify(original)!==JSON.stringify(state(model));
          hub.port('grove-3').detach();hub.port('grove-3').attach(await loadGroveModule('cardkb'));
          const unsupportedResult=layoutHubAttachments(model),restored=state(model).filter(s=>!s.path.startsWith('grove/grove-3/'));
          const unsupportedRestored=JSON.stringify(restored)===JSON.stringify(original.filter(s=>!s.path.startsWith('grove/grove-3/')));
          model.dispose();
          const failing=await prepare();layoutHubAttachments(failing);const before=state(failing),frame=failing.get('grove/grove-2/unitFrame'),setPose=frame.setPose;let once=true;
          frame.setPose=function(...args){if(once){once=false;throw new Error('injected optional layout failure');}return setPose.apply(this,args);};
          const failureResult=layoutHubAttachments(failing),rollback=JSON.stringify(before)===JSON.stringify(state(failing));frame.setPose=setPose;
          const componentPaths=failing.list().map(c=>c.path);failing.dispose();
          return{unchanged,first,changed,unsupportedResult,unsupportedRestored,failureResult,rollback,componentPaths};
        });
        assert.ok(report.scope_and_rollback.unchanged.every(r=>r.unchanged&&r.result.length===0));
        assert.ok(report.scope_and_rollback.changed&&report.scope_and_rollback.unsupportedRestored&&report.scope_and_rollback.rollback);
        assert.ok(report.scope_and_rollback.failureResult.some(r=>r.status==='unavailable'));
        report.checks.untested_host_custom_pose_and_unsupported_child_keep_original_layout=true;
        report.checks.optional_layout_failure_rolls_back_without_changing_paths=true;
        report.adapter_failure_isolation=[];
        for(const failure of['snapshot','restore']){
          const result=await page.evaluate(async failure=>{
            const{createModelShell}=await import('/platform/web/model-shell.js');
            window.shell=await createModelShell(document.querySelector('#host'),{id:'cores3',name:'CoreS3'},{live:true});
            window.faultEvents=[];shell.on('unit-input',event=>faultEvents.push(event));
            await shell.attachUnit('hub');for(const[index,id]of['button','tof','color'].entries())await shell.attachUnit(id,{port:`grove/grove-${index+1}`});
            const hub=shell.model.port('grove').module;
            const siblings=['grove-1','grove-2'].map(id=>hub.port(id).module);
            const positions=siblings.map(module=>module.get('unitFrame').object3d.getWorldPosition(new THREE.Vector3()).toArray());
            let undo;
            if(failure==='snapshot'){
              const cable=hub.get('cable'),getState=cable.getState;
              cable.getState=()=>{throw new Error('injected snapshot/getState failure');};undo=()=>{cable.getState=getState;};
            }else{
              const frame=siblings[1].get('unitFrame'),setPose=frame.setPose;let once=true;
              frame.setPose=function(...args){if(once){once=false;throw new Error('injected restore mid-transaction failure');}return setPose.apply(this,args);};undo=()=>{frame.setPose=setPose;};
            }
            const attached=await shell.attachUnit(failure==='snapshot'?'color':'cardkb',{port:'grove/grove-3'});
            undo();shell.model.root.updateWorldMatrix(true,true);
            const unchanged=siblings.every((module,index)=>hub.port(`grove-${index+1}`).module===module&&positions[index].every((v,j)=>Math.abs(v-module.get('unitFrame').object3d.getWorldPosition(new THREE.Vector3()).toArray()[j])<1e-7));
            return{failure,status:shell.unitAssemblyLayout,attachmentOwned:attached===hub.port('grove-3').module&&attached.parentHost===hub&&attached.components.size>0,siblingsUnchanged:unchanged,positionsBefore:positions,positionsAfter:siblings.map(module=>module.get('unitFrame').object3d.getWorldPosition(new THREE.Vector3()).toArray())};
          },failure);
          await page.waitForTimeout(100);
          assert.ok(result.attachmentOwned&&result.siblingsUnchanged);assert.ok(result.status.some(s=>s.status==='unavailable'&&s.reason.includes(failure)));
          const target=await page.evaluate(()=>{const component=shell.model.button('grove/grove-1/press'),r=shell.viewer.renderer.domElement.getBoundingClientRect(),p=component.object3d.getWorldPosition(new THREE.Vector3()).project(shell.viewer.camera),x=r.left+(p.x+1)*r.width/2,y=r.top+(1-p.y)*r.height/2;return{x,y,path:component.path,pick:shell.viewer.pick({clientX:x,clientY:y})?.component?.path,prior:faultEvents.length};});
          assert.equal(target.pick,target.path);await page.mouse.click(target.x,target.y);
          result.events=await page.evaluate(prior=>faultEvents.slice(prior).filter(e=>e.kind==='button').map(e=>({id:e.id,action:e.action,source:e.source})),target.prior);
          assert.deepEqual(result.events.filter(e=>['down','up'].includes(e.action)).map(e=>[e.id,e.action]),[[target.path,'down'],[target.path,'up']]);
          const file=`after-${failure}-failure-isolation-390.png`;await page.screenshot({path:resolve(output,file),fullPage:true});report.screenshots.push(file);
          report.adapter_failure_isolation.push(result);await page.evaluate(()=>shell.dispose());
        }
        report.checks.adapter_snapshot_and_restore_failure_preserve_ownership_siblings_and_trusted_input=true;
      }else await page.evaluate(()=>shell.dispose());
    }finally{await page.close();await new Promise(resolve=>server.close(resolve));}
  }
  assert.ok(Object.values(report.variants.before).every(r=>r.housingOverlaps.length>0));report.checks.baseline_overlap_reproduced_at_four_viewports=true;
  assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.error=error.stack;}
finally{await browser?.close();}
report.source_post_run_sha256=await sourceHashes();
if(JSON.stringify(report.source_sha256)!==JSON.stringify(report.source_post_run_sha256)){report.status='FAIL';report.errors.push('Named execution source drift during browser run');}
report.baseline_freeze_post_run_matches=true;
for(const[name,sha]of Object.entries(frozen))if(digest(await readFile(resolve(work,'base',name)))!==sha){report.status='FAIL';report.baseline_freeze_post_run_matches=false;report.errors.push('Baseline freeze drift: '+name);}
report.screenshot_sha256=Object.fromEntries(await Promise.all(report.screenshots.map(async name=>[name,createHash('sha256').update(await readFile(resolve(output,name))).digest('hex')])));
await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,checks:report.checks,error:report.error,screenshots:report.screenshots},null,2));
process.exitCode=report.status==='PASS'?0:1;
