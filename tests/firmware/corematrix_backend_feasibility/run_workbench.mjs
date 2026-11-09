import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import {createRequire} from 'node:module';

const require = createRequire(new URL('../../../platform/tests/package.json', import.meta.url));
const {chromium} = require('playwright');
const base = process.argv[2];
const output = process.argv[3];
if (!base || !/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(base) || !output) {
  throw new Error('Usage: node run_workbench.mjs http://127.0.0.1:PORT PROBE_OUTPUT');
}
const token = fs.readFileSync(output + '/workbench-token','utf8').trim();
const headers = {Authorization:'Bearer '+token,'Content-Type':'application/json'};
const request = async (path, init={}) => fetch(base+path,{...init,headers:{...headers,...init.headers}});
const pixels = mask => [[0,0], ...[0,1,2].filter(i => !(mask & (1<<i))).map(i => [2+5*i,1+3*i]),[15,15]];
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1050}});
    const page=await context.newPage();
    const errors=[], failed=[], inputs=[], frames=[];
    page.on('pageerror', error=>errors.push(error.message));
    page.on('response', async response=>{
      const route=new URL(response.url()).pathname;
      if (response.status()>=400) failed.push([route.replace(/\b[0-9a-f]{32}\b/g, '{session}'),response.status()]);
      if (/\/input$/.test(route)) inputs.push({payload:response.request().postDataJSON(),status:response.status(),accepted:(await response.json()).accepted});
      if (/\/frame\.png$/.test(route)&&response.ok()) frames.push(response.headers()['x-frame-sha256']);
    });
    await page.goto(base+'/?device=corematrix&mode=service');
    await page.locator('[data-renderer="corematrix-three"] canvas').waitFor();
    // Observe the real texture update after the production model presents it.
    // The diagnostic hook never writes pixels or dispatches guest input.
    await page.evaluate(async () => {
      const {MatrixDisplay}=await import('/platform/web/vendor/m5stack-models/src/devices/corematrix/MatrixDisplay.js');
      const original=MatrixDisplay.prototype.present;
      window.cmDisplay={count:0,lit:null,monochrome:false};
      MatrixDisplay.prototype.present=function(...args){
        const result=original.apply(this,args);
        const ctx=this.getContext2D();
        const data=ctx.getImageData(0,0,16,16).data;
        const lit=[];
        let monochrome=true;
        for(let y=0;y<16;y++)for(let x=0;x<16;x++){
          const i=(y*16+x)*4;
          if(data[i]===255&&data[i+1]===255&&data[i+2]===255) lit.push([x,y]);
          else if(data[i]!==0||data[i+1]!==0||data[i+2]!==0) monochrome=false;
        }
        window.cmDisplay={count:window.cmDisplay.count+1,lit,monochrome};
        return result;
      };
    });
    await page.locator('#serviceConnection').evaluate(el=>el.open=true);
    await page.locator('#serviceToken').fill(token);
    await page.locator('#connectServiceBtn').click();
    await page.locator('#serviceSessions').evaluate(el=>el.open=true);
    const adopt=page.getByRole('button',{name:'在工作台打开',exact:true});
    await adopt.waitFor();
    await adopt.click();
    const canvas=page.locator('[data-renderer="corematrix-three"] canvas');
    await canvas.waitFor();
    await page.waitForFunction(() => document.querySelector('#serialOutput').textContent.includes('CM_IDS PM1=2050 IOE=1234 OFF_NACK=1'));
    const list=await (await request('/api/v1/sessions')).json();
    const session=list.sessions[0];
    const root='/api/v1/sessions/'+session.session_id;
    const cases=[];
    let previous=0x1f;
    const capture=async (mask, key, action) => {
      const before=await page.evaluate(()=>window.cmDisplay.count);
      const serialBefore=await page.locator('#serialOutput').textContent();
      if(key) {
        await canvas.focus();
        if(action==='down') await page.keyboard.down(key);
        else await page.keyboard.up(key);
      }
      const marker='CM_FRAME keys='+mask.toString(16)+' irq='+((previous^mask).toString(16).padStart(2,'0'));
      const expected=pixels(mask);
      await page.waitForFunction(({expected,before,marker,key,serialLength})=>
        (key ? window.cmDisplay.count>before : window.cmDisplay.count>0)
        && window.cmDisplay.monochrome
        && JSON.stringify(window.cmDisplay.lit)===JSON.stringify(expected)
        && document.querySelector('#serialOutput').textContent.slice(key ? serialLength : 0).includes(marker),
        {expected,before,marker,key,serialLength:serialBefore.length});
      const pm=await (await request(root+'/device-state')).json();
      assert.equal(pm.components.pm1.properties['gpio-input-bits'],mask);
      const data=await request(root+'/frame.png');
      const raster=Buffer.from(await data.arrayBuffer());
      cases.push({key,action,marker,lit_xy:expected,frame_sha256:sha(raster)});
      previous=mask;
    };
    for(const args of [[31],[30,'a','down'],[31,'a','up'],[29,'b','down'],[31,'b','up'],
      [27,'c','down'],[26,'a','down'],[30,'c','up'],[31,'a','up']])await capture(...args);
    assert.equal(inputs.length,8);
    assert(inputs.every(row => row.status===200 && row.accepted));
    assert.equal((await request('/api/v1/firmware/import',{method:'POST',body:'{}'})).status,409);
    assert.equal((await request('/api/v1/artifacts',{method:'POST',body:'x'})).status,409);
    assert.equal((await request('/api/v1/sessions',{method:'POST',body:JSON.stringify({device_id:'corematrix',firmware_id:'uploaded'})})).status,409);
    assert.equal((await request('/api/v1/sessions',{headers:{Authorization:''}})).status,401);
    assert.equal((await request('/.git')).status,404);
    assert.equal((await request('/api/v1/sessions',{headers:{Origin:'https://example.invalid'}})).status,403);
    const invalidHost = await new Promise((resolve,reject) => {
      const probe = http.get(base+'/api/v1/sessions',{headers:{...headers,Host:'example.invalid'}}, response => {
        response.resume();
        resolve(response.statusCode);
      });
      probe.on('error',reject);
    });
    assert.equal(invalidHost,403);
    assert.equal((await request(root+'/qom',{method:'POST',body:'{}'})).status,409);
    await page.screenshot({path:output+'/workbench.png'});
    const evidence=await request(root+'/evidence');
    assert(evidence.ok);
    const zip=Buffer.from(await evidence.arrayBuffer());
    fs.writeFileSync(output+'/workbench-evidence.zip',zip);
    await page.getByRole('button',{name:'停止查看',exact:true}).click();
    const seen = await (await request(root)).json();
    assert.equal(seen.state,'running');
    assert.equal((await request(root+'/stop',{method:'POST',body:JSON.stringify({purge:false})})).status,200);
    const stopped=await (await request(root)).json();
    const eventNames=(await (await request(root+'/events')).json()).events.map(e=>e.event);
    assert.equal(stopped.state,'stopped');
    assert(eventNames.includes('worker_lease_released')&&eventNames.includes('flash_released'));
    assert.equal(errors.length,0);
    assert(failed.every(([path,status]) => path === '/api/v1/devices' && status === 401));
    console.log(JSON.stringify({browser:browser.version(),renderer:'corematrix-three',firmware_sha256:session.firmware_sha256,
      session_id_sha256:sha(session.session_id),evidence_sha256:sha(zip),cases,inputs,frame_response_count:frames.length,failed_requests:failed,
      guard_statuses:{firmware_import:409,artifact_upload:409,uploaded_session:409,
        qom_write:409,unauthorized:401,source_tree:404,cross_origin:403,foreign_host:403},
      stop_state:stopped.state,lease_released:true,flash_released:true},null,2));
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
