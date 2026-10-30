import {assetUrl, siteRoot} from './public-config.js';
import {downloadFirmware} from './public-firmware.js';
import {sha256Bytes} from './sha256.js';
import {loadQemuBrowserProfiles, getQemuBrowserProfile, resolveQemuFirmwareProfile, validateQemuFirmware, qemuInputCommand, validateQemuOnboardState} from './public-qemu-profiles.js';

const QEMU_COMMIT = '40edccac415693c5130f91c01d84176ae6008566';
const ROM_SHA = 'b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913';
const HISTORY_KEY = 'm5-public-qemu-history-v1';
const EXAMPLE_SHA = '78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f';
export const QEMU_BROWSER_PROFILE = Object.freeze({deviceId:'cores3',board:'m5cores3',chip:'esp32s3',flashMb:16,
  display:{width:320,height:240},execution:'browser-qemu-wasm',profile:'cores3-wasm-vm-div8',
  limitations:['实验性离线 CoreS3 / LVGL / 触摸 / PIR。','虚拟时间为墙钟的 1/8；看门狗到期也随之变慢。','网络、音频、其他 Unit 与任意固件兼容性未验证；刷新不保留 Flash。']});
function check(ok, message) { if (!ok) throw new Error(message); }
export function browserQemuHistory(storage) {
  try { const rows=JSON.parse((storage || globalThis.localStorage).getItem(HISTORY_KEY)||'[]'); return Array.isArray(rows)?rows:[]; } catch { return []; }
}
export class PublicQemuRuntime {
  constructor({onSerial=()=>{},onFrame=()=>{},onDeviceState=()=>{},onState=()=>{},onError=()=>{},root=siteRoot(),fetchImpl=globalThis.fetch,
    requestTimeout=20000,storage,downloadImpl=downloadFirmware,profiles,allowCandidateProfiles=false}={}) {
    try { storage ||= globalThis.localStorage; } catch { storage = null; }
    Object.assign(this,{onSerial,onFrame,onDeviceState,onState,onError,root:new URL(root),fetchImpl,requestTimeout,storage,downloadImpl,profiles,allowCandidateProfiles});
    this.fetchImpl=(...args)=>fetchImpl(...args);
    this.status='stopped';this.generation=0;this.pending=new Map();this.id=0;this.sequence=0;this.display=null;
  }
  observe() { return {status:this.status,deviceId:this.profile?.deviceId||null,sequence:this.sequence,execution:'browser-qemu-wasm',
    runtime:this.receipt||null,display:this.display,sessionId:this.sessionId,persistentStorage:false,cleanup:this.cleanupResult||null,
    resetCount:this.machineEvents?.filter(row=>row.event==='RESET').length||0,machineEvents:this.machineEvents||[]}; }
  state(status) { this.status=status;this.onState(this.observe()); }
  ask(op,value={},transfer=[]) {
    check(this.port,'浏览器设备尚未连接。');const id=++this.id;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`浏览器命令 ${op} 超时。`));},this.requestTimeout);
      this.pending.set(id,{resolve,reject,timer,op});
      try { this.port.postMessage({id,op,value},transfer); }
      catch(error) { clearTimeout(timer);this.pending.delete(id);reject(error); }
    });
  }
  waitFor(type,timeout=30000) {
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.waiters.delete(type);reject(new Error(`等待浏览器设备 ${type} 超时。`));},timeout);
      this.waiters.set(type,{resolve:(value)=>{clearTimeout(timer);resolve(value);},reject:(error)=>{clearTimeout(timer);reject(error);}});
    });
  }
  receive(data,generation) {
    if(generation!==this.generation)return;
    if(data.id) {
      const item=this.pending.get(data.id);if(!item)return;
      this.pending.delete(data.id);clearTimeout(item.timer);
      if(!data.error&&item.op==='dispose'&&data.value?.enginePlacement==='dedicated-worker-v1')this.engineDisposal=data.value;
      data.error?item.reject(new Error(data.error)):item.resolve(data.value);return;
    }
    this.waiters.get(data.type)?.resolve(data.value);this.waiters.delete(data.type);
    if(data.type==='serial') {
      const serial=this.serial+data.value;this.readySerialOffset=Math.max(0,(this.readySerialOffset||0)-Math.max(0,serial.length-65536));
      this.serial=serial.slice(-65536);this.onSerial(data.value);
      if(this.status==='booting'&&this.guestReady())this.state('running');
    }
    if(data.type==='machine-event') {
      if(!['RESET','SHUTDOWN','STOP','RESUME','POWERDOWN','SUSPEND','WAKEUP'].includes(data.value?.event))return;
      this.machineEvents.push({...data.value,at:new Date().toISOString()});if(this.machineEvents.length>50)this.machineEvents.shift();
      if(data.value.event==='SUSPEND')this.state('sleeping');
      if(data.value.event==='WAKEUP'&&this.status==='sleeping')this.state(this.guestReady()?'running':'booting');
      if(data.value.event==='RESET'){this.readySerialOffset=this.serial.length;this.lastDeviceState=null;if(this.status!=='paused')this.state(this.guestReady()?'running':'booting');}
    }
    if(data.type==='diagnostic') { this.diagnostics=(this.diagnostics+data.value+'\n').slice(-32768); }
    if(data.type==='frame') {
      if(this.profile?.display===null){this.receive({type:'error',value:'Headless QEMU device emitted an unadmitted framebuffer'},generation);return;}
      this.lastFrame={...data.value,sequence:++this.sequence};this.onFrame(this.lastFrame);
    }
    if(data.type==='device-state') {
      try { validateQemuOnboardState(this.profile,data.value); }
      catch(error){this.receive({type:'error',value:error.message},generation);return;}
      this.lastDeviceState=structuredClone(data.value);this.outputSequence++;this.onDeviceState(this.lastDeviceState);
    }
    if(data.type==='exit') { this.exit=data.value; if(!this.stopping){this.state('stopped');void this.stop();} }
    if(data.type==='error') {
      const error=new Error(data.value);this.state('error');this.onError(error);
      for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(error);}this.pending.clear();
      for(const waiter of this.waiters.values())waiter.reject(error);this.waiters.clear();
      void this.stop();
    }
  }
  async start({device,firmware,signal,clockDivisor}={}) {
    await this.stop();
    const generation=++this.generation;this.waiters=new Map();this.serial='';this.diagnostics='';this.sequence=0;this.machineEvents=[];this.readySerialOffset=0;
    this.inputs=[];this.lastFrame=null;this.lastDeviceState=null;this.outputSequence=0;this.exit=null;this.cleanupResult=null;this.engineDisposal=null;
    this.display=null;this.displayPollAt=0;
    this.receipt=null;this.profile=null;this.stoppedAt=null;
    this.sessionId=crypto.randomUUID();this.startedAt=new Date().toISOString();
    const bootAbort=this.abort=new AbortController();
    const cancel=()=>{bootAbort.abort();if(generation===this.generation)void this.stop();};signal?.addEventListener('abort',cancel,{once:true});
    this.signalCleanup=()=>signal?.removeEventListener('abort',cancel);
    const active=()=>{if(signal?.aborted||bootAbort.signal.aborted||generation!==this.generation)throw new DOMException('启动已取消','AbortError');};
    this.state('loading');
    try {
      active();
      const deviceId=typeof device==='string'?device:device?.id;
      const registry=this.profiles||await loadQemuBrowserProfiles({root:this.root,fetchImpl:this.fetchImpl,signal:bootAbort.signal});
      active();
      let profile=getQemuBrowserProfile(deviceId,registry,{allowCandidateProfiles:this.allowCandidateProfiles});
      check(profile,'该设备尚未取得浏览器运行准入。');
      check(globalThis.crossOriginIsolated&&typeof SharedArrayBuffer!=='undefined','浏览器共享内存尚未启用。请在 HTTPS 下刷新，允许本站 Service Worker；推荐桌面 Chromium。');
      const flash=validateQemuFirmware(firmware,profile),firmwareSHA256=sha256Bytes(flash);
      profile=resolveQemuFirmwareProfile(profile,firmwareSHA256);
      if(clockDivisor!==undefined){
        check(this.allowCandidateProfiles&&[1,8].includes(clockDivisor),'时钟覆盖仅用于明确的候选预览。');
        profile.clockDivisor=clockDivisor;profile.profile=`${deviceId}-wasm-${clockDivisor===1?'wallclock-candidate':'vm-div8'}`;
      }
      this.profile=profile;
      active();this.saved={device:deviceId,firmware:flash.slice(),clockDivisor};
      const manifestUrl=assetUrl('platform/runtime/qemu/runtime.json',this.root);
      const response=await this.fetchImpl(manifestUrl,{signal:bootAbort.signal});
      check(response.ok,'站点未包含 C/QEMU WASM，请先运行 Pages 构建。');const manifest=await response.json();
      check(manifest.schema_version===1&&manifest.engine==='qemu-wasm'&&manifest.source?.commit===QEMU_COMMIT&&(manifest.compiled_profiles||manifest.profiles)?.includes(deviceId),'C/QEMU 来源或执行配置不匹配。');
      const resource=async(row,maxBytes)=>{
        check(row&&/^[a-zA-Z0-9_.-]+$/.test(row.path)&&/^[a-f0-9]{64}$/.test(row.sha256),'C/QEMU 资源清单无效。');
        const result=await this.downloadImpl(new URL(row.path,manifestUrl).href,{signal:bootAbort.signal,expectedSha256:row.sha256,maxBytes,fetchImpl:this.fetchImpl});
        check(result.size===row.bytes,'C/QEMU 资源长度不匹配。');return result.bytes;
      };
      const [javascript,wasm,worker]=await Promise.all([resource(manifest.assets.javascript,2*1048576),resource(manifest.assets.wasm,64*1048576),resource(manifest.assets.worker,1048576)]);
      const roms=await Promise.all(profile.roms.map(async(row)=>{
        const result=await this.downloadImpl(row.url,{signal:bootAbort.signal,expectedSha256:row.sha256,maxBytes:row.bytes,fetchImpl:this.fetchImpl});
        check(result.size===row.bytes,'ROM 长度错误。');return {name:row.name,bytes:result.bytes,sha256:row.sha256};
      }));active();
      this.frameTransport=profile.display===null?null:manifest.frame_transport?.kind==='shared-rgb565-v1'?'shared-rgb565-v1':'qmp-screendump';
      this.receipt={engine:'qemu-wasm',deviceId,board:profile.board,profile:profile.profile,clockDivisor:profile.clockDivisor,
        accelerator:profile.accelerator||null,sourceCommit:QEMU_COMMIT,
        javascriptSha256:manifest.assets.javascript.sha256,workerSha256:manifest.assets.worker.sha256,
        wasmSha256:manifest.assets.wasm.sha256,romSha256:roms[0].sha256,roms:roms.map(({name,sha256})=>({name,sha256})),
        firmwareSha256:firmwareSHA256,firmwareVariant:profile.firmwareVariant||null,build:manifest.build,frameTransport:this.frameTransport,
        outputTransport:profile.outputs?.kind||null,
        controller:'same-origin-iframe-message-channel',persistentFlash:false};
      const iframe=document.createElement('iframe');this.iframe=iframe;
      iframe.title=`Local ${deviceId} QEMU`;iframe.setAttribute('aria-hidden','true');
      iframe.style.cssText='position:fixed;width:1px;height:1px;left:0;bottom:0;opacity:0;pointer-events:none;border:0';
      iframe.src=assetUrl('platform/web/public-qemu-instance.html',this.root);
      const loaded=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('浏览器设备容器加载超时。')),15000);
        const finish=(error)=>{clearTimeout(timer);bootAbort.signal.removeEventListener('abort',cancelLoad);error?reject(error):resolve();};
        const cancelLoad=()=>finish(new DOMException('启动已取消','AbortError'));
        bootAbort.signal.addEventListener('abort',cancelLoad,{once:true});
        iframe.onload=()=>finish();iframe.onerror=()=>finish(new Error('无法加载浏览器设备容器。'));
      });
      document.body.append(iframe);await loaded;active();
      const channel=new MessageChannel();this.port=channel.port1;
      this.port.onmessage=({data})=>this.receive(data,generation);this.port.start();
      const connected=this.waitFor('connected');connected.catch(()=>{});
      iframe.contentWindow.postMessage({type:'m5-qemu-connect'},this.root.origin,[channel.port2]);await connected;active();
      const ready=this.waitFor('ready',90000);ready.catch(()=>{});this.state('booting');
      const [,runtime]=await Promise.all([this.ask('start',{javascript,wasm,worker,javascriptURL:new URL(manifest.assets.javascript.path,manifestUrl).href,profile,frameTransport:this.frameTransport,roms,firmware:flash.buffer},[javascript,wasm,worker,...roms.map(row=>row.bytes),flash.buffer]),ready]);
      active();check(runtime.shared&&runtime.crossOriginIsolated,'QEMU 共享内存不可用。');
      this.receipt.memoryBytes=runtime.memoryBytes;this.receipt.relocatedGlueSha256=runtime.relocatedGlueSha256;
      this.display=this.profile.deviceId === 'cardputer-adv' ? await this.ask('display') : null;
      this.state(!this.guestReady()?'booting':'running');
      this.poll(generation);return this.observe();
    }catch(error){if(generation===this.generation){await this.stop();if(error.name!=='AbortError'){this.state('error');this.onError(error);}}throw error;}
  }
  guestReady() {
    const p=this.profile;
    return !p?.readyMarker||this.receipt?.firmwareSha256!==p.readyFirmwareSHA256||this.serial.slice(this.readySerialOffset||0).includes(p.readyMarker);
  }
  readEngineOwnership() {
    try {
      const ownership=this.iframe?.contentWindow?.m5QemuEngineOwnership;
      return ownership?{...ownership}:null;
    } catch { return null; }
  }
  engineOwnerFailed(ownership) {
    return ownership?.engineOwnerLive===false&&ownership.engineFallbackTerminations>0;
  }
  async poll(generation) {
    if(generation!==this.generation||!this.port||this.stopping)return;
    const begin=performance.now();
    try{
      // This read-only owner status also runs while paused, when no frame
      // request could otherwise reveal a fatally terminated engine.
      if(this.engineOwnerFailed(this.readEngineOwnership()))throw new Error('浏览器 QEMU 执行线程异常停止。');
      if(this.status==='running'&&this.guestReady()){
        if(this.profile.display!==null)await this.ask('frame');
        if(this.profile.outputs&&!this.stopping&&!this.exit)await this.ask('outputs');
        if(this.profile.deviceId==='cardputer-adv'&&performance.now()>=this.displayPollAt) {
          this.displayPollAt=performance.now()+250;
          const display=await this.ask('display');
          if(display.orientation!==this.display?.orientation||display.deviceRotationDeg!==this.display?.deviceRotationDeg) {
            this.display=display;this.onState(this.observe());
          }
        }
      }
    }
    catch(error){if(generation===this.generation&&!this.stopping&&!this.exit){this.state('error');this.onError(error);await this.stop();}return;}
    // One request in flight. Shared snapshots emit only actual display updates.
    if(generation===this.generation)this.frameTimer=setTimeout(()=>this.poll(generation),Math.max(0,(this.profile?.display===null?250:33)-(performance.now()-begin)));
  }
  async pause(){check(this.status==='running','设备未运行。');await this.ask('pause');this.state('paused');return this.observe();}
  async resume(){check(this.status==='paused','设备未暂停。');await this.ask('resume');this.state(this.guestReady()?'running':'booting');return this.observe();}
  reset(){check(['running','paused','sleeping'].includes(this.status),'设备未运行。');return this.input({type:'reset',down:true});}
  async input(event){
    check(this.status==='running'||this.status==='sleeping'&&['button','reset'].includes(event?.type)
      ||this.status==='paused'&&(event?.down===false||event?.type==='reset'),'请先启动或继续设备。');
    qemuInputCommand(this.profile,event); // Validate before crossing the iframe boundary.
    const result=await this.ask('input',event);
    this.inputs.push({at:new Date().toISOString(),...event,result});if(this.inputs.length>200)this.inputs.shift();return {accepted:true,result};
  }
  evidence(){return {schema_version:1,kind:'browser-local-qemu-evidence',session_id:this.sessionId,started_at:this.startedAt,
    stopped_at:this.stoppedAt||null,receipt:this.receipt,serial:this.serial,diagnostics:this.diagnostics,inputs:this.inputs,display:this.display,
    last_frame:this.lastFrame?{width:this.lastFrame.width,height:this.lastFrame.height,sequence:this.lastFrame.sequence,
      format:this.lastFrame.format,source:this.lastFrame.source,source_sequence:this.lastFrame.sourceSequence??null,
      source_updates:this.lastFrame.sourceUpdates??null,sha256:sha256Bytes(this.lastFrame.pixels),pixels:Array.from(this.lastFrame.pixels)}:null,
    last_device_state:this.lastDeviceState?{...this.lastDeviceState,observation_sequence:this.outputSequence}:null,
    cleanup:this.cleanupResult,machine_events:this.machineEvents||[],limits:this.profile?.limitations||[]};}
  stop(){
    if(this.stopping)return this.stopping;
    if(!this.iframe&&!this.abort)return Promise.resolve(this.observe());
    this.stopping=(async()=>{
      clearTimeout(this.frameTimer);this.abort?.abort();this.signalCleanup?.();this.signalCleanup=null;
      let graceful=this.exit?.code===0,disposed=false,disposal=null;
      let engineOwnership=this.readEngineOwnership();
      if(this.port&&!this.engineOwnerFailed(engineOwnership)){
        if(!this.exit&&this.status!=='loading'){
          const exit=this.waitFor('exit',6000).then(value=>value.code===0,()=>false);
          this.ask('quit').catch(()=>{});graceful=await exit;
        }
        engineOwnership=this.readEngineOwnership()||engineOwnership;
        if(!this.engineOwnerFailed(engineOwnership)){
          try{disposal=this.engineDisposal||await this.ask('dispose');disposed=true;}catch{}
        }
      }
      engineOwnership=this.readEngineOwnership()||engineOwnership;
      if(disposal?.enginePlacement==='dedicated-worker-v1'){
        // The notification precedes engine self.close. Only an external Worker
        // close observation proves its actual exit; this avoids pagehide racing
        // the ordinary acknowledgement/notification delivery.
        const deadline=performance.now()+2000;
        while((engineOwnership=this.readEngineOwnership()||engineOwnership)){
          if(engineOwnership.engineCloseNotificationReceived||this.engineOwnerFailed(engineOwnership)||performance.now()>deadline)break;
          await new Promise(resolve=>setTimeout(resolve,10));
        }
      }
      // Preserve failed-dispose/fallback ownership too. This snapshot is taken
      // before DOM removal and never claims the Worker was observed closed.
      engineOwnership=this.readEngineOwnership()||engineOwnership;
      this.generation++;this.port?.close();this.port=null;this.iframe?.remove();this.iframe=null;this.abort=null;
      for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(new DOMException('设备已停止','AbortError'));}this.pending.clear();
      for(const item of this.waiters?.values()||[])item.reject(new DOMException('设备已停止','AbortError'));this.waiters?.clear();
      this.stoppedAt=new Date().toISOString();this.cleanupResult={gracefulExit:graceful,exitCode:this.exit?.code??null,
        workersCreated:this.exit?.workersCreated??null,workersAtExit:this.exit?.workersRemaining??null,
        disposal,engineOwnership,engineOwnershipStage:'before-iframe-removal',explicitWorkerDisposal:disposed,iframeRemoved:true};
      if(this.receipt){const rows=browserQemuHistory(this.storage).filter(row=>row.session_id!==this.sessionId);
        rows.unshift({session_id:this.sessionId,started_at:this.startedAt,stopped_at:this.stoppedAt,receipt:this.receipt,
          serial:this.serial,frame_sha256:this.lastFrame?sha256Bytes(this.lastFrame.pixels):null,last_device_state:this.lastDeviceState,cleanup:this.cleanupResult});
        try{this.storage.setItem(HISTORY_KEY,JSON.stringify(rows.slice(0,5)));}catch{}}
      this.state('stopped');return this.observe();
    })().finally(()=>{this.stopping=null;});return this.stopping;
  }
}
