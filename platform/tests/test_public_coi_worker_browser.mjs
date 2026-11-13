// Real Chromium / Service Worker control, with HTTP fixtures only. No guest.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const source=await readFile(resolve(root,'platform/web/public-coi-serviceworker.js'));
const upstream=await readFile(resolve(root,'platform/web/vendor/coi-serviceworker/coi-serviceworker.js'));
const requests=[],failures=[],results=[];
let serveUpdatedWorker=false;
const server=createServer((request,response)=>{
  const headers={'Cache-Control':'no-store, no-cache, must-revalidate, max-age=0','Access-Control-Allow-Origin':'*'};
  if(request.url.startsWith('/showcase/coi-serviceworker.js')){
    response.writeHead(200,{...headers,'Content-Type':'application/javascript'});
    response.end(request.url.includes('upstream')&&!serveUpdatedWorker?upstream:source);return;
  }
  if(request.url.startsWith('/showcase/frame')){
    const status=request.headers['if-none-match']==='"frame"'?304:200;
    requests.push({status,conditional:!!request.headers['if-none-match']});
    response.writeHead(status,{...headers,ETag:'"frame"',...(status===200?{'Content-Type':'image/png','Content-Length':'4'}:{})});
    response.end(status===200?'DATA':undefined);return;
  }
  response.writeHead(200,{...headers,'Content-Type':'text/html'});response.end('<!doctype html><title>COI HTTP control</title>');
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE} : {})});
try {
  for(const worker of ['none','upstream','owned']){
    const context=await browser.newContext(),page=await context.newPage();
    page.on('requestfailed',request=>failures.push({worker,error:request.failure()?.errorText}));
    await page.goto(base+'/showcase/');
    if(worker!=='none'){
      await page.evaluate(async mode=>{await navigator.serviceWorker.register('/showcase/coi-serviceworker.js?'+mode);await navigator.serviceWorker.ready;},worker);
      await page.reload();await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
      assert.equal(await page.evaluate(()=>crossOriginIsolated),true,'the real worker must preserve document isolation');
    }
    for(const cache of ['no-store','default'])for(const redirect of ['error','follow']){
      const result=await page.evaluate(async({cache,redirect})=>{
        const path='/showcase/frame?'+cache+'-'+redirect;
        const first=await fetch(path,{cache,redirect,credentials:'omit'});const firstBody=await first.text();
        try {
          const response=await fetch(path,{cache,redirect,credentials:'omit',headers:{'If-None-Match':first.headers.get('ETag')}});
          return {first_status:first.status,first_body:firstBody,conditional_status:response.status,conditional_body:await response.text(),etag:response.headers.get('ETag'),coep:response.headers.get('Cross-Origin-Embedder-Policy'),coop:response.headers.get('Cross-Origin-Opener-Policy'),corp:response.headers.get('Cross-Origin-Resource-Policy')};
        } catch(error){return {first_status:first.status,first_body:firstBody,error:error.name+': '+error.message};}
      },{cache,redirect});
      results.push({worker,cache,redirect,...result});
      assert.equal(result.first_status,200);assert.equal(result.first_body,'DATA');
      if(worker==='upstream')assert.equal(result.error,'TypeError: Failed to fetch','negative control must reproduce the original null-body failure');
      else {assert.equal(result.conditional_status,304);assert.equal(result.conditional_body,'');assert.equal(result.etag,'"frame"');}
      if(worker==='owned'){assert.equal(result.coep,'require-corp');assert.equal(result.coop,'same-origin');assert.equal(result.corp,'cross-origin');}
    }
    if(worker==='upstream'){
      serveUpdatedWorker=true;
      await page.evaluate(async()=>{
        const changed=new Promise(resolve=>navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true}));
        await (await navigator.serviceWorker.getRegistration()).update();await changed;
      });
      const updated=await page.evaluate(async()=>{
        const response=await fetch('/showcase/frame?updated',{cache:'no-store',redirect:'error',headers:{'If-None-Match':'"frame"'}});
        return {status:response.status,body:await response.text(),coep:response.headers.get('Cross-Origin-Embedder-Policy')};
      });
      assert.deepEqual(updated,{status:304,body:'',coep:'require-corp'});
      results.push({worker:'owned-update',same_registration_refresh:true,...updated});
    }
    await context.close();
  }
  assert.equal(failures.length,4);assert.ok(failures.every(row=>row.worker==='upstream'&&row.error==='net::ERR_FAILED'));
} finally {await browser.close();await new Promise(done=>server.close(done));}
const report={status:'PASS',scope:'host-only HTTP/Chrome control; guest NOT RUN',worker_sha256:createHash('sha256').update(source).digest('hex'),results,requests,failures};
const out=resolve(process.env.M5_COI_WORKER_BROWSER_OUT||resolve(root,'.work/coi-worker-browser'));
await mkdir(out,{recursive:true});await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
console.log('COI_WORKER_BROWSER_PASS: 13 actual fetch/update controls; 4 original-worker failures retained; owned 304, isolation headers and existing registration refresh PASS; guest NOT RUN');
