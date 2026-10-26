import { createDeviceShell } from './device-shell-factory.js?v=20261026c';

const $ = id => document.getElementById(id);
const state = {
  catalog: null,
  peripheralById: {},
  inventory: null,
  selected: null,
  shell: null,
  filter: ''
};

function humanBytes(value) {
  if (value == null) return '未确认';
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`;
  return String(value);
}

function displayText(display) {
  if (!display) return '无板载显示屏';
  const diagonal = display.diagonal_in ? ` · ${display.diagonal_in}"` : '';
  return `${display.width}×${display.height} ${display.type}${diagonal}${display.touch ? ' · 触摸' : ''}`;
}

function dimensionsText(dimensions) {
  return dimensions ? `${dimensions.map(value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })).join(' × ')} mm` : '官方未确认';
}

async function init() {
  [state.catalog, state.inventory] = await Promise.all([
    fetch('/devices/catalog.json', { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error(`catalog HTTP ${response.status}`);
      return response.json();
    }),
    fetch('/api/peripherals', { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error(`peripherals HTTP ${response.status}`);
      return response.json();
    })
  ]);
  state.peripheralById = Object.fromEntries(
    state.inventory.devices.map(device => [device.id, device])
  );
  $('catalogChip').textContent =
    `${state.catalog.devices.length} devices · ${state.inventory.complete_devices}/${state.inventory.device_count} peripheral-complete`;
  $('search').addEventListener('input', event => {
    state.filter = event.target.value.trim().toLowerCase();
    renderNav();
  });
  renderNav();
  const preferred = new URLSearchParams(location.search).get('device');
  const first = state.catalog.devices.find(item => item.path === preferred) ||
    state.catalog.devices.find(item => item.id === 'stopwatch') ||
    state.catalog.devices[0];
  selectDevice(first.path);
}

function renderNav() {
  const nav = $('deviceNav');
  nav.innerHTML = '';
  for (const group of state.catalog.groups) {
    const devices = state.catalog.devices.filter(item => item.group === group.id).filter(item => {
      if (!state.filter) return true;
      const haystack = `${item.name} ${item.sku || ''} ${item.path} ${item.display?.driver || ''}`.toLowerCase();
      return haystack.includes(state.filter);
    });
    if (!devices.length) continue;
    const section = document.createElement('section');
    section.className = 'nav-group';
    section.innerHTML = `<h3 class="nav-group-title">${group.label}</h3>`;
    for (const device of devices) {
      const peripheral = state.peripheralById[device.id];
      const button = document.createElement('button');
      button.className = 'device-card' + (state.selected?.path === device.path ? ' active' : '');
      button.innerHTML = `
        <div class="device-card-top">
          <span class="device-card-name">${device.name}</span>
          <span class="status-chip ${device.runtime.status}"></span>
        </div>
        <div class="device-card-sku">${device.sku || ''} · ${device.runtime.status}</div>
        <div class="peripheral-badge ${peripheral?.complete ? 'ok' : 'partial'}">
          外设 ${peripheral?.complete ? '完整' : `${peripheral?.blocked_models?.length || '?'} 项待补`}
        </div>`;
      button.addEventListener('click', () => selectDevice(device.path));
      section.append(button);
    }
    nav.append(section);
  }
}

async function selectDevice(path) {
  const entry = state.catalog.devices.find(item => item.path === path);
  if (!entry) return;
  const device = await fetch(`/devices/${path}/device.json`, { cache: 'no-store' }).then(response => response.json());
  state.selected = device;
  renderNav();
  $('stageTitle').textContent = device.name;
  $('stageSub').textContent = `${device.group_label} · ${device.hardware.soc}`;
  for (const old of [$('deviceMount')]) old.innerHTML = '';
  state.shell = await createDeviceShell($('deviceMount'), device);
  for (const button of $('viewToggle').querySelectorAll('button')) {
    button.addEventListener('click', () => {
      for (const item of $('viewToggle').querySelectorAll('button')) item.classList.toggle('active', item === button);
      state.shell.setViewMode(button.dataset.view);
    });
  }
  state.shell.on('control', ({ id, down }) => {
    const control = device.hardware.controls?.find(item => item.id === id);
    state.shell.showOverlay(
      down ? 'Input captured' : 'Input released',
      `<span>${control?.label || id}</span><small>Open the standalone simulator to wire this input to firmware.</small>`
    );
  });
  $('openBtn').hidden = false;
  $('openBtn').href = `/devices/${path}/index.html`;
  renderDetails(device);
  history.replaceState(null, '', `/platform/web/index.html?device=${encodeURIComponent(path)}`);
}

function renderDetails(device) {
  const firmware = device.uiflow2?.firmware;
  const peripheral = state.peripheralById[device.id];
  $('detailName').textContent = device.name;
  $('detailSub').textContent = `${device.sku || 'SKU 未确认'} · ${device.runtime.status}`;
  const runtimeClass = device.runtime.status === 'reference-ready' ? 'ok' : device.runtime.status === 'backend-required' ? 'danger' : '';
  $('detailBody').innerHTML = `
    <div class="notice ${runtimeClass}">${device.status_label}</div>
    <div class="section">
      <div class="section-title">Official reference</div>
      <img class="reference-photo ${device.shell.cutout ? '' : 'raw'}" src="${device.shell.reference_image || ''}" alt="${device.name} official reference">
      <div class="reference-caption">官方产品主图，用于校准机身、屏幕与按键位置。</div>
    </div>
    <div class="section">
      <div class="section-title">Hardware</div>
      <dl class="kv">
        <dt>SoC</dt><dd>${device.hardware.soc}</dd>
        <dt>架构</dt><dd>${device.hardware.architecture}</dd>
        <dt>Flash</dt><dd>${humanBytes(device.hardware.flash_bytes)}</dd>
        <dt>PSRAM</dt><dd>${humanBytes(device.hardware.psram_bytes)}</dd>
        <dt>机身</dt><dd>${dimensionsText(device.hardware.dimensions_mm)}</dd>
        <dt>重量</dt><dd>${device.hardware.weight_g != null ? `${device.hardware.weight_g} g` : '未确认'}</dd>
        <dt>显示</dt><dd>${displayText(device.hardware.display)}</dd>
        <dt>传感器</dt><dd>${(device.hardware.sensors || []).join(', ') || '无'}</dd>
      </dl>
    </div>
    <div class="section">
      <div class="section-title">UIFlow2</div>
      <dl class="kv">
        <dt>支持</dt><dd>${device.uiflow2?.supported ? '是' : '否'}</dd>
        <dt>m5ui</dt><dd>${device.uiflow2?.m5ui ? '支持' : '不支持'}</dd>
        <dt>固件</dt><dd>${firmware ? `${firmware.version}<br><code>${firmware.firmware_id}</code>` : '无'}</dd>
      </dl>
    </div>
    <div class="section">
      <div class="section-title">Peripheral contract</div>
      <div class="notice ${peripheral?.complete ? 'ok' : 'danger'}">
        ${peripheral?.complete
          ? `${peripheral.components.length} 个外设组件全部闭环。`
          : `${peripheral?.blocked_models?.length || 0} 个阻断模型：${peripheral?.blocked_models?.join(', ') || '未知'}`}
      </div>
    </div>
    <div class="section">
      <div class="section-title">Runtime contract</div>
      <pre class="log" style="height:auto;max-height:160px">${JSON.stringify(device.runtime, null, 2)}</pre>
    </div>`;
}
init().catch(error => {
  document.body.innerHTML = `<main style="padding:40px"><h1>Catalog error</h1><pre>${error.stack || error.message}</pre></main>`;
});
