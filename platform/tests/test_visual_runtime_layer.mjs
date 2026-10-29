// Actual browser rendering contracts only; no service, guest or hardware run.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const out=resolve(process.env.M5_VISUAL_LAYER_OUT||resolve(repo,'.work/visual-runtime-layer-browser'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'));
await mkdir(out,{recursive:false});
const viewerPath='platform/web/vendor/m5stack-models/src/core/DeviceViewer.js';
const manifest=JSON.parse(await readFile(resolve(repo,'platform/web/vendor/m5stack-models/vendor-manifest.json')));
const layer=manifest.local_runtime_patches.find(row=>row.target==='src/core/DeviceViewer.js');assert.ok(layer);
assert.equal(createHash('sha256').update(await readFile(resolve(repo,viewerPath))).digest('hex'),layer.effective.sha256);
const html=`<!doctype html><html><head><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><div id="host" style="width:640px;height:480px;display:none"></div></body></html>`;
const requests=[],errors=[];
const server=createServer(async(request,response)=>{
  try{
    const name=new URL(request.url,'http://localhost').pathname;
    if(name==='/'){response.setHeader('content-type','text/html');response.end(html);return;}
    if(name==='/favicon.ico'){response.writeHead(204).end();return;}
    const path=resolve(repo,'.'+decodeURIComponent(name));if(!path.startsWith(repo+'/')){response.writeHead(403).end();return;}
    response.setHeader('content-type',{'.js':'text/javascript','.png':'image/png','.json':'application/json'}[extname(path)]||'application/octet-stream');
    response.end(await readFile(path));
  }catch{response.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser,page;
const report={kind:'browser-visual-runtime-layer-contract',status:'FAIL',guest_execution:'NOT RUN',hardware_execution:'NOT RUN',
  layer,checks:[],errors};
try{
  browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  report.browser=browser.version();page=await browser.newPage({viewport:{width:900,height:700}});
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push(request.url()));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  report.observations=await page.evaluate(async()=>{
    const THREE=await import('three');
    const {DeviceViewer}=await import('/platform/web/vendor/m5stack-models/src/core/DeviceViewer.js');
    const {loadModel}=await import('/platform/web/vendor/m5stack-models/src/loaders.js');
    const host=document.querySelector('#host'),model=await loadModel('atoms3-lite');
    const viewer=new DeviceViewer(host,{keyboard:'focused',fov:25}),events=[];
    let renders=0;viewer.on('render',()=>renders++);model.on('input',event=>events.push(event));viewer.mount(model);
    const settle=async()=>{for(let i=0;i<8;i++)await new Promise(requestAnimationFrame);};
    const bounds=()=>{
      viewer.camera.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(model.root),points=[];
      for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z])points.push(new THREE.Vector3(x,y,z).project(viewer.camera));
      return {min:['x','y','z'].map(axis=>Math.min(...points.map(point=>point[axis]))),max:['x','y','z'].map(axis=>Math.max(...points.map(point=>point[axis]))),distance:viewer.distance};
    };
    viewer.setView('front',{duration:0});const hiddenDistance=viewer.distance;viewer.fit({padding:1.4});
    if(viewer.distance!==hiddenDistance)throw new Error('Hidden fit must defer rather than using the fallback 1px viewport');
    host.style.display='block';await settle();const visible=bounds();
    viewer.pauseRendering();viewer.pauseRendering();const paused=renders;
    model.handle({type:'led',target:'rgb',color:0xff6600,brightness:0.5});viewer.requestRender();await settle();
    if(!viewer.renderingPaused||renders!==paused)throw new Error('Paused model rendered after a real component update');
    host.style.display='none';viewer.fit({padding:1.4});await settle();host.style.height='320px';host.style.display='block';await settle();
    if(renders!==paused)throw new Error('Resize resumed a paused renderer');
    viewer.resumeRendering();viewer.resumeRendering();await settle();const resumed=bounds();
    if(viewer.renderingPaused||renders<=paused)throw new Error('Resume failed to render the pending state');
    const led=model.find('rgb','led').getState(),atDispose=renders;
    viewer.pauseRendering();viewer.dispose();viewer.resumeRendering();viewer.requestRender();await settle();
    if(renders!==atDispose||host.querySelector('canvas'))throw new Error('Disposed renderer restarted or retained its canvas');
    if(events.length)throw new Error('Rendering lifecycle echoed runtime input');
    return {hidden_deferred:true,visible,paused_renders:paused,resumed,led,final_renders:renders,disposed_canvas_count:host.querySelectorAll('canvas').length,output_echo:events.length};
  });
  for(const [name,value]of Object.entries({visible:report.observations.visible,resumed:report.observations.resumed})){
    for(const axis of [0,1])assert.ok(value.min[axis]>=-0.98&&value.max[axis]<=0.98,`${name} hidden-viewport fit clips axis ${axis}`);
  }
  assert.deepEqual(report.observations.led,{color:'#ff6600',brightness:0.5});assert.deepEqual(errors,[]);
  assert.ok(!requests.some(url=>/\/api\/v1|:8787\b|:8830\b/.test(url)));
  report.checks=['upstream-hidden-fit-retained','pause-stops-rendering-on-component-and-resize','resume-renders-pending-state',
    'dispose-while-paused-cannot-restart','zero-runtime-input-echo','no-service-or-guest'];report.status='PASS';
  console.log('VISUAL_RUNTIME_LAYER_BROWSER_PASS');
}catch(error){report.error=error.stack;process.exitCode=1;}
finally{
  await browser?.close();await new Promise(resolve=>server.close(resolve));
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
}
