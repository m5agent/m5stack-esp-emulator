// Publication gate: each public default editor and buttons, then fixed examples.
// Compilation and another image's results never grant browser admission.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateQemuBrowserProfiles} from '../web/public-qemu-profiles.js';
import {validateUIFlowWorkbenchRegistry} from '../web/public-uiflow-firmware.js';
import {PUBLIC_QEMU_BUTTON_CASES} from './public_qemu_button_cases.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export const PUBLIC_QEMU_GATE_PHASES=Object.freeze(['all','uiflow','editor','buttons','fixed']);

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
  assert.equal(provenance?.runtime_assets?.['qemu-system-xtensa.wasm']?.sha256,wasmSHA256,'Gate cannot inherit another runtime result');
  if(item.lane==='fixed')return;
  assert.ok(['uiflow-editor','uiflow-buttons','stackchan-body-touch','cardputer-keyboard'].includes(item.lane),'Unknown workbench lane');
  const expected=workbenchRegistry.profiles.find(row=>row.deviceId===item.device);
  assert.ok(expected,'Gate workbench identity missing');
  const receipt=item.lane==='cardputer-keyboard'?result.initial?.evidence?.receipt
    :item.lane==='uiflow-buttons'?result.running?.receipt:result.initial?.receipt;
  assert.equal(receipt?.deviceId,item.device,'Gate child device mismatch');
  assert.equal(receipt?.firmwareSha256,expected.firmwareSHA256,'Gate requires the exact default workbench image');
  assert.equal(receipt?.wasmSha256,wasmSHA256,'Gate cannot inherit another runtime receipt');
  if(item.lane==='uiflow-editor')assert.equal(result.smoke_only,false,'Publication requires the full editor runner');
  // Cleanup assertions stay in each source-bound runner. In particular the
  // keyboard runner does not measure a nested-worker fence with iframe held.
  return receipt;
}

/** Pure planning: no process, browser, firmware or runtime execution. */
export function planPublicQemuGate({manifest,config,registry,runtime,workbenchRegistry,
  phase='all',devices=[],requireAll=false}){
  assert.ok(PUBLIC_QEMU_GATE_PHASES.includes(phase),'Unknown M5_QEMU_GATE_PHASE');
  assert.ok(Array.isArray(devices)&&new Set(devices).size===devices.length,'Duplicate gate device selection');
  assert.equal(manifest.publication_eligible,true);assert.equal(config.publication_eligible,true);
  assert.deepEqual(manifest.candidate_profiles,[]);assert.deepEqual(config.browser_candidate_profiles,[]);
  validateQemuBrowserProfiles(registry);validateUIFlowWorkbenchRegistry(workbenchRegistry);
  assert.ok(registry.profiles.length&&registry.profiles.some(profile=>profile.deviceId==='cores3'));
  assert.ok(registry.profiles.every(profile=>profile.admission==='public'
    && (runtime.compiled_profiles||runtime.profiles).includes(profile.deviceId)),
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
    const assets={};
    async function json(path){const bytes=await readFile(resolve(site,path));assets[path]={bytes:bytes.length,sha256:digest(bytes)};return JSON.parse(bytes);}
    const manifest=await json('public-site-manifest.json'),config=await json('platform/web/site-config.json');
    const registry=await json('platform/web/qemu-browser-profiles.json'),runtime=await json('platform/runtime/qemu/runtime.json');
    const workbenchRegistry=await json('platform/web/uiflow-workbench-profiles.json');
    Object.assign(report,{assets,wasm_sha256:runtime.assets?.wasm?.sha256});
    const plan=planPublicQemuGate({manifest,config,registry,runtime,workbenchRegistry,
      phase:process.env.M5_QEMU_GATE_PHASE||'all',
      devices:process.env.M5_QEMU_GATE_DEVICES?process.env.M5_QEMU_GATE_DEVICES.split(','):[],
      requireAll:process.env.M5_QEMU_GATE_REQUIRE_ALL==='1'});
    Object.assign(report,{phase:plan.phase,selected_devices:plan.devices,full_scope:plan.publication_eligible,
      expected_cases:plan.cases.length,case_plan_sha256:digest(JSON.stringify(plan.cases)),
      lane_counts:Object.fromEntries(['uiflow-editor','uiflow-buttons','cardputer-keyboard','stackchan-body-touch','fixed'].map(lane=>[lane,plan.cases.filter(row=>row.lane===lane).length])),
    });
    for(const item of plan.cases){
      const parent=resolve(out,item.lane);await mkdir(parent,{recursive:true});
      const output=resolve(parent,item.device+(item.example?'-'+item.example:''));
      const env=publicQemuGateChildEnvironment(process.env,item,{site,output});
      const row={...item,status:'FAIL',started_at:new Date().toISOString(),
        test_script_sha256:digest(await readFile(resolve(repo,'platform/tests',item.script)))};
      report.cases.push(row);
      try{
        const code=await new Promise((done,reject)=>{
          const child=spawn(process.execPath,[resolve(repo,'platform/tests',item.script)],{cwd:repo,env,stdio:'inherit'});
          child.on('error',reject);child.on('exit',(code,signal)=>done({code,signal}));
        });
        row.exit_code=code.code;row.exit_signal=code.signal;
        const raw=await readFile(resolve(output,'report.json')),result=JSON.parse(raw);
        Object.assign(row,{status:result.result||result.status,report_sha256:digest(raw),report_bytes:raw.length});
        assert.equal(code.code,0,`${item.lane}/${item.device}/${item.example||'default'} guest runner failed`);
        assert.equal(row.status,'PASS',`${item.lane}/${item.device} guest did not pass`);
        validatePublicQemuGateResult(item,result,{workbenchRegistry,wasmSHA256:runtime.assets.wasm.sha256,
          siteManifestSHA256:assets['public-site-manifest.json'].sha256,testScriptSHA256:row.test_script_sha256});
      }catch(error){row.status='FAIL';row.error=String(error?.message||error).slice(0,2000);throw error;}
      finally{row.finished_at=new Date().toISOString();}
    }
    report.publication_eligible=plan.publication_eligible;
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
