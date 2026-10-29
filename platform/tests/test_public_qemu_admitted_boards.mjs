// Publication gate: independently execute every admitted board in this export.
// Compilation or a different board's result never grants browser admission.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateQemuBrowserProfiles} from '../web/public-qemu-profiles.js';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
if(!process.env.M5_PUBLIC_SITE){console.log('SKIP: explicit M5_PUBLIC_SITE public export required');process.exit(0);}
const site=resolve(process.env.M5_PUBLIC_SITE);
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-admitted'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'raw browser evidence must stay in ignored .work');
await mkdir(out,{recursive:false});
const json=async path=>JSON.parse(await readFile(resolve(site,path),'utf8'));
const manifest=await json('public-site-manifest.json');
const config=await json('platform/web/site-config.json');
const registry=validateQemuBrowserProfiles(await json('platform/web/qemu-browser-profiles.json'));
const runtime=await json('platform/runtime/qemu/runtime.json');
assert.equal(manifest.publication_eligible,true);
assert.equal(config.publication_eligible,true);
assert.deepEqual(manifest.candidate_profiles,[]);
assert.deepEqual(config.browser_candidate_profiles,[]);
assert.ok(registry.profiles.some(profile=>profile.deviceId==='cores3'));
assert.ok(registry.profiles.every(profile=>profile.admission==='public'
  && (runtime.compiled_profiles||runtime.profiles).includes(profile.deviceId)));
const cases=registry.profiles.flatMap(profile=>profile.deviceId==='cores3'
  ? ['stock-div8',...(config.browser_wallclock_example?['wallclock-candidate']:[])].map(example=>({device:'cores3',example,script:'test_public_qemu_guest.mjs'}))
  : [{device:profile.deviceId,script:'test_public_qemu_board_guest.mjs'}]);
const report={kind:'public-qemu-every-admitted-board-gate',started_at:new Date().toISOString(),
  wasm_sha256:runtime.assets.wasm.sha256,cases:[],status:'FAIL',hardware_validation:'NOT RUN'};
try{
  for(const item of cases){
    const output=resolve(out,item.device+(item.example?'-'+item.example:''));
    const env={...process.env,M5_PUBLIC_SITE:site,M5_PUBLIC_QEMU_OUT:output,M5_QEMU_DEVICE:item.device,
      M5_QEMU_EXAMPLE:item.example||'',M5_PUBLIC_UI:'1',M5_WASM_CHROME:process.env.M5_WASM_CHROME||process.env.M5_CHROME||''};
    const code=await new Promise((done,reject)=>{
      const child=spawn(process.execPath,[resolve(repo,'platform/tests',item.script)],{cwd:repo,env,stdio:'inherit'});
      child.on('error',reject);child.on('exit',code=>done(code));
    });
    const raw=await readFile(resolve(output,'report.json'));
    const result=JSON.parse(raw),status=result.result||result.status;
    report.cases.push({...item,exit_code:code,status,report_sha256:createHash('sha256').update(raw).digest('hex')});
    assert.equal(code,0,`${item.device}/${item.example||'board'} guest runner failed`);
    assert.equal(status,'PASS',`${item.device}/${item.example||'board'} guest did not pass`);
  }
  report.status='PASS';
}finally{
  report.finished_at=new Date().toISOString();
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
}
console.log(`${cases.length} independently executed public browser board/example cases passed`);
