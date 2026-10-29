// Static fixture audit only: no browser, emulator, ROM or real firmware.
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {capturePublicQemuProvenance,QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';

const sha256=value=>createHash('sha256').update(value).digest('hex');
const canonical=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const candidates=canonical.profiles.filter(profile=>profile.admission==='candidate');assert.ok(candidates.length>=2);
const selected=ids=>({...canonical,profiles:canonical.profiles.filter(profile=>profile.admission==='public'&&profile.deviceId==='cores3'||ids.includes(profile.deviceId))});
const builder=await readFile(new URL('../tools/build_public_site.py',import.meta.url));
const temp=await mkdtemp(resolve(tmpdir(),'m5-public-provenance-')),repo=resolve(temp,'repo'),site=resolve(temp,'site');
const source=new Map([
  ['platform/web/index.html','<script src="/platform/web/public.js"></script>'],
  ['platform/web/public.js','export const fixture="/devices/catalog.json";'],
  ['platform/web/public-coi-serviceworker.js','/* static worker fixture */'],
  ...['public-qemu-profiles.js','qemu-browser-profiles.json','public-qemu-frame.js','public-qemu-probe-firmware.js'].map(name=>['platform/web/'+name,'/* execution dependency fixture '+name+' */']),
]);
source.set('platform/web/qemu-browser-profiles.json',JSON.stringify(canonical));
for(const name of ['public-qemu-profiles.js','qemu-browser-profiles.json','public-qemu-frame.js','public-qemu-probe-firmware.js'])assert.ok(QEMU_EXECUTED_WEB_PATHS.includes('platform/web/'+name));
const files=new Map([...source].map(([path,text])=>[path,Buffer.from(text.replaceAll('"/platform/','"/showcase/platform/').replaceAll('"/devices/','"/showcase/devices/'))]));
files.set('platform/web/qemu-browser-profiles.json',Buffer.from(JSON.stringify(selected([]))));
files.set('index.html',files.get('platform/web/index.html'));files.set('coi-serviceworker.js',files.get('platform/web/public-coi-serviceworker.js'));
const wasm=Buffer.from('synthetic bytes, not an executable runtime');
files.set('platform/runtime/qemu/qemu.wasm',wasm);
files.set('platform/runtime/qemu/runtime.json',Buffer.from(JSON.stringify({schema_version:1,engine:'qemu-wasm',source:{commit:canonical.source.commit},profiles:['cores3'],compiled_profiles:['cores3',candidates[0].deviceId],build:{kind:'test-fixture'},required_rom:{bundled:false},
  assets:{wasm:{path:'qemu.wasm',sha256:sha256(wasm),bytes:wasm.length}}})));
const manifest={kind:'m5stack-public-site',schema_version:1,base_path:'/showcase/',candidate_profiles:[],publication_eligible:true,assets:[...files].map(([path,data])=>({path,bytes:data.length,sha256:sha256(data)}))};
files.set('public-site-manifest.json',Buffer.from(JSON.stringify(manifest)));
async function put(root,path,data){await mkdir(dirname(resolve(root,path)),{recursive:true});await writeFile(resolve(root,path),data);}
const options={repo,site,webPaths:[...source.keys()]};
try{
  for(const [path,data]of source)await put(repo,path,data);
  await put(repo,'platform/tests/test_public_qemu_guest.mjs','/* runner fixture */');
  await put(repo,'platform/tools/build_public_site.py',builder);
  for(const [path,data]of files)await put(site,path,data);
  const local=await capturePublicQemuProvenance(options);
  assert.equal(local.site_manifest_sha256,sha256(files.get('public-site-manifest.json')));
  assert.equal(local.runtime_assets['qemu.wasm'].sha256,sha256(wasm));
  assert.equal(local.web['platform/web/public.js'].source_sha256,sha256(source.get('platform/web/public.js')));
  assert.equal(local.web['platform/web/qemu-browser-profiles.json'].transform.builder_sha256,sha256(builder));
  assert.deepEqual(local.web['platform/web/qemu-browser-profiles.json'].transform.selected_profiles,['cores3']);
  async function refresh(){manifest.assets=[...files].filter(([path])=>path!=='public-site-manifest.json').map(([path,data])=>({path,bytes:data.length,sha256:sha256(data)}));files.set('public-site-manifest.json',Buffer.from(JSON.stringify(manifest)));for(const [path,data]of files)await put(site,path,data);}
  assert.deepEqual(local.web['platform/web/qemu-browser-profiles.json'].transform.public_profiles,['cores3'],'compiled candidate machines cannot inherit public admission');
  const runtimePath='platform/runtime/qemu/runtime.json',baselineRuntime=files.get(runtimePath);
  const compiledOnly=JSON.parse(baselineRuntime);compiledOnly.profiles=[];
  files.set(runtimePath,Buffer.from(JSON.stringify(compiledOnly)));await refresh();
  const availablePublic=await capturePublicQemuProvenance(options);
  assert.deepEqual(availablePublic.web['platform/web/qemu-browser-profiles.json'].transform.public_profiles,['cores3'],'canonical public admission intersects compiled machines rather than the legacy baseline list');
  files.set(runtimePath,baselineRuntime);await refresh();
  manifest.candidate_profiles=[candidates[0].deviceId];manifest.publication_eligible=false;files.set('platform/web/qemu-browser-profiles.json',Buffer.from(JSON.stringify(selected(manifest.candidate_profiles))));await refresh();
  const preview=await capturePublicQemuProvenance(options);assert.ok(preview.web['platform/web/qemu-browser-profiles.json'].transform.selected_profiles.includes(candidates[0].deviceId));
  for(const [ids,eligible,message] of [[['missing-board'],false,/canonical candidate/],[['cores3'],false,/canonical candidate/],[[candidates[1].deviceId],false,/not compiled/],[[candidates[0].deviceId,candidates[0].deviceId],false,/duplicate preview/],[[candidates[0].deviceId],true,/publication eligible/]]){manifest.candidate_profiles=ids;manifest.publication_eligible=eligible;await refresh();await assert.rejects(capturePublicQemuProvenance(options),message);}
  manifest.candidate_profiles=[];manifest.publication_eligible=true;await refresh();await assert.rejects(capturePublicQemuProvenance(options),/deterministic selection/);
  files.set('platform/web/qemu-browser-profiles.json',Buffer.from(JSON.stringify(selected([]))));await refresh();
  const requests=[];
  const remote=await capturePublicQemuProvenance({...options,publicUrl:'https://example.test/showcase/?device=cores3',fetchImpl:async(url,config)=>{
    requests.push({url:String(url),config});const path=new URL(url).pathname.slice('/showcase/'.length);return new Response(files.get(path),{status:files.has(path)?200:404});
  }});
  assert.equal(remote.site_manifest_sha256,local.site_manifest_sha256);assert.deepEqual(remote.web,local.web);
  assert.ok(requests.every(item=>item.config.credentials==='omit'&&item.config.cache==='no-store'&&!item.url.includes('?')));
  await put(repo,'platform/web/public.js','/* newer source */');
  await assert.rejects(capturePublicQemuProvenance(options),/export does not match current source/);
  await put(repo,'platform/web/public.js',source.get('platform/web/public.js'));
  for(const name of ['public-qemu-profiles.js','qemu-browser-profiles.json','public-qemu-frame.js','public-qemu-probe-firmware.js']){
    const path='platform/web/'+name;await put(repo,path,name==='qemu-browser-profiles.json'?JSON.stringify({...canonical,scope:'changed dependency'}):'/* changed dependency */');await assert.rejects(capturePublicQemuProvenance(options),/export does not match current source|deterministic selection/);await put(repo,path,source.get(path));
  }
  await put(site,'platform/runtime/qemu/qemu.wasm',Buffer.alloc(wasm.length,1));
  await assert.rejects(capturePublicQemuProvenance(options),/site manifest SHA mismatch/);
  await put(site,'platform/runtime/qemu/qemu.wasm',wasm);
  const changed=JSON.parse(await readFile(resolve(site,'public-site-manifest.json'),'utf8'));changed.assets.push({path:'../outside',bytes:0,sha256:'0'.repeat(64)});
  await put(site,'public-site-manifest.json',JSON.stringify(changed));
  await assert.rejects(capturePublicQemuProvenance(options),/invalid static artifact path/);
  console.log('public QEMU source/export/remote manifest SHA binding, stale export and tamper contracts passed; no guest executed');
}finally{await rm(temp,{recursive:true,force:true});}
