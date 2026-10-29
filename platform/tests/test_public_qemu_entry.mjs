// Actual public.js initialization/share/lane logic with mock DOM and execution
// boundaries. No browser, service, network request or guest is started.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import * as config from '../web/public-config.js';
import * as firmware from '../web/public-firmware.js';
import * as demoFirmware from '../web/public-demo-firmware.js';
import * as qemuProfiles from '../web/public-qemu-profiles.js';
import * as qemuFrame from '../web/public-qemu-frame.js';
import {PublicQemuRuntime,QEMU_BROWSER_PROFILE} from '../web/public-qemu-runtime.js';

const pageRoot='https://example.test/showcase/';
const fixtureSha='78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f';
const wallclockSha=demoFirmware.WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256;
const html=await readFile(new URL('../web/index.html',import.meta.url),'utf8');
const defaultExample=html.match(/id="referenceExample"[^>]*>\s*<option value="([^"]+)"/)[1];
const source=await readFile(new URL('../web/public.js',import.meta.url),'utf8');
const imports=[...source.matchAll(/^import \{([^}]+)\} from '([^']+)';$/gm)];
assert.equal(imports.length,15,'review the harness if the entry module dependency boundary changes');
assert.ok(source.endsWith('void init().catch(error);\n'));
const body=source.replace(/^import \{[^}]+\} from '[^']+';\n/gm,'').replace(/void init\(\)\.catch\(error\);\n$/,'');
const required=imports.flatMap(match=>match[1].split(',').map(name=>name.trim()));
const registry=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const catalog=JSON.parse(await readFile(new URL('../../devices/catalog.json',import.meta.url),'utf8'));
// A candidate may precede native catalog admission; the real entry also merges
// these hosts from the pinned visual catalog. Keep that boundary in this mock.
const visualCandidates=registry.profiles.filter(profile=>!catalog.devices.some(device=>device.id===profile.deviceId))
  .map(profile=>({id:profile.deviceId,name:profile.deviceId,category:'controller',display:profile.display}));

async function entry({search='',isolationError,registryFailure=false,publicationEligible=true,wallclockExample=false,isolation={isolated:true,reloading:false}}={}){
  const elements=new Map(),events=[],clipboard=[];
  const element=(id)=>{
    if(!elements.has(id))elements.set(id,{id,value:'',textContent:'',hidden:true,dataset:{},files:[],
      addEventListener(){},setAttribute(){},replaceChildren(){},append(){},focus(){},scrollIntoView(){},
      classList:{add(){},remove(){},toggle(){}}});
    return elements.get(id);
  };
  element('referenceExample').value=defaultExample;
  const radios=new Map(['reference','url','local'].map(value=>[value,{value,checked:value==='reference'}]));
  const document={getElementById:element,querySelectorAll:()=>[],
    querySelector(selector){if(selector.includes(':checked'))return [...radios.values()].find(item=>item.checked);
      const match=selector.match(/\[value="([^"]+)"\]/);return match?radios.get(match[1]):null;},
    createElement:element,createTextNode:text=>({textContent:text})};
  const fetchFixture=async url=>{
    if(url.endsWith('qemu-browser-profiles.json')){events.push('registry');return new Response(JSON.stringify(registry),{status:registryFailure?503:200});}
    if(url.endsWith('devices/catalog.json'))return new Response(JSON.stringify(catalog));
    if(url.endsWith('catalog/products.json'))return new Response(JSON.stringify({products:visualCandidates}));
    if(url.endsWith('browser-profiles.json'))return new Response(JSON.stringify({devices:[]}));
    if(url.endsWith('site-config.json'))return new Response(JSON.stringify({browser_runtime_engine:'qemu-wasm',browser_board_execution:true,publication_eligible:publicationEligible,browser_wallclock_example:wallclockExample}));
    throw new Error('Unexpected fetch '+url);
  };
  const dependencies=Object.fromEntries(required.map(name=>[name,()=>{throw new Error(`Unexpected execution boundary ${name}`);} ]));
  Object.assign(dependencies,config,firmware,demoFirmware,qemuProfiles,qemuFrame,{
    siteRoot:()=>new URL(pageRoot),
    ensurePublicIsolation:async()=>{events.push('isolation');if(isolationError)throw isolationError;return isolation;},
    getBrowserProfile:()=>null,QEMU_BROWSER_PROFILE,PublicQemuRuntime,browserQemuHistory:()=>[],
    loadQemuBrowserProfiles:options=>qemuProfiles.loadQemuBrowserProfiles({...options,fetchImpl:fetchFixture}),
  });
  const context=vm.createContext({...dependencies,document,window:{addEventListener(){}},
    navigator:{clipboard:{writeText:async url=>clipboard.push(url)}},location:{href:pageRoot+search,search},
    URL,URLSearchParams,Map,TextEncoder,AbortController,DOMException,console,
    fetch:fetchFixture,events,
  });
  vm.runInContext(body+`
    renderDevices=()=>events.push('render-devices');renderUnits=()=>events.push('render-units');
    selectDevice=async id=>{state.selected=state.devices.find(item=>item.id===id);state.shell={};events.push('select:'+id);};
    connectService=async()=>{state.serviceDevices=[{device_id:state.selected.id,creatable:true}];events.push('connect-service');};
    startRun=async()=>events.push('start:'+lane());
    globalThis.contract={state,browserProfile,lane,share,reference,status};
    globalThis.initialization=init();
  `,context);
  await context.initialization;
  return {...context.contract,elements,events,clipboard,element,radios};
}

for(const code of ['coi_unavailable','coi_insecure_context','coi_storage_unavailable']){
  const app=await entry({search:'?device=cores3&mode=service&service=https://service.example.test&autostart=0',isolationError:Object.assign(new Error(code),{code})});
  assert.equal(app.state.browserUnavailable,true);assert.equal(app.browserProfile('cores3'),null);
  assert.equal(app.state.devices.length,catalog.devices.length+visualCandidates.length);assert.equal(app.state.selected.id,'cores3');
  assert.ok(app.events.includes('render-devices')&&app.events.includes('render-units'));
  assert.ok(app.events.includes('connect-service'));assert.equal(app.lane(),'service');
  app.element('runtimeMode').value='model';assert.equal(app.lane(),'model');
  app.element('runtimeMode').value='browser';assert.equal(app.lane(),null);
  assert.match(app.element('errorBanner').textContent,/仍可浏览模型或连接 HTTPS 仿真服务/);
}
const navigation=await entry({isolation:{isolated:false,reloading:true}});
assert.deepEqual(navigation.events,['registry','isolation'],'a first-load isolation navigation must not accept firmware or start execution');

const unavailable=await entry({registryFailure:true,search:'?device=cores3&mode=service&service=https://service.example.test&autostart=0'});
assert.equal(unavailable.state.browserUnavailable,true);assert.equal(unavailable.browserProfile('cores3'),null);
assert.ok(unavailable.events.includes('render-devices')&&unavailable.events.includes('connect-service'));assert.equal(unavailable.lane(),'service');
unavailable.element('runtimeMode').value='model';assert.equal(unavailable.lane(),'model');assert.match(unavailable.element('errorBanner').textContent,/仍可浏览模型或连接 HTTPS 仿真服务/);

const original=await entry();assert.equal(original.events.some(item=>item.startsWith('start:')),false);
original.element('runtimeMode').value='browser';await original.share();
const share=new URL(original.clipboard[0]);
assert.equal(share.searchParams.get('device'),'cores3');assert.equal(share.searchParams.get('sha256'),fixtureSha);
assert.equal(share.searchParams.has('firmware'),false,'the composed reference has no prebuilt firmware URL');
const reopened=await entry({search:share.search});
assert.ok(reopened.events.includes('start:browser'),'an exact composed-reference SHA authorizes reference autostart');
assert.equal(reopened.element('firmwareSha').value,fixtureSha);
assert.equal(reopened.element('referenceExample').value,'stock-div8');
const wallclock=await entry({wallclockExample:true});
assert.equal(wallclock.reference().sha256,wallclockSha);assert.equal(wallclock.reference().wallclockCandidate,true);
wallclock.element('runtimeMode').value='browser';await wallclock.share();
const wallclockLink=new URL(wallclock.clipboard[0]);assert.equal(wallclockLink.searchParams.get('sha256'),wallclockSha);
assert.equal(wallclockLink.searchParams.has('firmware'),false);
const wallclockReopen=await entry({wallclockExample:true,search:wallclockLink.search});
assert.equal(wallclockReopen.element('referenceExample').value,'wallclock-candidate');
assert.equal(wallclockReopen.reference().sha256,wallclockSha);assert.ok(wallclockReopen.events.includes('start:browser'));
const oldReopen=await entry({wallclockExample:true,search:share.search});
assert.equal(oldReopen.element('referenceExample').value,'stock-div8');assert.equal(oldReopen.reference().sha256,fixtureSha);
assert.ok(oldReopen.events.includes('start:browser'),'old hash sharing must restore the old composer even with the new default');
const disabledCandidate=await entry({wallclockExample:false,search:wallclockLink.search});
assert.equal(disabledCandidate.reference().sha256,fixtureSha);assert.equal(disabledCandidate.events.some(item=>item.startsWith('start:')),false);
const unknownCandidate=await entry({wallclockExample:true,search:wallclockLink.search.replace(wallclockSha,'0'.repeat(64))});
assert.equal(unknownCandidate.events.some(item=>item.startsWith('start:')),false);
wallclock.element('referenceExample').value='stock-div8';assert.equal(wallclock.reference().sha256,fixtureSha);
for(const search of [share.search+'&autostart=0',share.search.replace(fixtureSha,'0'.repeat(64)),share.search.replace('cores3','core2'),share.search.replace('mode=browser','mode=model')]){
  const app=await entry({search});assert.equal(app.events.some(item=>item.startsWith('start:')),false,'wrong device/hash, disabled autostart and model mode cannot run the reference');
}
for(const profile of registry.profiles){
  const app=await entry({publicationEligible:false,search:`?device=${profile.deviceId}&mode=browser&autostart=0`});
  assert.equal(app.browserProfile(profile.deviceId).board,profile.board);assert.equal(app.lane(),'browser');
  assert.equal(app.browserProfile(profile.deviceId).inputs.uart,false);
  const controller=new PublicQemuRuntime({root:pageRoot,profiles:registry,allowCandidateProfiles:true});controller.profile=app.browserProfile(profile.deviceId);
  app.state.run={kind:'browser',generation:app.state.runGeneration,controller};app.status('running');
  assert.equal(app.element('serialInput').disabled,true,'QEMU output-only UART cannot become a send UI');
  assert.equal(app.element('browserPirPanel').hidden,!profile.inputs.pir,'PIR controls must follow the selected actual profile');
  assert.equal(app.element('nativeScreenBtn').hidden,profile.display===null,'headless devices cannot offer a fabricated flat screen');
  const reference=app.reference();
  if(['xtensa-board-display-v1','xtensa-board-led-v1'].includes(profile.fixture?.id)){
    assert.equal(reference.composedProbe,true);assert.equal(reference.sha256,profile.fixture.firmwareSHA256);
    await app.share();const link=new URL(app.clipboard[0]);assert.equal(link.searchParams.get('device'),profile.deviceId);assert.equal(link.searchParams.get('sha256'),profile.fixture.firmwareSHA256);assert.equal(link.searchParams.has('firmware'),false);
    const reopenedProbe=await entry({publicationEligible:false,search:link.search});assert.ok(reopenedProbe.events.includes('start:browser'));
    const wrong=await entry({publicationEligible:false,search:link.search.replace(profile.fixture.firmwareSHA256,'0'.repeat(64))});assert.equal(wrong.events.some(event=>event.startsWith('start:')),false);
  }
  if(profile.admission==='candidate'){
    const published=await entry({publicationEligible:true,search:`?device=${profile.deviceId}&mode=browser&autostart=0`});assert.equal(published.browserProfile(profile.deviceId),null);assert.equal(published.lane(),null);
    app.state.picker={attachments:()=>[{id:'unsupported-extra-unit'}]};assert.equal(app.lane(),null,'candidate browser admission cannot inherit arbitrary attached Units');app.element('runtimeMode').value='auto';app.state.serviceDevices=[{device_id:profile.deviceId,creatable:true}];assert.equal(app.lane(),'service');
  }
}
console.log('public QEMU entry COI fallback and exact composed-reference share/autostart contracts passed; no guest executed');
console.log('public.js SHA256 '+createHash('sha256').update(source).digest('hex'));
