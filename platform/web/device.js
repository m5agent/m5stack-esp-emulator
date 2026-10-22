import { createDeviceShell } from './device-shell-factory.js?v=20261022c';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const requested = params.get('device');
const state = {
  catalog: null,
  device: null,
  shell: null,
  worker: null,
  firmware: null,
  firmwareName: null,
  peripheral: null,
  running: false,
  log: ''
};

function stripAnsi(value) {
  return value.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '');
}

function appendLog(value) {
  state.log = (state.log + stripAnsi(value)).slice(-120000);
  $('log').textContent = state.log;
  $('log').scrollTop = $('log').scrollHeight;
}

function setRuntimeNotice(kind, text) {
  const node = $('runtimeNotice');
  node.className = 'notice' + (kind ? ` ${kind}` : '');
  node.textContent = text;
}

function humanBytes(value) {
  if (value == null) return '未确认';
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`;
  if (value >= 1024) return `${(value / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KB`;
  return `${value} B`;
}

function displayText(display) {
  if (!display) return '无显示屏';
  const diagonal = display.diagonal_in ? ` · ${display.diagonal_in}"` : '';
  return `${display.width}×${display.height} ${display.type}${diagonal}${display.touch ? ' · 触摸' : ''}`;
}

function isNativeQemu(device) {
  return device?.runtime?.execution === 'native-qemu' ||
    device?.runtime?.backend?.startsWith('qemu-');
}

function dimensionsText(dimensions) {
  return dimensions ? `${dimensions.map(value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })).join(' × ')} mm` : '官方未确认';
}

async function loadDevice() {
  const catalog = await fetch('/devices/catalog.json', { cache: 'no-store' }).then(response => {
    if (!response.ok) throw new Error(`catalog: ${response.status}`);
    return response.json();
  });
  state.catalog = catalog;
  const entry = catalog.devices.find(item => item.path === requested);
  if (!entry) throw new Error(`Unknown device: ${requested || '(missing)'}`);
  const device = await fetch(`/devices/${entry.path}/device.json`, { cache: 'no-store' }).then(response => {
    if (!response.ok) throw new Error(`device: ${response.status}`);
    return response.json();
  });
  const peripheral = await fetch(`/api/peripherals/${encodeURIComponent(device.id)}`, { cache: 'no-store' }).then(response => {
    if (!response.ok) throw new Error(`peripherals: ${response.status}`);
    return response.json();
  });
  state.device = device;
  state.peripheral = peripheral;
  await render(device);
}

async function render(device) {
  document.title = `${device.name} · M5Stack Simulator`;
  $('brandTitle').textContent = `${device.name} Simulator`;
  $('brandSub').textContent = `${device.group_label} · ${device.hardware.soc}`;
  $('stageTitle').textContent = device.name;
  $('stageSub').textContent = `${device.hardware.soc} · ${device.shell.preset}`;
  $('deviceName').textContent = device.name;
  $('deviceSku').textContent = `${device.sku || 'SKU 未确认'} · ${device.group_label}`;
  const chip = $('runtimeChip');
  chip.className = `status-chip ${device.runtime.status}`;
  chip.textContent = device.runtime.status;

  state.shell = await createDeviceShell($('deviceMount'), device);
  for (const button of $('viewToggle').querySelectorAll('button')) {
    button.addEventListener('click', () => {
      for (const item of $('viewToggle').querySelectorAll('button')) item.classList.toggle('active', item === button);
      state.shell.setViewMode(button.dataset.view);
    });
  }
  state.shell.on('touch', ({ x, y, down }) => sendUart(`@tp ${x} ${y} ${down ? 1 : 0}\n`));
  state.shell.on('control', ({ id, gpio, down }) => {
    const control = (device.hardware.controls || []).find(item => item.id === id);
    if (gpio != null && state.worker) {
      state.worker.postMessage({ type: 'gpio', pin: gpio, high: !down });
      appendLog(`\n[input] ${control?.label || id} gpio${gpio}=${down ? 'pressed' : 'released'}\n`);
    } else if (control?.type === 'button') {
      const mapping = gpio == null ? 'GPIO mapping not yet modelled' : `gpio${gpio}; browser session not connected`;
      appendLog(`\n[input] ${control.label || id} ${down ? 'pressed' : 'released'} (${mapping})\n`);
    }
    postState();
  });

  const referencePhoto = $('referencePhoto');
  if (device.shell.reference_image) {
    referencePhoto.src = device.shell.reference_image;
    referencePhoto.alt = `${device.name} 官方参考图`;
    referencePhoto.classList.toggle('raw', !device.shell.cutout);
  } else {
    referencePhoto.parentElement.hidden = true;
  }

  const runtime = device.runtime;
  if (runtime.page) {
    $('referenceBtn').hidden = false;
    $('referenceBtn').href = runtime.page;
  }
  let runtimeText;
  let runtimeClass = '';
  if (isNativeQemu(device)) {
    if (runtime.status === 'reference-ready') {
      runtimeClass = 'ok';
      runtimeText = 'QEMU 虚拟主机已验证：参考固件可启动，目标尺寸首帧与输入重绘通过。本页面展示设备档案；执行与实时画面由本地矩阵或设备中心接入。';
    } else {
      runtimeClass = runtime.validation?.status === 'bootloader-panic' ? 'danger' : '';
      runtimeText = `本地 QEMU/esp-emu 后端状态：${runtime.status}。显示协议：${runtime.display_protocol || '未接入'}。`;
    }
    $('firmwareFile').disabled = true;
    $('fetchBtn').disabled = true;
    $('firmwareNotice').textContent = '该型号使用本地 QEMU 虚拟主机，不在浏览器 WASM 中执行。';
  } else if (runtime.status === 'reference-ready') {
    runtimeClass = 'ok';
    runtimeText = '该设备已有真实固件参考运行时；点击右上角“打开参考运行时”查看显示和交互。';
  } else if (runtime.status === 'boot-capable') {
    runtimeText = `WASM 后端可启动 ${device.hardware.soc} 固件并查看串口。板级显示适配：${runtime.display_protocol === 'pending' ? '待接入' : runtime.display_protocol}。`;
  } else {
    runtimeClass = 'danger';
    runtimeText = runtime.reason || '当前后端不支持该主控架构。';
    $('firmwareFile').disabled = true;
    $('fetchBtn').disabled = true;
    state.shell.showOverlay('Backend required', runtime.reason || '需要独立模拟后端');
  }
  const validation = runtime.validation;
  if (validation && validation.status !== 'not-run') {
    runtimeText += ` 验证：${validation.status}。${validation.detail}`;
    if (validation.status === 'bootloader-panic') runtimeClass = 'danger';
  }
  setRuntimeNotice(runtimeClass, runtimeText);

  const hardware = device.hardware;
  $('hardwareKv').innerHTML = [
    ['SoC', hardware.soc || '未确认'],
    ['架构', hardware.architecture || '未确认'],
    ['Flash', humanBytes(hardware.flash_bytes)],
    ['PSRAM', humanBytes(hardware.psram_bytes)],
    ['机身', dimensionsText(hardware.dimensions_mm)],
    ['重量', hardware.weight_g != null ? `${hardware.weight_g} g` : '未确认'],
    ['显示', displayText(hardware.display)],
    ['UIFlow2', device.uiflow2?.supported ? `支持${device.uiflow2.m5ui ? ' · m5ui' : ''}` : '不支持'],
    ['固件', device.uiflow2?.firmware ? `${device.uiflow2.firmware.version} / ${device.uiflow2.firmware.firmware_id}` : '无']
  ].map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join('');

  renderSensors(device);
  renderPeripherals(state.peripheral);
  $('firmwareFile').addEventListener('change', onFirmwareFile);
  $('fetchBtn').addEventListener('click', fetchUIFlow2);
  $('resetBtn').addEventListener('click', () => state.firmware && startFirmware(state.firmware, state.firmwareName));
  $('pauseBtn').addEventListener('click', togglePause);
  installAutomationApi();
  window.parent?.postMessage({ type: 'm5emu:ready', deviceId: device.id, status: runtime.status }, location.origin);
}

function renderPeripherals(peripheral) {
  const summary = $('peripheralSummary');
  const list = $('peripheralList');
  if (!peripheral) {
    summary.className = 'notice danger';
    summary.textContent = '外设契约不可用。';
    list.innerHTML = '';
    return;
  }
  const blocked = peripheral.blocked_models || [];
  const caseCount = (peripheral.runtime_cases?.matrix?.length || 0) +
    (peripheral.runtime_cases?.external?.length || 0);
  summary.className = `notice ${peripheral.complete ? 'ok' : 'danger'}`;
  summary.textContent = peripheral.complete
    ? `外设闭环：${peripheral.components.length} 个组件全部通过，${caseCount} 个运行时用例。`
    : `外设未闭环：${blocked.length} 个阻断项，${caseCount} 个运行时用例；${peripheral.completion_exemption
      ? `临时豁免至 ${peripheral.completion_exemption.review_by}`
      : '无豁免'}`;
  list.innerHTML = (peripheral.components || []).map(component => {
    const status = component.device_status || component.model_status || 'planned';
    const bus = [component.interface, component.address].filter(Boolean).join(' · ');
    return `<div class="peripheral-item ${status}">
      <div class="peripheral-item-top">
        <span class="peripheral-item-name">${component.id}</span>
        <span class="peripheral-item-model">${status}</span>
      </div>
      <div><span class="peripheral-item-model">${component.model}</span></div>
      ${bus ? `<div class="peripheral-item-bus">${bus}</div>` : ''}
      ${status !== 'simulated' && component.blocker
        ? `<div class="peripheral-item-blocker">${component.blocker}</div>`
        : ''}
    </div>`;
  }).join('');
}

function hasSensor(device, prefix) {
  return (device.hardware.sensors || []).some(value => value.startsWith(prefix));
}

function renderSensors(device) {
  const rows = [];
  if (hasSensor(device, 'imu')) {
    rows.push(slider('ax', 'IMU ax', -2, 2, .01, 0), slider('ay', 'IMU ay', -2, 2, .01, 0), slider('az', 'IMU az', -2, 2, .01, 1));
  }
  if (hasSensor(device, 'battery') || device.id === 'stopwatch') {
    rows.push(slider('battery', '电池 %', 0, 100, 1, 80));
  }
  if (hasSensor(device, 'rtc')) {
    rows.push(`<label>RTC</label><button class="btn" data-action="rtc">同步本机时间</button>`);
  }
  if (!rows.length) {
    $('sensorControls').className = 'notice';
    $('sensorControls').textContent = '此设备当前没有可注入的传感器模型。';
    return;
  }
  $('sensorControls').className = 'control-grid';
  $('sensorControls').innerHTML = rows.join('');
  for (const input of $('sensorControls').querySelectorAll('input[type=range]')) {
    input.addEventListener('input', () => {
      const output = $('sensorControls').querySelector(`output[for="${input.id}"]`);
      if (output) output.textContent = input.value;
      pushSensors();
    });
  }
  $('sensorControls').querySelector('[data-action="rtc"]')?.addEventListener('click', () => {
    const epoch = Math.floor(Date.now() / 1000);
    sendUart(`@rtc ${epoch}\n`);
    appendLog(`\n[input] rtc=${epoch}\n`);
  });
}

function slider(id, label, min, max, step, value) {
  return `<label for="${id}">${label}</label><output for="${id}">${value}</output><input id="${id}" type="range" min="${min}" max="${max}" step="${step}" value="${value}">`;
}

function pushSensors() {
  const ax = $('ax')?.value;
  if (ax != null) {
    const ay = $('ay').value;
    const az = $('az').value;
    sendUart(`@imu ${ax} ${ay} ${az} 0 0 0\n`);
  }
  const battery = $('battery')?.value;
  if (battery != null) {
    const mv = Math.round(3300 + Number(battery) * 9);
    sendUart(`@bat ${battery} ${mv} 0 1\n`);
  }
}

function sendUart(text) {
  if (!state.worker) return false;
  state.worker.postMessage({ type: 'uart_text', data: text });
  return true;
}

function postState() {
  if (!state.device) return;
  const payload = {
    type: 'm5emu:state',
    deviceId: state.device.id,
    status: state.device.runtime.status,
    running: state.running,
    frames: state.shell?.frameSeq || 0,
    firmware: state.firmwareName
  };
  window.parent?.postMessage(payload, location.origin);
}

async function onFirmwareFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  startFirmware(await file.arrayBuffer(), file.name);
}

async function fetchUIFlow2() {
  const firmware = state.device?.uiflow2?.firmware;
  if (!firmware?.download_url) {
    $('firmwareNotice').className = 'notice danger';
    $('firmwareNotice').textContent = '该设备没有可用的内置参考固件；可选择本地兼容镜像。';
    return;
  }
  $('fetchBtn').disabled = true;
  $('firmwareNotice').className = 'notice';
  $('firmwareNotice').textContent = `正在获取 ${firmware.version}…`;
  try {
    const response = await fetch(firmware.download_url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    startFirmware(await response.arrayBuffer(), `UIFlow2-${state.device.id}-${firmware.version}.bin`);
  } catch (error) {
    $('firmwareNotice').className = 'notice danger';
    $('firmwareNotice').textContent = `浏览器直连下载失败：${error.message}。可使用 fetch_firmware.py 预先缓存。`;
  } finally {
    $('fetchBtn').disabled = false;
  }
}

function startFirmware(buffer, name = 'firmware.bin') {
  const device = state.device;
  if (!device || device.runtime.status === 'backend-required') return;
  if (isNativeQemu(device) && !device.runtime.page) {
    state.shell.showOverlay('Local QEMU host', '该型号由本地 QEMU 执行，当前浏览器页面不承载固件 worker。');
    $('firmwareNotice').className = 'notice';
    $('firmwareNotice').textContent = '请使用 tests/uiflow2/run_device_matrix.py 或后续设备中心接口启动该虚拟主机。';
    return;
  }
  if (state.worker) {
    state.worker.onmessage = null;
    state.worker.terminate();
  }
  state.firmware = buffer.slice(0);
  state.firmwareName = name;
  state.running = true;
  state.log = '';
  $('log').textContent = '';
  $('pauseBtn').disabled = false;
  $('resetBtn').disabled = false;
  $('firmwareNotice').className = 'notice';
  $('firmwareNotice').textContent = `${name} · ${humanBytes(buffer.byteLength)} · 启动中…`;
  state.shell.showOverlay('Booting…', `${device.hardware.soc} · ${name}`);
  state.shell.setLed(device.shell.accent);

  const worker = new Worker('/platform/web/emulator-worker.js?v=20261020a', { type: 'module' });
  state.worker = worker;
  worker.onmessage = event => {
    const message = event.data;
    if (message.type === 'started') {
      $('firmwareNotice').className = 'notice ok';
      $('firmwareNotice').textContent = `${name} 已装载到 ${device.hardware.soc} WASM。`;
      if (device.runtime.display_protocol !== 'm5emu-shared-v1') {
        state.shell.showOverlay('Firmware running', '串口已连接；该型号的板级 framebuffer 适配尚未接入。');
      }
      appendLog(`\n[boot] ${message.chip} firmware loaded\n`);
      postState();
    } else if (message.type === 'uart') {
      appendLog(message.data);
    } else if (message.type === 'shared') {
      appendLog(`\n[display] shared=0x${message.address.toString(16)}\n`);
    } else if (message.type === 'frame') {
      state.shell.setFrame(message.pixels, message.width, message.height, message.sequence);
      postState();
    } else if (message.type === 'fatal') {
      state.running = false;
      $('pauseBtn').disabled = true;
      state.shell.showOverlay('Emulator stopped', message.message);
      appendLog(`\n[fatal] ${message.message}\n`);
      postState();
    } else if (message.type === 'state') {
      state.lastState = message;
    }
  };
  worker.onerror = event => {
    state.running = false;
    appendLog(`\n[worker error] ${event.message}\n`);
  };
  worker.postMessage({
    type: 'init',
    chip: device.runtime.chip,
    firmware: state.firmware,
    displayProtocol: device.runtime.display_protocol
  });
  postState();
}

function togglePause() {
  if (!state.worker) return;
  state.running = !state.running;
  state.worker.postMessage({ type: state.running ? 'resume' : 'pause' });
  $('pauseBtn').textContent = state.running ? '暂停' : '继续';
  postState();
}

function press(controlId, down) {
  const control = state.device?.hardware.controls?.find(item => item.id === controlId);
  if (!control) return false;
  if (control.gpio != null && state.worker) state.worker.postMessage({ type: 'gpio', pin: control.gpio, high: !down });
  appendLog(`\n[input] ${control.label || controlId} ${down ? 'pressed' : 'released'}\n`);
  return true;
}

function installAutomationApi() {
  window.m5emu = {
    deviceId: state.device.id,
    loadFirmware: (buffer, name = 'automation-firmware.bin') => startFirmware(buffer instanceof ArrayBuffer ? buffer : buffer.buffer, name),
    loadFirmwareUrl: async url => {
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      startFirmware(await response.arrayBuffer(), url.split('/').pop());
    },
    reset: () => state.firmware && startFirmware(state.firmware, state.firmwareName),
    pause: () => state.worker?.postMessage({ type: 'pause' }),
    resume: () => state.worker?.postMessage({ type: 'resume' }),
    press,
    touch: (x, y, down) => sendUart(`@tp ${x} ${y} ${down ? 1 : 0}\n`),
    setImu: (ax, ay, az, gx = 0, gy = 0, gz = 0) => sendUart(`@imu ${ax} ${ay} ${az} ${gx} ${gy} ${gz}\n`),
    setBattery: (pct, mv, charging = false, vbus = true) => sendUart(`@bat ${pct} ${mv} ${charging ? 1 : 0} ${vbus ? 1 : 0}\n`),
    setRtc: epoch => sendUart(`@rtc ${epoch}\n`),
    execPython: code => {
      if (!state.worker) return false;
      const encoder = new TextEncoder();
      state.worker.postMessage({ type: 'uart_bytes', data: [...encoder.encode('\r\x03\x03')] });
      setTimeout(() => state.worker?.postMessage({ type: 'uart_bytes', data: [...encoder.encode('\r\x01')] }), 120);
      setTimeout(() => state.worker?.postMessage({ type: 'uart_bytes', data: [...encoder.encode(`${code}\r\x04`)] }), 240);
      return true;
    },
    getFrame: () => state.shell?.frameDataUrl(),
    getLog: () => state.log,
    getState: () => ({ deviceId: state.device.id, running: state.running, frames: state.shell?.frameSeq || 0, firmware: state.firmwareName, lastState: state.lastState || null }),
    screenshot: () => state.shell?.frameDataUrl()
  };
  window.m5emu.ready = true;
}

loadDevice().catch(error => {
  document.body.innerHTML = `<main style="padding:40px"><h1>Device profile error</h1><pre>${error.stack || error.message}</pre></main>`;
});
