// Explicit Chrome host-only control with synthetic HTML/Canvas. No QEMU,
// firmware, Device Service, model viewer, virtual device or hardware is used.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {isMatchingCanvasObservation,waitForCanvasPixels} from './public_qemu_pixel_observer.mjs';

const chrome=process.env.M5_WASM_CHROME||process.env.M5_CHROME;
if(!chrome){console.log('SKIP: explicit M5_CHROME or M5_WASM_CHROME is required for the synthetic host-only Canvas control');process.exit(0);}
const {chromium}=createRequire(import.meta.url)('playwright');
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const out=resolve(process.env.M5_CANVAS_TEST_OUT||resolve(repo,'.work/public-qemu-pixel-observer-host-browser'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'Raw synthetic control evidence must stay in ignored .work');
await mkdir(out,{recursive:false});
const checks=[],pageErrors=[];
const report={kind:'synthetic-canvas-host-browser-control',started_at:new Date().toISOString(),
  helper_sha256:createHash('sha256').update(await readFile(new URL('./public_qemu_pixel_observer.mjs',import.meta.url))).digest('hex'),
  test_script_sha256:createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex'),
  validation_category:'host-only browser control; not virtual-device validation',hardware_validation:'NOT RUN',guest_execution:'NOT RUN',status:'FAIL',checks,page_errors:pageErrors};
const rgbaHash=color=>createHash('sha256').update(Buffer.from(Array.from({length:4},()=>color).flat())).digest('hex');
const BLACK=[0,0,0,255],RED=[255,0,0,255],GREEN=[0,255,0,255];
const regions=[{name:'primary',x:10,y:10,width:2,height:2,expected:rgbaHash(RED)},
  {name:'secondary',x:50,y:20,width:2,height:2,expected:rgbaHash(GREEN)}];
const html=`<!doctype html><meta charset="utf-8"><title>Host-only Canvas control</title>
<div id="deviceMount" data-frame-sequence="0"><canvas id="rawFrameCanvas" width="320" height="240"></canvas></div>
<script>
window.paintSyntheticFrame=(frame,sequence)=>{
 const canvas=document.querySelector('#rawFrameCanvas'),ctx=canvas.getContext('2d');
 ctx.fillStyle='black';ctx.fillRect(0,0,320,240);
 const colors=frame==='A'?['rgb(255,0,0)','rgb(0,255,0)']:frame==='B'?['rgb(0,0,255)','rgb(255,255,0)']:['black','black'];
 ctx.fillStyle=colors[0];ctx.fillRect(10,10,2,2);ctx.fillStyle=colors[1];ctx.fillRect(50,20,2,2);
 document.querySelector('#deviceMount').dataset.frameSequence=String(sequence);
};paintSyntheticFrame('zero',0);
</script>`;
let browser,context,page;
const check=(name,evidence)=>{checks.push({name,result:'PASS',evidence});};
try{
  browser=await chromium.launch({executablePath:chrome,headless:true,args:['--disable-background-networking']});
  report.browser=browser.version();
  context=await browser.newContext();
  await context.route('**/*',route=>route.request().url()==='https://canvas.example.test/'
    ?route.fulfill({status:200,contentType:'text/html',body:html}):route.abort('blockedbyclient'));
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(String(error)));
  await page.goto('https://canvas.example.test/',{waitUntil:'domcontentloaded'});
  assert.equal(await page.evaluate(()=>isSecureContext&&typeof crypto.subtle.digest==='function'),true);
  report.playwright_version=createRequire(import.meta.url)('playwright/package.json').version;
  // Reproduce the original harness error using the installed real Playwright.
  // This result is deliberately never used as a pixel-match observation.
  let oldHandle;
  try{
    oldHandle=await page.waitForFunction(async()=>false,{}, {timeout:300,polling:25});
    const actual=await oldHandle.jsonValue();assert.equal(actual,false);
    check('old-async-predicate-resolved-with-actual-false',{actual,meaning:'Promise truthiness allowed false to resolve; not pixel evidence'});
  }finally{await oldHandle?.dispose();}

  // Establish the real Canvas readback and digest path before starting the
  // timed frame-transition controls. This setup must itself read frame zero.
  const initialRegions=regions.map(region=>({...region,expected:rgbaHash(BLACK)}));
  const setupStarted=performance.now();
  const initial=await waitForCanvasPixels(page,{regions:initialRegions,
    boundary:{minimumSequence:-1,notBeforeMs:0},timeoutMs:15000});
  assert.equal(initial.frame_sequence,0);
  check('initial-black-frame-readback',{observation:initial,elapsed_ms:performance.now()-setupStarted});

  const boundary=await page.evaluate(()=>({minimumSequence:Number(document.querySelector('#deviceMount').dataset.frameSequence),notBeforeMs:performance.now()}));
  await page.evaluate(()=>setTimeout(()=>paintSyntheticFrame('A',1),60));
  const first=await waitForCanvasPixels(page,{regions,boundary,timeoutMs:1000,pollingMs:10});
  assert.equal(isMatchingCanvasObservation(first,{regions,boundary}),true);
  assert.equal(first.frame_sequence,1);assert.equal(typeof first,'object');assert.ok(!Array.isArray(first));
  check('delayed-actual-canvas-zero-to-one',{observation:first});

  // Fixture-only deterministic race: change the live Canvas and sequence
  // inside the first async digest, after the sampler should own one snapshot.
  // Correct sampling returns both old-frame hashes and its old sequence.
  const raceBoundary=await page.evaluate(()=>{
    paintSyntheticFrame('A',1);
    const native=crypto.subtle.digest.bind(crypto.subtle);
    window.syntheticDigestCalls=0;window.restoreSyntheticDigest=()=>{delete crypto.subtle.digest;};
    Object.defineProperty(crypto.subtle,'digest',{configurable:true,value:async(...args)=>{
      const call=++window.syntheticDigestCalls;
      if(call===1){paintSyntheticFrame('B',2);await new Promise(done=>setTimeout(done,25));}
      return native(...args);
    }});
    return {minimumSequence:0,notBeforeMs:performance.now()};
  });
  const race=await waitForCanvasPixels(page,{regions,boundary:raceBoundary,timeoutMs:1000,pollingMs:10});
  const raceState=await page.evaluate(()=>({calls:syntheticDigestCalls,live_sequence:Number(document.querySelector('#deviceMount').dataset.frameSequence)}));
  await page.evaluate(()=>restoreSyntheticDigest());
  assert.equal(race.frame_sequence,1,'Observed sequence is captured with the pixel buffer, not after asynchronous hashes');
  assert.equal(raceState.live_sequence,2);assert.equal(raceState.calls,2);
  assert.deepEqual(race.regions,regions.map(r=>({name:r.name,rgba_sha256:r.expected})),'The two ROI hashes must come from the same old snapshot');
  check('async-hash-live-frame-race-single-snapshot',{observation:race,...raceState,scope:'Synthetic fixture digest hook only; no guest or product data modified'});

  const wrongBoundary=await page.evaluate(()=>{paintSyntheticFrame('B',3);return {minimumSequence:2,notBeforeMs:performance.now()};});
  await assert.rejects(waitForCanvasPixels(page,{regions,boundary:wrongBoundary,timeoutMs:120,pollingMs:20}),error=>{
    assert.match(error.message,/timeout|timed out/i);
    assert.equal(error.lastObservation.frame_sequence,3);
    assert.equal(isMatchingCanvasObservation(error.lastObservation,{regions,boundary:wrongBoundary}),false);
    check('real-wrong-hashes-timeout',{last_observation:error.lastObservation});return true;
  });
  assert.equal(pageErrors.length,0);report.status='PASS';
}catch(error){report.failure=String(error.stack||error);process.exitCode=1;}
finally{
  await context?.close().catch(error=>(report.cleanup_errors||=[]).push(String(error)));
  await browser?.close().catch(error=>(report.cleanup_errors||=[]).push(String(error)));
  report.browser_closed=browser?!browser.isConnected():true;
  if(report.cleanup_errors?.length||!report.browser_closed){report.status='FAIL';process.exitCode=1;}
  report.finished_at=new Date().toISOString();
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
}
console.log(`HOST_CANVAS_BROWSER_${report.status}: synthetic HTML only; no guest; ${checks.length} controls; report.json retained`);
