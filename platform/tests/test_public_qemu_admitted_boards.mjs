// Publication gate: each public default editor and buttons, then fixed examples.
// Compilation and another image's results never grant browser admission.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateQemuBrowserProfiles, ATOM_MATRIX_WORKBENCH_FLASH_SHA256,
  ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS} from '../web/public-qemu-profiles.js';
import {validateUIFlowWorkbenchRegistry} from '../web/public-uiflow-firmware.js';
import {PUBLIC_QEMU_BUTTON_CASES} from './public_qemu_button_cases.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export const PUBLIC_QEMU_GATE_PHASES=Object.freeze(['all','uiflow','editor','buttons','fixed']);

export function publicQemuGateWorkers(value,{ci=false}={}){
  assert.ok(value===undefined||value==='1'||value==='2','M5_QEMU_GATE_WORKERS must be exactly 1 or 2');
  const workers=value===undefined?1:Number(value);
  assert.ok(!ci||workers===1,'CI requires M5_QEMU_GATE_WORKERS=1');
  return workers;
}

/** Process-free scheduling contract. Each callback owns one independent child
 * until its report and normal cleanup finish. Failure stops dispatch, not the
 * other callback's cleanup. The result never rejects while callbacks are live. */
export async function schedulePublicQemuGate(cases,{workers=1,runCase}={}){
  assert.ok(workers===1||workers===2,'Gate workers must be 1 or 2');
  assert.ok(Array.isArray(cases)&&cases.length&&typeof runCase==='function','Gate cases and callback required');
  const lanes=['uiflow-editor','uiflow-buttons','cardputer-keyboard','stackchan-body-touch','fixed'];
  assert.ok(cases.every(item=>typeof item.device==='string'&&lanes.includes(item.lane)),'Unknown scheduled gate case');
  const rows=cases.map(item=>({...item,status:'NOT RUN'}));
  let firstFailure=null,active=0,maxActive=0;
  for(const phase of ['uiflow','fixed']){
    if(firstFailure)break;
    const byDevice=new Map();
    cases.forEach((item,index)=>{
      if((item.lane==='fixed')!==(phase==='fixed'))return;
      if(!byDevice.has(item.device))byDevice.set(item.device,[]);
      byDevice.get(item.device).push(index);
    });
    const groups=[...byDevice.values()];let nextGroup=0;
    async function worker(workerId){
      while(!firstFailure){
        const group=groups[nextGroup++];if(!group)return;
        for(const index of group){
          if(firstFailure)return;
          const item=cases[index],row=rows[index];
          Object.assign(row,{status:'RUNNING',worker:workerId,phase});
          active++;maxActive=Math.max(maxActive,active);
          const noteFailure=error=>{firstFailure??={case_index:index,...item,worker:workerId,phase,
            error:String(error?.message||error).slice(0,2000)};};
          try{
            const result=await runCase({...item},{index,worker:workerId,phase,noteFailure});
            Object.assign(row,result,item,{worker:workerId,phase,status:result?.status});
            if(row.status!=='PASS')throw new Error(row.error||'Gate callback did not return PASS');
          }catch(error){
            row.status='FAIL';row.error=String(error?.message||error).slice(0,2000);
            noteFailure(error);
          }finally{active--;}
        }
      }
    }
    // Never let one rejection finish the parent while the other child is live.
    const completed=await Promise.allSettled(Array.from({length:Math.min(workers,groups.length)},(_,i)=>worker(i+1)));
    for(const result of completed)if(result.status==='rejected')
      firstFailure??={case_index:null,phase,error:String(result.reason?.message||result.reason).slice(0,2000)};
  }
  if(firstFailure)for(const row of rows)if(row.status==='NOT RUN')row.not_run_reason='Dispatch stopped after the first failure';
  return {workers,max_active_children:maxActive,first_failure:firstFailure,cases:rows,
    all_passed:!firstFailure&&rows.every(row=>row.status==='PASS')};
}

/** One explicit export/image/input path for every gate child. Standalone
 * runners retain diagnostic overrides; a publication case cannot inherit them. */
export function publicQemuGateChildEnvironment(parent,item,{site,output}){
  const chrome=parent.M5_WASM_CHROME||parent.M5_CHROME||'';
  return {...parent,M5_PUBLIC_SITE:site,M5_PUBLIC_QEMU_OUT:output,M5_QEMU_DEVICE:item.device,
    M5_QEMU_EXAMPLE:item.example||'',M5_UIFLOW_SMOKE_ONLY:'',M5_PUBLIC_UI:'1',M5_PUBLIC_URL:'',
    M5_QEMU_UPLOAD:'',M5_QEMU_CLOCK_DIVISOR:'',M5_QEMU_FRAME_DIAGNOSTIC:'',
    M5_CARDPUTER_KEYBOARD_IRQ:item.lane==='cardputer-keyboard'?'1':'',
    M5_QEMU_BUTTON_HOLD_MS:'250',M5_WASM_CHROME:chrome,M5_CHROME:chrome};
}

/** Bind each actual child report to this test source, export and runtime.
 * Different runner receipt layouts are explicit; missing fields fail closed. */
export function validatePublicQemuGateResult(item,result,{workbenchRegistry,wasmSHA256,siteManifestSHA256,testScriptSHA256}){
  const provenance=result.provenance;
  assert.equal(provenance?.site_manifest_sha256,siteManifestSHA256,'Gate cannot inherit another export result');
  assert.equal(provenance?.test_script?.path,'platform/tests/'+item.script,'Gate child control script path mismatch');
  assert.equal(provenance?.test_script?.sha256,testScriptSHA256,'Gate child control script SHA mismatch');
  const runtimeArtifact=item.device==='corematrix'
    ? provenance?.c61_runtime_assets?.['qemu-system-riscv32.wasm']
    : provenance?.runtime_assets?.['qemu-system-xtensa.wasm'];
  assert.equal(runtimeArtifact?.sha256,wasmSHA256,'Gate cannot inherit another runtime result');
  if(item.lane==='fixed')return;
  assert.ok(['uiflow-editor','uiflow-buttons','stackchan-body-touch','cardputer-keyboard'].includes(item.lane),'Unknown workbench lane');
  const expected=workbenchRegistry.profiles.find(row=>row.deviceId===item.device);
  assert.ok(expected,'Gate workbench identity missing');
  const receipt=item.lane==='cardputer-keyboard'?result.initial?.evidence?.receipt
    :item.lane==='uiflow-buttons'?result.running?.receipt:result.initial?.receipt;
  assert.equal(receipt?.deviceId,item.device,'Gate child device mismatch');
  assert.equal(receipt?.firmwareSha256,expected.firmwareSHA256,'Gate requires the exact default workbench image');
  assert.equal(receipt?.wasmSha256,wasmSHA256,'Gate cannot inherit another runtime receipt');
  const cap=item.device==='atom-matrix'&&expected.firmwareSHA256===ATOM_MATRIX_WORKBENCH_FLASH_SHA256
    ? ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS : undefined;
  assert.equal(receipt.accelerator?.icountMaxPerCpuNs,cap,'Gate child scheduling binding mismatch');
  if(item.lane==='uiflow-editor')assert.equal(result.smoke_only,false,'Publication requires the full editor runner');
  // Cleanup assertions stay in each source-bound runner. In particular the
  // keyboard runner does not measure a pthread fence with iframe held.
  return receipt;
}

/** Pure planning: no process, browser, firmware or runtime execution. */
export function planPublicQemuGate({manifest,config,registry,runtime,c61Runtime,workbenchRegistry,
  phase='all',devices=[],requireAll=false}){
  assert.ok(PUBLIC_QEMU_GATE_PHASES.includes(phase),'Unknown M5_QEMU_GATE_PHASE');
  assert.ok(Array.isArray(devices)&&new Set(devices).size===devices.length,'Duplicate gate device selection');
  assert.equal(manifest.publication_eligible,true);assert.equal(config.publication_eligible,true);
  assert.deepEqual(manifest.candidate_profiles,[]);assert.deepEqual(config.browser_candidate_profiles,[]);
  validateQemuBrowserProfiles(registry);validateUIFlowWorkbenchRegistry(workbenchRegistry);
  assert.ok(registry.profiles.length&&registry.profiles.some(profile=>profile.deviceId==='cores3'));
  const compiled=new Map([
    ['xtensa-softmmu',runtime.compiled_profiles||runtime.profiles],
    ['riscv32-softmmu',c61Runtime?.compiled_profiles||[]],
  ]);
  assert.ok(registry.profiles.every(profile=>profile.admission==='public'
    && compiled.get(profile.target)?.includes(profile.deviceId)),
  'Only explicitly public, compiled registry boards enter this gate');
  const publicIds=registry.profiles.map(profile=>profile.deviceId);
  assert.deepEqual(workbenchRegistry.profiles.map(row=>row.deviceId).sort(),[...publicIds].sort(),
    'Every exported public board needs its own default workbench identity');
  for(const profile of registry.profiles)assert.ok(PUBLIC_QEMU_BUTTON_CASES[profile.deviceId]?.length,
    `No public button observer case for ${profile.deviceId}`);
  for(const id of devices)assert.ok(publicIds.includes(id),`Unadmitted gate device: ${id}`);
  const publicationEligible=phase==='all'&&devices.length===0;
  assert.ok(!requireAll||publicationEligible,'Publication requires every phase and every public board');
  if(publicationEligible)assert.equal(config.browser_wallclock_example,true,
    'Publication retains the independent CoreS3 SDK fixed example');
  const priority={'atom-matrix':0,'stickc-plus':1,'cardputer-adv':2,cores3:3};
  const profiles=registry.profiles.filter(profile=>!devices.length||devices.includes(profile.deviceId))
    .sort((a,b)=>(priority[a.deviceId]??4)-(priority[b.deviceId]??4));
  const cases=[];
  // Adjacent editor/button results keep per-board progress reviewable.
  for(const profile of profiles){
    if(['all','uiflow','editor'].includes(phase))cases.push({lane:'uiflow-editor',device:profile.deviceId,script:'test_public_uiflow_guest.mjs'});
    if(['all','uiflow','buttons'].includes(phase))cases.push({lane:'uiflow-buttons',device:profile.deviceId,script:'test_public_qemu_buttons_guest.mjs'});
    if(profile.deviceId==='cardputer-adv'&&['all','uiflow','buttons'].includes(phase))
      cases.push({lane:'cardputer-keyboard',device:'cardputer-adv',script:'test_public_uiflow_cardputer_keyboard_guest.mjs'});
    if(profile.deviceId==='stackchan'&&['all','uiflow','buttons'].includes(phase))
      cases.push({lane:'stackchan-body-touch',device:'stackchan',script:'test_public_stackchan_body_touch_guest.mjs'});
  }
  if(['all','fixed'].includes(phase))for(const profile of profiles){
    if(profile.deviceId==='cores3')for(const example of ['stock-reference',...(config.browser_wallclock_example?['wallclock-candidate']:[])])
      cases.push({lane:'fixed',device:'cores3',example,script:'test_public_qemu_guest.mjs'});
    else cases.push({lane:'fixed',device:profile.deviceId,script:profile.display===null
      ? 'test_public_qemu_headless_guest.mjs':'test_public_qemu_board_guest.mjs'});
  }
  return {phase,devices:[...devices],publication_eligible:publicationEligible,cases};
}

async function run(){
  if(!process.env.M5_PUBLIC_SITE){console.log('SKIP: explicit M5_PUBLIC_SITE public export required');return;}
  const site=resolve(process.env.M5_PUBLIC_SITE);
  const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-admitted'));
  assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'raw browser evidence must stay in ignored .work');
  await mkdir(out,{recursive:false});
  const report={kind:'public-qemu-every-admitted-board-gate',started_at:new Date().toISOString(),
    cases:[],status:'FAIL',publication_eligible:false,hardware_validation:'NOT RUN',
    gate_script_sha256:digest(await readFile(fileURLToPath(import.meta.url)))};
  try{
    const workers=publicQemuGateWorkers(process.env.M5_QEMU_GATE_WORKERS,
      {ci:!!process.env.CI&&process.env.CI!=='false'});
    Object.assign(report,{workers,execution_context:{kind:'functional-only',performance_sample:false,
      max_parallel_guests:workers,isolation:'Independent Node child, Chrome, VM, ephemeral server and output per case',
      ordering:'Same-device cases serial; all UIFlow groups complete before fixed examples'}});
    const assets={};
    async function json(path){const bytes=await readFile(resolve(site,path));assets[path]={bytes:bytes.length,sha256:digest(bytes)};return JSON.parse(bytes);}
    const manifest=await json('public-site-manifest.json'),config=await json('platform/web/site-config.json');
    const registry=await json('platform/web/qemu-browser-profiles.json'),runtime=await json('platform/runtime/qemu/runtime.json');
    const c61Runtime=registry.profiles.some(row=>row.target==='riscv32-softmmu')
      ? await json('platform/runtime/qemu-c61/runtime.json') : null;
    const workbenchRegistry=await json('platform/web/uiflow-workbench-profiles.json');
    Object.assign(report,{assets,wasm_sha256:runtime.assets?.wasm?.sha256});
    if(c61Runtime)report.c61_wasm_sha256=c61Runtime.assets.wasm.sha256;
    const plan=planPublicQemuGate({manifest,config,registry,runtime,c61Runtime,workbenchRegistry,
      phase:process.env.M5_QEMU_GATE_PHASE||'all',
      devices:process.env.M5_QEMU_GATE_DEVICES?process.env.M5_QEMU_GATE_DEVICES.split(','):[],
      requireAll:process.env.M5_QEMU_GATE_REQUIRE_ALL==='1'});
    Object.assign(report,{phase:plan.phase,selected_devices:plan.devices,full_scope:plan.publication_eligible,
      expected_cases:plan.cases.length,case_plan_sha256:digest(JSON.stringify(plan.cases)),
      lane_counts:Object.fromEntries(['uiflow-editor','uiflow-buttons','cardputer-keyboard','stackchan-body-touch','fixed'].map(lane=>[lane,plan.cases.filter(row=>row.lane===lane).length])),
    });
    // Prepare all paths and source identities before any child can start.
    // Callback dispatch then reaches spawn without an intervening async gap.
    const scriptHashes=new Map();
    for(const item of plan.cases){
      if(!scriptHashes.has(item.script))scriptHashes.set(item.script,digest(await readFile(resolve(repo,'platform/tests',item.script))));
      await mkdir(resolve(out,item.lane),{recursive:true});
    }
    const scheduled=await schedulePublicQemuGate(plan.cases,{workers,runCase:async (item,{noteFailure})=>{
      const output=resolve(out,item.lane,item.device+(item.example?'-'+item.example:''));
      const env=publicQemuGateChildEnvironment(process.env,item,{site,output});
      const row={...item,status:'FAIL',started_at:new Date().toISOString(),
        test_script_sha256:scriptHashes.get(item.script)};
      try{
        const code=await new Promise(done=>{
          let child;
          try{child=spawn(process.execPath,[resolve(repo,'platform/tests',item.script)],{cwd:repo,env,stdio:'inherit'});}
          catch(error){noteFailure(error);done({code:null,signal:null,error});return;}
          let launchError=null;
          child.once('error',error=>{launchError=error;noteFailure(error);});
          child.once('close',(code,signal)=>{
            if(launchError||code!==0)noteFailure(launchError||new Error(`${item.lane}/${item.device}/${item.example||'default'} guest runner failed`));
            done({code,signal,error:launchError});
          });
        });
        row.exit_code=code.code;row.exit_signal=code.signal;
        if(code.error)throw code.error;
        const raw=await readFile(resolve(output,'report.json')),result=JSON.parse(raw);
        Object.assign(row,{status:result.result||result.status,report_sha256:digest(raw),report_bytes:raw.length});
        assert.equal(code.code,0,`${item.lane}/${item.device}/${item.example||'default'} guest runner failed`);
        assert.equal(row.status,'PASS',`${item.lane}/${item.device} guest did not pass`);
        const executionRuntime=item.device==='corematrix'?c61Runtime:runtime;
        validatePublicQemuGateResult(item,result,{workbenchRegistry,wasmSHA256:executionRuntime.assets.wasm.sha256,
          siteManifestSHA256:assets['public-site-manifest.json'].sha256,testScriptSHA256:row.test_script_sha256});
      }catch(error){noteFailure(error);row.status='FAIL';row.error=String(error?.message||error).slice(0,2000);}
      finally{row.finished_at=new Date().toISOString();}
      return row;
    }});
    Object.assign(report,{cases:scheduled.cases,first_failure:scheduled.first_failure,
      max_active_children:scheduled.max_active_children,
      completed_cases:scheduled.cases.filter(row=>row.status==='PASS'||row.status==='FAIL').length,
      not_run_cases:scheduled.cases.filter(row=>row.status==='NOT RUN').length});
    if(!scheduled.all_passed)throw new Error(scheduled.first_failure?.error||'Not every planned guest passed');
    report.publication_eligible=plan.publication_eligible&&scheduled.cases.length===plan.cases.length
      &&scheduled.cases.every(row=>row.status==='PASS');
    report.status=plan.publication_eligible?'PASS':'DIAGNOSTIC_PASS';
  }catch(error){report.error=String(error?.message||error).slice(0,2000);throw error;}
  finally{
    report.finished_at=new Date().toISOString();
    const encoded=JSON.stringify(report,null,2)+'\n';
    assert.ok(Buffer.byteLength(encoded)<=65536,'Gate summary exceeds the bounded evidence budget');
    await writeFile(resolve(out,'report.json'),encoded);
  }
  console.log(`${report.cases.length} independent browser guest cases: ${report.status}`);
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))await run();
