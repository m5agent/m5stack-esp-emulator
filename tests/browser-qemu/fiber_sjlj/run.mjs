#!/usr/bin/env node
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {open,readFile} from 'node:fs/promises';
import {extname,relative,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {createRequire} from 'node:module';

const {values:args}=parseArgs({options:{'out-dir':{type:'string'},'browser-executable':{type:'string'},'playwright-module':{type:'string'}}});
assert.ok(args['out-dir'],'--out-dir must name the existing build output');
const require=createRequire(import.meta.url);
const {chromium}=args['playwright-module']?require(resolve(args['playwright-module'])):require('playwright');
const base=resolve(args['out-dir']),site=resolve(base,'site');
const reportFile=await open(resolve(base,'report.json'),'wx');
const report={status:'FAIL',category:'no-guest-fiber-sjlj-reproducer',started_at:new Date().toISOString(),firmware_execution:'NOT RUN',qemu_machine_execution:'NOT RUN',hardware_execution:'NOT RUN',variants:{},checks:{}};
const profiles={
 'baseline-2m':{restore_after_longjmp:0,stack_size:'2MB',pthread_stack_size:'2MB'},
 'compat-2m':{restore_after_longjmp:1,stack_size:'2MB',pthread_stack_size:'2MB'},
 'compat-64k':{restore_after_longjmp:1,stack_size:'64KB',pthread_stack_size:'64KB'},
};
const assetNames=['index.html','repro.js','repro.wasm','repro.worker.js'];
const sha=data=>createHash('sha256').update(data).digest('hex');
const verifiedAssets=new Map();
report.served_artifacts={};
const types={'.html':'text/html;charset=utf-8','.js':'text/javascript;charset=utf-8','.wasm':'application/wasm'};
let server,browser,failure;
try{
 const receiptBytes=await readFile(resolve(base,'build-receipt.json'));
 const receipt=JSON.parse(receiptBytes);
 assert.equal(receipt.status,'PASS','build receipt must report PASS');
 assert.equal(receipt.sdk,'3.1.50');
 assert.equal(receipt.source_sha256,sha(await readFile(new URL('repro.c',import.meta.url))),'reproducer source hash mismatch');
 assert.match(receipt.libffi_sha256,/^[0-9a-f]{64}$/);
 assert.match(receipt.build_script_sha256,/^[0-9a-f]{64}$/);
 assert.deepEqual(receipt.profiles,profiles,'build profile mismatch');
 report.build={receipt_sha256:sha(receiptBytes),sdk:receipt.sdk,source_sha256:receipt.source_sha256,libffi_sha256:receipt.libffi_sha256,profiles:receipt.profiles,build_script_sha256:receipt.build_script_sha256};
 for(const [name,profile] of Object.entries(profiles)){
  const command=receipt.commands[name];
  assert.ok(Array.isArray(command));
  for(const flag of [`-DM5_RESTORE_AFTER_LONGJMP=${profile.restore_after_longjmp}`,`-sSTACK_SIZE=${profile.stack_size}`,`-sDEFAULT_PTHREAD_STACK_SIZE=${profile.pthread_stack_size}`])assert.ok(command.includes(flag),`missing build profile flag: ${name} ${flag}`);
  assert.deepEqual(Object.keys(receipt.artifacts[name]).sort(),[...assetNames].sort());
  for(const filename of assetNames){
   const path=resolve(site,name,filename),data=await readFile(path),expected=receipt.artifacts[name][filename];
   assert.equal(data.length,expected.size,`artifact size mismatch: ${name}/${filename}`);
   assert.equal(sha(data),expected.sha256,`artifact hash mismatch: ${name}/${filename}`);
   verifiedAssets.set(path,{...expected,name:`${name}/${filename}`});
  }
 }
 report.checks.build_artifact_hashes_verified=true;
 server=createServer(async(request,response)=>{try{
 const url=new URL(request.url,'http://localhost'),path=resolve(site,'.'+(url.pathname.endsWith('/')?url.pathname+'index.html':url.pathname));
 assert.ok(path.startsWith(site+sep));
 const expected=verifiedAssets.get(path);assert.ok(expected,'asset is not declared by the verified build');
 const data=await readFile(path);assert.equal(data.length,expected.size);assert.equal(sha(data),expected.sha256);
 const served=report.served_artifacts[relative(site,path)]||={size:data.length,sha256:sha(data),requests:0};served.requests++;
 response.writeHead(200,{'Content-Type':types[extname(path)]||'text/plain','Cache-Control':'no-store','Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp'}).end(data);
}catch{response.writeHead(404).end();}});
 await new Promise((done,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',done);});
 assert.ok(![8787,8830,8841].includes(server.address().port));
 report.test_server_port=server.address().port;
 browser=await chromium.launch({headless:true,...(args['browser-executable']?{executablePath:args['browser-executable']}:{})});
 report.browser=browser.version();
 for(const name of Object.keys(profiles)){
  const context=await browser.newContext(),page=await context.newPage();
  const variant={errors:[],workers:[]};report.variants[name]=variant;
  const workers=[];
  let cleanupStarted=false;
  try{
   page.on('pageerror',error=>variant.errors.push(error.message));
   page.on('worker',worker=>{
    const state={url:worker.url(),closed:false,closed_before_cleanup:false};
    variant.workers.push(state);workers.push({worker,state});
    worker.on('close',()=>{state.closed=true;state.closed_before_cleanup=!cleanupStarted;});
   });
   await page.goto(`http://127.0.0.1:${server.address().port}/${name}/`);
   await page.waitForFunction(()=>globalThis.probe?.exitCode!==null||globalThis.probe?.abort,undefined,{timeout:30000});
   variant.execution=await page.evaluate(()=>probe);
   assert.equal(variant.execution.exitCode,0,'normal libc exit(0) must reach onExit');
   assert.ok(!variant.execution.abort);
   const rows=variant.execution.output.filter(text=>text.startsWith('M5_SETJMP_ROW ')).map(text=>JSON.parse(text.substring('M5_SETJMP_ROW '.length)));
   const parseMarker=prefix=>JSON.parse(variant.execution.output.find(text=>text.startsWith(prefix)).substring(prefix.length));
   variant.start=parseMarker('M5_SETJMP_START ');
   variant.result=parseMarker('M5_SETJMP_DONE ');
   variant.c_result=parseMarker('M5_SETJMP_RESULT ');
   variant.rows=rows;variant.lanes={};
   for(const lane of [0,1]){
    const data=rows.filter(row=>row.lane===lane);
    variant.lanes[lane]={count:data.length,first:data[0],last:data.at(-1),
     before_setjmp_unique_count:new Set(data.map(row=>row.before_setjmp)).size,
     before_restore_deltas:[...new Set(data.map(row=>row.before_restore-row.before_setjmp))],
     after_longjmp_deltas:[...new Set(data.map(row=>row.after_longjmp-row.before_setjmp))],
     restore_mismatches:data.filter(row=>row.before_setjmp!==row.after_longjmp).length,
     fiber_sp_mismatches:data.filter(row=>row.before_fiber_swap!==row.after_fiber_swap).length};
    assert.equal(data.length,1000);
    assert.ok(data.every((row,index)=>row.iteration===index&&row.helper_calls===1&&row.fiber_visits===1&&row.before_fiber_swap===row.after_fiber_swap));
   }
   assert.equal(variant.execution.initial.isolated,true);
   assert.equal(variant.execution.initial.sab,'function');
   assert.equal(rows.length,2000);
   assert.equal(variant.result.callback_count,2000);
   assert.equal(variant.result.fiber_visit_count,2000);
   assert.equal(variant.result.bad_callbacks,0);
   assert.deepEqual(variant.errors,[]);
   if(name==='baseline-2m'){
    assert.equal(variant.c_result.compat,0);
    assert.equal(variant.c_result.result,1);
    assert.equal(variant.result.restore_mismatches,2000);
    assert.equal(variant.result.entry_drift,1998);
    assert.ok(variant.lanes[0].after_longjmp_deltas[0]<0);
    assert.ok(variant.lanes[1].after_longjmp_deltas[0]<0);
    variant.status='EXPECTED FAILURE REPRODUCED';
   }else{
    assert.equal(variant.c_result.compat,1);
    assert.equal(variant.c_result.result,0);
    assert.equal(variant.result.restore_mismatches,0);
    assert.equal(variant.result.entry_drift,0);
    assert.equal(variant.lanes[0].before_setjmp_unique_count,1);
    assert.equal(variant.lanes[1].before_setjmp_unique_count,1);
    assert.deepEqual(variant.lanes[0].after_longjmp_deltas,[0]);
    assert.deepEqual(variant.lanes[1].after_longjmp_deltas,[0]);
    variant.status='PASS';
   }
   assert.ok(workers.length>0,'proxy-main must create a real Worker');
   await Promise.all(workers.map(({worker,state})=>state.closed?undefined:worker.waitForEvent('close',{timeout:10000})));
   assert.ok(variant.workers.every(worker=>worker.closed&&worker.closed_before_cleanup));
   assert.equal(page.workers().length,0);
   for(const filename of assetNames)assert.ok(report.served_artifacts[`${name}/${filename}`]?.requests>0,`build artifact was not loaded: ${name}/${filename}`);
   variant.natural_worker_exit=true;
  }catch(error){variant.status='FAIL';variant.failure=error.stack;variant.diagnostic=await page.evaluate(()=>globalThis.probe).catch(error=>({error:error.message}));throw error;}
  finally{cleanupStarted=true;await context.close();variant.context_closed=true;}
 }
 report.status='PASS';
}catch(error){report.failure=error.stack;failure=error;}
finally{
 try{
  if(browser)await browser.close();
  report.checks.browser_closed=true;
 }catch(error){report.status='FAIL';report.browser_cleanup_failure=error.stack;failure||=error;}
 finally{
  try{
   if(server?.listening)await new Promise((done,reject)=>server.close(error=>error?reject(error):done()));
   report.checks.own_static_server_closed=!server?.listening;
  }catch(error){report.status='FAIL';report.server_cleanup_failure=error.stack;failure||=error;}
  finally{
   report.finished_at=new Date().toISOString();report.harness_sha256=sha(await readFile(fileURLToPath(import.meta.url)));
   try{await reportFile.writeFile(JSON.stringify(report,null,2)+'\n');}finally{await reportFile.close();}
   console.log(JSON.stringify({status:report.status,browser:report.browser,variants:Object.fromEntries(Object.entries(report.variants).map(([name,value])=>[name,{status:value.status,result:value.result,c_result:value.c_result,natural_worker_exit:value.natural_worker_exit,workers:value.workers,errors:value.errors}]))}));
  }
 }
}
if(failure)throw failure;
