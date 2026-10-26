// Focused browser geometry contract; no Device Service, firmware or hardware.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const root=resolve(process.env.M5_FRONTEND_REPO_ROOT || dirname(fileURLToPath(import.meta.url))+'/../..');
const {chromium}=createRequire(resolve(root,'platform/tests/test_session_mount.mjs'))('playwright');
const sourceRoot=resolve(process.argv[2] || root);
const output=resolve(process.argv[3] || '/tmp/m5-session-mount-contract');
await mkdir(output,{recursive:true});
const source=await readFile(resolve(sourceRoot,'platform/web/sessions.js'),'utf8');
const fragment=source.slice(source.indexOf('class SessionVisual {'),source.indexOf('\nfunction createSessionCard'));
const profile=JSON.parse(await readFile(resolve(root,'devices/catalog.source.json'),'utf8')).devices.find(d=>d.id==='cores3');
const harness=`<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/platform/web/sessions.css"><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><style>body{margin:0;background:#fff}#host{width:440px;height:420px}</style><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><div id="host" class="session-visual"></div></body></html>`;
const server=createServer(async(req,res)=>{try{const pathname=new URL(req.url,'http://localhost').pathname;if(pathname==='/__test__'){res.setHeader('Content-Type','text/html');res.end(harness);return;}const path=resolve(root,'.'+decodeURIComponent(pathname));if(!path.startsWith(root+'/')){res.writeHead(403).end();return;}res.setHeader('Content-Type',{'.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'}[extname(path)]||'application/octet-stream');res.end(await readFile(path));}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1200,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(`http://127.0.0.1:${server.address().port}/__test__`);
 const setup=await page.evaluate(async({fragment,profile})=>{
  const {createDeviceShell}=await import('/platform/web/device-shell-factory.js');
  const state={deviceProfiles:new Map([[profile.id,profile]]),devicePaths:new Map([[profile.id,profile.id]]),deviceStates:new Map()};
  let constructedDetached=false;
  const factory=(host,...args)=>{constructedDetached=!host.isConnected;return createDeviceShell(host,...args);};
  const Visual=new Function('state','createDeviceShell','CONTROL_RELEASE_TIMEOUT_MS','api','framePlaceholder',fragment+'\nreturn SessionVisual;')(state,factory,5000,async()=>{},()=> 'waiting');
  const visual=Object.create(Visual.prototype);Object.assign(visual,{container:document.querySelector('#host'),session:{session_id:'geometry-fixture',device_id:profile.id,state:'running'},allowThree:true,threeAttempted:false,shellLoading:false,shellGeneration:0,destroyed:false,shell:null,unitPanel:null,frameBlob:null,activeControls:new Set(),controlReleaseTimers:new Map(),frameApply:Promise.resolve()});
  window.mountVisual=visual;await visual.init();return {constructedDetached,model:visual.shell?.root?.dataset.modelSource};
 },{fragment,profile});
 assert.equal(setup.constructedDetached,true);assert.equal(setup.model,'m5stack-models');
 await page.waitForFunction(()=>{const shell=window.mountVisual.shell;return shell?.stage.clientWidth===440&&shell.viewer.renderer.domElement.width===440;});
 const initial=await page.evaluate(()=>{const s=window.mountVisual.shell;return {mountWidth:s.host.clientWidth,mountHeight:s.host.clientHeight,stageWidth:s.stage.clientWidth,stageHeight:s.stage.clientHeight,canvasWidth:s.viewer.renderer.domElement.width,canvasHeight:s.viewer.renderer.domElement.height};});
 assert.deepEqual(initial,{mountWidth:440,mountHeight:420,stageWidth:440,stageHeight:420,canvasWidth:440,canvasHeight:420});
 await page.locator('#host').screenshot({path:resolve(output,'mount-initial.png')});
 await page.evaluate(()=>{document.querySelector('#host').style.width='320px';});
 await page.waitForFunction(()=>window.mountVisual.shell.viewer.renderer.domElement.width===320);
 const resized=await page.evaluate(()=>{const s=window.mountVisual.shell;return {mountWidth:s.host.clientWidth,stageWidth:s.stage.clientWidth,canvasWidth:s.viewer.renderer.domElement.width,canvasHeight:s.viewer.renderer.domElement.height};});
 assert.deepEqual(resized,{mountWidth:320,stageWidth:320,canvasWidth:320,canvasHeight:420});
 await page.locator('#host').screenshot({path:resolve(output,'mount-resized.png')});
 await page.evaluate(()=>window.mountVisual.destroy());
 assert.equal(await page.locator('#host canvas').count(),0);assert.deepEqual(errors,[]);
 const report={category:'browser-session-mount-contract',status:'PASS',firmware_execution:'NOT RUN',hardware_execution:'NOT RUN',browser_version:browser.version(),source_sha256:{'platform/web/sessions.js':createHash('sha256').update(source).digest('hex')},checks:{constructed_in_detached_owned_mount:true,valid_generation_committed:true,initial_dimensions:initial,resize_observer_dimensions:resized,dispose_removes_owned_canvas:true},errors};
 await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log('SESSION_MOUNT_BROWSER_OK');
}finally{await browser.close();await new Promise(r=>server.close(r));}
