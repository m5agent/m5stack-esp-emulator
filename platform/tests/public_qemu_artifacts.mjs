// Provenance gate for the real guest runner. This reads static assets only;
// it cannot establish guest execution, public deployment or hardware results.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const sha256=bytes=>createHash('sha256').update(bytes).digest('hex');
export const QEMU_EXECUTED_WEB_PATHS=Object.freeze([
  'platform/web/index.html','platform/web/public.js','platform/web/public.css','platform/web/public-config.js',
  'platform/web/public-firmware.js','platform/web/sha256.js','platform/web/public-demo-firmware.js',
  'platform/web/public-coi.js','platform/web/public-coi-serviceworker.js',
  'platform/web/vendor/coi-serviceworker/coi-serviceworker.js',
  'platform/web/public-qemu-runtime.js','platform/web/public-qemu-instance.js',
  'platform/web/public-qemu-instance.html',
]);

function safePath(path){
  assert.equal(typeof path,'string');
  assert.ok(path&&!path.startsWith('/')&&!/[\\\u0000-\u001f]/.test(path)&&path.split('/').every(part=>part&&part!=='.'&&part!=='..'),'invalid static artifact path');
  return path;
}
export async function capturePublicQemuProvenance({repo,site,publicUrl,fetchImpl=globalThis.fetch,
  webPaths=QEMU_EXECUTED_WEB_PATHS,testScript='platform/tests/test_public_qemu_guest.mjs'}={}){
  const remote=publicUrl?new URL('./',publicUrl):null;
  if(remote)assert.ok(['https:','http:'].includes(remote.protocol)&&!remote.username&&!remote.password,'invalid static deployment URL');
  async function asset(path){
    safePath(path);
    if(!remote)return readFile(resolve(site,path));
    const response=await fetchImpl(new URL(path,remote),{credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store'});
    assert.ok(response.ok,`static artifact unavailable: ${path}`);
    return Buffer.from(await response.arrayBuffer());
  }
  const manifestBytes=await asset('public-site-manifest.json'),manifest=JSON.parse(manifestBytes);
  assert.equal(manifest.kind,'m5stack-public-site');assert.equal(manifest.schema_version,1);
  assert.match(manifest.base_path,/^\/(?:[a-zA-Z0-9._~-]+\/)*$/);
  assert.ok(!manifest.base_path.split('/').some(part=>part==='.'||part==='..'));
  const declared=new Map(manifest.assets.map(row=>[safePath(row.path),row]));
  async function verified(path){
    const bytes=await asset(path),row=declared.get(path);
    assert.ok(row,`asset missing from site manifest: ${path}`);
    assert.equal(bytes.length,row.bytes,`site manifest length mismatch: ${path}`);
    assert.equal(sha256(bytes),row.sha256,`site manifest SHA mismatch: ${path}`);
    return bytes;
  }
  const web={};
  for(const path of webPaths){
    const source=await readFile(resolve(repo,safePath(path))),exported=await verified(path);
    const rewritten=Buffer.from(source.toString('utf8').replace(/(?<=["'`(])\/(platform|devices|data)\//g,(_,group)=>manifest.base_path+group+'/'));
    assert.deepEqual(exported,rewritten,`export does not match current source: ${path}`);
    web[path]={source_sha256:sha256(source),exported_sha256:sha256(exported)};
  }
  // The root copies have a different pathname but must be the same execution.
  assert.deepEqual(await verified('index.html'),await verified('platform/web/index.html'),'root entry differs from public web entry');
  assert.deepEqual(await verified('coi-serviceworker.js'),await verified('platform/web/public-coi-serviceworker.js'),'project-root isolation wrapper differs');
  const runtimeBytes=await verified('platform/runtime/qemu/runtime.json'),runtime=JSON.parse(runtimeBytes);
  assert.equal(runtime.engine,'qemu-wasm');assert.equal(runtime.schema_version,1);
  const runtimeAssets={};
  for(const row of Object.values(runtime.assets)){
    const path='platform/runtime/qemu/'+safePath(row.path),bytes=await verified(path);
    assert.equal(bytes.length,row.bytes,`runtime manifest length mismatch: ${path}`);
    assert.equal(sha256(bytes),row.sha256,`runtime manifest SHA mismatch: ${path}`);
    runtimeAssets[row.path]={bytes:bytes.length,sha256:sha256(bytes)};
  }
  const runner=await readFile(resolve(repo,safePath(testScript)));
  const helper=await readFile(fileURLToPath(import.meta.url));
  return {
    kind:'public-qemu-static-artifact-provenance',location:remote?'remote-static-host':'local-export',
    site_manifest_sha256:sha256(manifestBytes),base_path:manifest.base_path,web,
    runtime_manifest_sha256:sha256(runtimeBytes),runtime_source_commit:runtime.source?.commit,
    runtime_build:runtime.build,required_rom:runtime.required_rom,runtime_assets:runtimeAssets,
    test_script:{path:testScript,sha256:sha256(runner)},helper_sha256:sha256(helper),
  };
}
