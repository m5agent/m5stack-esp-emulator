// Opt-in real guest benchmark. No native emulator or Device Service is used.
// M5_PUBLIC_SITE=.work/qemu-public-site-final M5_CHROME=/path/to/chrome \
// NODE_PATH=/path/to/node_modules node platform/tests/test_public_qemu_performance.mjs
// Optional: M5_QEMU_PERF_OUT, M5_QEMU_PERF_SAMPLE_MS, M5_QEMU_PERF_TRIALS,
// M5_QEMU_PERF_BASELINE=<previous report.json>, M5_QEMU_PERF_GPU=hardware|swiftshader,
// M5_QEMU_EXAMPLE=stock-div8 (default) | wallclock-candidate,
// M5_QEMU_PERF_SOURCE_REF=<commit> for a frozen old export. New output folder only.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {resolve,dirname,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import os from 'node:os';
import {capturePublicQemuProvenance,QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';
import {distribution,installPerformanceProbe,summarizePerformance,installAnimationProbe,summarizeAnimationCurve} from './public_qemu_performance.mjs';
const exec=promisify(execFile),repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=resolve(process.env.M5_PUBLIC_SITE||resolve(repo,'.work/qemu-public-site-final'));
const sourceRoot=resolve(process.env.M5_QEMU_PERF_SOURCE_ROOT||repo);
const out=resolve(process.env.M5_QEMU_PERF_OUT||resolve(repo,`.work/public-qemu-performance-${new Date().toISOString().replace(/[:.]/g,'-')}`));
function integer(name,fallback,min,max){const value=Number(process.env[name]??fallback);assert.ok(Number.isInteger(value)&&value>=min&&value<=max,`${name} must be ${min}..${max}`);return value;}
const sampleMs=integer('M5_QEMU_PERF_SAMPLE_MS',10000,5000,120000),controlMs=integer('M5_QEMU_PERF_CONTROL_MS',10000,5000,60000),trials=integer('M5_QEMU_PERF_TRIALS',6,1,30);
const gpuMode=process.env.M5_QEMU_PERF_GPU||'swiftshader';assert.ok(['swiftshader','hardware'].includes(gpuMode));
const example=process.env.M5_QEMU_EXAMPLE||'stock-div8';assert.ok(['stock-div8','wallclock-candidate'].includes(example));
const fixture=example==='stock-div8'?{sha256:'78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f',profile:'cores3-wasm-vm-div8',clockDivisor:8}
  :{sha256:'e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554',profile:'cores3-wasm-wallclock-sdk-candidate',clockDivisor:1,sourceSHA256:'4d60594952ef5af609084fc519e85b7064349b0782da35836b8c1673cdd73ecf',schedulerCandidate:'sdk-python-single-schedule-v1'};
if(process.argv.includes('--self-test')){
  assert.deepEqual(distribution([]),{samples:0,min:null,p50:null,p90:null,p95:null,max:null,mean:null});
  assert.equal(distribution([40,10,30,20,null,NaN]).p50,25);assert.equal(distribution([7]).p95,7);
  const animation=summarizeAnimationCurve({animation:{roi:{},period_pixels:260,samples:[270,20,30].map((centroid_x,index)=>({phase:'steady',at_ms:index*100,centroid_x,roi_digest:String(index),observer_ms:1}))},
    phases:[{name:'steady',start_ms:0,end_ms:200}],guest_events:[]});
  assert.equal(animation.phases.steady.wraps,1);assert.equal(animation.phases.steady.centroid_velocity_pixels_per_host_second,100);
  assert.equal(summarizeAnimationCurve({}),null);
  console.log('performance statistics self-test PASS');process.exit(0);
}
const {chromium}=createRequire(import.meta.url)('playwright');
assert.ok(out.startsWith(resolve(repo,'.work')+sep),'raw performance output must stay in repository .work');
try{await stat(out);throw new Error('Output exists; preserve it and select a new M5_QEMU_PERF_OUT');}catch(error){if(error.code!=='ENOENT')throw error;}
await mkdir(out,{recursive:true});
const report={kind:'browser-local-qemu-performance',schema_version:1,started_at:new Date().toISOString(),configuration:{sample_ms:sampleMs,control_ms:controlMs,input_trials:trials,hold_ms:650,resource_interval_ms:1000,gpu_mode:gpuMode,example},
  host:{platform:os.platform(),release:os.release(),arch:os.arch(),logical_cpus:os.cpus().length,cpu_model:os.cpus()[0]?.model,total_memory_bytes:os.totalmem(),load_average_at_start:os.loadavg()},
  scope:{execution:'actual CoreS3 guest in exported static browser site',fps:'framebuffer capture delivery, including unchanged captures; not guest redraw FPS; a dirty-only idle publisher can deliver zero frames',callback:'guest callback observed via real UART serial on the browser main thread',visible:'counter-label pixels committed to 2D canvas after a matching guest click; double requestAnimationFrame is a browser paint opportunity, not optical display latency',cpu:'sum of matched owned-browser process cpuTime deltas / wall interval; 100 percent is one CPU core; includes shell/GPU/browser and QEMU pthreads attributed to renderer, not a per-thread breakdown',memory:'sum of process RSS may double-count shared pages and is not unique residency; page-target JS heap excludes WASM/shared heap and worker heaps; receipt memoryBytes is initial shared WASM allocation',service_worker:'isolation Service Worker lifecycle is excluded from runtime pthread count'},resources:[],workers:[],errors:[],requests:[],checks:[]};
let server,browser,context,page,resourceTimer,sampleInFlight=false,lastResource,cdp,pageCDP,closingContext=false;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'};
const check=(name,value)=>{report.checks.push({name,ok:!!value});assert.ok(value,name);};
async function snapshot(){return page.evaluate(()=>__m5QemuPerformance.snapshot());}
async function waitCondition(predicate,arg,timeout=180000){await page.waitForFunction(predicate,arg,{timeout});const error=await page.locator('#errorBanner').textContent();if(error)throw new Error(error);}
async function evidence(name){const pending=page.waitForEvent('download');await page.locator('#browserEvidenceBtn').click();const download=await pending;const path=resolve(out,name+'.json');await download.saveAs(path);return JSON.parse(await readFile(path,'utf8'));}
async function sampleResources(){
  if(sampleInFlight||!cdp||!page)return;sampleInFlight=true;
  try{
    const now=performance.now(),phase=await page.evaluate(()=>globalThis.__m5QemuPerformance?.phase||'navigation'),{processInfo}=await cdp.send('SystemInfo.getProcessInfo'),metrics=await pageCDP.send('Performance.getMetrics');
    const values=Object.fromEntries(metrics.metrics.map(row=>[row.name,row.value])),row={at_node_ms:now,phase,processes:processInfo,js_heap_used_bytes:values.JSHeapUsedSize??null,js_heap_total_bytes:values.JSHeapTotalSize??null,renderer_task_duration_seconds:values.TaskDuration??null,interval_cpu_percent:null,summed_rss_kib:null};
    if(lastResource&&lastResource.phase===phase){let cpu=0,matched=0;row.cpu_by_process_type={};row.cpu_by_process=[];const seconds=(now-lastResource.at_node_ms)/1000,previous=new Map(lastResource.processes.map(process=>[String(process.id),process.cpuTime]));for(const process of processInfo){const old=previous.get(String(process.id));if(old!==undefined&&process.cpuTime>=old){const delta=process.cpuTime-old,percent=100*delta/seconds;cpu+=delta;matched++;row.cpu_by_process.push({id:process.id,type:process.type,cpu_percent:percent});row.cpu_by_process_type[process.type]=(row.cpu_by_process_type[process.type]||0)+percent;}}row.interval_cpu_percent=matched?100*cpu/seconds:null;row.matched_processes=matched;}
    const ids=processInfo.map(process=>String(process.id)).filter(id=>/^\d+$/.test(id));
    if(ids.length){try{const {stdout}=await exec('ps',['-p',ids.join(','),'-o','pid=','-o','rss=']);row.process_rss_kib=stdout.trim().split('\n').map(line=>{const [pid,rss]=line.trim().split(/\s+/).map(Number);return {pid,rss};});row.summed_rss_kib=row.process_rss_kib.reduce((sum,process)=>sum+process.rss,0);}catch(error){row.rss_unavailable=error.code||error.name;}}
    report.resources.push(row);lastResource=row;
  }catch(error){report.resources.push({phase:'unavailable',error:String(error.message)});}finally{sampleInFlight=false;}
}
try{
  report.source_head=(await exec('git',['rev-parse',process.env.M5_QEMU_PERF_SOURCE_REF||'HEAD'],{cwd:repo})).stdout.trim();
  report.source_input=process.env.M5_QEMU_PERF_SOURCE_ROOT?'frozen-source-root':process.env.M5_QEMU_PERF_SOURCE_REF?'git-source-ref':'working-source';
  const sourceSnapshot=resolve(out,'executed-source');
  const declared=new Set(JSON.parse(await readFile(resolve(site,'public-site-manifest.json'),'utf8')).assets.map(row=>row.path));
  const webPaths=QEMU_EXECUTED_WEB_PATHS.filter(path=>declared.has(path));
  report.execution_web_paths=webPaths;
  for(const path of [...webPaths,'platform/tests/test_public_qemu_performance.mjs','platform/tests/public_qemu_performance.mjs','platform/tests/public_qemu_artifacts.mjs','platform/tools/build_public_site.py']){
    const inputRoot=webPaths.includes(path)||path==='platform/tools/build_public_site.py'?sourceRoot:repo;
    const bytes=process.env.M5_QEMU_PERF_SOURCE_REF&&webPaths.includes(path)?(await exec('git',['show',`${report.source_head}:${path}`],{cwd:repo,maxBuffer:4*1024*1024,encoding:'buffer'})).stdout:await readFile(resolve(inputRoot,path));
    const target=resolve(sourceSnapshot,path);await mkdir(dirname(target),{recursive:true});await writeFile(target,bytes);
  }
  report.provenance=await capturePublicQemuProvenance({repo:sourceSnapshot,site,webPaths,testScript:'platform/tests/test_public_qemu_performance.mjs'});
  report.helper_sha256=createHash('sha256').update(await readFile(fileURLToPath(new URL('./public_qemu_performance.mjs',import.meta.url)))).digest('hex');
  report.baseline_observer_function_sha256=createHash('sha256').update(installPerformanceProbe.toString()).digest('hex');
  const base=report.provenance.base_path;
  server=createServer(async(req,res)=>{try{const path=new URL(req.url,'http://localhost').pathname;if(!path.startsWith(base)){res.writeHead(404).end();return;}const file=resolve(site,decodeURIComponent(path.slice(base.length))||'index.html');if(!file.startsWith(site+sep)){res.writeHead(403).end();return;}res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(await readFile(file));}catch{res.writeHead(404).end();}});
  await new Promise(done=>server.listen(0,'127.0.0.1',done));const port=server.address().port;assert.ok(![8787,8830].includes(port));report.url=`http://127.0.0.1:${port}${base}`;
  report.configuration.browser_args=gpuMode==='swiftshader'?['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']:['--enable-gpu','--enable-webgl','--use-gl=angle',...(os.platform()==='darwin'?['--use-angle=metal']:[])];
  browser=await chromium.launch({headless:true,...(process.env.M5_CHROME?{executablePath:process.env.M5_CHROME}:{}),args:report.configuration.browser_args});
  report.browser_version=browser.version();context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{report.requests.push({blocked:true,url:route.request().url()});return route.abort('blockedbyclient');});
  page=await context.newPage();page.on('pageerror',error=>report.errors.push(String(error)));
  page.on('request',request=>{const url=new URL(request.url());report.requests.push({url:url.origin+url.pathname,method:request.method()});});
  page.on('worker',worker=>{const row={url:worker.url(),created_at:new Date().toISOString()};report.workers.push(row);worker.on('close',()=>{row.closed_at=new Date().toISOString();row.closed_before_context_close=!closingContext;});});
  cdp=await browser.newBrowserCDPSession();pageCDP=await context.newCDPSession(page);await pageCDP.send('Performance.enable');
  await page.goto(report.url,{waitUntil:'domcontentloaded'});
  await waitCondition(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{},45000);
  if(await page.locator('#referenceExample').count()){
    await page.locator('#referenceExample').selectOption(example);
    check('explicit-public-reference-example',await page.locator('#referenceExample').inputValue()===example);
  }else check('legacy-site-stock-example',example==='stock-div8');
  await page.evaluate(installPerformanceProbe,{moduleURL:new URL('platform/web/public-qemu-runtime.js',report.url).href});
  if(example==='wallclock-candidate')await page.evaluate(installAnimationProbe,{moduleURL:new URL('platform/web/public-qemu-runtime.js',report.url).href});
  await sampleResources();resourceTimer=setInterval(()=>void sampleResources(),1000);
  await page.locator('#startBtn').click();
  await waitCondition(()=>__m5QemuPerformance.guest_events.some(row=>row.event.kind==='ready')||!document.querySelector('#errorBanner').hidden);
  await waitCondition(()=>__m5QemuPerformance.frames.some(row=>row.varied)||!document.querySelector('#errorBanner').hidden,{},45000);
  await page.locator('#nativeScreenBtn').click();
  report.webgl=await page.evaluate(()=>Array.from(document.querySelectorAll('#deviceMount canvas')).flatMap(canvas=>{
    const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');if(!gl)return [];
    const ext=gl.getExtension('WEBGL_debug_renderer_info');return [{canvas_id:canvas.id,version:gl.getParameter(gl.VERSION),vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),unmasked_vendor:ext?gl.getParameter(ext.UNMASKED_VENDOR_WEBGL):null,unmasked_renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null}];
  }));
  const gpuInfo=await cdp.send('SystemInfo.getInfo');report.gpu={devices:gpuInfo.gpu.devices,aux_attributes:gpuInfo.gpu.auxAttributes,feature_status:gpuInfo.gpu.featureStatus};
  if(gpuMode==='hardware')check('actual-hardware-webgl-renderer',report.webgl.length>0&&report.webgl.every(row=>row.unmasked_renderer&&!/swiftshader|llvmpipe|softpipe|software/i.test(row.unmasked_renderer)&&/Apple|AMD|Intel|NVIDIA|Qualcomm|Adreno|Mali|PowerVR/i.test(row.unmasked_renderer+' '+row.unmasked_vendor)));
  await page.waitForTimeout(1800);report.boot_evidence=await evidence('boot-evidence');
  const receipt=report.boot_evidence.receipt;
  check('exact-real-guest',receipt.firmwareSha256===fixture.sha256&&receipt.profile===fixture.profile&&receipt.clockDivisor===fixture.clockDivisor);
  if(example==='wallclock-candidate')check('exact-sdk-scheduler-candidate',receipt.firmwareVariant?.sourceSHA256===fixture.sourceSHA256&&receipt.firmwareVariant.schedulerCandidate===fixture.schedulerCandidate);
  await page.evaluate(()=>__m5QemuPerformance.setPhase('steady'));console.log('Sampling actual guest captures');
  await page.waitForTimeout(sampleMs);await page.evaluate(()=>__m5QemuPerformance.setPhase('input'));
  for(let index=1;index<=trials;index++){
    await page.evaluate(id=>{const p=__m5QemuPerformance;p.active_trial=id;p.trials.push({id,clicks:id,before_roi:p.roi(),armed_ms:performance.now()});},index);
    const box=await page.locator('#rawFrameCanvas').boundingBox();assert.ok(box?.width&&box?.height);
    await page.mouse.move(box.x+box.width*160/320,box.y+box.height*184/240);await page.mouse.down();await page.waitForTimeout(650);await page.mouse.up();
    await waitCondition(id=>{const p=__m5QemuPerformance,t=p.trials.find(row=>row.id===id),click=p.guest_events.find(row=>row.event.kind==='touch_clicked'&&row.event.clicks===t.clicks);return !!(click&&p.frames.some(row=>row.at_ms>=click.at_ms&&row.roi_digest&&row.roi_digest!==t.before_roi&&row.paint_opportunity_ms))||!document.querySelector('#errorBanner').hidden;},index,20000);
    await page.waitForTimeout(250);
  }
  await page.screenshot({path:resolve(out,'after-input.png'),fullPage:true});
  await page.evaluate(()=>__m5QemuPerformance.setPhase('transition'));await page.locator('#pauseBtn').click();await waitCondition(()=>document.querySelector('#runtimeStatus').dataset.status==='paused',{},30000);
  await page.evaluate(()=>__m5QemuPerformance.setPhase('paused'));console.log('Sampling paused browser control');await page.waitForTimeout(controlMs);
  await page.evaluate(()=>__m5QemuPerformance.setPhase('transition'));await page.locator('#pauseBtn').click();await waitCondition(()=>document.querySelector('#runtimeStatus').dataset.status==='running',{},30000);
  await page.waitForTimeout(300);await page.evaluate(()=>__m5QemuPerformance.setPhase('stopping'));report.before_stop=await evidence('before-stop-evidence');
  const runtimeTargets=async()=>((await cdp.send('Target.getTargets')).targetInfos).filter(row=>row.type==='worker'&&row.url.startsWith('blob:'+new URL(report.url).origin+'/'));
  report.worker_targets_before_stop=await runtimeTargets();
  await page.locator('#stopBtn').click();await waitCondition(()=>document.querySelector('#runtimeStatus').dataset.status==='stopped',{},30000);
  await page.evaluate(()=>__m5QemuPerformance.setPhase('stopped'));console.log('Sampling stopped browser control');await page.waitForTimeout(controlMs);
  report.worker_targets_after_stop=await runtimeTargets();report.worker_close_events_before_context_close=report.workers.filter(row=>row.closed_before_context_close).length;
  report.stopped_evidence=await evidence('stopped-evidence');await page.evaluate(()=>__m5QemuPerformance.setPhase('finished'));
  report.probe=await snapshot();report.summary=summarizePerformance(report.probe,report.resources);
  if(example==='wallclock-candidate'){
    report.animation_curve=summarizeAnimationCurve(report.probe);
    check('actual-guest-animation-pixels',report.animation_curve.phases.steady.distinct_roi>=2&&report.animation_curve.phases.steady.glyph_samples>=2);
    await writeFile(resolve(out,'animation-curve.csv'),'phase,host_ms,frame_sequence,centroid_x,unwrapped_x,yellow_pixels\n'+Object.entries(report.animation_curve.phases).flatMap(([phase,row])=>row.curve.map(sample=>[phase,sample.at_ms,sample.sequence,sample.centroid_x,sample.unwrapped_x,sample.yellow_pixels].join(','))).join('\n')+'\n');
  }
  check('actual-frame-requests',report.summary.steady_capture.requests>=3);
  check('guest-callback-and-counter-pixels',report.summary.input_trials.every(row=>row.up_to_callback_ms!==null&&row.up_to_visible_commit_ms!==null&&row.after_roi!==row.before_roi));
  const cleanup=report.stopped_evidence.cleanup;check('graceful-guest-quit',cleanup.gracefulExit&&cleanup.exitCode===0);
  check('no-runtime-worker-leak',cleanup.explicitWorkerDisposal&&cleanup.workersAtExit===0&&cleanup.disposal?.workersRemaining===0&&cleanup.disposal?.workersTerminatedByDispose===0&&report.workers.length>0&&report.worker_targets_before_stop.length>0&&report.worker_targets_after_stop.length===0);
  check('iframe-removed',await page.locator('iframe[src*="public-qemu-instance.html"]').count()===0);
  check('no-service-attempts',!report.requests.some(row=>row.blocked));check('no-javascript-errors',report.errors.length===0);
  if(process.env.M5_QEMU_PERF_BASELINE){const baseline=JSON.parse(await readFile(resolve(process.env.M5_QEMU_PERF_BASELINE),'utf8'));assert.equal(baseline.result,'PASS');assert.equal(baseline.boot_evidence.receipt.firmwareSha256,report.boot_evidence.receipt.firmwareSha256);baseline.summary=summarizePerformance(baseline.probe,baseline.resources);const metrics={capture_requests_fps:r=>r.summary.steady_capture.requests_per_second,delivered_frames_fps:r=>r.summary.steady_capture.frames_per_second,new_pixels_fps:r=>r.summary.steady_capture.new_pixel_frames_per_second,frame_request_p50_ms:r=>r.summary.steady_capture.request_ms.p50,input_up_to_frame_p50_ms:r=>r.summary.input_latency_ms.up_to_visible_commit_ms.p50,input_up_to_callback_p50_ms:r=>r.summary.input_latency_ms.up_to_callback_ms.p50,browser_cpu_mean_percent:r=>r.summary.resources.browser_process_cpu_percent.mean,rss_mean_kib:r=>r.summary.resources.summed_process_rss_kib.mean};report.comparison={baseline_report_sha256:createHash('sha256').update(await readFile(resolve(process.env.M5_QEMU_PERF_BASELINE))).digest('hex'),baseline_summary_recomputed_from_raw:true,same_gpu_mode:(baseline.configuration.gpu_mode||'swiftshader')===gpuMode,same_gl_renderer:JSON.stringify(baseline.webgl)===JSON.stringify(report.webgl),same_browser:baseline.browser_version===report.browser_version,same_host:baseline.host.cpu_model===report.host.cpu_model&&baseline.host.logical_cpus===report.host.logical_cpus,metrics:Object.fromEntries(Object.entries(metrics).map(([name,get])=>{const before=get(baseline),after=get(report);return [name,{baseline:before,current:after,delta:before!==null&&after!==null?after-before:null,ratio:before?after/before:null}];}))};}
  report.result='PASS';
}catch(error){report.result='FAIL';report.failure=String(error.stack||error);console.error(error);if(page){report.probe=await snapshot().catch(()=>null);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}}
finally{
  clearInterval(resourceTimer);while(sampleInFlight)await new Promise(done=>setTimeout(done,25));
  if(page)await page.locator('#stopBtn').click({timeout:2000}).catch(()=>{});
  closingContext=true;await context?.close();await browser?.close();if(server)await new Promise(done=>server.close(done));
  report.finished_at=new Date().toISOString();report.host.load_average_at_finish=os.loadavg();
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
  await writeFile(resolve(out,'summary.json'),JSON.stringify({result:report.result,summary:report.summary,comparison:report.comparison,failure:report.failure},null,2)+'\n');
  console.log(JSON.stringify({result:report.result,output:out,summary:report.summary,comparison:report.comparison}));if(report.result!=='PASS')process.exitCode=1;
}
