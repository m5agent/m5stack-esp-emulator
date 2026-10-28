// Actual public.js initialization/share/lane logic with mock DOM and execution
// boundaries. No browser, service, network request or guest is started.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import * as config from '../web/public-config.js';
import * as firmware from '../web/public-firmware.js';

const pageRoot='https://example.test/showcase/';
const fixtureSha='78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f';
const source=await readFile(new URL('../web/public.js',import.meta.url),'utf8');
const imports=[...source.matchAll(/^import \{([^}]+)\} from '([^']+)';$/gm)];
assert.equal(imports.length,12,'review the harness if the entry module dependency boundary changes');
assert.ok(source.endsWith('void init().catch(error);\n'));
const body=source.replace(/^import \{[^}]+\} from '[^']+';\n/gm,'').replace(/void init\(\)\.catch\(error\);\n$/,'');
const required=imports.flatMap(match=>match[1].split(',').map(name=>name.trim()));

async function entry({search='',isolationError,isolation={isolated:true,reloading:false}}={}){
  const elements=new Map(),events=[],clipboard=[];
  const element=(id)=>{
    if(!elements.has(id))elements.set(id,{id,value:'',textContent:'',hidden:true,dataset:{},files:[],
      addEventListener(){},setAttribute(){},replaceChildren(){},append(){},focus(){},scrollIntoView(){},
      classList:{add(){},remove(){},toggle(){}}});
    return elements.get(id);
  };
  const radios=new Map(['reference','url','local'].map(value=>[value,{value,checked:value==='reference'}]));
  const document={getElementById:element,querySelectorAll:()=>[],
    querySelector(selector){if(selector.includes(':checked'))return [...radios.values()].find(item=>item.checked);
      const match=selector.match(/\[value="([^"]+)"\]/);return match?radios.get(match[1]):null;},
    createElement:element,createTextNode:text=>({textContent:text})};
  const catalog={devices:[{id:'cores3',name:'CoreS3'},{id:'core2',name:'Core2'}]};
  const dependencies=Object.fromEntries(required.map(name=>[name,()=>{throw new Error(`Unexpected execution boundary ${name}`);} ]));
  Object.assign(dependencies,config,firmware,{
    siteRoot:()=>new URL(pageRoot),
    ensurePublicIsolation:async()=>{events.push('isolation');if(isolationError)throw isolationError;return isolation;},
    getBrowserProfile:()=>null,QEMU_BROWSER_PROFILE:{deviceId:'cores3'},browserQemuHistory:()=>[],
  });
  const context=vm.createContext({...dependencies,document,window:{addEventListener(){}},
    navigator:{clipboard:{writeText:async url=>clipboard.push(url)}},location:{href:pageRoot+search,search},
    URL,URLSearchParams,Map,TextEncoder,AbortController,DOMException,console,
    fetch:async url=>({ok:true,json:async()=>{
      if(url.endsWith('devices/catalog.json'))return catalog;
      if(url.endsWith('catalog/products.json'))return {products:[]};
      if(url.endsWith('browser-profiles.json'))return {devices:[]};
      if(url.endsWith('site-config.json'))return {browser_runtime_engine:'qemu-wasm',browser_board_execution:true};
      throw new Error('Unexpected fetch '+url);
    }}),events,
  });
  vm.runInContext(body+`
    renderDevices=()=>events.push('render-devices');renderUnits=()=>events.push('render-units');
    selectDevice=async id=>{state.selected=state.devices.find(item=>item.id===id);state.shell={};events.push('select:'+id);};
    connectService=async()=>{state.serviceDevices=[{device_id:state.selected.id,creatable:true}];events.push('connect-service');};
    startRun=async()=>events.push('start:'+lane());
    globalThis.contract={state,browserProfile,lane,share,reference};
    globalThis.initialization=init();
  `,context);
  await context.initialization;
  return {...context.contract,elements,events,clipboard,element,radios};
}

for(const code of ['coi_unavailable','coi_insecure_context','coi_storage_unavailable']){
  const app=await entry({search:'?device=cores3&mode=service&service=https://service.example.test&autostart=0',isolationError:Object.assign(new Error(code),{code})});
  assert.equal(app.state.browserUnavailable,true);assert.equal(app.browserProfile('cores3'),null);
  assert.equal(app.state.devices.length,2);assert.equal(app.state.selected.id,'cores3');
  assert.ok(app.events.includes('render-devices')&&app.events.includes('render-units'));
  assert.ok(app.events.includes('connect-service'));assert.equal(app.lane(),'service');
  app.element('runtimeMode').value='model';assert.equal(app.lane(),'model');
  app.element('runtimeMode').value='browser';assert.equal(app.lane(),null);
  assert.match(app.element('errorBanner').textContent,/仍可浏览模型或连接 HTTPS 仿真服务/);
}
const navigation=await entry({isolation:{isolated:false,reloading:true}});
assert.deepEqual(navigation.events,['isolation'],'a first-load isolation navigation must not accept firmware or start execution');

const original=await entry();assert.equal(original.events.some(item=>item.startsWith('start:')),false);
original.element('runtimeMode').value='browser';await original.share();
const share=new URL(original.clipboard[0]);
assert.equal(share.searchParams.get('device'),'cores3');assert.equal(share.searchParams.get('sha256'),fixtureSha);
assert.equal(share.searchParams.has('firmware'),false,'the composed reference has no prebuilt firmware URL');
const reopened=await entry({search:share.search});
assert.ok(reopened.events.includes('start:browser'),'an exact composed-reference SHA authorizes reference autostart');
assert.equal(reopened.element('firmwareSha').value,fixtureSha);
for(const search of [share.search+'&autostart=0',share.search.replace(fixtureSha,'0'.repeat(64)),share.search.replace('cores3','core2'),share.search.replace('mode=browser','mode=model')]){
  const app=await entry({search});assert.equal(app.events.some(item=>item.startsWith('start:')),false,'wrong device/hash, disabled autostart and model mode cannot run the reference');
}
console.log('public QEMU entry COI fallback and exact composed-reference share/autostart contracts passed; no guest executed');
console.log('public.js SHA256 '+createHash('sha256').update(source).digest('hex'));
