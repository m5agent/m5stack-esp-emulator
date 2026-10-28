import {assetUrl, siteRoot} from './public-config.js';
import {downloadFirmware} from './public-firmware.js';
import {sha256Bytes} from './sha256.js';
import {validateBrowserFirmware} from './public-browser-runtime.js';

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
  constructor({onSerial=()=>{},onFrame=()=>{},onState=()=>{},onError=()=>{},root=siteRoot(),fetchImpl=globalThis.fetch,
    requestTimeout=20000,storage,downloadImpl=downloadFirmware}={}) {
    try { storage ||= globalThis.localStorage; } catch { storage = null; }
    Object.assign(this,{onSerial,onFrame,onState,onError,root:new URL(root),fetchImpl,requestTimeout,storage,downloadImpl});
    this.fetchImpl=(...args)=>fetchImpl(...args);
    this.status='stopped';this.generation=0;this.pending=new Map();this.id=0;this.sequence=0;
  }
  observe() { return {status:this.status,deviceId:'cores3',sequence:this.sequence,execution:'browser-qemu-wasm',
    runtime:this.receipt||null,sessionId:this.sessionId,persistentStorage:false,cleanup:this.cleanupResult||null}; }
  state(status) { this.status=status;this.onState(this.observe()); }
  ask(op,value={},transfer=[]) {
    check(this.port,'浏览器设备尚未连接。');const id=++this.id;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`浏览器命令 ${op} 超时。`));},this.requestTimeout);
      this.pending.set(id,{resolve,reject,timer});
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
      this.pending.delete(data.id);clearTimeout(item.timer);data.error?item.reject(new Error(data.error)):item.resolve(data.value);return;
    }
    this.waiters.get(data.type)?.resolve(data.value);this.waiters.delete(data.type);
    if(data.type==='serial') {
      this.serial=(this.serial+data.value).slice(-65536);this.onSerial(data.value);
      if(this.status==='booting'&&this.receipt?.firmwareSha256===EXAMPLE_SHA&&this.serial.includes('"kind": "ready"'))this.state('running');
    }
    if(data.type==='diagnostic') { this.diagnostics=(this.diagnostics+data.value+'\n').slice(-32768); }
    if(data.type==='frame') {
      this.lastFrame={...data.value,sequence:++this.sequence};this.onFrame(this.lastFrame);
    }
    if(data.type==='exit') { this.exit=data.value; if(!this.stopping){this.state('stopped');void this.stop();} }
    if(data.type==='error') {
      const error=new Error(data.value);this.state('error');this.onError(error);
      for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(error);}this.pending.clear();
      for(const waiter of this.waiters.values())waiter.reject(error);this.waiters.clear();
      void this.stop();
    }
  }
  async start({device,firmware,signal}={}) {
    await this.stop();
    check((typeof device==='string'?device:device?.id)==='cores3','该 C/QEMU 浏览器配置只准入 CoreS3。');
    check(globalThis.crossOriginIsolated&&typeof SharedArrayBuffer!=='undefined','浏览器共享内存尚未启用。请在 HTTPS 下刷新，允许本站 Service Worker；推荐桌面 Chromium。');
    const input=firmware instanceof ArrayBuffer?new Uint8Array(firmware):firmware;
    validateBrowserFirmware(input,QEMU_BROWSER_PROFILE);
    check(input instanceof Uint8Array&&input.length<=16777216&&input.length>0x10000&&input[0]===0xe9&&input[0x8000]===0xaa&&input[0x8001]===0x50,'需要从偏移 0 开始的 CoreS3 ESP32-S3 完整合并固件。');
    const view=new DataView(input.buffer,input.byteOffset,input.byteLength);
    check(view.getUint16(12,true)===9,'固件芯片必须为 ESP32-S3。');
    const flash=new Uint8Array(16777216);flash.fill(255);flash.set(input);
    const generation=++this.generation;this.waiters=new Map();this.serial='';this.diagnostics='';this.sequence=0;
    this.inputs=[];this.lastFrame=null;this.exit=null;this.cleanupResult=null;
    this.receipt=null;this.stoppedAt=null;
    this.sessionId=crypto.randomUUID();this.startedAt=new Date().toISOString();this.saved={device:'cores3',firmware:flash.slice()};
    this.abort=new AbortController();
    const cancel=()=>{this.abort.abort();void this.stop();};signal?.addEventListener('abort',cancel,{once:true});
    this.signalCleanup=()=>signal?.removeEventListener('abort',cancel);
    const active=()=>{if(signal?.aborted||generation!==this.generation)throw new DOMException('启动已取消','AbortError');};
    this.state('loading');
    try {
      active();const manifestUrl=assetUrl('platform/runtime/qemu/runtime.json',this.root);
      const response=await this.fetchImpl(manifestUrl,{signal:this.abort.signal});
      check(response.ok,'站点未包含 C/QEMU WASM，请先运行 Pages 构建。');const manifest=await response.json();
      check(manifest.schema_version===1&&manifest.engine==='qemu-wasm'&&manifest.source?.commit===QEMU_COMMIT&&manifest.profiles?.includes('cores3')&&manifest.execution_profile?.id==='cores3-wasm-vm-div8','C/QEMU 来源或执行配置不匹配。');
      const resource=async(row,maxBytes)=>{
        check(row&&/^[a-zA-Z0-9_.-]+$/.test(row.path)&&/^[a-f0-9]{64}$/.test(row.sha256),'C/QEMU 资源清单无效。');
        const result=await this.downloadImpl(new URL(row.path,manifestUrl).href,{signal:this.abort.signal,expectedSha256:row.sha256,maxBytes,fetchImpl:this.fetchImpl});
        check(result.size===row.bytes,'C/QEMU 资源长度不匹配。');return result.bytes;
      };
      const [javascript,wasm,worker]=await Promise.all([resource(manifest.assets.javascript,2*1048576),resource(manifest.assets.wasm,64*1048576),resource(manifest.assets.worker,1048576)]);
      active();check(manifest.required_rom.sha256===ROM_SHA,'ROM pin 与已验证版本不一致。');
      const rom=await this.downloadImpl(manifest.required_rom.url,{signal:this.abort.signal,expectedSha256:ROM_SHA,maxBytes:393216,fetchImpl:this.fetchImpl});active();
      check(rom.size===393216,'ROM 长度错误。');
      this.receipt={engine:'qemu-wasm',profile:QEMU_BROWSER_PROFILE.profile,clockDivisor:8,sourceCommit:QEMU_COMMIT,
        javascriptSha256:manifest.assets.javascript.sha256,workerSha256:manifest.assets.worker.sha256,
        wasmSha256:manifest.assets.wasm.sha256,romSha256:ROM_SHA,firmwareSha256:sha256Bytes(flash),build:manifest.build,
        controller:'same-origin-iframe-message-channel',persistentFlash:false};
      const iframe=document.createElement('iframe');this.iframe=iframe;
      iframe.title='Local CoreS3 QEMU';iframe.setAttribute('aria-hidden','true');
      iframe.style.cssText='position:fixed;width:1px;height:1px;left:0;bottom:0;opacity:0;pointer-events:none;border:0';
      iframe.src=assetUrl('platform/web/public-qemu-instance.html',this.root);
      const loaded=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('浏览器设备容器加载超时。')),15000);
        const finish=(error)=>{clearTimeout(timer);this.abort?.signal.removeEventListener('abort',cancelLoad);error?reject(error):resolve();};
        const cancelLoad=()=>finish(new DOMException('启动已取消','AbortError'));
        this.abort.signal.addEventListener('abort',cancelLoad,{once:true});
        iframe.onload=()=>finish();iframe.onerror=()=>finish(new Error('无法加载浏览器设备容器。'));
      });
      document.body.append(iframe);await loaded;active();
      const channel=new MessageChannel();this.port=channel.port1;
      this.port.onmessage=({data})=>this.receive(data,generation);this.port.start();
      const connected=this.waitFor('connected');connected.catch(()=>{});
      iframe.contentWindow.postMessage({type:'m5-qemu-connect'},this.root.origin,[channel.port2]);await connected;active();
      const ready=this.waitFor('ready',90000);ready.catch(()=>{});this.state('booting');
      const [,runtime]=await Promise.all([this.ask('start',{javascript,wasm,worker,javascriptURL:new URL(manifest.assets.javascript.path,manifestUrl).href,rom:rom.bytes,firmware:flash.buffer},[javascript,wasm,worker,rom.bytes,flash.buffer]),ready]);
      active();check(runtime.shared&&runtime.crossOriginIsolated,'QEMU 共享内存不可用。');
      this.receipt.memoryBytes=runtime.memoryBytes;this.receipt.relocatedGlueSha256=runtime.relocatedGlueSha256;
      this.state(this.receipt.firmwareSha256===EXAMPLE_SHA&&!this.serial.includes('"kind": "ready"')?'booting':'running');
      this.poll(generation);return this.observe();
    }catch(error){if(generation===this.generation){await this.stop();if(error.name!=='AbortError'){this.state('error');this.onError(error);}}throw error;}
  }
  async poll(generation) {
    if(generation!==this.generation||!this.port)return;
    // The fixed example has an authoritative guest readiness marker. Avoid a
    // startup display coroutine racing its ROM/Flash initialization.
    const example=this.receipt?.firmwareSha256===EXAMPLE_SHA;
    const ready=!example||this.serial.includes('"kind": "ready"');
    try{if(this.status==='running'&&ready)await this.ask('frame');}
    catch(error){if(generation===this.generation){this.state('error');this.onError(error);await this.stop();}return;}
    if(generation===this.generation)this.frameTimer=setTimeout(()=>this.poll(generation),750);
  }
  async pause(){check(this.status==='running','设备未运行。');await this.ask('pause');this.state('paused');return this.observe();}
  async resume(){check(this.status==='paused','设备未暂停。');await this.ask('resume');this.state('running');return this.observe();}
  reset(){check(this.saved,'没有可重启的固件。');return this.start(this.saved);}
  async input(event){
    check(this.status==='running'||this.status==='paused'&&event?.down===false,'请先启动或继续设备。');
    let result;
    if(event?.type==='touch'){
      check(Number.isInteger(event.x)&&event.x>=0&&event.x<320&&Number.isInteger(event.y)&&event.y>=0&&event.y<240&&typeof event.down==='boolean','触摸坐标越界。');
      result=await this.ask('touch',event);
    }else if(event?.type==='pir'){
      check(typeof event.motion==='boolean','PIR 状态必须为布尔值。');result=await this.ask('pir',event);
    }else if(event?.type==='uart'){
      check(typeof event.text==='string'&&new TextEncoder().encode(event.text).length<=128,'每次串口最多 128 字节。');result=await this.ask('uart',event);
    }else throw new Error('该浏览器配置未验证此输入。');
    this.inputs.push({at:new Date().toISOString(),...event,result});if(this.inputs.length>200)this.inputs.shift();return {accepted:true,result};
  }
  evidence(){return {schema_version:1,kind:'browser-local-qemu-evidence',session_id:this.sessionId,started_at:this.startedAt,
    stopped_at:this.stoppedAt||null,receipt:this.receipt,serial:this.serial,diagnostics:this.diagnostics,inputs:this.inputs,
    last_frame:this.lastFrame?{width:this.lastFrame.width,height:this.lastFrame.height,sequence:this.lastFrame.sequence,
      format:this.lastFrame.format,sha256:sha256Bytes(this.lastFrame.pixels),pixels:Array.from(this.lastFrame.pixels)}:null,
    cleanup:this.cleanupResult,limits:QEMU_BROWSER_PROFILE.limitations};}
  stop(){
    if(this.stopping)return this.stopping;
    if(!this.iframe&&!this.abort)return Promise.resolve(this.observe());
    this.stopping=(async()=>{
      clearTimeout(this.frameTimer);this.abort?.abort();this.signalCleanup?.();this.signalCleanup=null;
      let graceful=this.exit?.code===0,disposed=false,disposal=null;
      if(this.port){
        if(!this.exit&&this.status!=='loading'){
          const exit=this.waitFor('exit',6000).then(value=>value.code===0,()=>false);
          this.ask('quit').catch(()=>{});graceful=await exit;
        }
        try{disposal=await this.ask('dispose');disposed=true;}catch{}
      }
      this.generation++;this.port?.close();this.port=null;this.iframe?.remove();this.iframe=null;this.abort=null;
      for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(new DOMException('设备已停止','AbortError'));}this.pending.clear();
      for(const item of this.waiters?.values()||[])item.reject(new DOMException('设备已停止','AbortError'));this.waiters?.clear();
      this.stoppedAt=new Date().toISOString();this.cleanupResult={gracefulExit:graceful,exitCode:this.exit?.code??null,
        workersCreated:this.exit?.workersCreated??null,workersAtExit:this.exit?.workersRemaining??null,
        disposal,explicitWorkerDisposal:disposed,iframeRemoved:true};
      if(this.receipt){const rows=browserQemuHistory(this.storage).filter(row=>row.session_id!==this.sessionId);
        rows.unshift({session_id:this.sessionId,started_at:this.startedAt,stopped_at:this.stoppedAt,receipt:this.receipt,
          serial:this.serial,frame_sha256:this.lastFrame?sha256Bytes(this.lastFrame.pixels):null,cleanup:this.cleanupResult});
        try{this.storage.setItem(HISTORY_KEY,JSON.stringify(rows.slice(0,5)));}catch{}}
      this.state('stopped');return this.observe();
    })().finally(()=>{this.stopping=null;});return this.stopping;
  }
}
