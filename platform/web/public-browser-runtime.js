import { assetUrl, siteRoot } from './public-config.js';
import { downloadFirmware } from './public-firmware.js';
import { sha256Bytes } from './sha256.js';
import { cardputerAdvBoardKey } from './cardputer-adv-keymap.js';
import { readTab5Sidecar } from './public-tab5-sidecar.js';
import admittedBoards from './esp32sim-browser-boards.json' with {type:'json'};

export const ESP32SIM_SOURCE_COMMIT = 'd2f4af9ede499fbfb0f56ed3b425c09d451709c5';
export const ESP32SIM_LEGACY_COMMIT = '3cd3db3b7202e9fc559328c7247c11134c0437f9';
const CURRENT_PROFILES = new Map(admittedBoards.map(profile => [profile.deviceId,profile]));
const CHIP_LAYOUT = {
  esp32: {id:0,bootloader:0x1000,rom:'esp32_rev300_rom.elf',sha256:'920b70635440517866aab2230964a570d2cf2b676658d93c52fbac108c1cca31'},
  esp32s3: {id:9,bootloader:0,rom:'esp32s3_rev0_rom.elf',sha256:'c0ce0f338d1de1bdc6efbef1591779a2a42c1ab7d759d3c6ae8ae63a7dd34cfd'},
  esp32c6: {id:13,bootloader:0,rom:'esp32c6_rev0_rom.elf',sha256:'788e1d38724aeb8fd974fa10c4a7b089c02627d35342ce84b9e0b12b239f3551'},
  esp32p4: {id:18,bootloader:0x2000,rom:'esp32p4_rev0_rom.elf',sha256:'948f2c7d108d04a9c3a982f9c1c498fb17f2c4a68abc51f87782592034d7ce44'},
  'esp32p4-rev3': {id:18,bootloader:0x2000,rom:'esp32p4_rev300_rom.elf',sha256:'90e723f71fe4701adee7e40bfab6971d8ecf5e356f4d5a81e77743248abc3a97'},
};
const ADV_REFERENCE_LIMIT = 'ADV 的 UIFlow2 v2.5.3 支持离线首页。浏览器运行尚未开放联网与云端绑定。';
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
    probeSha256:'9ca3d53adf8bc81013a1062461961c27ae0450c1ee5e5b1ece6c21753818623b',
    limitations:['点击模型后使用电脑键盘，方向键通过 Fn 层映射；F12 对应 G0。']},
  cardputer: {deviceId:'cardputer',board:'m5stack-cardputer',chip:'esp32s3',flashMb:8,psramMb:0,jit:true,
    display:{width:240,height:135}, inputs:{touch:false}, execution:'browser-wasm', preferQemu:true,
    referenceVersion:'v2.5.4', referenceSha256:'d9e1287eccb641863e7b1cc7cf057733592403d65aeec2d4b1fa4cb3e8b1b309',
    probeSha256:'2a086148973b22f6c7f289536c977e1e7968e17f7f02717c552088269ed3ac55',
    limitations:['支持 GPIO0 和物理键盘矩阵。']},

  papers3: {deviceId:'papers3',board:'papers3',chip:'esp32s3',flashMb:16,psramMb:8,jit:true,legacy:true,
    display:{width:540,height:960}, execution:'browser-wasm',
    limitations:['黑白电子纸与单点触摸子集；灰阶光学、RTC、TF、音频、电源键及网络未验证。']},
  stopwatch: {deviceId:'stopwatch',board:'stopwatch',chip:'esp32s3',flashMb:16,psramMb:8,jit:false,legacy:true,
    display:{width:468,height:466}, execution:'browser-wasm',
    limitations:['使用解释器避开官方 V0.5 IMU 页面的已知 JIT 卡住；速度可能低于实时。','RTC、音频、实体电源与全部固件兼容性未验证。']},
};

export function getBrowserProfile(deviceId, availableProfiles) {
  const id = String(deviceId || '').toLowerCase();
  const canonical = ['papers3','m5papers3','paper-s3','m5stack-c139'].includes(id) ? 'papers3' : id;
  const current = CURRENT_PROFILES.get(canonical);
  if (current && (!availableProfiles || availableProfiles.includes(current.board))) return structuredClone(current);
  const previous = Object.hasOwn(PROFILES, canonical) && PROFILES[canonical];
  return previous && (!availableProfiles || availableProfiles.includes(previous.board)) ? structuredClone(previous) : null;
}

export function getBrowserReference(device, profile = getBrowserProfile(device?.id)) {
  const firmware = device?.uiflow2?.firmware;
  if (!profile?.referenceSha256 || firmware?.version !== (profile.referenceVersion || 'v2.5.3')) return null;
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
  requireValue(Object.hasOwn(CHIP_LAYOUT,profile.chip), 'firmware_chip_mismatch', '所选芯片尚未配置浏览器 Flash 布局。');
  const layout = CHIP_LAYOUT[profile.chip];
  const bootloader = layout.bootloader;
  requireValue(bytes.length <= flashBytes, 'flash_overflow', '固件超过该设备的 Flash 容量。');
  requireValue(bytes.length > table + 32 && bytes[bootloader] === 0xe9 && bytes[table] === 0xaa && bytes[table + 1] === 0x50,
    'merged_firmware_required', `浏览器运行需要完整合并固件，引导程序须位于 0x${bootloader.toString(16)}，分区表须位于 0x8000。`);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const image = (at, end) => {
    requireValue(at + 24 <= end && bytes[at] === 0xe9 && bytes[at + 1] > 0 && bytes[at + 1] <= 16, 'truncated_firmware', '固件镜像头无效或不完整。');
    requireValue(view.getUint16(at + 12, true) === layout.id, 'firmware_chip_mismatch', '固件芯片与所选设备不匹配。');
    let offset = at + 24;
    for (let i = 0; i < bytes[at + 1]; i++) {
      requireValue(offset + 8 <= end, 'truncated_firmware', '固件段头不完整。');
      offset += 8 + view.getUint32(offset + 4, true);
      requireValue(offset <= end, 'truncated_firmware', '固件数据段不完整。');
    }
  };
  image(bootloader, table);
  const flashSizeCode = bytes[bootloader + 3] >> 4;
  // The pinned Tab5 stock image declares 32 MiB; real Tab5 has 16 MiB and
  // this image's partitions fit the native capacity.
  const stockTab5 = profile.deviceId === 'tab5' && flashSizeCode === 4 && sha256Bytes(bytes) === profile.referenceSha256;
  requireValue(flashSizeCode <= 7 && (stockTab5 || 2 ** flashSizeCode <= profile.flashMb), 'flash_size_mismatch', '引导程序声明的 Flash 容量超过板型容量。');
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
  constructor({onSerial = () => {}, onFrame = () => {}, onCamera = () => {}, onLeds = () => {}, onServo = () => {}, onState = () => {}, onError = () => {}, availableProfiles,
    root = siteRoot(), fetchImpl = globalThis.fetch,
    workerFactory = url => new Worker(url, {type:'module'}), requestTimeout = 30000, downloadImpl = downloadFirmware} = {}) {
    Object.assign(this, {onSerial,onFrame,onCamera,onLeds,onServo,onState,onError,availableProfiles,root:new URL(root),fetchImpl,workerFactory,requestTimeout,downloadImpl});
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
        else if (data?.t === 'mic-input') {
          const pending = this.pending.get('mic-input');
          if (pending) {
            this.pending.delete('mic-input');
            clearTimeout(pending.timer);
            pending.resolve(data);
          }
        }
        else if (data?.t === 'ring' && this.profile.ledTargets) {
          const targets = this.profile.ledTargets;
          requireValue(Array.isArray(data.leds) && data.leds.length === targets.length
            && data.leds.every(rgb => Array.isArray(rgb) && rgb.length === 3
              && rgb.every(value => Number.isInteger(value) && value >= 0 && value <= 255)),
            'invalid_led', '运行时返回了无效的 RGB LED 状态。');
          targets.forEach((target,index) => {
            if (!target) return;
            const [red,green,blue] = data.leds[index];
            const color = (red << 16) | (green << 8) | blue;
            this.onLeds({type:'led',target,color,brightness:1,on:color !== 0});
          });
        }
        else if (data?.t === 'servo' && this.profile.deviceId === 'stackchan') {
          const {yaw,pitch,packets} = data;
          requireValue(Number.isFinite(yaw) && Number.isFinite(pitch)
            && Number.isSafeInteger(packets) && packets > 0, 'invalid_servo', '运行时返回了无效的舵机状态。');
          if (this.servo?.yaw !== yaw || this.servo?.pitch !== pitch || this.servo?.packets !== packets) {
            this.servo = {yaw,pitch,packets};
            this.onServo(this.servo);
          }
        }
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
          const bytes = new Uint8Array(message.bin);
          if (bytes[0] === 1 && this.profile.display) {
            const frame = decodeBrowserFrame(message.bin, ++this.sequence);
            requireValue(frame.width === this.profile.display?.width && frame.height === this.profile.display?.height, 'frame_profile_mismatch', '显示帧与所选浏览器板型不匹配。');
            this.lastFrame = frame;
            this.onFrame(frame);
          } else if (bytes[0] === 2) {
            this.audioPlayer?.push(message.bin);
          } else if (bytes[0] === 4 && this.profile.camera) {
            const width = bytes[1] | bytes[2] << 8, height = bytes[3] | bytes[4] << 8;
            requireValue(width === 320 && height === 240 && bytes.length === 5 + width * height * 3,
              'invalid_camera_frame', '运行时返回了无效的相机预览。');
            this.onCamera({width,height,rgb:bytes.subarray(5)});
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

  async start({device, firmware, signal, audio, sidecarArchive} = {}) {
    this.stop();
    const generation = this.generation;
    const profile = getBrowserProfile(typeof device === 'string' ? device : device?.id, this.availableProfiles);
    requireValue(profile, 'browser_board_unsupported', '该设备尚未接入浏览器内核，请连接 Device Service。');
    if (profile.flashSizes) {
      const image = firmware instanceof ArrayBuffer ? new Uint8Array(firmware) : firmware;
      const size = 2 ** (image?.[CHIP_LAYOUT[profile.chip].bootloader + 3] >> 4);
      requireValue(profile.flashSizes.includes(size), 'flash_size_mismatch', '引导程序声明的 Flash 容量与板型不匹配。');
      profile.flashMb = size;
    }
    validateBrowserFirmware(firmware, profile);
    this.profile = profile; this.sequence = 0; this.receipt = null; this.stats = {};
    this.display = null; this.lastFrame = null; this.servo = null;
    this.advKeys = new Map(); this.advFnKeys = new Set();
    this.saved = {device:profile.deviceId,firmware:firmware.slice(0),sidecarArchive};
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
      const tab5 = profile.chip === 'esp32p4';
      const input = new Uint8Array(firmware);
      const bootloader = CHIP_LAYOUT[profile.chip].bootloader;
      const revision3 = tab5 && (input[bootloader+15] | input[bootloader+16]<<8) >= 300;
      if (revision3) profile.board = profile.rev3Board;
      const sidecar = tab5 ? await readTab5Sidecar(sidecarArchive) : null;
      active();
      const legacy = profile.legacy;
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
      const fetchRom = async chip => {
        const layout = CHIP_LAYOUT[chip];
        const entry = chip === 'esp32s3' ? manifest.rom : manifest.extra_roms?.[chip];
        requireValue(entry?.path === layout.rom && entry.sha256 === layout.sha256, 'rom_mismatch', '芯片 ROM 与已审阅版本不匹配。');
        const rom = await resource(entry, 2 * 1024 * 1024); active();
        requireValue(rom.sha256 === layout.sha256, 'rom_mismatch', '芯片 ROM 与已审阅版本不匹配。');
        return rom;
      };
      const rom = await fetchRom(revision3 ? 'esp32p4-rev3' : profile.chip);
      const c6Rom = tab5 ? await fetchRom('esp32c6') : null;
      const flash = new Uint8Array(profile.flashMb * 1024 * 1024);
      flash.fill(0xff);
      flash.set(input);
      const firmwareInputSha256 = sha256Bytes(input), firmwareRuntimeSha256 = sha256Bytes(flash);
      this.receipt = {sourceCommit:manifest.source.commit,wasmSha256:wasm.sha256,romSha256:rom.sha256,
        firmwareSha256:firmwareRuntimeSha256,firmwareInputSha256,firmwareRuntimeSha256,
        normalization:{kind:input.length === flash.length ? 'exact' : 'pad-ff',inputBytes:input.length,runtimeBytes:flash.length},
        jit:profile.jit,build:manifest.build,profile:profile.board};
      if (sidecar) this.receipt.sidecar = {archiveSha256:sidecar.archiveSHA256,flashSha256:sidecar.flashSHA256,romSha256:c6Rom.sha256};
      const worker = this.workerFactory(assetUrl(`platform/web/vendor/esp32sim/${legacy ? 'legacy/' : ''}worker.js`, this.root));
      this.worker = worker;
      worker.onmessage = event => { if (generation === this.generation && this.worker === worker) this.receive(event.data); };
      worker.onerror = () => { if (generation === this.generation && this.worker === worker) this.fail(new BrowserRuntimeError('browser_worker_error', '浏览器执行线程出错，请查看串口或重新启动。')); };
      await this.ask('ready', {op:'init',wasm:wasm.bytes,frameAck:true}, [wasm.bytes]); active();
      requireValue((await this.ask('created', {op:'create',board:profile.board,flash_mb:profile.flashMb,psram_mb:profile.psramMb,jit:profile.jit})).created, 'browser_create_failed', '无法创建所选浏览器板模型。');
      requireValue((await this.ask('load:5', {op:'load',kind:5,data:flash.buffer}, [flash.buffer])).ok, 'firmware_load_failed', '浏览器内核拒绝该固件。'); active();
      requireValue((await this.ask('load:0', {op:'load',kind:0,data:rom.bytes}, [rom.bytes])).ok, 'rom_load_failed', '浏览器内核拒绝该 ROM。'); active();
      if (sidecar) {
        requireValue((await this.ask('load:256', {op:'load',kind:256,data:c6Rom.bytes}, [c6Rom.bytes])).ok,
          'c6_rom_load_failed', '浏览器内核拒绝 Tab5 C6 ROM。'); active();
        requireValue((await this.ask('load:261', {op:'load',kind:261,data:sidecar.flash}, [sidecar.flash])).ok,
          'c6_firmware_load_failed', '浏览器内核拒绝 Tab5 C6 固件。'); active();
        // The pinned hosted build has the same baseband calibration shim as Device Service.
        this.worker.postMessage({op:'stub',spec:'c6:0x4208084c=0'});
      }
      if (profile.camera) await this.queueInput({t:'camera-pattern',enabled:1});
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
      requireValue(this.profile.inputs?.touch !== false && this.profile.display, 'unsupported_control', '该设备没有触摸屏。');
      const {width,height} = this.profile.display;
      requireValue(Number.isInteger(event.x) && Number.isInteger(event.y) && event.x >= 0 && event.y >= 0 && event.x < width && event.y < height && typeof event.down === 'boolean', 'invalid_input', '触摸坐标必须位于设备原生屏幕内。');
      message = {t:'touch',x:event.x,y:event.y,down:event.down ? 1 : 0};
    } else if (event?.type === 'button') {
      const pins = {'button-a':2,'btnA':2,'a':2,'button-b':1,'btnB':1,'b':1};
      const down = event.down ?? event.pressed;
      requireValue(typeof down === 'boolean', 'invalid_input', '按键需要明确的按下或释放状态。');
      if (['cores3','stackchan'].includes(this.profile.deviceId) && ['power','p'].includes(event.id)) {
        if (!down) return {accepted:true,delivery:'timed'};
        message = {t:'power-key'};
      } else if (Object.hasOwn(this.profile.inputs?.plcKeys || {}, event.id)) {
        message = {t:'plc-key',key:this.profile.inputs.plcKeys[event.id],down:down ? 1 : 0};
      } else if (this.profile.inputs?.encoderButton === event.id && event.id) {
        message = {t:'knobpress',v:down ? 1 : 0};
      } else if (['cardputer', 'cardputer-adv'].includes(this.profile.deviceId)) {
        if (['boot','g0','f12'].includes(event.id)) message = {t:'btn',pin:0,v:down ? 1 : 0};
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
        const buttons = this.profile.inputs?.buttons || (this.profile.legacy && this.profile.deviceId === 'stopwatch' ? pins : {});
        requireValue(Object.hasOwn(buttons,event.id), 'unsupported_control', '该浏览器板型不支持此按键。');
        message = {t:'btn',pin:buttons[event.id],v:down ? 1 : 0};
      }
    } else if (event?.type === 'capacitive-touch') {
      requireValue(this.profile.inputs?.capacitiveTouch, 'unsupported_control', '该设备没有机身触摸区。');
      requireValue(Number.isInteger(event.zone) && event.zone >= 1 && event.zone <= 3
        && typeof event.down === 'boolean', 'invalid_input', '机身触摸区或按压状态无效。');
      message = {t:'head-touch',zone:event.zone - 1,level:event.down ? 3 : 0};
    } else if (event?.type === 'encoder') {
      requireValue(this.profile.inputs?.encoder, 'unsupported_control', '该设备没有旋转编码器。');
      requireValue(Number.isInteger(event.delta) && Math.abs(event.delta) >= 1 && Math.abs(event.delta) <= 64, 'invalid_input', '编码器步数无效。');
      message = {t:'knob',d:event.delta};
    } else if (event?.type === 'mic-wav') {
      requireValue(this.status === 'running' && this.profile.inputs?.microphone,
        'unsupported_control', '该设备没有可用的浏览器麦克风输入。');
      requireValue(event.bytes instanceof ArrayBuffer && event.bytes.byteLength >= 44 && event.bytes.byteLength <= 2 * 1024 * 1024,
        'invalid_input', '请选择不超过 2 MiB 的 PCM16 WAV 文件。');
      const packet = new Uint8Array(1 + event.bytes.byteLength);
      packet[0] = 6;
      packet.set(new Uint8Array(event.bytes),1);
      const reply = await this.ask('mic-input',{op:'bin',data:packet.buffer},[packet.buffer]);
      requireValue(reply.ok === true, 'invalid_mic_input', reply.message || '麦克风输入失败。');
      return {accepted:true,delivery:'i2s-source'};
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
