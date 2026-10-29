import {assetUrl, siteRoot, parseLaunchConfig, buildShareUrl, normalizeServiceUrl} from './public-config.js';
import {downloadFirmware, normalizeFirmwareSha256, DEFAULT_MAX_FIRMWARE_BYTES} from './public-firmware.js';
import {sha256Blob} from './sha256.js';
import {PublicDeviceService} from './public-service.js';
import {PublicBrowserRuntime, getBrowserProfile} from './public-browser-runtime.js';
import {PublicQemuRuntime, browserQemuHistory} from './public-qemu-runtime.js';
import {composeDemoFirmware, composeWallclockDemoFirmware, DEMO_FIRMWARE, WALLCLOCK_DEMO_FIRMWARE} from './public-demo-firmware.js';
import {loadQemuBrowserProfiles,getQemuBrowserProfile} from './public-qemu-profiles.js';
import {composeQemuProbeFirmware} from './public-qemu-probe-firmware.js';
import {ensurePublicIsolation} from './public-coi.js';
import {PublicSessionController} from './public-session-controller.js';
import {createDeviceShell} from './device-shell-factory.js';
import {createVisualModelShell} from './model-shell.js';
import {createUnitPicker} from './unit-panel.js';

const $ = (id) => document.getElementById(id),
  root = siteRoot();
const state = {
  devices: [],
  units: [],
  config: {},
  selected: null,
  shell: null,
  unitShell: null,
  selection: 0,
  unitSelection: 0,
  runGeneration: 0,
  serviceGeneration: 0,
  run: null,
  abort: null,
  service: null,
  serviceDevices: [],
  inventory: null,
  picker: null,
  busy: false,
  serial: '',
  serialBytes: 0,
  deviceFilter: 'all',
  unitFilter: 'all',
  selectedUnit: null,
  holds: new Map(),
  stopped: false,
};
const node = (tag, className, value) => {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (value != null) n.textContent = value;
  return n;
};
const bytes = (size) => (size >= 1048576 ? `${(size / 1048576).toFixed(1)} MiB` : `${size} B`);
const source = () => document.querySelector('input[name="firmwareSource"]:checked').value;
const active = (run) => run && run === state.run && run.generation === state.runGeneration && !run.stopping;
function message(id, text = '') {
  $(id).textContent = text;
  $(id).hidden = !text;
}
function error(error) {
  if (error?.name !== 'AbortError') message('errorBanner', error?.message || String(error));
}
function browserProfile(id) {
  if (state.browserUnavailable) return null;
  if (state.config.browser_runtime_engine === 'qemu-wasm') return state.qemuProfiles ? getQemuBrowserProfile(id,state.qemuProfiles,{allowCandidateProfiles:state.config.publication_eligible===false}) : null;
  return getBrowserProfile(id);
}
function reference(device = state.selected) {
  const profile=browserProfile(device?.id);
  if (profile?.fixture?.id==='xtensa-board-display-v1') return {name:`${device.name} 屏幕与输入示例`,composedProbe:true,sha256:profile.fixture.firmwareSHA256};
  if (device?.id === 'cores3' && state.config.browser_runtime_engine === 'qemu-wasm') {
    if (state.config.browser_wallclock_example && $('referenceExample').value !== 'stock-div8')
      return {name:'CoreS3 LVGL + PIR（正常速度，候选修复）',composed:true,wallclockCandidate:true,
        sha256:WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256};
    return {name:'CoreS3 LVGL + PIR（原始基线，1/8 速度）',composed:true,sha256:DEMO_FIRMWARE.firmwareSHA256};
  }
  return (
    device?.browser?.reference ||
    (device?.uiflow2?.firmware?.download_url
      ? {url: device.uiflow2.firmware.download_url, name: `UIFlow2 ${device.uiflow2.firmware.version}`}
      : null)
  );
}
function selectedAttachments() {
  try {
    return state.picker?.attachments(state.selected?.id) || [];
  } catch {
    return [];
  }
}
function lane(device = state.selected) {
  const mode = $('runtimeMode').value;
  const serviceReady = state.serviceDevices.some((item) => item.device_id === device?.id && item.creatable);
  if (mode === 'model') return 'model';
  if (selectedAttachments().length) {
    if (mode === 'browser') return null;
    return serviceReady ? 'service' : null;
  }
  if (mode !== 'service' && browserProfile(device?.id)) return 'browser';
  if (mode !== 'browser' && serviceReady) return 'service';
  return null;
}
function appendSerial(text) {
  if (!text) return;
  state.serialBytes += new TextEncoder().encode(text).byteLength;
  state.serial = (state.serial + text).slice(-65536);
  $('serialOutput').textContent = state.serial;
  $('serialCount').textContent = bytes(state.serialBytes);
  if ($('serialDrawer').open) $('serialOutput').scrollTop = $('serialOutput').scrollHeight;
}
function status(status, detail) {
  const labels = {
    loading: '正在加载固件',
    booting: '设备启动中',
    provisioning: '正在创建设备',
    flashing: '正在写入固件',
    running: '固件运行中',
    paused: '固件已暂停',
    stopped: '运行已停止',
    stopping: '正在停止会话',
    stop_pending: '停止结果未确认',
    error: '运行未完成',
    model: '模型预览',
  };
  $('runtimeStatus').replaceChildren(node('i'), document.createTextNode(labels[status] || status));
  $('runtimeStatus').dataset.status = status;
  if (detail) $('frameStatus').textContent = detail;
  $('serialInput').disabled = $('serialSendBtn').disabled =
    !state.run || state.run.kind !== 'browser' || state.run.controller instanceof PublicQemuRuntime || !['running', 'paused'].includes(status);
  $('pauseBtn').hidden = !state.run || state.run.kind !== 'browser' || !['running', 'paused'].includes(status);
  $('pauseBtn').textContent = status === 'paused' ? '继续' : '暂停';
  $('nativeScreenBtn').hidden = !(state.run?.controller instanceof PublicQemuRuntime);
  $('browserPirPanel').hidden = !(state.run?.controller instanceof PublicQemuRuntime && !!state.run.controller.profile?.inputs.pir);
  $('browserPir').disabled = status !== 'running';
  $('browserEvidenceBtn').hidden = !state.lastBrowserController?.receipt;
  $('stopBtn').hidden = !state.run;
  $('stopBtn').textContent = state.stopUnconfirmed ? '重试停止' : '停止';
}
function updateCapability() {
  const device = state.selected,
    selectedLane = lane(),
    supported = !!browserProfile(device?.id);
  $('capabilityTitle').textContent =
    selectedLane === 'browser'
      ? '浏览器本地运行'
      : selectedLane === 'service'
        ? '通过仿真服务运行'
        : selectedLane === 'model'
          ? '仅浏览模型'
          : supported
            ? '请选择浏览器运行'
            : '此设备需要仿真服务';
  $('capabilityText').textContent =
    selectedLane === 'browser'
      ? '固件在当前浏览器中执行，屏幕与串口来自模拟器。不同固件的兼容性仍有边界。'
      : selectedLane === 'service'
        ? '固件运行在你连接的原生设备服务中，画面与输入绑定本次会话。'
        : selectedLane === 'model'
          ? '可旋转、缩放并探索模型；本模式不执行固件。'
          : '现在可以浏览 3D 模型。连接兼容服务后，可启动此设备的固件。';
  if (selectedLane === 'browser' && state.config.browser_runtime_engine==='qemu-wasm') {
    const p=browserProfile(device?.id);
    const wallclock=source()==='reference'&&reference()?.wallclockCandidate;
    $('capabilityText').textContent=`C/QEMU 在浏览器执行 ${device.name}。${p?.admission==='candidate'?'候选预览，尚未公开准入。':''}${wallclock?'本示例采用正常时钟和 LVGL 调度候选修复。':p?.clockDivisor===8?'虚拟时间与看门狗按 1/8 慢放。':'采用正常虚拟时钟。'}刷新不保存 Flash。`;
  }
  if ($('runtimeMode').value === 'browser' && selectedAttachments().length) {
    $('capabilityTitle').textContent = '所选 Unit 需要服务运行';
    $('capabilityText').textContent = '浏览器内核尚未接入这些 Unit。请选择自动或服务运行，或取消已连接的 Unit。';
  }
  $('openServiceBtn').hidden = !!selectedLane || $('runtimeMode').value === 'browser';
  $('startBtn').disabled = state.busy || state.stopUnconfirmed || !device || !state.shell || !selectedLane;
  $('startBtn').textContent =
    selectedLane === 'model' ? '浏览设备模型 →' : state.busy ? '正在加载…' : state.run ? '重新运行 →' : '开始运行 →';
  $('cancelLoadBtn').hidden = !state.busy;
}
function renderDevices() {
  const query = $('search').value.trim().toLowerCase();
  const filtered = state.devices.filter(
    (d) =>
      `${d.name} ${d.id} ${d.sku || ''} ${d.hardware?.soc || d.group_label || ''}`.toLowerCase().includes(query) &&
      (state.deviceFilter !== 'browser' || browserProfile(d.id)),
  );
  $('deviceNav').replaceChildren();
  for (const device of filtered) {
    const item = node('button', 'device-choice');
    item.type = 'button';
    item.dataset.deviceId = device.id;
    item.setAttribute('aria-pressed', String(state.selected?.id === device.id));
    item.append(node('strong', '', device.name));
    item.append(
      node(
        'small',
        browserProfile(device.id) ? 'browser-marker' : '',
        `${device.sku || device.group_label || 'M5Stack'} · ${browserProfile(device.id) ? '浏览器运行' : device.visual_only ? '仅模型' : '连接服务'}`,
      ),
    );
    item.addEventListener('click', () => void selectDevice(device.id).catch(error));
    $('deviceNav').append(item);
  }
  if (!filtered.length) $('deviceNav').append(node('p', 'empty-list', '没有匹配设备。试试产品名或 SKU。'));
  $('deviceResults').textContent = `${filtered.length} 个匹配设备`;
}
function renderDetails() {
  const device = state.selected,
    list = node('dl');
  const display = device.hardware?.display || device.display;
  for (const [label, value] of [
    ['芯片', device.hardware?.soc || device.group_label],
    [
      '屏幕',
      display ? `${display.width} × ${display.height} · ${display.driver || display.type || ''}` : '无板载显示屏',
    ],
    ['运行范围', device.browser?.description || device.runtime?.execution || '独立视觉模型'],
  ])
    if (value) list.append(node('dt', '', label), node('dd', '', value));
  $('deviceDetails').replaceChildren(list);
  for (const text of [...(device.browser?.limitations || []), ...(device.runtime?.blockers || [])])
    $('deviceDetails').append(node('p', '', text));
  const ref = reference();
  $('referenceExampleFields').hidden = !(device?.id==='cores3' && state.config.browser_runtime_engine==='qemu-wasm' && state.config.browser_wallclock_example);
  $('referenceTitle').textContent = ref?.name || '此型号暂无参考固件';
  $('referenceDescription').textContent = ref?.wallclockCandidate
    ? '在官方 UIFlow2 基底中加入明确的 LVGL 调度候选修复，用于本交互示例。'
    : ref?.composedProbe
    ? ({'cardputer-adv':'点击模型键盘，或先点击模型再用电脑键盘输入；屏幕显示按键状态和累计次数。',
        papermono:'点击屏幕下方的触摸区域，观察计数和电子纸刷新；区域外点击不计数。',
        papercolor:'按模型正面的 A 键，观察计数和六色电子纸刷新。',
        stopwatch:'点击圆屏，观察计数和屏幕标记变化。'}[device.id]
      || '点击模型上的按键或触摸屏，观察设备屏幕中的计数变化。')
    : ref
    ? '已为当前设备选择对应固件。也可以使用自己的链接或本地文件。'
    : '请选择固件链接或本地 .bin 文件。';
}
function sourceChanged() {
  for (const [name, value] of [
    ['referenceFields', 'reference'],
    ['urlFields', 'url'],
    ['localFields', 'local'],
  ])
    $(name).hidden = source() !== value;
  $('shareStatus').textContent = '';
  updateCapability();
}
function view(mode) {
  state.shell?.setViewMode?.(mode);
  for (const button of document.querySelectorAll('[data-view]'))
    button.setAttribute('aria-pressed', String(button.dataset.view === mode));
}
function normalizeDevice(device) {
  return {
    ...device,
    hardware: device.hardware || {display: device.display, soc: device.group_label || 'M5Stack', controls: []},
    shell: {
      ...(typeof device.shell === 'object' ? device.shell : {preset: 'core'}),
      ...(device.shell?.reference_image ? {reference_image: assetUrl(device.shell.reference_image, root)} : {}),
    },
  };
}
async function selectDevice(id) {
  const selection = ++state.selection,
    row = state.devices.find((d) => d.id === id);
  if (!row) return;
  await stopRun();
  if (selection !== state.selection) return;
  message('errorBanner');
  state.inventory = null;
  state.picker?.dispose();
  state.picker = null;
  $('unitConnectionPicker').replaceChildren();
  state.selected = row;
  renderDevices();
  $('stageTitle').textContent = row.name;
  $('stageSub').textContent = `${row.sku || ''} · ${row.hardware?.soc || row.group_label || 'M5STACK DEVICE'}`;
  state.shell?.dispose();
  state.shell = null;
  $('deviceMount').replaceChildren(node('p', 'stage-loading', '正在准备设备模型…'));
  $('rawFramePanel').hidden = true;
  $('deviceMount').classList.remove('has-raw-frame');
  delete $('deviceMount').dataset.frameSequence;
  const device = row.path
    ? {...row, ...(await json(assetUrl(`devices/${row.path}/device.json`))), browser: row.browser}
    : row;
  if (selection !== state.selection) return;
  state.selected = normalizeDevice(device);
  renderDetails();
  sourceChanged();
  updateCapability();
  const mount = node('div', 'device-render-mount');
  let shell;
  try {
    shell = row.visual_only
      ? await createVisualModelShell(mount, id)
      : await createDeviceShell(mount, state.selected, {live: true});
  } catch (cause) {
    if (selection === state.selection) {
      message('errorBanner', `设备模型加载失败：${cause.message}。可重新选择型号后重试。`);
      $('deviceMount').replaceChildren(node('p', 'stage-loading', '模型暂时不可用'));
    }
    return;
  }
  if (selection !== state.selection) {
    shell.dispose();
    return;
  }
  state.shell = shell;
  $('deviceMount').replaceChildren(mount);
  shell.viewer?.resize();
  shell.resetView?.();
  view('shell');
  document.querySelector('[data-view="shell"]').textContent = shell.model ? '3D' : '屏幕';
  $('resetViewBtn').disabled = !shell.model;
  const photo = !!state.selected.shell?.reference_image;
  document.querySelector('[data-view="photo"]').disabled = !photo;
  shell.on?.(
    'control',
    (event) => void deliverInput({type: 'button', id: event.key || event.id, down: event.down}, event),
  );
  shell.on?.(
    'touch',
    (event) =>
      void deliverInput(
        {type: 'touch', x: event.x, y: event.y, down: event.down ?? !['end', 'cancel'].includes(event.action)},
        event,
      ),
  );
  status(
    'model',
    browserProfile(id) ? '选择固件后即可开始' : row.visual_only ? '此型号目前仅有视觉模型' : '尚未运行固件',
  );
  $('deviceMount').dataset.deviceId = id;
  if (matchMedia('(max-width: 800px)').matches) $('deviceLibrary').open = false;
  updateCapability();
  renderUnits();
  if (state.service) await loadServiceUnits(selection);
}
async function releaseInputs(run = state.run) {
  const held = [...state.holds.values()];
  state.holds.clear();
  await Promise.allSettled(held.map((command) => run?.controller.input({...command, down: false})));
}
async function deliverInput(command, original = {}) {
  const run = state.run;
  if (!active(run) || state.busy) return;
  try {
    if (run.kind === 'browser') {
      if (command.type==='touch' && run.controller instanceof PublicQemuRuntime && !run.controller.profile?.inputs.touch) return;
      if (command.type === 'button') {
        if (command.down) state.holds.set(command.id, command);
        else state.holds.delete(command.id);
      } else if (command.type === 'touch') {
        if (command.down) state.holds.set('touch', command);
        else state.holds.delete('touch');
      }
      await run.controller.input(command);
    } else if (command.type === 'button')
      await run.controller.input({kind: 'key', key: command.id, action: command.down ? 'down' : 'up'});
    else if (command.type === 'touch' && command.down && (!original.action || original.action === 'start'))
      await run.controller.input({kind: 'touch', x: command.x, y: command.y});
  } catch (cause) {
    if (active(run)) error(cause);
  }
}
async function stopRun() {
  if (state.stopping) return state.stopping;
  const generation = ++state.runGeneration;
  state.abort?.abort();
  state.abort = null;
  const run = state.run;
  if (!run) {
    state.busy = false;
    status('stopped', '保留最后显示帧');
    message('runProgress');
    updateCapability();
    return;
  }
  run.stopping = true;
  run.stopGeneration = generation;
  state.busy = true;
  status('stopping', '正在保留记录并停止当前会话…');
  updateCapability();
  const attempt = (async () => {
    try {
      await releaseInputs(run);
      await run.controller.stop();
      if (run.controller instanceof PublicQemuRuntime) renderBrowserHistory();
      if (state.run === run) state.run = null;
      state.stopUnconfirmed = false;
      status('stopped', '保留最后显示帧');
      message('runProgress');
    } catch (cause) {
      state.stopUnconfirmed = true;
      status('stop_pending', '当前会话仍保留，请重试停止');
      $('stopBtn').textContent = '重试停止';
      const failure = new Error(`停止结果未确认。请重试停止当前会话：${cause.message}`);
      error(failure);
      throw failure;
    } finally {
      state.busy = false;
      if (state.stopping === attempt) state.stopping = null;
      updateCapability();
    }
  })();
  state.stopping = attempt;
  return attempt;
}
async function firmware(signal, runGeneration) {
  const selectedSource = source(),
    ref = reference(),
    expected = normalizeFirmwareSha256(
      $('firmwareSha').value.trim() || (selectedSource === 'reference' ? ref?.sha256 : null),
    );
  if (selectedSource === 'reference' && ref?.composedProbe) {
    const result=await composeQemuProbeFirmware({profile:browserProfile(state.selected.id),root,signal,onProgress:()=>message('runProgress','正在本地组合设备示例')});
    if(expected&&expected!==result.sha256)throw new Error('设备示例 SHA-256 与预期不一致。');
    return {...result,name:result.fileName||`${state.selected.id}-probe.bin`,size:result.bytes.byteLength};
  }
  if (selectedSource === 'reference' && ref?.composed) {
    const phases = {'load-composer':'加载本地固件组合器','download-base':'下载官方固件基底','verify-base':'校验官方固件','compose':'写入示例源码','verify-result':'校验最终 Flash'};
    const compose=ref.wallclockCandidate?composeWallclockDemoFirmware:composeDemoFirmware;
    const result = await compose({signal,onProgress:(p)=>message('runProgress',phases[p.phase]||'正在准备浏览器示例')});
    if (expected && expected !== result.sha256) throw new Error('示例 SHA-256 与预期不一致。');
    return {...result,name:result.fileName||'cores3-lvgl-pir.bin',size:result.bytes.byteLength};
  }
  if (selectedSource !== 'local') {
    const url = selectedSource === 'reference' ? ref?.url : $('firmwareUrl').value.trim();
    if (!url) throw new Error('请先选择一个固件文件或填写公开固件地址。');
    return downloadFirmware(url, {
      signal,
      expectedSha256: expected,
      maxBytes: state.config.max_firmware_bytes || DEFAULT_MAX_FIRMWARE_BYTES,
      onProgress: (p) => {
        if (runGeneration === state.runGeneration)
          message('runProgress', `正在下载固件 · ${bytes(p.received)}${p.total ? ` / ${bytes(p.total)}` : ''}`);
      },
    });
  }
  const file = $('firmwareFile').files[0];
  if (!file?.size) throw new Error('请先选择非空的 .bin 固件文件。');
  if (file.size > (state.config.max_firmware_bytes || DEFAULT_MAX_FIRMWARE_BYTES))
    throw new Error('固件文件超过 64 MiB 上限。');
  const sha256 = await sha256Blob(file);
  if (signal.aborted) throw new DOMException('已取消加载', 'AbortError');
  if (expected && expected !== sha256) throw new Error('固件 SHA-256 与预期不一致，未加载固件。');
  return {bytes: await file.arrayBuffer(), name: file.name, size: file.size, sha256};
}
function applyBrowserFrame(frame, run) {
  if (!active(run)) return;
  if (state.config.browser_runtime_engine==='qemu-wasm' || state.selected.id === 'stopwatch' && frame.width === 468 && frame.height === 466) {
    const canvas = $('rawFrameCanvas');
    canvas.width = frame.width;
    canvas.height = frame.height;
    const context = canvas.getContext('2d'),
      image = context.createImageData(frame.width, frame.height);
    for (let i = 0, p = 0; i < frame.pixels.length; i += 2, p += 4) {
      const value = frame.pixels[i] | (frame.pixels[i + 1] << 8);
      image.data[p] = (((value >> 11) & 31) * 255) / 31;
      image.data[p + 1] = (((value >> 5) & 63) * 255) / 63;
      image.data[p + 2] = ((value & 31) * 255) / 31;
      image.data[p + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    const touch=!(run.controller instanceof PublicQemuRuntime)||run.controller.profile?.inputs.touch;
    $('rawFrameDescription').textContent = `完整 ${frame.width} × ${frame.height} 固件帧 · ${touch?'支持触摸':'请使用设备按键'}`;
    if (state.selected.id === 'stopwatch' && !(run.controller instanceof PublicQemuRuntime)) {
      const first = $('rawFramePanel').hidden;
      $('rawFramePanel').hidden = false;
      $('deviceMount').classList.add('has-raw-frame');
      if (first) {
        state.shell?.viewer?.resize();
        state.shell?.resetView?.();
      }
      $('frameStatus').textContent = `原始屏幕帧 ${frame.width} × ${frame.height} · 帧 ${frame.sequence}`;
      canvas.dataset.frameSequence = frame.sequence;
      return;
    }
    canvas.dataset.frameSequence = frame.sequence;
  }
  let applied;
  if (state.shell.setFrameLE) applied = state.shell.setFrameLE(frame.pixels, frame.width, frame.height, frame.sequence);
  else {
    const be = frame.pixels.slice();
    for (let i = 0; i < be.length; i += 2) [be[i], be[i + 1]] = [be[i + 1], be[i]];
    applied = state.shell.setFrame(be, frame.width, frame.height, frame.sequence);
  }
  if (applied !== false) {
    $('frameStatus').textContent = `实际屏幕 · ${frame.width} × ${frame.height} · 帧 ${frame.sequence}`;
    $('deviceMount').dataset.frameSequence = frame.sequence;
  } else error(new Error(`固件输出 ${frame.width} × ${frame.height} 与当前模型屏幕不匹配。`));
}
async function startRun() {
  if (state.busy) return;
  const selection = state.selection;
  await stopRun();
  if (selection !== state.selection) return;
  message('errorBanner');
  message('launchNotice');
  const kind = lane();
  if (kind === 'model') {
    view('shell');
    status('model', '模型交互不执行固件');
    return;
  }
  if (!kind) {
    error(new Error('当前设备需要兼容运行时。请连接仿真服务，或选择支持浏览器运行的设备。'));
    $('serviceConnection').open = true;
    return;
  }
  const generation = ++state.runGeneration,
    abort = (state.abort = new AbortController());
  state.busy = true;
  if (kind === 'browser') state.shell?.pauseRendering?.();
  status('loading', '尚未取得应用首帧');
  updateCapability();
  let run;
  try {
    const loaded = await firmware(abort.signal, generation);
    if (generation !== state.runGeneration || selection !== state.selection) return;
    $('rawFramePanel').hidden = true;
    $('deviceMount').classList.remove('has-raw-frame');
    state.shell.display?.fill('#000000');
    state.shell.viewer?.requestRender();
    state.serial = '';
    state.serialBytes = 0;
    $('serialOutput').textContent = '';
    $('serialCount').textContent = '0 B';
    message('runProgress', `已校验 ${loaded.name} · ${bytes(loaded.size)}，正在启动…`);
    run = {kind, generation, controller: null};
    const callbacks = {
      onSerial: (text) => {
        if (active(run)) appendSerial(text);
      },
      onError: (cause) => {
        if (active(run)) {
          error(cause);
          status('error', '请查看错误信息或串口输出');
        } else if (run.stopping && run.stopGeneration === state.runGeneration) error(cause);
      },
    };
    if (kind === 'browser') {
      const BrowserRuntime = state.config.browser_runtime_engine==='qemu-wasm' ? PublicQemuRuntime : PublicBrowserRuntime;
      run.controller = new BrowserRuntime({
        ...callbacks,
        root,profiles:state.qemuProfiles,allowCandidateProfiles:state.config.publication_eligible===false,
        onFrame: (frame) => applyBrowserFrame(frame, run),
        onState: (value) => {
          if (active(run)) {
            status(value.status);
            if (['running', 'paused', 'error', 'stopped'].includes(value.status)) state.shell?.resumeRendering?.();
          }
        },
      });
      if (run.controller instanceof PublicQemuRuntime) {
        state.lastBrowserController = run.controller;
        $('browserPir').checked = false;
        $('browserPirState').textContent = 'QOM: CLEAR';
      }
      state.run = run;
      await run.controller.start({device: state.selected.id, firmware: loaded.bytes, signal: abort.signal});
    } else {
      const imported = await state.service.importFirmware(
        new File([loaded.bytes], loaded.name, {type: 'application/octet-stream'}),
        state.selected.id,
        {signal: abort.signal},
      );
      if (generation !== state.runGeneration) return;
      const units = state.picker?.attachments(state.selected.id) || [];
      run.controller = new PublicSessionController({
        ...callbacks,
        service: state.service,
        shell: state.shell,
        unitContainer: $('runtimeUnitPanel'),
        onState: (value) => {
          if (active(run)) status(value.status, value.frameReady ? '实际会话屏幕已更新' : '等待应用显示帧');
        },
      });
      state.run = run;
      await run.controller.start({
        deviceId: state.selected.id,
        firmwareId: imported.firmware_id,
        units,
        signal: abort.signal,
      });
    }
    if (active(run)) message('runProgress', `已加载 ${loaded.name} · ${bytes(loaded.size)}`);
  } catch (cause) {
    if (generation === state.runGeneration) {
      if (run?.controller && state.run === run) {
        try {
          await stopRun();
        } catch {
          return;
        } // The retained native session must be stopped before retrying.
      }
      error(cause);
      status(cause.name === 'AbortError' ? 'stopped' : 'error', '可修改固件或运行选项后重试');
      state.shell?.resumeRendering?.();
      state.busy = false;
      updateCapability();
    }
  } finally {
    if (generation === state.runGeneration) {
      state.shell?.resumeRendering?.();
      state.busy = false;
      updateCapability();
    }
  }
}
function updateServiceLinks() {
  for (const link of document.querySelectorAll('[data-service-console]')) {
    if (state.service) {
      link.href = new URL(link.dataset.serviceConsole, state.service.url + '/').href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.title = '打开已连接服务的控制台';
    } else {
      link.href = '#serviceConnection';
      link.removeAttribute('target');
      link.removeAttribute('rel');
      link.title = '连接仿真服务后打开控制台';
    }
  }
}
async function connectService() {
  const generation = ++state.serviceGeneration;
  $('connectServiceBtn').disabled = true;
  message('serviceStatus', '正在连接…');
  try {
    const url = normalizeServiceUrl($('serviceUrl').value.trim()),
      service = new PublicDeviceService(url, {token: $('serviceToken').value});
    const result = await service.devices();
    if (generation !== state.serviceGeneration) return;
    if (
      !Array.isArray(result.devices) ||
      result.devices.some((device) => !device || typeof device.device_id !== 'string' || typeof device.creatable !== 'boolean') ||
      new Set(result.devices.map((device) => device.device_id)).size !== result.devices.length
    )
      throw new Error('服务返回的设备目录无效。');
    // Keep the current service and its selected Units until the candidate is
    // admitted. An owned native session (including an unresolved create) must
    // finish its stop/recovery before another service can replace that owner.
    // A pending firmware load also belongs to the previous service generation.
    if (state.stopUnconfirmed || state.busy || state.run?.kind === 'service') await stopRun();
    if (generation !== state.serviceGeneration) return;
    state.service = service;
    state.serviceDevices = result.devices;
    $('serviceUrl').value = service.url;
    updateServiceLinks();
    message('serviceStatus', `已连接 · ${state.serviceDevices.filter((d) => d.creatable).length} 个可运行设备`);
    await loadServiceUnits(state.selection);
    updateCapability();
    renderDevices();
  } catch (cause) {
    if (generation === state.serviceGeneration) {
      if (state.service) {
        $('serviceUrl').value = state.service.url;
        $('serviceToken').value = state.service.token;
      } else {
        state.serviceDevices = [];
        state.inventory = null;
        state.picker?.dispose();
        state.picker = null;
        $('unitConnectionPicker').replaceChildren();
      }
      message('serviceStatus', `连接失败：${cause.message}${state.service ? '；已保留原服务连接与 Unit 配置。' : ''}`);
      updateServiceLinks();
      renderUnits();
      updateCapability();
    }
  } finally {
    if (generation === state.serviceGeneration) $('connectServiceBtn').disabled = false;
  }
}
async function loadServiceUnits(selection) {
  state.picker?.dispose();
  state.picker = null;
  state.inventory = null;
  const service = state.service,
    deviceId = state.selected?.id,
    mount = node('div');
  $('unitConnectionPicker').replaceChildren(mount);
  if (!service || !state.serviceDevices.some((d) => d.device_id === deviceId && d.creatable)) {
    renderUnits();
    return;
  }
  try {
    const inventory = await service.units(deviceId);
    if (selection !== state.selection || service !== state.service) return;
    state.inventory = inventory;
    const picker = await createUnitPicker(mount, {deviceId, api: async () => inventory});
    if (selection !== state.selection || service !== state.service) {
      picker.dispose();
      return;
    }
    state.picker = picker;
    renderUnits();
  } catch (cause) {
    if (selection === state.selection) message('serviceStatus', `服务已连接，Unit 目录读取失败：${cause.message}`);
  }
}
function runnableUnit(id) {
  const unit = state.inventory?.units?.find((unit) => unit.id === id);
  return (
    ['implemented', 'validated'].includes(unit?.runtime?.status) && unit.runtime.hosts?.includes(state.selected?.id)
  );
}
function renderUnits() {
  const query = $('unitSearch').value.trim().toLowerCase(),
    filtered = state.units.filter(
      (unit) =>
        `${unit.name} ${unit.id} ${unit.sku || ''}`.toLowerCase().includes(query) &&
        (state.unitFilter !== 'runtime' || runnableUnit(unit.id)),
    );
  $('unitResults').textContent =
    `${filtered.length} 个匹配${state.unitFilter === 'runtime' && !state.service ? ' · 先连接服务以确认运行支持' : ''}`;
  $('unitList').replaceChildren();
  for (const unit of filtered) {
    const button = node('button', 'unit-choice');
    button.type = 'button';
    button.dataset.unitModel = unit.id;
    button.setAttribute('aria-pressed', String(state.selectedUnit === unit.id));
    button.append(
      node('strong', '', unit.name),
      node('small', '', `${unit.sku || unit.id} · ${runnableUnit(unit.id) ? '本机可运行' : '模型预览'}`),
    );
    button.addEventListener('click', () => void selectUnit(unit.id).catch(error));
    $('unitList').append(button);
  }
  if (!filtered.length)
    $('unitList').append(
      node(
        'p',
        'empty-list',
        state.unitFilter === 'runtime'
          ? '当前没有已确认可运行的 Unit。可以浏览全部模型，或连接兼容服务。'
          : '没有匹配的 Unit。试试型号或 SKU。',
      ),
    );
}
async function selectUnit(id) {
  const generation = ++state.unitSelection,
    unit = state.units.find((unit) => unit.id === id);
  if (!unit) return;
  state.selectedUnit = id;
  state.unitShell?.dispose();
  state.unitShell = null;
  renderUnits();
  $('unitTitle').textContent = unit.name;
  $('unitCapability').textContent = runnableUnit(id) ? '可在当前主机运行' : '独立模型预览';
  $('unitDetailBody').replaceChildren();
  for (const text of [unit.sku, ...(unit.limitations || []), unit.nextAction].filter(Boolean))
    $('unitDetailBody').append(node('p', '', text));
  $('unitDetails').hidden = false;
  $('unitDetails').open = false;
  const mount = node('div');
  $('unitModelMount').replaceChildren(node('p', 'field-help', '正在加载 Unit 模型…'));
  try {
    const shell = await createVisualModelShell(mount, id);
    if (generation !== state.unitSelection) {
      shell.dispose();
      return;
    }
    state.unitShell = shell;
    $('unitModelMount').replaceChildren(mount);
    shell.viewer?.resize();
    shell.resetView();
  } catch (cause) {
    if (generation === state.unitSelection)
      $('unitModelMount').replaceChildren(node('p', 'field-help', `模型暂时无法加载：${cause.message}`));
  }
}
async function share() {
  try {
    const selectedSource = source(),
      ref = reference(),
      firmwareUrl =
        selectedSource === 'url' ? $('firmwareUrl').value.trim() : selectedSource === 'reference' ? ref?.url : null;
    const url = buildShareUrl(
      {
        deviceId: state.selected.id,
        firmware: firmwareUrl,
        sha256: $('firmwareSha').value.trim() || (selectedSource === 'reference' ? ref?.sha256 : null),
        serviceUrl: $('serviceUrl').value.trim(),
        mode: $('runtimeMode').value,
        autostart: $('runtimeMode').value !== 'model',
      },
      new URL(root),
    );
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      $('shareStatus').textContent =
        selectedSource === 'local'
          ? '已复制设备链接。本地文件需由对方重新选择。'
          : '已复制链接，打开即可加载对应设备与固件。';
    } else $('shareStatus').textContent = `分享链接：${url}`;
  } catch (cause) {
    error(cause);
  }
}
async function json(url, fallback) {
  const response = await fetch(url);
  if (!response.ok) {
    if (fallback !== undefined) return fallback;
    throw new Error(`站点资源读取失败（${response.status}）。`);
  }
  return response.json();
}
async function init() {
  for (const item of document.querySelectorAll('[data-site-link]')) item.href = assetUrl(item.dataset.siteLink, root);
  updateServiceLinks();
  for (const item of document.querySelectorAll('[data-asset]')) item.src = assetUrl(item.dataset.asset, root);
  const [catalog, visual, browser, config] = await Promise.all([
    json(assetUrl('devices/catalog.json')),
    json(assetUrl('platform/web/vendor/m5stack-models/catalog/products.json')),
    json(assetUrl('platform/web/browser-profiles.json'), {devices: []}),
    json(assetUrl('platform/web/site-config.json'), {}),
  ]);
  state.config = config;
  if (config.browser_runtime_engine === 'qemu-wasm') {
    try {
      state.qemuProfiles=await loadQemuBrowserProfiles({root});
      const isolation = await ensurePublicIsolation({root});
      if (isolation.reloading) return;
    } catch (cause) {
      state.browserUnavailable = true;
      error(new Error(`${cause.message} 仍可浏览模型或连接 HTTPS 仿真服务。`));
    }
    renderBrowserHistory();
  }
  const rows = new Map(catalog.devices.map((d) => [d.id, {...d}]));
  for (const model of visual.products.filter((m) => m.category === 'controller'))
    if (!rows.has(model.id))
      rows.set(model.id, {
        id: model.id,
        name: model.name,
        sku: model.sku,
        visual_only: true,
        display: model.display,
        hardware: {display: model.display, controls: []},
        shell: {preset: 'core'},
        runtime: {status: 'visual-only'},
      });
  for (const profile of browser.devices) rows.set(profile.id, {...rows.get(profile.id), ...profile});
  state.devices = [...rows.values()];
  state.units = visual.products.filter((model) => model.category === 'unit');
  $('deviceCount').textContent = state.devices.length;
  $('unitCount').textContent = `${state.units.length} 个 Unit 模型`;
  $('catalogChip').textContent = `${state.devices.length} DEVICES / ${state.units.length} UNITS`;
  let launch;
  const params = new URLSearchParams(location.search);
  if (!params.has('device')) params.set('device', config.browser_runtime_engine === 'qemu-wasm' ? 'cores3' : config.browser_board_execution ? 'stopwatch' : 'cores3');
  try {
    launch = parseLaunchConfig(params.toString(), state.devices);
  } catch (cause) {
    error(cause);
    launch = {device: null, warnings: [], mode: 'auto', serviceUrl: '', firmware: null};
  }
  $('runtimeMode').value = launch.mode;
  if (launch.sha256===DEMO_FIRMWARE.firmwareSHA256) $('referenceExample').value='stock-div8';
  else if (launch.sha256===WALLCLOCK_DEMO_FIRMWARE.firmwareSHA256) $('referenceExample').value='wallclock-candidate';
  $('serviceUrl').value = launch.serviceUrl || config.service_url || '';
  if (launch.firmware) {
    $('firmwareUrl').value = launch.firmware;
    document.querySelector('[name="firmwareSource"][value="url"]').checked = true;
  }
  if (launch.sha256) $('firmwareSha').value = launch.sha256;
  if (launch.warnings.length) message('launchNotice', launch.warnings.join(' '));
  renderDevices();
  renderUnits();
  if (launch.device) await selectDevice(launch.device.id);
  else {
    $('stageTitle').textContent = '请选择设备';
    $('deviceMount').replaceChildren(node('p', 'stage-loading', '链接中的设备无法确认，请从设备列表选择。'));
  }
  if ($('serviceUrl').value && launch.device && (launch.mode === 'service' || !browserProfile(launch.device.id)))
    await connectService();
  const sharedReference = (reference()?.composed || reference()?.composedProbe) && launch.sha256 === reference().sha256;
  if ((launch.firmware || sharedReference) && launch.autostart && launch.device) {
    if (lane()) await startRun();
    else message('launchNotice', '已读取链接中的设备与固件。此设备需要仿真服务，连接后点击开始运行。');
  }
}
function renderBrowserHistory() {
  const rows = browserQemuHistory();
  $('browserHistory').hidden = rows.length === 0;
  $('browserHistoryText').textContent = rows.map(row=>`${row.stopped_at} · ${row.receipt.deviceId||'cores3'} · ${row.receipt.firmwareSha256.slice(0,12)} · ${row.cleanup.gracefulExit ? '正常退出' : '已释放浏览器容器'}`).join('\n');
}
$('search').addEventListener('input', renderDevices);
$('unitSearch').addEventListener('input', renderUnits);
for (const button of document.querySelectorAll('[data-device-filter]'))
  button.addEventListener('click', () => {
    state.deviceFilter = button.dataset.deviceFilter;
    for (const b of document.querySelectorAll('[data-device-filter]'))
      b.setAttribute('aria-pressed', String(b === button));
    renderDevices();
  });
for (const button of document.querySelectorAll('[data-unit-filter]'))
  button.addEventListener('click', () => {
    state.unitFilter = button.dataset.unitFilter;
    for (const b of document.querySelectorAll('[data-unit-filter]'))
      b.setAttribute('aria-pressed', String(b === button));
    renderUnits();
  });
for (const input of document.querySelectorAll('[name="firmwareSource"]'))
  input.addEventListener('change', sourceChanged);
$('referenceExample').addEventListener('change', () => {
  $('firmwareSha').value='';
  $('shareStatus').textContent='';
  renderDetails();updateCapability();
});
for (const button of document.querySelectorAll('[data-view]'))
  button.addEventListener('click', () => view(button.dataset.view));
$('resetViewBtn').addEventListener('click', () => {
  state.shell?.resetView?.();
  if (!state.shell?.resetView) state.shell?.viewer?.fit();
});
$('startBtn').addEventListener('click', () => void startRun().catch(error));
$('stopBtn').addEventListener('click', () => void stopRun().catch(error));
$('cancelLoadBtn').addEventListener('click', () => void stopRun().catch(error));
$('runtimeMode').addEventListener('change', updateCapability);
$('unitConnectionPicker').addEventListener('change', updateCapability);
$('connectServiceBtn').addEventListener('click', () => void connectService());
for (const link of document.querySelectorAll('[data-service-console]'))
  link.addEventListener('click', (event) => {
    if (state.service) return;
    event.preventDefault();
    $('serviceConnection').open = true;
    message('serviceStatus', '设备会话与 WebBurner 是仿真服务控制台，请先连接你有权使用的服务。');
    $('serviceUrl').focus();
    $('serviceConnection').scrollIntoView({block: 'center'});
  });
$('openServiceBtn').addEventListener('click', () => {
  $('serviceConnection').open = true;
  $('serviceUrl').focus();
});
$('shareBtn').addEventListener('click', () => void share());
$('pauseBtn').addEventListener('click', async () => {
  const run = state.run;
  if (!active(run) || run.kind !== 'browser') return;
  try {
    await releaseInputs(run);
    await (run.controller.status === 'paused' ? run.controller.resume() : run.controller.pause());
  } catch (cause) {
    if (active(run)) error(cause);
  }
});
$('firmwareFile').addEventListener('change', () => {
  $('localFileName').textContent = $('firmwareFile').files[0]?.name || '选择 .bin 固件';
});
$('serialForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const run = state.run,
    text = $('serialInput').value;
  if (!active(run) || !text) return;
  if (run.kind !== 'browser') {
    error(new Error('当前服务未开放串口文本输入。'));
    return;
  }
  try {
    await run.controller.input({type: 'uart', text: text + '\n'});
    if (active(run)) $('serialInput').value = '';
  } catch (cause) {
    error(cause);
  }
});
$('browserPir').addEventListener('change', async (event) => {
  const run = state.run;
  if (!active(run) || !run.controller.profile?.inputs.pir) return;
  try { const receipt = await run.controller.input({type:'pir',motion:event.target.checked});
    $('browserPirState').textContent = receipt.result.motion ? 'QOM: MOTION' : 'QOM: CLEAR';
  } catch (cause) { error(cause); }
});
$('nativeScreenBtn').addEventListener('click',()=>{
  $('rawFramePanel').hidden=!$('rawFramePanel').hidden;
  $('nativeScreenBtn').textContent=$('rawFramePanel').hidden?'平面触屏':'收起平面触屏';
});
$('browserEvidenceBtn').addEventListener('click', () => {
  const controller = state.lastBrowserController;
  if (!controller?.receipt) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(controller.evidence(),null,2)],{type:'application/json'}));
  const link = document.createElement('a');link.href=url;link.download=`${controller.receipt.deviceId||'cores3'}-${controller.sessionId}.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('unitExplorer').addEventListener('toggle', () => {
  if ($('unitExplorer').open && !state.selectedUnit && state.units[0]) void selectUnit(state.units[0].id);
});
for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel'])
  $('rawFrameCanvas').addEventListener(type, (event) => {
    if (type === 'pointermove' && !event.buttons) return;
    const canvas = $('rawFrameCanvas'),
      rect = canvas.getBoundingClientRect();
    if (type === 'pointerdown') canvas.setPointerCapture(event.pointerId);
    void deliverInput({
      type: 'touch',
      x: Math.max(0, Math.min(canvas.width - 1, Math.floor(((event.clientX - rect.left) * canvas.width) / rect.width))),
      y: Math.max(
        0,
        Math.min(canvas.height - 1, Math.floor(((event.clientY - rect.top) * canvas.height) / rect.height)),
      ),
      down: ['pointerdown', 'pointermove'].includes(type),
    });
  });
window.addEventListener('blur', () => void releaseInputs());
window.addEventListener('pagehide', () => {
  state.selection++;
  state.unitSelection++;
  state.abort?.abort();
  state.run?.controller.stop();
  state.shell?.dispose();
  state.unitShell?.dispose();
  state.picker?.dispose();
});
void init().catch(error);
