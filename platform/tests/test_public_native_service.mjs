// Explicit development acceptance through a dedicated Device Service. No direct
// QEMU launch, no default CI execution, and never the user's port 8787.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

if (!process.argv.includes('--execute')) {
  console.log('NOT RUN: --execute --service http://127.0.0.1:8829 --token-file <private-file> --firmware <CoreS3.bin> --out <ignored-dir>');
  process.exit(0);
}
const args=process.argv.slice(2), option=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const service=option('--service','http://127.0.0.1:8829');
const target=new URL(service);
assert.ok(['127.0.0.1','localhost','[::1]'].includes(target.hostname));
assert.notEqual(target.port,'8787','The user testing service is forbidden.');
assert.ok(option('--token-file')&&option('--firmware'));
const token=(await readFile(resolve(option('--token-file')),'utf8')).trim();
assert.ok(token.length>=32);
const firmwarePath=resolve(option('--firmware')), firmware=await readFile(firmwarePath);
const python=option('--python',process.env.M5_PYTHON||'python3');
const fixture=option('--fixture')?JSON.parse(await readFile(resolve(option('--fixture')),'utf8')):null;
// Golden pixels of cores3_ui_test/main.py before input, independently captured
// and visually inspected from this fixed runtime. Ignore PNG compression.
const fixturePixelsSha='a4465d4d653ce913f734627d9cc523509041c9a79bfe6d785bb77b8ae3d1349b';
const output=resolve(option('--out','.work/public-native-smoke'));
await mkdir(output,{recursive:true});
const hash=data=>createHash('sha256').update(data).digest('hex');
async function waitForCheck(check,{timeout=90000,interval=350}={}) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){if(await check())return;await delay(interval);}
  throw new Error(`Async frame condition did not pass within ${timeout}ms.`);
}
const receipt={schema_version:1,category:'public-native-device-service',status:'FAIL',hardware_validation:'NOT RUN',firmware_source_sha256:hash(firmware),http:[],page_errors:[],checks:{}};
if(fixture)receipt.fixture={kind:'service-composed-source',firmware_sha256:fixture.sha256,source_sha256:fixture.source.metadata.source_sha256,scope:'repository cores3_ui_test/main.py on explicitly imported base; not stock application acceptance'};
const sourcePaths=['platform/web/public.js','platform/web/public-service.js','platform/web/public-session-controller.js','platform/tools/serve.py','platform/tools/device_service.py'];
receipt.sources=Object.fromEntries(await Promise.all(sourcePaths.map(async path=>[path,hash(await readFile(resolve(root,path)))])));
async function api(path,method='GET',body) {
  const response=await fetch(service+'/api/v1/'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(30000)});
  const data=Buffer.from(await response.arrayBuffer());
  assert.ok(response.ok,`Service ${method} ${path} returned ${response.status}: ${data.toString().slice(0,200)}`);
  return path.includes('frame.png')||path.includes('/evidence')?data:JSON.parse(data);
}
const initial=await api('health');
assert.equal(initial.capacity.active_sessions,0,'Use an empty dedicated service.');
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.png':'image/png','.svg':'image/svg+xml','.webp':'image/webp','.jpg':'image/jpeg','.wasm':'application/wasm'};
const server=createServer(async(request,response)=>{
  const pathname=new URL(request.url,'http://localhost').pathname;
  try {
    if(pathname==='/favicon.ico'){response.writeHead(204);response.end();return;}
    const file=resolve(root,'.'+(pathname==='/'?'/platform/web/index.html':decodeURIComponent(pathname)));
    if(!['platform/web/','devices/'].some(prefix=>file.startsWith(resolve(root,prefix)+'/'))){response.writeHead(403);response.end();return;}
    let data=await readFile(file);
    if(file===resolve(root,'platform/web/public.js')) data=Buffer.concat([data,Buffer.from('\nwindow.__publicNativeProbe={state,appendSerial,status,error};\n')]);
    response.setHeader('Content-Type',types[extname(file)]||'application/octet-stream');response.end(data);
  }catch{response.writeHead(404);response.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const pageOrigin=`http://127.0.0.1:${server.address().port}`;
assert.notEqual(new URL(pageOrigin).origin,target.origin,'This must exercise cross-origin CORS.');
let browser,page,ownedId,deleted=false;
const observedWrites=[];
try {
  browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  page=await browser.newPage({viewport:{width:1440,height:1080}});
  page.on('pageerror',error=>receipt.page_errors.push(error.message));
  page.on('response',response=>{
    if(!response.url().startsWith(service+'/api/v1/'))return;
    const request=response.request(),url=new URL(response.url()),row={method:request.method(),path:url.pathname,status:response.status(),purge:url.searchParams.get('purge')};
    receipt.http.push(row);
    if(row.method==='POST'&&row.path==='/api/v1/sessions') observedWrites.push(response.json().then(data=>{ownedId=data.session_id;row.session_id=ownedId;}));
  });
  await page.goto(pageOrigin+'/?device=cores3&mode=service&autostart=0',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__publicNativeProbe?.state.selected?.id==='cores3'&&window.__publicNativeProbe.state.shell);
  await page.locator('#serviceConnection').evaluate(node=>{node.open=true;});
  await page.fill('#serviceUrl',service);await page.fill('#serviceToken',token);await page.click('#connectServiceBtn');
  await page.waitForFunction(()=>window.__publicNativeProbe.state.serviceDevices.some(row=>row.device_id==='cores3'&&row.creatable));
  receipt.checks.cross_origin_connected=true;
  if(fixture){
    await page.evaluate(async fixture=>{
      const {state,appendSerial,status,error}=window.__publicNativeProbe;
      const {PublicSessionController}=await import('/platform/web/public-session-controller.js');
      const service=Object.create(state.service);
      // This explicit regression fixture uses the existing source-binding API;
      // no production create method or firmware provenance is bypassed.
      service.create=({deviceId,firmwareId,units=[]})=>state.service.request('/api/v1/sessions',{method:'POST',body:{device_id:deviceId,firmware_id:firmwareId,uiflow_source_sha256:fixture.source.metadata.source_sha256,ttl_seconds:600,units,...(fixture.test_runtime==='qemu-unified'?{runtime:'qemu-unified',network:{profile:'uiflow2-cores3-unified',capture_pcap:false}}:{})}});
      const controller=new PublicSessionController({service,shell:state.shell,onSerial:appendSerial,onState:value=>status(value.status,value.frameReady?'实际会话屏幕已更新':'等待应用显示帧'),onError:error});
      state.run={kind:'service',generation:++state.runGeneration,controller};
      await controller.start({deviceId:'cores3',firmwareId:fixture.firmware_id});
    },{...fixture,test_runtime:option('--runtime','qemu')});
  }else{
    await page.check('input[name="firmwareSource"][value="local"]');
    await page.locator('#firmwareFile').setInputFiles(firmwarePath);
    await page.click('#startBtn');
  }
  await page.waitForFunction(()=>['running','failed','stopped'].includes(window.__publicNativeProbe.state.run?.controller.current?.state),{},{timeout:180000});
  const startup=await page.evaluate(()=>window.__publicNativeProbe.state.run.controller.current);
  assert.equal(startup.state,'running',`Session startup reached ${startup.state}: ${JSON.stringify(startup.error||startup.failure||startup)}`);
  await Promise.all(observedWrites);
  assert.ok(ownedId);
  const session=await api(`sessions/${ownedId}`);
  receipt.session={session_id:ownedId,device_id:session.device_id,pid:session.pid,firmware_sha256:session.firmware_sha256,runtime:session.runtime,profile:session.profile};
  assert.equal(session.device_id,'cores3');assert.ok(session.pid);
  const identity=JSON.parse(execFileSync(python,['-c','import ctypes,hashlib,json,pathlib,sys;p=int(sys.argv[1]);b=ctypes.create_string_buffer(4096);assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0;f=pathlib.Path(b.value.decode());print(json.dumps({"pid":p,"name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))',String(session.pid)],{encoding:'utf8'}));
  receipt.session.runtime_identity=identity;
  assert.equal(identity.sha256,option('--expected-runtime','cc21773f0ad91fa589447d3badb1eb681b74170cd8b749153f37ad23cebc70c2'));
  await page.waitForFunction(()=>window.__publicNativeProbe.state.run.controller.frameReady,{},{timeout:90000});
  // A valid boot-time black PNG is an actual capture but not an application
  // frame. Wait for contrasting guest pixels rather than treating a successful
  // frame API call or ROM banner as application readiness.
  await waitForCheck(()=>page.evaluate(async expectedPixelsSha=>{
    const controller=window.__publicNativeProbe.state.run?.controller,id=controller?.current?.session_id;
    if(!id)return false;
    const response=await controller.service.fetch(`/api/v1/sessions/${id}/frame.png?max_age_ms=500`);
    if(!response.ok)return false;
    const image=await createImageBitmap(await response.blob()),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const context=canvas.getContext('2d');context.drawImage(image,0,0);const pixels=context.getImageData(0,0,canvas.width,canvas.height).data,colors=new Set();
    for(let i=0;i<pixels.length;i+=4){colors.add(`${pixels[i]},${pixels[i+1]},${pixels[i+2]}`);if(colors.size>3)break;}
    if(colors.size<=3)return false;
    if(!expectedPixelsSha)return true;
    const digest=await crypto.subtle.digest('SHA-256',pixels);
    return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('')===expectedPixelsSha;
  },fixture?fixturePixelsSha:null),{interval:700,timeout:90000});
  const serial=await api(`sessions/${ownedId}/serial?offset=0&limit=1048576`);
  await writeFile(resolve(output,'serial.txt'),serial.data);
  const frame=await api(`sessions/${ownedId}/frame.png`);
  await writeFile(resolve(output,'frame.png'),frame);
  const frameInfo=await page.evaluate(async bytes=>{
    const image=await createImageBitmap(new Blob([new Uint8Array(bytes)],{type:'image/png'})),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const data=ctx.getImageData(0,0,canvas.width,canvas.height).data,colors=new Set();for(let i=0;i<data.length;i+=4)colors.add(`${data[i]},${data[i+1]},${data[i+2]}`);let greenMarkerPixels=0;for(let y=1;y<=4;y++)for(let x=1;x<=4;x++){const i=4*(y*canvas.width+x);if(data[i]===0&&data[i+1]===255&&data[i+2]===0)greenMarkerPixels++;}return{width:image.width,height:image.height,colors:colors.size,greenMarkerPixels};
  },[...frame]);
  assert.equal(frameInfo.width,320);assert.equal(frameInfo.height,240);assert.ok(frameInfo.colors>3);
  receipt.frame={...frameInfo,sha256:hash(frame),bytes:frame.length};receipt.checks.actual_serial_and_application_frame_collected=true;
  receipt.serial={bytes:Buffer.byteLength(serial.data),sha256:hash(serial.data),application_marker_present:serial.data.includes('CORES3_MAIN_START')};
  if(fixture)assert.notEqual(frameInfo.greenMarkerPixels,16,'Fixture must start without the touch-response marker.');
  const input=await page.evaluate(()=>window.__publicNativeProbe.state.run.controller.input({kind:'longpress',x:160,y:180,hold_seconds:1}));
  receipt.input=input;assert.ok(input);receipt.checks.same_controller_input_accepted=true;
  if(fixture){
    await waitForCheck(()=>page.evaluate(async()=>{
      const controller=window.__publicNativeProbe.state.run.controller,id=controller.current.session_id,response=await controller.service.fetch(`/api/v1/sessions/${id}/frame.png?max_age_ms=0`);
      if(!response.ok)return false;
      const image=await createImageBitmap(await response.blob()),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const context=canvas.getContext('2d');context.drawImage(image,0,0);const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
      for(let y=1;y<=4;y++)for(let x=1;x<=4;x++){const i=4*(y*canvas.width+x);if(pixels[i]!==0||pixels[i+1]!==255||pixels[i+2]!==0)return false;}
      return true;
    }),{interval:350,timeout:30000});
    const touchFrame=await api(`sessions/${ownedId}/frame.png?max_age_ms=0`);
    await writeFile(resolve(output,'touch-frame.png'),touchFrame);
    receipt.touch_frame={sha256:hash(touchFrame),bytes:touchFrame.length,green_marker_pixels:16};
    receipt.checks.same_guest_touch_frame_response=true;
  }
  await page.screenshot({path:resolve(output,'homepage-running.png'),fullPage:true});
  await page.evaluate(()=>{window.__lastNativeController=window.__publicNativeProbe.state.run.controller;});
  await page.click('#stopBtn');
  await page.waitForFunction(()=>window.__lastNativeController.current===null&&!window.__lastNativeController.stopPromise,{},{timeout:60000});
  deleted=true;
  await Promise.all(observedWrites);
  // Read the controller's actual pre-stop Blob. The local Playwright response
  // adapter does not preserve binary response.body() bytes.
  const evidenceBytes=Buffer.from(await page.evaluate(async()=>[...new Uint8Array(await window.__lastNativeController.lastEvidence.arrayBuffer())]));
  await writeFile(resolve(output,'evidence.zip'),evidenceBytes);
  const evidenceRow=receipt.http.find(row=>row.path.endsWith('/evidence')&&row.status===200);
  if(evidenceRow){evidenceRow.sha256=hash(evidenceBytes);evidenceRow.bytes=evidenceBytes.length;}
  const zip=receipt.http.findIndex(row=>row.path.endsWith('/evidence')&&row.status===200);
  const stop=receipt.http.findIndex(row=>row.method==='DELETE'&&row.path===`/api/v1/sessions/${ownedId}`);
  assert.ok(zip>=0&&stop>zip,'Evidence ZIP must be requested before DELETE.');
  assert.equal(receipt.http[stop].purge,'0');
  const evidence=await readFile(resolve(output,'evidence.zip'));assert.equal(evidence.subarray(0,2).toString(),'PK');
  receipt.evidence=JSON.parse(execFileSync(python,['-c','import hashlib,json,sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read("manifest.json"));rows=m["files"];assert all(len(z.read(p))==r["size"] and hashlib.sha256(z.read(p)).hexdigest()==r["sha256"] for p,r in rows.items());print(json.dumps({"zip_sha256":hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest(),"verified_files":len(rows),"session_id":m["session"]["session_id"]}))',resolve(output,'evidence.zip')],{encoding:'utf8'}));
  assert.equal(receipt.evidence.session_id,ownedId,'Evidence must belong to the same owned guest.');
  const history=await api(`sessions/${ownedId}`);
  await writeFile(resolve(output,'history.json'),JSON.stringify(history,null,2)+'\n');
  assert.equal(history.state,'stopped');assert.equal(history.flash_retained,false);
  const last=await api(`sessions/${ownedId}/frame.png`);assert.ok(last.length>0);
  assert.equal((await api('health')).capacity.active_sessions,0);
  for(let i=0;i<30;i++){try{process.kill(session.pid,0);await delay(100);}catch(error){if(error.code==='ESRCH'){receipt.checks.guest_process_reaped=true;break;}throw error;}}
  assert.equal(receipt.checks.guest_process_reaped,true);
  receipt.checks.zip_before_delete_and_history=true;
  assert.deepEqual(receipt.page_errors,[]);
  receipt.status='PASS';
  console.log(JSON.stringify({status:receipt.status,checks:receipt.checks,frame:receipt.frame,firmware_source_sha256:receipt.firmware_source_sha256,runtime_sha256:identity.sha256}));
} finally {
  if(ownedId&&!deleted){try{await writeFile(resolve(output,'cleanup-evidence.zip'),await api(`sessions/${ownedId}/evidence`));await api(`sessions/${ownedId}?purge=0`,'DELETE');}catch(error){receipt.cleanup_error=error.message;}}
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
  await writeFile(resolve(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
}
