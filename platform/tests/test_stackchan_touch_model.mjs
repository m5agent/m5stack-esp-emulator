// Actual DOM pointer/raycast coverage for the moving screen. No guest runs;
// this proves model input only, never firmware touch or motor behavior.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const modules=resolve(process.env.M5_WASM_NODE_MODULES||resolve(root,'platform/tests/node_modules'));
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const out=resolve(process.env.M5_STACKCHAN_MODEL_OUT||resolve(root,'.work/stackchan-touch-model'));
assert.ok(out.startsWith(resolve(root,'.work')+'/'),'Raw evidence belongs in ignored storage');
await mkdir(out,{recursive:false});
const html=`<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0}#host,.three-device-root,.three-device-stage{width:1000px;height:850px!important;min-height:850px!important}</style><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><div id="host"></div></body></html>`;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.webp':'image/webp'};
const server=createServer(async(req,res)=>{
  try{
    const name=new URL(req.url,'http://localhost').pathname;
    if(name==='/__touch_model__'){res.writeHead(200,{'content-type':'text/html'}).end(html);return;}
    if(name==='/favicon.ico'){res.writeHead(204).end();return;}
    const path=resolve(root,'.'+decodeURIComponent(name));
    if(!path.startsWith(root+'/')){res.writeHead(403).end();return;}
    res.writeHead(200,{'content-type':mime[extname(path)]||'application/octet-stream','cache-control':'no-cache'}).end(await readFile(path));
  }catch{res.writeHead(404).end();}
});
const report={kind:'stackchan-moving-screen-model-input',status:'FAIL',guest_validation:'NOT RUN',hardware_validation:'NOT RUN',cases:[],errors:[]};
let browser;
try{
  await new Promise(yes=>server.listen(0,'127.0.0.1',yes));
  const origin=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({headless:true,executablePath:process.env.M5_WASM_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  report.browser=browser.version();
  report.harness_sha256=createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex');
  const page=await browser.newPage({viewport:{width:1100,height:950}});
  page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(origin+'/__touch_model__');
  await page.evaluate(async()=>{
    const {ModelDeviceShell}=await import('/platform/web/model-shell.js');
    const THREE=await import('three');globalThis.probeThree=THREE;
    globalThis.shell=await ModelDeviceShell.create(document.querySelector('#host'),{id:'stackchan',name:'StackChan'},{live:true});
    globalThis.touchEvents=[];shell.on('touch',e=>touchEvents.push({...e,at:performance.now()}));
    globalThis.rendered=()=>new Promise(yes=>{const off=shell.viewer.on('render',()=>{off();yes();});shell.viewer.requestRender();});
    await rendered();
  });
  const poses=[[0,0],[-50,0],[50,0],[0,30],[-40,30],[40,30],[0,55]];
  for(const [yaw,pitch]of poses){
    await page.evaluate(async({yaw,pitch})=>{shell.applyVisualState([{type:'joint',target:'yaw',angleDeg:yaw},{type:'joint',target:'pitch',angleDeg:pitch}]);await rendered();},{yaw,pitch});
    for(const [u,v]of [[.25,.25],[.5,.5],[.75,.75]]){
      const target=await page.evaluate(({u,v})=>{
        const d=shell.model.find('lcd','display'),THREE=probeThree;
        const point=d.panel.localToWorld(new THREE.Vector3((u-.5)*d.size[0],(.5-v)*d.size[1],0)).project(shell.viewer.camera);
        const box=shell.viewer.renderer.domElement.getBoundingClientRect(),x=box.left+(point.x+1)*box.width/2,y=box.top+(1-point.y)*box.height/2;
        const hit=shell.viewer.pick({clientX:x,clientY:y});
        return {x,y,expected:{x:Math.floor(u*d.width),y:Math.floor(v*d.height)},hit:hit?.component?.id,object:hit?.intersection?.object?.name,events:touchEvents.length};
      },{u,v});
      const row={yaw,pitch,u,v,target};report.cases.push(row);
      assert.equal(target.hit,'lcd',`Screen not pickable at yaw${yaw}/pitch${pitch}: ${target.hit||target.object}`);
      await page.mouse.move(target.x,target.y);await page.mouse.down();await page.mouse.up();
      row.events=await page.evaluate(n=>touchEvents.slice(n),target.events);
      assert.deepEqual(row.events.map(e=>e.down),[true,false]);
      for(const e of row.events){assert.ok(Math.abs(e.x-target.expected.x)<=2);assert.ok(Math.abs(e.y-target.expected.y)<=2);}
      row.status='PASS';
    }
  }
  // A captured screen contact must be released even if joint readback moves
  // the physical panel before the pointer-up reaches the canvas.
  await page.evaluate(async()=>{shell.applyVisualState([{type:'joint',target:'yaw',angleDeg:0},{type:'joint',target:'pitch',angleDeg:0}]);await rendered();});
  const hold=await page.evaluate(()=>{
    const d=shell.display,p=d.panel.getWorldPosition(new probeThree.Vector3()).project(shell.viewer.camera),b=shell.viewer.renderer.domElement.getBoundingClientRect();
    return {x:b.left+(p.x+1)*b.width/2,y:b.top+(1-p.y)*b.height/2,events:touchEvents.length};
  });
  await page.mouse.move(hold.x,hold.y);await page.mouse.down();
  await page.evaluate(async()=>{shell.applyVisualState([{type:'joint',target:'yaw',angleDeg:45},{type:'joint',target:'pitch',angleDeg:30}]);await rendered();});
  await page.mouse.up();
  const release=await page.evaluate(n=>({events:touchEvents.slice(n),touches:shell.display.touches.size}),hold.events);
  assert.deepEqual(release.events.map(e=>e.down),[true,false]);assert.equal(release.touches,0);
  report.captured_release=release;
  await page.screenshot({path:resolve(out,'moving-screen.png')});
  await page.evaluate(()=>shell.dispose());
  assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.error=String(error.stack||error);process.exitCode=1;}
finally{
  await browser?.close();await new Promise(yes=>server.close(yes));
  report.source_sha256=Object.fromEntries(await Promise.all(['platform/web/model-shell.js','platform/web/vendor/m5stack-models/src/core/DeviceViewer.js','platform/web/vendor/m5stack-models/src/core/components/Display.js'].map(async p=>[p,createHash('sha256').update(await readFile(resolve(root,p))).digest('hex')])));
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,cases:report.cases.length,error:report.error}));
}
