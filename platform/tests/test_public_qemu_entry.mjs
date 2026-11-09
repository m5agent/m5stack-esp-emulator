// Actual public.js initialization/share/lane logic with mock DOM and execution
// boundaries. No browser, service, network request or guest is started.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import * as config from '../web/public-config.js';
import * as firmware from '../web/public-firmware.js';
import * as demoFirmware from '../web/public-demo-firmware.js';
import * as uiflowFirmware from '../web/public-uiflow-firmware.js';
import {PublicMicroPythonRunner} from '../web/public-micropython.js';
import * as qemuProfiles from '../web/public-qemu-profiles.js';
import * as qemuFrame from '../web/public-qemu-frame.js';
import * as qemuServo from '../web/public-qemu-servo.js';
import {PublicQemuRuntime,QEMU_BROWSER_PROFILE} from '../web/public-qemu-runtime.js';

const pageRoot='https://example.test/showcase/';
const fixtureSha='78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f';
const wallclockSha=demoFirmware.WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256;
const html=await readFile(new URL('../web/index.html',import.meta.url),'utf8');
const defaultExample=html.match(/id="referenceExample"[^>]*>\s*<option value="([^"]+)"/)[1];
const source=await readFile(new URL('../web/public.js',import.meta.url),'utf8');
const imports=[...source.matchAll(/^import \{([^}]+)\} from '([^']+)';$/gm)];
for(const module of ['./public-uiflow-firmware.js','./public-micropython.js','./public-unit-assembly.js','./public-service-program.js'])
  assert.ok(imports.some(match=>match[2]===module),'the workbench imports its programming and assembly adapters');
assert.deepEqual(imports.filter(match=>match[2]==='./public-qemu-servo.js')
  .flatMap(match=>match[1].split(',').map(name=>name.trim())),
['qemuServoVisualCommands','qemuServoDiagnostic']);
assert.ok(source.endsWith('void init().catch(error);\n'));
const body=source.replace(/^import \{[^}]+\} from '[^']+';\n/gm,'').replace(/void init\(\)\.catch\(error\);\n$/,'');
const required=imports.flatMap(match=>match[1].split(',').map(name=>name.trim()));
const registry=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const workbenchRegistry=JSON.parse(await readFile(new URL('../web/uiflow-workbench-profiles.json',import.meta.url),'utf8'));
const catalog=JSON.parse(await readFile(new URL('../../devices/catalog.json',import.meta.url),'utf8'));
const legacyBrowserDevices=JSON.parse(await readFile(new URL('../web/browser-profiles.json',import.meta.url),'utf8')).devices;
// A candidate may precede native catalog admission; the real entry also merges
// these hosts from the pinned visual catalog. Keep that boundary in this mock.
const visualCandidates=registry.profiles.filter(profile=>!catalog.devices.some(device=>device.id===profile.deviceId))
  .map(profile=>({id:profile.deviceId,name:profile.deviceId,category:'controller',display:profile.display}));

async function entry({search='',pageUrl=pageRoot,siteServiceUrl='',isolationError,registryFailure=false,publicationEligible=true,wallclockExample=false,
  browserEnabled=true,runtimeEngine='qemu-wasm',legacyProfile=null,browserDevices=[],visualProducts=visualCandidates,
  deviceCatalog=catalog,
  isolation={isolated:true,reloading:false}}={}){
  const elements=new Map(),events=[],clipboard=[];
  const makeElement=id=>({id,value:'',textContent:'',hidden:true,dataset:{},files:[],options:[],children:[],
    listeners:new Map(),addEventListener(type,callback){this.listeners.set(type,callback);},setAttribute(){},
    replaceChildren(...children){this.children=children;},append(...children){this.children.push(...children);},focus(){},scrollIntoView(){},
    classList:{add(){},remove(){},toggle(){}}});
  const element=(id)=>{
    if(!elements.has(id))elements.set(id,makeElement(id));
    return elements.get(id);
  };
  element('referenceExample').value=defaultExample;
  const radios=new Map(['reference','url','local'].map(value=>[value,{value,checked:value==='reference'}]));
  const document={getElementById:element,querySelectorAll:()=>[],
    querySelector(selector){if(selector.includes(':checked'))return [...radios.values()].find(item=>item.checked);
      const match=selector.match(/\[value="([^"]+)"\]/);return match?radios.get(match[1]):null;},
    createElement:makeElement,createTextNode:text=>({textContent:text})};
  const fetchFixture=async url=>{
    if(url.endsWith('platform/units/catalog.json'))return new Response('{"units":[]}');
    if(url.endsWith('platform/units/host-ports.json'))return new Response('{"hosts":[]}');
    if(url.endsWith('platform/units/runtime-profiles.json'))return new Response('{"units":{}}');
    if(url.endsWith('uiflow-workbench-profiles.json'))return new Response(JSON.stringify(workbenchRegistry));
    if(url.endsWith('qemu-browser-profiles.json')){events.push('registry');return new Response(JSON.stringify(registry),{status:registryFailure?503:200});}
    if(url.endsWith('devices/catalog.json'))return new Response(JSON.stringify(deviceCatalog));
    if(url.endsWith('catalog/products.json'))return new Response(JSON.stringify({products:visualProducts}));
    if(url.endsWith('browser-profiles.json'))return new Response(JSON.stringify({devices:browserDevices}));
    if(url.endsWith('site-config.json'))return new Response(JSON.stringify({service_url:siteServiceUrl,browser_runtime_engine:runtimeEngine,browser_board_execution:browserEnabled,publication_eligible:publicationEligible,browser_wallclock_example:wallclockExample}));
    throw new Error('Unexpected fetch '+url);
  };
  const dependencies=Object.fromEntries(required.map(name=>[name,()=>{throw new Error(`Unexpected execution boundary ${name}`);} ]));
  Object.assign(dependencies,config,firmware,demoFirmware,uiflowFirmware,qemuProfiles,qemuFrame,qemuServo,{
    siteRoot:()=>new URL(pageUrl),
    ensurePublicIsolation:async()=>{events.push('isolation');if(isolationError)throw isolationError;return isolation;},
    PublicMicroPythonRunner,
    createPublicUnitAssembly:async()=>({attachments:()=>[]}),
    loadUIFlowWorkbenchProfiles:options=>uiflowFirmware.loadUIFlowWorkbenchProfiles({...options,fetchImpl:fetchFixture}),
    getBrowserProfile:id=>legacyProfile?.deviceId===id?legacyProfile:null,QEMU_BROWSER_PROFILE,PublicQemuRuntime,browserQemuHistory:()=>[],
    loadQemuBrowserProfiles:options=>qemuProfiles.loadQemuBrowserProfiles({...options,fetchImpl:fetchFixture}),
  });
  const context=vm.createContext({...dependencies,document,window:{addEventListener(){}},
    navigator:{clipboard:{writeText:async url=>clipboard.push(url)}},location:{href:new URL(search,pageUrl).href,search},
    URL,URLSearchParams,Map,TextEncoder,AbortController,DOMException,console,
    fetch:fetchFixture,events,
  });
  vm.runInContext(body+`
    renderDevices=()=>events.push('render-devices');renderUnits=()=>events.push('render-units');
    selectDevice=async id=>{state.selected=state.devices.find(item=>item.id===id);state.shell={};events.push('select:'+id);};
    connectService=async()=>{state.serviceDevices=[{device_id:state.selected.id,creatable:true}];events.push('connect-service');};
    startRun=async()=>events.push('start:'+lane());
    globalThis.contract={state,browserProfile,lane,deviceRuntimeLabel,share,reference,status,applyBrowserFrame,applyBrowserPresentation,firmware,updateCapability};
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

const localService=await entry({pageUrl:'http://127.0.0.1:8787/platform/web/',siteServiceUrl:'http://127.0.0.1:8787',search:'?device=cardputer-adv&autostart=0'});
assert.equal(localService.element('serviceUrl').value,'http://127.0.0.1:8787');
assert.ok(localService.events.includes('connect-service'),'a loopback page served by its own Device Service must connect the same origin automatically');
assert.equal(localService.lane(),'service','auto uses a connected device service even when browser QEMU is available');
localService.element('runtimeMode').value='browser';assert.equal(localService.lane(),'browser','an explicit browser choice is preserved');
localService.element('runtimeMode').value='auto';
localService.state.serviceDevices=[{device_id:'stackchan',creatable:true}];assert.equal(localService.lane(),'browser','another device cannot authorize native execution');
localService.state.serviceDevices=[{device_id:'cardputer-adv',creatable:false}];assert.equal(localService.lane(),'browser','an unavailable native backend does not win auto selection');
localService.state.serviceDevices=[{device_id:'cardputer-adv',creatable:true}];
localService.state.picker={attachments:()=>[{id:'service-unit'}]};assert.equal(localService.lane(),'service');
localService.element('runtimeMode').value='browser';assert.equal(localService.lane(),null,'Unit routing remains fail-closed in browser mode');
localService.state.picker=null;localService.element('runtimeMode').value='auto';
localService.state.browserUnavailable=true;
assert.equal(localService.deviceRuntimeLabel(localService.state.selected),'服务可运行','connected devices must not keep the connect-service label');
const localBrowser=await entry({pageUrl:'http://127.0.0.1:8787/platform/web/',siteServiceUrl:'http://127.0.0.1:8787',search:'?device=cardputer-adv&mode=browser&autostart=0'});
assert.equal(localBrowser.element('serviceUrl').value,'http://127.0.0.1:8787');
assert.equal(localBrowser.events.includes('connect-service'),false,'an explicit browser-only link must not create a service connection');
const staticBrowser=await entry({pageUrl:'http://127.0.0.1:8000/platform/web/',search:'?device=cardputer-adv&autostart=0'});
assert.equal(staticBrowser.element('serviceUrl').value,'');
assert.equal(staticBrowser.events.includes('connect-service'),false,'a static loopback export must not probe or connect a Device Service');
assert.equal(staticBrowser.lane(),'browser');
const disabledBrowser=await entry({browserEnabled:false,search:'?device=stopwatch&autostart=0'});
assert.equal(disabledBrowser.browserProfile('stopwatch'),null);assert.equal(disabledBrowser.lane(),null);
const legacy={deviceId:'stopwatch',board:'stopwatch',display:{width:468,height:466}};
const disabledLegacy=await entry({browserEnabled:false,runtimeEngine:null,legacyProfile:legacy,
  siteServiceUrl:'https://service.example.test',search:'?device=stopwatch&autostart=0'});
assert.equal(disabledLegacy.browserProfile('stopwatch'),null,'a hardcoded legacy profile cannot bypass the site runtime switch');
assert.equal(disabledLegacy.lane(),'service');
disabledLegacy.element('runtimeMode').value='browser';assert.equal(disabledLegacy.lane(),null);

const textOf=node=>[node.textContent||'',...(node.children||[]).map(textOf)].join(' ');
const paperModel={id:'papers3',name:'PaperS3',category:'controller',display:{width:540,height:960}};
const visualWithPaper=[...visualCandidates,paperModel];
const catalogWithoutPaper={...catalog,devices:catalog.devices.filter(row=>row.id!=='papers3')};
const papers=await entry({browserDevices:legacyBrowserDevices,visualProducts:visualWithPaper,deviceCatalog:catalogWithoutPaper,
  search:'?device=papers3&mode=browser&autostart=0'});
papers.status('model');
assert.equal(papers.browserProfile('papers3'),null);assert.equal(papers.lane(),null);assert.equal(papers.element('startBtn').disabled,true);
assert.equal(papers.deviceRuntimeLabel(papers.state.selected),'仅模型');
assert.equal(papers.reference(),null,'the legacy PaperS3 BIN cannot become this QEMU site reference');
assert.match(textOf(papers.element('deviceDetails')),/旧浏览器演示不属于当前运行内核/);
assert.doesNotMatch(textOf(papers.element('deviceDetails')),/浏览器运行 · 黑白显示与单点触摸/);
assert.match(papers.element('pythonStatus').textContent,/模型预览/);assert.equal(papers.element('pythonRunBtn').disabled,true);
const legacyPapers=await entry({runtimeEngine:null,legacyProfile:{deviceId:'papers3'},browserDevices:legacyBrowserDevices,visualProducts:visualWithPaper,
  deviceCatalog:catalogWithoutPaper,search:'?device=papers3&mode=browser&autostart=0'});
assert.equal(legacyPapers.reference().sha256,legacyBrowserDevices.find(row=>row.id==='papers3').browser.reference.sha256,
  'engine-specific metadata selection preserves the separate legacy reference path');
assert.match(textOf(legacyPapers.element('deviceDetails')),/浏览器运行 · 黑白显示与单点触摸/);
assert.equal(legacyPapers.lane(),'browser','a legacy experimental profile can replace the PaperS3 model-only row in its own build');
const nativePaper={id:'papers3',name:'PaperS3',path:'esp32-s3/papers3',hardware:{controls:[{id:'power'}]}};
const nativePapers=await entry({browserDevices:legacyBrowserDevices,visualProducts:visualWithPaper,
  deviceCatalog:{...catalogWithoutPaper,devices:[...catalogWithoutPaper.devices,nativePaper]},
  search:'?device=papers3&mode=service&autostart=0'});
assert.equal(nativePapers.state.selected.path,nativePaper.path);
assert.equal(nativePapers.state.selected.hardware.controls[0].id,'power');
assert.equal(nativePapers.state.selected.browser_only,undefined);
assert.equal(nativePapers.browserProfile('papers3'),null);
assert.equal(nativePapers.reference(),null);
const stopwatchScope=await entry({browserDevices:legacyBrowserDevices,search:'?device=stopwatch&mode=browser&autostart=0'});
assert.match(textOf(stopwatchScope.element('deviceDetails')),/PM1 应用配置/);
assert.match(textOf(stopwatchScope.element('deviceDetails')),/BtnPWR.*应用中配置/);
assert.doesNotMatch(textOf(stopwatchScope.element('deviceDetails')),/RTC、音频与物理电源键未接入/);
assert.equal(stopwatchScope.reference().composedWorkbench,true);
for(const id of ['cardputer-zero','m5stick','stickt2']){
  const app=await entry({search:`?device=${id}&mode=browser&autostart=0`});app.status('model');
  assert.equal(app.lane(),null);assert.equal(app.element('startBtn').disabled,true);assert.equal(app.element('pythonRunBtn').disabled,true);
  assert.match(app.element('pythonStatus').textContent,/不支持 UIFlow2.*网页编程不可用/);
  assert.match(textOf(app.element('deviceDetails')),/不支持 UIFlow2/);
  if(id==='cardputer-zero')assert.match(textOf(app.element('deviceDetails')),/Raspberry Pi CM0\/Linux/);
  app.state.serviceDevices=[{device_id:id,creatable:true}];app.element('runtimeMode').value='service';
  assert.equal(app.lane(),'service','an explicit compatible service remains available for non-UIFlow firmware');
}
const visualOnly=await entry({visualProducts:[{id:'stickv',name:'StickV',category:'controller'}],
  search:'?device=stickv&mode=browser&autostart=0'});visualOnly.status('model');
assert.equal(visualOnly.lane(),null);assert.equal(visualOnly.element('startBtn').disabled,true);
assert.equal(visualOnly.element('pythonRunBtn').disabled,true);assert.match(visualOnly.element('pythonStatus').textContent,/仅提供.*模型预览/);
visualOnly.element('runtimeMode').value='model';visualOnly.updateCapability();
assert.equal(visualOnly.element('startBtn').textContent,'浏览设备模型 →');assert.equal(visualOnly.element('pythonRunBtn').disabled,true);
const uploadedUart=await entry({search:'?device=cores3&mode=browser&autostart=0'});
const uploadController=new PublicQemuRuntime({root:pageRoot,profiles:registry});uploadController.profile=uploadedUart.browserProfile('cores3');
uploadController.receipt={deviceId:'cores3',firmwareSha256:'f'.repeat(64),uiflowWorkbench:null};
uploadedUart.state.run={kind:'browser',generation:uploadedUart.state.runGeneration,controller:uploadController};uploadedUart.status('running');
assert.equal(uploadedUart.element('pythonRunBtn').disabled,false,'compatible UART still permits the existing REPL handshake attempt');
assert.match(uploadedUart.element('pythonStatus').textContent,/串口已连接，MicroPython 待确认/);
assert.doesNotMatch(uploadedUart.element('pythonStatus').textContent,/UIFlow.*就绪/);
assert.equal(uploadedUart.element('stageFirmwareNotice').hidden,true);
uploadController.receipt.uiflowWorkbench={};uploadedUart.status('running');
assert.doesNotMatch(uploadedUart.element('pythonStatus').textContent,/UIFlow.*就绪/,'stale workbench metadata cannot label an unknown Flash ready');
assert.equal(uploadedUart.element('stageFirmwareNotice').hidden,true);
const uploadedWorkbench=workbenchRegistry.profiles.find(row=>row.deviceId==='cores3');
uploadController.receipt.firmwareSha256=uploadedWorkbench.firmwareSHA256;
uploadedUart.status('booting');assert.equal(uploadedUart.element('pythonRunBtn').disabled,true);assert.match(uploadedUart.element('pythonStatus').textContent,/正在启动 UIFlow/);
assert.equal(uploadedUart.element('stageFirmwareNotice').dataset.phase,'starting');
assert.equal(uploadedUart.element('stageFirmwareEditor').hidden,true);
uploadedUart.status('running');assert.equal(uploadedUart.element('pythonStatus').textContent,'UIFlow 已就绪');
assert.equal(uploadedUart.element('stageFirmwareNotice').dataset.phase,'ready');
assert.match(uploadedUart.element('stageFirmwareDetail').textContent,/程序绘图后/);
assert.equal(uploadedUart.element('stageFirmwareEditor').hidden,false);
uploadedUart.status('error');assert.equal(uploadedUart.element('pythonRunBtn').disabled,true);
assert.match(uploadedUart.element('pythonStatus').textContent,/运行未完成/);
assert.equal(uploadedUart.element('stageFirmwareNotice').hidden,true);
uploadedUart.status('sleeping');assert.equal(uploadedUart.element('pythonRunBtn').disabled,true);
assert.match(uploadedUart.element('pythonStatus').textContent,/已休眠/);

// Execute the production local-file path: WebCrypto hashes the same buffer
// handed to the runtime, with one File read and the existing SHA rejection.
const localFile=await entry({search:'?device=stackchan&autostart=0'});
for(const [name,radio] of localFile.radios)radio.checked=name==='local';
const localBytes=new Uint8Array([0xe9,1,2,3,4,5]).buffer;let fileReads=0;
localFile.element('firmwareFile').files=[{size:localBytes.byteLength,name:'fixture.bin',arrayBuffer:async()=>{fileReads++;return localBytes;}}];
const loadedLocal=await localFile.firmware(new AbortController().signal,localFile.state.runGeneration);
assert.equal(loadedLocal.bytes,localBytes);assert.equal(fileReads,1,'local Flash is read once and the hashed buffer is reused');
assert.equal(loadedLocal.sha256,createHash('sha256').update(new Uint8Array(localBytes)).digest('hex'));
localFile.element('firmwareSha').value='0'.repeat(64);
await assert.rejects(localFile.firmware(new AbortController().signal,localFile.state.runGeneration),/SHA-256/);

const unavailable=await entry({registryFailure:true,search:'?device=cores3&mode=service&service=https://service.example.test&autostart=0'});
assert.equal(unavailable.state.browserUnavailable,true);assert.equal(unavailable.browserProfile('cores3'),null);
assert.ok(unavailable.events.includes('render-devices')&&unavailable.events.includes('connect-service'));assert.equal(unavailable.lane(),'service');
unavailable.element('runtimeMode').value='model';assert.equal(unavailable.lane(),'model');assert.match(unavailable.element('errorBanner').textContent,/仍可浏览模型或连接 HTTPS 仿真服务/);

const original=await entry();assert.equal(original.events.some(item=>item.startsWith('start:')),false);
assert.equal(original.reference().composedWorkbench,true,'official UIFlow programming firmware is the default');
assert.equal(original.reference().sha256,workbenchRegistry.profiles.find(row=>row.deviceId==='cores3').firmwareSHA256);
original.element('referenceExample').value='stock-div8';
original.element('runtimeMode').value='browser';await original.share();
const share=new URL(original.clipboard[0]);
assert.equal(share.searchParams.get('device'),'cores3');assert.equal(share.searchParams.get('sha256'),fixtureSha);
assert.equal(share.searchParams.has('firmware'),false,'the composed reference has no prebuilt firmware URL');
const reopened=await entry({search:share.search});
assert.ok(reopened.events.includes('start:browser'),'an exact composed-reference SHA authorizes reference autostart');
assert.equal(reopened.element('firmwareSha').value,fixtureSha);
assert.equal(reopened.element('referenceExample').value,'stock-div8');
const wallclock=await entry({wallclockExample:true});wallclock.element('referenceExample').value='wallclock-candidate';
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
wallclock.updateCapability();
assert.match(wallclock.element('capabilityText').textContent,/正常虚拟时钟/,
  'the exact stock reference resolves its normal-clock execution before display');
assert.doesNotMatch(wallclock.element('capabilityText').textContent,/1\/8|调度候选/);
assert.match(wallclock.reference().name,/原始程序，正常时钟/);
wallclock.radios.get('reference').checked=false;wallclock.radios.get('local').checked=true;
wallclock.updateCapability();
assert.match(wallclock.element('capabilityText').textContent,/1\/8/,
  'an unidentified local image keeps the base clock explanation');
const runningStock=new PublicQemuRuntime({root:pageRoot,profiles:registry});
runningStock.profile=qemuProfiles.resolveQemuFirmwareProfile(qemuProfiles.getQemuBrowserProfile('cores3',registry),fixtureSha);
wallclock.state.run={controller:runningStock,generation:wallclock.state.runGeneration};
wallclock.updateCapability();
assert.match(wallclock.element('capabilityText').textContent,/正常虚拟时钟/,
  'an active uploaded image reports its actual resolved execution profile');
wallclock.state.run.stopping=true;wallclock.updateCapability();
assert.match(wallclock.element('capabilityText').textContent,/1\/8/,
  'a stopping run cannot override the next unidentified upload');
wallclock.state.run=null;
wallclock.radios.get('local').checked=false;wallclock.radios.get('reference').checked=true;
for(const search of [share.search+'&autostart=0',share.search.replace(fixtureSha,'0'.repeat(64)),share.search.replace('cores3','core2'),share.search.replace('mode=browser','mode=model')]){
  const app=await entry({search});assert.equal(app.events.some(item=>item.startsWith('start:')),false,'wrong device/hash, disabled autostart and model mode cannot run the reference');
}
for(const profile of registry.profiles){
  const app=await entry({publicationEligible:false,search:`?device=${profile.deviceId}&mode=browser&autostart=0`});
  assert.equal(app.browserProfile(profile.deviceId).board,profile.board);assert.equal(app.lane(),'browser');
  assert.equal(app.browserProfile(profile.deviceId).inputs.uart,true);
  const controller=new PublicQemuRuntime({root:pageRoot,profiles:registry,allowCandidateProfiles:true});controller.profile=app.browserProfile(profile.deviceId);
  app.state.run={kind:'browser',generation:app.state.runGeneration,controller};app.status('running');
  assert.equal(app.element('serialInput').disabled,false,'an active UART-capable QEMU run exposes its real serial input');
  assert.equal(app.element('browserPirPanel').hidden,!profile.inputs.pir,'PIR controls must follow the selected actual profile');
  assert.equal(app.element('nativeScreenBtn').hidden,profile.display===null,'headless devices cannot offer a fabricated flat screen');
  if(workbenchRegistry.profiles.some(row=>row.deviceId===profile.deviceId)){
    assert.equal(app.reference().composedWorkbench,true);
    assert.equal(app.element('referenceExampleFields').hidden,false,'all19 retain the default UIFlow startup selector');
  }else assert.equal(app.element('referenceExampleFields').hidden,true,'a preview without a workbench identity cannot advertise the UIFlow selector');
  app.element('referenceExample').value='probe';
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
// Execute the production frame and pointer handlers with an asymmetric raster.
// This is a host contract; real driver/glass evidence is a separate guest test.
const raster=await entry({search:'?device=cardputer-adv&mode=browser&autostart=0'});
const rgba=[[255,0,0,255],[0,255,0,255],[0,0,255,255],
  [255,255,255,255],[255,255,0,255],[0,255,255,255]];
const packed=[0xf800,0x07e0,0x001f,0xffff,0xffe0,0x07ff];
let painted;const canvas=raster.element('rawFrameCanvas');
canvas.getContext=()=>({createImageData:(w,h)=>({width:w,height:h,data:new Uint8ClampedArray(w*h*4)}),
  putImageData:image=>{painted=image;}});
canvas.closest=()=>raster.element('rawFramePanel');
canvas.getBoundingClientRect=()=>({left:0,top:0,width:canvas.width,height:canvas.height});
canvas.setPointerCapture=()=>{};
const controller=new PublicQemuRuntime({root:pageRoot,profiles:registry}),input=[];
controller.profile={inputs:{touch:true}};controller.status='running';controller.input=async event=>{input.push(event);};
const run={kind:'browser',generation:raster.state.runGeneration,controller};
raster.state.run=run;raster.state.shell={setFrameLE:()=>true,setDeviceRotation:()=>{}};
const frame={width:3,height:2,sequence:1,pixels:new Uint8Array(packed.flatMap(v=>[v&255,v>>8]))};
controller.display={orientation:'portrait',deviceRotationDeg:-90};
raster.applyBrowserPresentation({display:controller.display});raster.applyBrowserFrame(frame,run);
controller.lastFrame=frame;
assert.deepEqual([canvas.width,canvas.height],[2,3]);
assert.deepEqual(Array.from(painted.data),[rgba[3],rgba[0],rgba[4],rgba[1],rgba[5],rgba[2]].flat(),
  'portrait canvas must rotate the native glass clockwise without mirroring');
canvas.listeners.get('pointerdown')({clientX:1.5,clientY:2.5,pointerId:1});
assert.deepEqual([input.at(-1).x,input.at(-1).y,input.at(-1).down],[2,0,true],
  'portrait pointer mapping must invert the displayed rotation');
controller.display={orientation:'landscape',deviceRotationDeg:0};
raster.applyBrowserPresentation({display:controller.display});
assert.deepEqual([canvas.width,canvas.height],[3,2]);assert.deepEqual(Array.from(painted.data),rgba.flat());
assert.equal(Number(raster.element('deviceMount').dataset.frameSequence),frame.sequence,
  'presentation-only repaint must retain the real guest frame sequence');
const paintedBeforeStale=painted;
raster.applyBrowserPresentation({display:{orientation:'portrait',deviceRotationDeg:-90}},{...run});
assert.equal(painted,paintedBeforeStale,'an unowned presentation event cannot repaint the active run');
assert.deepEqual([canvas.width,canvas.height],[3,2]);
canvas.listeners.get('pointerup')({clientX:2.5,clientY:1.5,pointerId:1});
assert.deepEqual([input.at(-1).x,input.at(-1).y,input.at(-1).down],[2,1,false]);
console.log('public QEMU entry, exact reference sharing and asymmetric portrait/frame pointer contracts passed; no guest executed');
console.log('public.js SHA256 '+createHash('sha256').update(source).digest('hex'));
