import { assetUrl, siteRoot } from './public-config.js';
import { downloadFirmware } from './public-firmware.js';
import { sha256Bytes } from './sha256.js';
import { cardputerAdvBoardKey } from './cardputer-adv-keymap.js';

export const ESP32SIM_SOURCE_COMMIT = '25c3948c8311f5afe95d6058add3d2c298e75c4b';
export const ESP32SIM_LEGACY_COMMIT = '3cd3db3b7202e9fc559328c7247c11134c0437f9';
const LEGACY_PROFILES = new Set(['papers3', 'stopwatch']);
const ESP32S3_CHIP_ID = 9;
const ADV_REFERENCE_LIMIT = 'ADV 的 UIFlow2 v2.5.3 在此内核启动后屏幕保持黑色。可载入文档中的兼容 Arduino 示例。';
const PROFILES = {
  cores3: {deviceId:'cores3',board:'m5stack-cores3',chip:'esp32s3',flashMb:16,psramMb:8,jit:true,
    display:{width:320,height:240}, inputs:{touch:true}, execution:'browser-wasm',
    referenceSha256:'1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264',
    limitations:['浏览器内运行，支持屏幕、触摸与电源键；外接 Unit 和联网功能未启用。']},
  'cardputer-adv': {deviceId:'cardputer-adv',board:'m5stack-cardputer-adv',chip:'esp32s3',flashMb:8,psramMb:0,jit:true,
    display:{width:240,height:135}, inputs:{touch:false}, execution:'browser-wasm',
    referenceUrl:'https://m5burner-cdn.m5stack.com/community/1/1897200000000000936/2113079532912463874/bin/2113079532912463875.bin',
    referenceLimit:ADV_REFERENCE_LIMIT,
    referenceSha256:'38b308769e35fe3393bde711e67d27403c32166cf62c10951c19d684fdb38631',
    limitations:['点击模型后使用电脑键盘，方向键通过 Fn 层映射；F12 对应 G0。']},

  papers3: {deviceId:'papers3',board:'papers3',chip:'esp32s3',flashMb:16,psramMb:8,jit:true,
    display:{width:540,height:960}, execution:'browser-wasm',
    limitations:['黑白电子纸与单点触摸子集；灰阶光学、RTC、TF、音频、电源键及网络未验证。']},
  stopwatch: {deviceId:'stopwatch',board:'stopwatch',chip:'esp32s3',flashMb:16,psramMb:8,jit:false,
    display:{width:468,height:466}, execution:'browser-wasm',
    limitations:['使用解释器避开官方 V0.5 IMU 页面的已知 JIT 卡住；速度可能低于实时。','RTC、音频、实体电源与全部固件兼容性未验证。']},
};

export function getBrowserProfile(deviceId) {
  const id = String(deviceId || '').toLowerCase();
  const canonical = ['papers3','m5papers3','paper-s3','m5stack-c139'].includes(id) ? 'papers3' : id;
  return Object.hasOwn(PROFILES, canonical) ? structuredClone(PROFILES[canonical]) : null;
}

export function getBrowserReference(device, profile = getBrowserProfile(device?.id)) {
  const firmware = device?.uiflow2?.firmware;
  if (!profile?.referenceSha256 || firmware?.version !== 'v2.5.3') return null;
  const url = profile.referenceUrl || firmware.download_url;
  return url ? {url, name:`UIFlow2 ${firmware.version}`, sha256:profile.referenceSha256, limit:profile.referenceLimit} : null;
}

export class BrowserRuntimeError extends Error {
  constructor(code, message) { super(message); this.name = 'BrowserRuntimeError'; this.code = code; }
}

function requireValue(condition, code, message) {
  if (!condition) throw new BrowserRuntimeError(code, message);
}

export function validateBrowserFirmware(firmware, profile) {
  const bytes = firmware instanceof ArrayBuffer ? new Uint8Array(firmware) : firmware;
  requireValue(bytes instanceof Uint8Array, 'invalid_firmware', '固件必须是二进制数据。');
  const flashBytes = profile.flashMb * 1024 * 1024, table = 0x8000;
  requireValue(bytes.length <= flashBytes, 'flash_overflow', '固件超过该设备的 Flash 容量。');
  requireValue(bytes.length > table + 32 && bytes[0] === 0xe9 && bytes[table] === 0xaa && bytes[table + 1] === 0x50,
    'merged_firmware_required', '浏览器运行需要从偏移 0 开始、包含引导程序与 0x8000 分区表的完整合并固件。');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const image = (at, end) => {
    requireValue(at + 24 <= end && bytes[at] === 0xe9 && bytes[at + 1] > 0 && bytes[at + 1] <= 16, 'truncated_firmware', '固件镜像头无效或不完整。');
    requireValue(profile.chip === 'esp32s3' && view.getUint16(at + 12, true) === ESP32S3_CHIP_ID, 'firmware_chip_mismatch', '固件芯片与所选 ESP32-S3 设备不匹配。');
    let offset = at + 24;
    for (let i = 0; i < bytes[at + 1]; i++) {
      requireValue(offset + 8 <= end, 'truncated_firmware', '固件段头不完整。');
      offset += 8 + view.getUint32(offset + 4, true);
      requireValue(offset <= end, 'truncated_firmware', '固件数据段不完整。');
    }
  };
  image(0, table);
  const flashSizeCode = bytes[3] >> 4;
  requireValue(flashSizeCode <= 7 && 2 ** flashSizeCode <= profile.flashMb, 'flash_size_mismatch', '引导程序声明的 Flash 容量超过板型容量。');
  const partitions = [];
  let apps = 0;
  for (let at = table; at + 32 <= Math.min(bytes.length, table + 0x1000); at += 32) {
    const magic = view.getUint16(at, true);
    if (magic === 0xffff || magic === 0xebeb) break;
    requireValue(magic === 0x50aa, 'invalid_partition', '固件分区表无效。');
    const offset = view.getUint32(at + 4, true), size = view.getUint32(at + 8, true);
    requireValue(size > 0 && offset >= table + 0x1000 && offset + size <= flashBytes, 'invalid_partition', '固件分区超出所选设备的 Flash 范围。');
    requireValue(!partitions.some(part => offset < part.end && offset + size > part.start), 'invalid_partition', '固件分区重叠。');
    partitions.push({start:offset,end:offset+size});
    if (bytes[at + 2] === 0 && offset < bytes.length && bytes[offset] === 0xe9) { image(offset, Math.min(bytes.length, offset + size)); apps++; }
  }
  requireValue(apps > 0, 'missing_app', '合并固件中没有完整的应用分区。');
  return true;
}

export function decodeBrowserFrame(buffer, sequence) {
  const bytes = new Uint8Array(buffer);
  requireValue(bytes.length >= 5 && bytes[0] === 1, 'invalid_frame', '运行时返回了无效显示帧。');
  const width = bytes[1] | bytes[2] << 8, height = bytes[3] | bytes[4] << 8;
  requireValue(width > 0 && height > 0 && width * height <= 2048 * 2048 && bytes.length === 5 + width * height * 2,
    'invalid_frame', '运行时显示帧尺寸或长度无效。');
  // Native board-controller output, RGB565 little endian; no guest framebuffer
  // scanning, screenshot substitute, or host-side application rendering.
  return {width, height, pixels:bytes.slice(5), sequence, format:'rgb565le', source:'emulator'};
}

export class PublicBrowserRuntime {
  constructor({onSerial = () => {}, onFrame = () => {}, onState = () => {}, onError = () => {},
    root = siteRoot(), fetchImpl = globalThis.fetch,
    workerFactory = url => new Worker(url, {type:'module'}), requestTimeout = 30000, downloadImpl = downloadFirmware} = {}) {
    Object.assign(this, {onSerial,onFrame,onState,onError,root:new URL(root),fetchImpl,workerFactory,requestTimeout,downloadImpl});
    this.fetchImpl = (...args) => fetchImpl(...args);
    this.status = 'stopped'; this.worker = null; this.pending = new Map();
    this.generation = 0; this.sequence = 0; this.inputSequence = 0; this.profile = null;
    this.stats = {};
  }

  observe() { return {status:this.status,deviceId:this.profile?.deviceId || null,sequence:this.sequence,execution:'browser-wasm',runtime:this.receipt || null,display:this.display,stats:{...this.stats},persistentStorage:false}; }
  state(status) { this.status = status; this.onState(this.observe()); }
  rejectPending(error) { for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(error); } this.pending.clear(); }
  fail(error) {
    if (this.status === 'error' && this.worker === null) return;
    this.worker?.terminate(); this.worker = null;
    this.audioPlayer?.close(); this.audioPlayer = null; this.rejectPending(error); this.state('error'); this.onError(error);
  }

  ask(key, message, transfer = []) {
    requireValue(this.worker, 'not_running', '浏览器运行时尚未启动。');
    requireValue(!this.pending.has(key), 'runtime_busy', '上一条运行时命令尚未完成。');
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(key); reject(new BrowserRuntimeError('runtime_timeout', '浏览器运行时响应超时。')); }, this.requestTimeout);
      this.pending.set(key, {resolve,reject,timer});
      try { this.worker.postMessage(message, transfer); }
      catch (error) { clearTimeout(timer); this.pending.delete(key); reject(error); }
    });
  }

  receive(message) {
    try {
      if (message.text !== undefined) {
        let data;
        try { data = JSON.parse(message.text); } catch { this.onSerial(String(message.text)); }
        if (data?.t === 'serial') this.onSerial(data.data || '');
        else if (data?.t === 'emu') this.onSerial(`[emulator] ${data.msg}\n`);
        else if (data?.t === 'stat') {
          this.stats = {...this.stats,...data};
          const rotation = data.display_rotation;
          const portrait = this.profile.deviceId === 'cardputer-adv' && (rotation === -90 || rotation === 90);
          this.display = {orientation:portrait ? 'portrait' : 'landscape',deviceRotationDeg:portrait ? rotation : 0};
          this.onState(this.observe());
        }
      }
      if (message.log !== undefined) this.onSerial(`[emulator] ${message.log}\n`);
      if (message.bin !== undefined) {
        try {
          if (new Uint8Array(message.bin)[0] === 1) {
            const frame = decodeBrowserFrame(message.bin, ++this.sequence);
            requireValue(frame.width === this.profile.display.width && frame.height === this.profile.display.height, 'frame_profile_mismatch', '显示帧与所选浏览器板型不匹配。');
            this.lastFrame = frame;
            this.onFrame(frame);
          } else if (new Uint8Array(message.bin)[0] === 2) {
            this.audioPlayer?.push(message.bin);
          }
        }
        finally { if (message.ack) this.worker?.postMessage({op:'frame-ack'}); }
      }
      if (message.pace) { this.stats = {...this.stats,...message.pace}; this.onState(this.observe()); }
      const key = message.ready !== undefined ? 'ready' : message.created !== undefined ? 'created'
        : message.loaded !== undefined ? `load:${message.loaded}` : message.started !== undefined ? 'started'
        : message.resumed !== undefined ? 'resumed' : message.stopped !== undefined ? 'stopped'
        : message.inputQueued !== undefined ? `input:${message.inputQueued}` : null;
      if (key && this.pending.has(key)) {
        const item = this.pending.get(key); this.pending.delete(key); clearTimeout(item.timer); item.resolve(message);
      }
      if (message.stopped && message.stopped !== 0) throw new BrowserRuntimeError('guest_stopped', `客体执行停止（${message.stopped}），请查看串口输出。`);
    } catch (error) { this.fail(error); }
  }

  async start({device, firmware, signal, audio} = {}) {
    this.stop();
    const generation = this.generation;
    const profile = getBrowserProfile(typeof device === 'string' ? device : device?.id);
    requireValue(profile, 'browser_board_unsupported', '该设备尚未接入浏览器内核，请连接 Device Service。');
    validateBrowserFirmware(firmware, profile);
    this.profile = profile; this.sequence = 0; this.receipt = null; this.stats = {};
    this.display = null; this.lastFrame = null;
    this.advKeys = new Map(); this.advFnKeys = new Set();
    this.saved = {device:profile.deviceId,firmware:firmware.slice(0)};
    this.controller = new AbortController();
    const cancel = () => this.stop();
    signal?.addEventListener('abort', cancel, {once:true});
    this.signalCleanup = () => signal?.removeEventListener('abort', cancel);
    const active = () => {
      if (signal?.aborted || generation !== this.generation) throw new DOMException('浏览器启动已取消。', 'AbortError');
    };
    this.state('loading');
    try {
      active();
      this.audioPlayer = audio?.player;
      const legacy = LEGACY_PROFILES.has(profile.deviceId);
      const runtimeName = legacy ? 'esp32sim-legacy' : 'esp32sim';
      const sourceCommit = legacy ? ESP32SIM_LEGACY_COMMIT : ESP32SIM_SOURCE_COMMIT;
      const manifestUrl = assetUrl(`platform/runtime/${runtimeName}/runtime.json`, this.root);
      const response = await this.fetchImpl(manifestUrl, {signal:this.controller.signal,credentials:'omit',referrerPolicy:'no-referrer'});
      requireValue(response.ok, 'browser_runtime_missing', '浏览器内核尚未准备；请先构建带 runtime 的站点。');
      const manifest = await response.json();
      requireValue(manifest.schema_version === 1 && manifest.source?.commit === sourceCommit && manifest.profiles?.includes(profile.board), 'browser_runtime_mismatch', '浏览器内核来源或设备配置不匹配。');
      const resource = async (entry, maxBytes) => {
        requireValue(entry && /^[a-f0-9]{64}$/.test(entry.sha256) && typeof entry.path === 'string' && /^[a-zA-Z0-9_.-]+$/.test(entry.path), 'invalid_runtime_manifest', '浏览器内核资源清单无效。');
        return this.downloadImpl(new URL(entry.path, manifestUrl).href, {signal:this.controller.signal,expectedSha256:entry.sha256,maxBytes,fetchImpl:this.fetchImpl});
      };
      const wasm = await resource(manifest.wasm, 16 * 1024 * 1024); active();
      const rom = await resource(manifest.rom, 2 * 1024 * 1024); active();
      requireValue(rom.sha256 === 'c0ce0f338d1de1bdc6efbef1591779a2a42c1ab7d759d3c6ae8ae63a7dd34cfd', 'rom_mismatch', 'ESP32-S3 ROM 与已审阅版本不匹配。');
      const input = new Uint8Array(firmware);
      const flash = new Uint8Array(profile.flashMb * 1024 * 1024);
      flash.fill(0xff);
      flash.set(input);
      const firmwareInputSha256 = sha256Bytes(input), firmwareRuntimeSha256 = sha256Bytes(flash);
      this.receipt = {sourceCommit:manifest.source.commit,wasmSha256:wasm.sha256,romSha256:rom.sha256,
        firmwareSha256:firmwareRuntimeSha256,firmwareInputSha256,firmwareRuntimeSha256,
        normalization:{kind:input.length === flash.length ? 'exact' : 'pad-ff',inputBytes:input.length,runtimeBytes:flash.length},
        jit:profile.jit,build:manifest.build,profile:profile.board};
      const worker = this.workerFactory(assetUrl(`platform/web/vendor/esp32sim/${legacy ? 'legacy/' : ''}worker.js`, this.root));
      this.worker = worker;
      worker.onmessage = event => { if (generation === this.generation && this.worker === worker) this.receive(event.data); };
      worker.onerror = () => { if (generation === this.generation && this.worker === worker) this.fail(new BrowserRuntimeError('browser_worker_error', '浏览器执行线程出错，请查看串口或重新启动。')); };
      await this.ask('ready', {op:'init',wasm:wasm.bytes,frameAck:true}, [wasm.bytes]); active();
      requireValue((await this.ask('created', {op:'create',board:profile.board,flash_mb:profile.flashMb,psram_mb:profile.psramMb,jit:profile.jit})).created, 'browser_create_failed', '无法创建所选浏览器板模型。');
      requireValue((await this.ask('load:5', {op:'load',kind:5,data:flash.buffer}, [flash.buffer])).ok, 'firmware_load_failed', '浏览器内核拒绝该固件。'); active();
      requireValue((await this.ask('load:0', {op:'load',kind:0,data:rom.bytes}, [rom.bytes])).ok, 'rom_load_failed', '浏览器内核拒绝该 ROM。'); active();
      requireValue((await this.ask('started', {op:'start',appDirect:false})).started, 'browser_boot_failed', '客体启动失败，请查看串口。'); active();
      this.state('running');
      return this.observe();
    } catch (error) {
      if (generation === this.generation) {
        if (error.name === 'AbortError') this.stop();
        else { this.signalCleanup?.(); this.controller?.abort(); this.fail(error); }
      }
      throw error;
    }
  }

  async pause() {
    requireValue(this.status === 'running', 'not_running', '请先启动浏览器固件。');
    await this.ask('stopped', {op:'stop'}); this.audioPlayer?.setActive(false); this.state('paused'); return this.observe();
  }
  async resume() {
    requireValue(this.status === 'paused', 'not_paused', '浏览器固件没有暂停。');
    requireValue((await this.ask('resumed', {op:'resume'})).resumed, 'resume_failed', '无法继续客体执行。');
    this.audioPlayer?.setActive(true);
    this.state('running'); return this.observe();
  }
  reset() {
    requireValue(this.saved, 'not_running', '没有可以重启的固件。');
    const player = this.audioPlayer;
    this.audioPlayer = null;
    player?.setActive(false);
    return this.start({...this.saved,audio:{player}}).finally(() => {
      if (this.audioPlayer === player) player?.setActive(true);
    });
  }
  stop() {
    this.generation++; this.controller?.abort(); this.signalCleanup?.(); this.signalCleanup = null;
    this.worker?.terminate(); this.worker = null;
    this.audioPlayer?.close(); this.audioPlayer = null;
    this.rejectPending(new DOMException('浏览器会话已停止。', 'AbortError'));
    this.state('stopped'); return this.observe();
  }
  async input(event) {
    if (event?.type === 'reset') return this.reset();
    const release = (event?.type === 'touch' && event.down === false) || (event?.type === 'button' && (event.down ?? event.pressed) === false);
    requireValue(this.worker && (this.status === 'running' || this.status === 'paused' && release), 'not_running', '请先启动或继续浏览器固件。');
    let message;
    if (event?.type === 'touch') {
      requireValue(this.profile.inputs?.touch !== false, 'unsupported_control', '该设备没有触摸屏。');
      const {width,height} = this.profile.display;
      requireValue(Number.isInteger(event.x) && Number.isInteger(event.y) && event.x >= 0 && event.y >= 0 && event.x < width && event.y < height && typeof event.down === 'boolean', 'invalid_input', '触摸坐标必须位于设备原生屏幕内。');
      message = {t:'touch',x:event.x,y:event.y,down:event.down ? 1 : 0};
    } else if (event?.type === 'button') {
      const pins = {'button-a':2,'btnA':2,'a':2,'button-b':1,'btnB':1,'b':1};
      const down = event.down ?? event.pressed;
      requireValue(typeof down === 'boolean', 'invalid_input', '按键需要明确的按下或释放状态。');
      if (this.profile.deviceId === 'cores3' && ['power','p'].includes(event.id)) {
        if (!down) return {accepted:true,delivery:'timed'};
        message = {t:'power-key'};
      } else if (this.profile.deviceId === 'cardputer-adv') {
        if (['boot','g0'].includes(event.id)) message = {t:'btn',pin:0,v:down ? 1 : 0};
        else {
          const key = cardputerAdvBoardKey(event.id);
          requireValue(key, 'unsupported_control', '该浏览器板型不支持此按键。');
          const fnWasDown = this.advKeys.has('fn') || this.advFnKeys.size > 0;
          if (key.fn) {
            if (down) this.advFnKeys.add(event.id);
            else this.advFnKeys.delete(event.id);
          }
          const owners = this.advKeys.get(key.name) || new Set();
          const wasDown = owners.size > 0;
          if (down) owners.add(event.id);
          else owners.delete(event.id);
          if (owners.size) this.advKeys.set(key.name, owners);
          else this.advKeys.delete(key.name);
          const fnDown = this.advKeys.has('fn') || this.advFnKeys.size > 0;
          const queued = [];
          if (fnWasDown !== fnDown && fnDown) queued.push(this.queueInput({t:'matrix-key',key:'fn',down:1}));
          if (key.name !== 'fn' && wasDown !== !!owners.size)
            queued.push(this.queueInput({t:'matrix-key',key:key.name,down:down ? 1 : 0}));
          if (fnWasDown !== fnDown && !fnDown) queued.push(this.queueInput({t:'matrix-key',key:'fn',down:0}));
          await Promise.all(queued);
          return {accepted:true,delivery:'queued'};
        }
      } else {
        requireValue(this.profile.deviceId === 'stopwatch' && Object.hasOwn(pins,event.id), 'unsupported_control', '该浏览器板型不支持此按键。');
        message = {t:'btn',pin:pins[event.id],v:down ? 1 : 0};
      }
    } else if (event?.type === 'uart') {
      requireValue(typeof event.text === 'string' && new TextEncoder().encode(event.text).length <= 128, 'invalid_input', '串口输入每次最多 128 字节。');
      message = {t:'key',src:event.channel === 'usb' ? 'usb' : 'uart0',data:event.text};
    } else throw new BrowserRuntimeError('unsupported_control', '浏览器板型尚不支持此输入。');
    return this.queueInput(message);
  }
  async queueInput(message) {
    const inputId = ++this.inputSequence;
    const receipt = await this.ask(`input:${inputId}`, {op:'text',inputId,data:JSON.stringify(message)});
    return {accepted:true,delivery:'queued',guestTime:receipt.time};
  }
}
