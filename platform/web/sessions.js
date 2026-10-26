import { createDeviceShell } from './device-shell-factory.js?v=20261026g';
import { createUnitPanel, createUnitPicker } from './unit-panel.js?v=20261026g';
import { createProgramPanel } from './program-panel.js';

const ACTIVE_STATES = new Set(['provisioning', 'flashing', 'booting', 'running']);
const THREE_PREVIEW_LIMIT = 4;
const FRAME_INTERVAL_MS = 125;
const FRAME_REQUEST_TIMEOUT_MS = 3000;
const HIDDEN_FRAME_INTERVAL_MS = 1000;
const CONTROL_RELEASE_TIMEOUT_MS = 5000;

const state = {
  devices: [],
  devicePaths: new Map(),
  deviceProfiles: new Map(),
  sessions: [],
  serial: new Map(),
  visuals: new Map(),
  deviceStates: new Map(),
  token: sessionStorage.getItem('m5-service-token') || '',
  busy: false,
  showHistory: false,
  frameLoopStarted: false,
  unitPicker: null,
  unitPickerGeneration: 0,
  unitPickerDeviceId: null,
  creating: false,
};

const $ = id => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  const response = await fetch(path, { ...options, headers });
  const type = response.headers.get('Content-Type') || '';
  const body = type.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.error?.message || body?.error || String(body);
    throw new Error(`${response.status}: ${message}`);
  }
  return body;
}

function showError(message) {
  const banner = $('errorBanner');
  if (!message) {
    banner.hidden = true;
    banner.textContent = '';
    return;
  }
  banner.hidden = false;
  banner.textContent = message;
}

function deviceFor(deviceId) {
  return state.devices.find(device => device.device_id === deviceId) || {};
}

function statusClass(value) {
  if (value === 'running') return 'ok';
  if (value === 'failed') return 'danger';
  return '';
}

function framePlaceholder(session) {
  const display = session.display;
  if (!display?.width || !display?.height) return 'serial-only device';
  if (session.last_frame_available) return '加载最后一帧…';
  if (['stopped', 'failed'].includes(session.state)) return '该历史会话未保存最后一帧';
  return '等待应用首帧…';
}

function formatTime(value) {
  if (!value) return '未记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits).replace(/\.?0+$/, '') : '—';
}

class SessionVisual {
  constructor(container, session, allowThree) {
    this.container = container;
    this.session = session;
    this.shell = null;
    this.frameBlob = null;
    this.frameUrl = null;
    this.lastFrameHash = null;
    this.frameEtag = null;
    this.frameMetadata = null;
    this.frameGeneration = 0;
    this.frameRequest = null;
    this.frameOwnerKey = this.frameOwner();
    this.lastFrameAt = 0;
    this.lastFrameAttemptAt = 0;
    this.frameApply = Promise.resolve();
    this.controlQueues = new Map();
    this.activeControls = new Set();
    this.controlReleaseTimers = new Map();
    this.destroyed = false;
    this.allowThree = allowThree;
    this.threeAttempted = false;
    this.shellGeneration = 0;
    this.shellLoading = false;
    this.placeholder = framePlaceholder(session);
    this.container.innerHTML = `<span class="no-frame">${escapeHtml(this.placeholder)}</span>`;
    const programContainer = this.container.closest('.session-card')?.querySelector('[data-program-panel]');
    if (programContainer) this.programPanel = createProgramPanel(programContainer, {session, api});
    const unitContainer = this.container.closest('.session-card')?.querySelector('[data-unit-panel]');
    if (unitContainer) {
      createUnitPanel(unitContainer, { session, shell: null, api }).then(panel => {
        if (this.destroyed) { panel.dispose(); return; }
        this.unitPanel = panel;
        panel.updateSession(this.session);
        if (this.shell) panel.setShell(this.shell);
      }).catch(error => console.warn('Unit panel initialization failed.', error));
    }
    this.init().catch(error => {
      console.warn('Session preview initialization failed.', error);
      this.setMessage(this.placeholder);
    });
  }

  updateSession(session) {
    const owner = this.frameOwner(session);
    if (owner !== this.frameOwnerKey) {
      this.invalidateFrame();
      this.releaseActiveControls();
      this.shellGeneration += 1;
      this.threeAttempted = false;
      this.unitPanel?.setShell(null);
      this.shell?.dispose();
      this.shell = null;
      this.container.classList.remove('is-three', 'has-frame');
      this.container.replaceChildren();
    }
    this.session = session;
    this.frameOwnerKey = owner;
    this.unitPanel?.updateSession(session);
    this.programPanel?.updateSession(session);
    if (!ACTIVE_STATES.has(session.state)) this.releaseActiveControls();
    if (!this.frameBlob && !this.shell) {
      this.placeholder = framePlaceholder(session);
      this.setMessage(this.placeholder);
    }
    if (this.allowThree && !this.threeAttempted) {
      this.init().catch(error => console.warn('Session preview initialization failed.', error));
    }
  }

  frameOwner(session = this.session) {
    return JSON.stringify([session.session_id, session.created_at, session.device_id,
      session.firmware_sha256, session.pid]);
  }

  invalidateFrame() {
    this.frameGeneration = (this.frameGeneration || 0) + 1;
    this.frameRequest?.cancel();
    this.frameRequest = null;
    this.frameApply = Promise.resolve();
    this.frameBlob = null;
    this.lastFrameHash = null;
    this.frameEtag = null;
    this.frameMetadata = null;
    this.lastFrameAt = this.lastFrameAttemptAt = 0;
    if (this.frameUrl) URL.revokeObjectURL(this.frameUrl);
    this.frameUrl = null;
  }

  setThreeAllowed(allowThree) {
    const changed = this.allowThree !== allowThree;
    this.allowThree = allowThree;
    if (changed && !allowThree) {
      this.shellGeneration += 1;
      this.threeAttempted = false;
      this.releaseActiveControls();
      this.unitPanel?.setShell(null);
      this.shell?.dispose();
      this.shell = null;
      this.frameApply = Promise.resolve();
      this.container.classList.remove('is-three');
      if (this.frameBlob) this.setGenericFrame(this.frameBlob);
      else this.setMessage(this.placeholder);
    }
    if (allowThree && !this.threeAttempted) {
      this.init().catch(error => {
        console.warn('Session preview initialization failed.', error);
        this.setMessage(this.placeholder);
      });
    }
  }

  async init() {
    if (!this.allowThree || this.threeAttempted || this.shellLoading) return;
    const generation = ++this.shellGeneration;
    this.threeAttempted = true;
    const catalogPath = state.devicePaths.get(this.session.device_id);
    if (!catalogPath) {
      this.threeAttempted = false;
      return;
    }
    let profile = state.deviceProfiles.get(this.session.device_id);
    if (!profile) {
      const response = await fetch(`/devices/${catalogPath}/device.json`, { cache: 'no-store' });
      if (!response.ok) {
        this.threeAttempted = false;
        return;
      }
      profile = await response.json();
      state.deviceProfiles.set(this.session.device_id, profile);
    }
    if (this.destroyed || !this.allowThree || generation !== this.shellGeneration) return;
    this.shellLoading = true;
    // Constructors and disposal may replace their host's children. Give each
    // load its own detached mount so a stale result never touches a new owner.
    const mount = document.createElement('div');
    mount.style.width = '100%';
    mount.style.height = '100%';
    mount.style.minWidth = '0';
    mount.style.minHeight = '0';
    let shell = null;
    try {
      shell = await createDeviceShell(mount, profile, { live: true });
      if (this.destroyed || !this.allowThree || generation !== this.shellGeneration) { shell.dispose?.(); return; }
      this.container.replaceChildren(mount);
      this.container.classList.add('is-three');
      this.shell = shell;
      this.unitPanel?.setShell(shell);
      this.shell.setViewMode('shell');
      this.shell.on('control', event => this.handleControl(event));
      this.shell.on('unit-input', event => this.unitPanel?.handleInput(event));
      this.shell.on('reset', () => {
        if (this.session.state !== 'running') return;
        api(`/api/v1/sessions/${encodeURIComponent(this.session.session_id)}/reset`, { method: 'POST' })
          .catch(error => console.warn('Session reset failed.', error));
      });
      this.shell.on('touch', ({ x, y, action }) => {
        if (action !== 'start' || this.session.state !== 'running') return;
        api(`/api/v1/sessions/${encodeURIComponent(this.session.session_id)}/input`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: 'touch', x, y, settle_seconds: 0.05 }),
        }).catch(error => console.warn('Session touch injection failed.', error));
      });
      this.shell.setDeviceState?.(state.deviceStates.get(this.session.session_id));
      if (this.frameBlob) await this.applyThreeFrame();
    } catch (error) {
      if (shell) {
        if (this.shell === shell) {
          this.unitPanel?.setShell(null);
          this.shell = null;
        }
        try { shell.dispose?.(); }
        catch (cleanupError) { console.warn('Session shell cleanup failed.', cleanupError); }
      }
      if (this.destroyed || !this.allowThree || generation !== this.shellGeneration || this.shell) return;
      console.warn('3D session preview unavailable; using the framebuffer image.', error);
      this.container.classList.remove('is-three');
      this.setMessage(this.placeholder);
      if (this.frameBlob) this.setGenericFrame(this.frameBlob);
    } finally {
      this.shellLoading = false;
      if (!this.destroyed && this.allowThree && !this.shell && generation !== this.shellGeneration) {
        this.threeAttempted = false;
        this.init().catch(error => console.warn('Session preview retry failed.', error));
      }
    }
  }

  setMessage(message) {
    if (this.shell || this.frameBlob) return;
    this.container.innerHTML = `<span class="no-frame">${escapeHtml(message)}</span>`;
  }

  async setFrame(blob, hash = null, commitGuard = () => true) {
    const owner = this.frameOwner();
    const current = () => !this.destroyed && this.frameOwner() === owner && commitGuard();
    if (!current()) return false;
    const applied = this.shell
      ? await this.applyThreeFrame(blob, current)
      : await this.setGenericFrame(blob, current);
    if (!current() || applied === false) return false;
    this.frameBlob = blob;
    this.lastFrameHash = hash;
    this.lastFrameAt = Date.now();
    return true;
  }

  applyThreeFrame(blob = this.frameBlob, commitGuard = null) {
    const shell = this.shell, owner = this.frameOwner(), generation = this.shellGeneration;
    const current = () => !this.destroyed && this.shell === shell &&
      this.shellGeneration === generation && this.frameOwner() === owner &&
      (commitGuard ? commitGuard() : this.frameBlob === blob);
    this.frameApply = (this.frameApply || Promise.resolve())
      .catch(() => {})
      .then(async () => {
        if (!shell || !blob || !current()) return false;
        const applied = await shell.setImage(blob, undefined, current);
        return current() && applied !== false;
      });
    return this.frameApply;
  }

  async setGenericFrame(blob, commitGuard = null) {
    const owner = this.frameOwner();
    const url = URL.createObjectURL(blob);
    let committed = false;
    try {
      const image = document.createElement('img');
      image.className = 'session-frame';
      image.alt = `${this.session.device_id} live frame`;
      image.src = url;
      await image.decode();
      if (this.destroyed || this.shell || this.frameOwner() !== owner ||
          !(commitGuard ? commitGuard() : this.frameBlob === blob)) return false;
      if (this.frameUrl) URL.revokeObjectURL(this.frameUrl);
      this.frameUrl = url;
      this.container.replaceChildren(image);
      this.container.classList.add('has-frame');
      committed = true;
      return true;
    } catch {
      return false;
    } finally {
      if (!committed) URL.revokeObjectURL(url);
    }
  }

  controlKey(id) {
    return id === 'power' ? 'p' : id;
  }

  handleControl({ id, key: runtimeKey, down }) {
    if (this.session.state !== 'running') return;
    const key = runtimeKey || this.controlKey(id);
    if (down) {
      this.activeControls.add(key);
      clearTimeout(this.controlReleaseTimers.get(key));
      this.enqueueControl(key, 'down');
      this.controlReleaseTimers.set(
        key,
        setTimeout(() => {
          this.activeControls.delete(key);
          this.enqueueControl(key, 'up');
        }, CONTROL_RELEASE_TIMEOUT_MS),
      );
      return;
    }
    clearTimeout(this.controlReleaseTimers.get(key));
    this.controlReleaseTimers.delete(key);
    this.activeControls.delete(key);
    this.enqueueControl(key, 'up');
  }

  enqueueControl(key, action, keepalive = false) {
    const sessionId = this.session.session_id;
    const previous = this.controlQueues.get(key) || Promise.resolve();
    const request = previous
      .catch(() => {})
      .then(() => api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/input`, {
        method: 'POST',
        keepalive,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'key', key, action, settle_seconds: 0.02 }),
      }))
      .catch(error => console.warn(`Session key ${action} injection failed.`, error));
    this.controlQueues.set(key, request);
    request.finally(() => {
      if (this.controlQueues.get(key) === request) this.controlQueues.delete(key);
    });
  }

  releaseActiveControls() {
    for (const key of this.activeControls) {
      this.enqueueControl(key, 'up', true);
      clearTimeout(this.controlReleaseTimers.get(key));
    }
    this.activeControls.clear();
    this.controlReleaseTimers.clear();
  }

  destroy() {
    this.destroyed = true;
    this.invalidateFrame();
    this.releaseActiveControls();
    this.unitPanel?.dispose();
    this.programPanel?.dispose();
    this.shell?.dispose();
    this.shell = null;
    if (this.frameUrl) URL.revokeObjectURL(this.frameUrl);
    this.frameUrl = null;
  }
}

function createSessionCard(session, allowThree) {
  const device = deviceFor(session.device_id);
  const card = document.createElement('article');
  card.className = 'panel session-card';
  card.dataset.sessionId = session.session_id;
  card.innerHTML = `
    <div class="session-visual">
      <span class="no-frame">${escapeHtml(framePlaceholder(session))}</span>
    </div>
    <div class="session-body">
      <div class="session-title-row">
        <span class="session-title" data-field="title">${escapeHtml(device.name || session.device_id)}</span>
        <span class="status-chip" data-field="state">${escapeHtml(session.state)}</span>
        <span class="session-id" data-field="session-id">${escapeHtml(session.session_id)}</span>
      </div>
      <div class="session-meta">
        <span data-field="device-id">${escapeHtml(session.device_id)}</span>
        <span data-field="firmware-source">${escapeHtml(session.firmware_source || 'firmware')}</span>
        <span data-field="firmware-sha">${escapeHtml((session.firmware_sha256 || '').slice(0, 12))}</span>
        <span data-field="serial-bytes">${escapeHtml(session.serial_bytes || 0)} bytes</span>
        <span data-field="flash">flash 未确认</span>
        <span data-field="last-frame">frame 未记录</span>
      </div>
      <div class="session-warning" data-field="warning" hidden></div>
      <div class="session-runtime" data-field="runtime" hidden>
        <span><small>Battery</small><strong data-runtime="battery">—</strong></span>
        <span><small>Power</small><strong data-runtime="power">—</strong></span>
        <span><small>Audio PA</small><strong data-runtime="audio">—</strong></span>
        <span><small>PMIC inputs</small><strong data-runtime="pmic-inputs">—</strong></span>
        <span><small>Accel</small><strong data-runtime="accel">—</strong></span>
        <span><small>Gyro</small><strong data-runtime="gyro">—</strong></span>
      </div>
      <div class="session-runtime-note" data-field="runtime-note" hidden></div>
      <div data-unit-panel></div>
      <div data-program-panel></div>
      <div class="session-actions">
        <button class="btn" data-action="wait" type="button">等待运行</button>
        <button class="btn" data-action="renew" type="button">续期</button>
        <button class="btn" data-action="reset" type="button">复位</button>
        <button class="btn" data-action="stop" type="button">停止</button>
      </div>
      <pre class="session-serial" data-field="serial">等待串口输出…</pre>
    </div>`;
  const visualNode = card.querySelector('.session-visual');
  state.visuals.set(
    session.session_id,
    new SessionVisual(visualNode, session, allowThree)
  );
  updateSessionCard(card, session);
  return card;
}

function updateSessionCard(card, session) {
  const device = deviceFor(session.device_id);
  const field = name => card.querySelector(`[data-field="${name}"]`);
  field('title').textContent = device.name || session.device_id;
  const status = field('state');
  status.className = `status-chip ${statusClass(session.state)}`;
  status.textContent = session.state;
  field('session-id').textContent = session.session_id;
  field('device-id').textContent = session.device_id;
  field('firmware-source').textContent = session.firmware_source || 'firmware';
  field('firmware-sha').textContent = (session.firmware_sha256 || '').slice(0, 12);
  field('serial-bytes').textContent = `${session.serial_bytes || 0} bytes`;
  const flash = session.flash || {};
  field('flash').textContent = flash.verified
    ? `flash verified · ${Math.round((flash.flash_size || 0) / 1024 / 1024)} MB`
    : `flash ${flash.transport || '未确认'}`;
  field('last-frame').textContent = session.last_frame_captured_at
    ? `frame ${formatTime(session.last_frame_captured_at)}`
    : 'frame 未记录';
  const warning = field('warning');
  const warningParts = [];
  if (session.interrupted) {
    warningParts.push(session.error || '服务重启时该会话尚未结束，已标记为中断。');
  } else if (session.error) {
    warningParts.push(`会话错误：${session.error}`);
  }
  if (device.warnings?.length) {
    warningParts.push(`partial: ${device.warnings.join(' ')}`);
  }
  const warningText = warningParts.join(' ');
  warning.hidden = !warningText;
  warning.textContent = warningText.slice(0, 500);
  const active = ACTIVE_STATES.has(session.state);
  card.querySelector('[data-action="wait"]').disabled = !active;
  card.querySelector('[data-action="renew"]').disabled = !active;
  card.querySelector('[data-action="reset"]').disabled = session.state !== 'running';
  card.querySelector('[data-action="stop"]').disabled = !active;
  card.querySelector('.session-body').dataset.sessionState = session.state;
  state.visuals.get(session.session_id)?.updateSession(session);
  updateDeviceStateUi(card, state.deviceStates.get(session.session_id), session);
}

function render() {
  const list = $('sessionList');
  const wanted = state.sessions
    .slice()
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  if (!wanted.length) {
    for (const visual of state.visuals.values()) visual.destroy();
    state.visuals.clear();
    list.innerHTML = `<div class="panel empty-state">${state.showHistory ? '还没有虚拟设备会话记录。' : '当前没有活动或近期完成的虚拟设备会话。'}</div>`;
    return;
  }
  list.querySelector('.empty-state')?.remove();
  const existing = new Map(
    [...list.querySelectorAll('[data-session-id]')].map(card => [card.dataset.sessionId, card])
  );
  const wantedIds = new Set(wanted.map(session => session.session_id));
  for (const [sessionId, card] of existing) {
    if (wantedIds.has(sessionId)) continue;
    state.visuals.get(sessionId)?.destroy();
    state.visuals.delete(sessionId);
    state.deviceStates.delete(sessionId);
    card.remove();
  }
  // Moving an existing card detaches its canvas, cancels pointer capture and
  // can make an active 3D drag jump the document to the top.
  let cursor = list.firstElementChild;
  for (const [index, session] of wanted.entries()) {
    const allowThree = index < THREE_PREVIEW_LIMIT;
    const card = existing.get(session.session_id) || createSessionCard(session, allowThree);
    state.visuals.get(session.session_id)?.setThreeAllowed(allowThree);
    updateSessionCard(card, session);
    if (card === cursor) {
      cursor = card.nextElementSibling;
    } else {
      list.insertBefore(card, cursor);
    }
  }
}

function renderDevices() {
  const select = $('deviceSelect');
  const rows = state.devices.filter(device => device.creatable);
  select.innerHTML = rows.map(device => `
    <option value="${escapeHtml(device.device_id)}">
      ${escapeHtml(device.name)} (${escapeHtml(device.device_id)})${device.peripheral_status === 'partial' ? ' · partial' : ''}
    </option>`).join('');
  updateProgramMode();
}

function updateProgramMode() {
  const modes = deviceFor($('deviceSelect').value).program_modes;
  const enabled = Array.isArray(modes) && modes.includes('uiflow-live');
  const input = $('programModeInput');
  input.disabled = !enabled;
  if (!enabled) input.checked = false;
  $('createBtn').textContent = input.checked ? '创建编程设备' : '创建参考设备';
  $('programModeHint').textContent = enabled
    ? '创建后可在当前设备中反复运行源码，屏幕和 Unit 状态随程序更新。'
    : '该型号暂未开放实时编程，可继续创建参考设备。';
  updateCreateControls();
}

function updateCreateControls() {
  const deviceId = $('deviceSelect').value;
  $('createBtn').disabled = state.creating || !deviceId
    || state.unitPickerDeviceId !== deviceId || state.unitPicker?.readyDeviceId !== deviceId;
}

async function loadUnitPicker(deviceId) {
  const generation = ++state.unitPickerGeneration;
  state.unitPicker?.dispose();
  state.unitPicker = null;
  state.unitPickerDeviceId = null;
  updateCreateControls();
  // An initial createUnitPicker() can still be awaiting its first catalog.
  // Give every load its own mount so a late old load/dispose cannot touch the
  // selected device's controls, even before its picker has been published.
  const mount = document.createElement('div');
  mount.dataset.unitPickerDeviceId = deviceId;
  $('unitPicker').replaceChildren(mount);
  const current = () => generation === state.unitPickerGeneration && $('deviceSelect').value === deviceId;
  try {
    const picker = await createUnitPicker(mount, {api, deviceId});
    if (!current()) { picker.dispose(); return; }
    state.unitPicker = picker;
    state.unitPickerDeviceId = deviceId;
    if (picker.loadError) showError(`Unit 配置读取失败：${picker.loadError}`);
  } catch (error) {
    if (current()) showError(`Unit 配置读取失败：${error.message}`);
  } finally {
    if (current()) updateCreateControls();
  }
}

function renderCapacity(capacity) {
  $('capacityChip').textContent = `${capacity.active_sessions}/${capacity.max_sessions} active`;
  $('sessionSub').textContent = `network disabled · ${capacity.available_sessions} slot(s) available`;
  const summary = $('serviceSummary');
  summary.className = 'notice ok';
  summary.textContent = `API online · ${capacity.active_sessions}/${capacity.max_sessions} active · network disabled`;
}

async function loadCatalog() {
  const [payload, catalog] = await Promise.all([
    api('/api/v1/devices'),
    fetch('/devices/catalog.json', { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error(`catalog ${response.status}`);
      return response.json();
    }),
  ]);
  state.devices = payload.devices || [];
  state.devicePaths = new Map(catalog.devices.map(device => [device.id, device.path]));
  renderDevices();
  await loadUnitPicker($('deviceSelect').value);
}

async function refreshSessions() {
  if (state.busy) return;
  state.busy = true;
  try {
    const [sessionsPayload, capacity] = await Promise.all([
      api('/api/v1/sessions'),
      api('/api/v1/capacity'),
    ]);
    const allSessions = sessionsPayload.sessions || [];
    const recentCutoff = Date.now() - 30 * 60 * 1000;
    state.sessions = state.showHistory
      ? allSessions
      : allSessions.filter(session => {
          if (!ACTIVE_STATES.has(session.state)) {
            const recent = Date.parse(session.completed_at || session.created_at) >= recentCutoff;
            return recent;
          }
          return true;
        });
    renderCapacity(capacity);
    render();
    showError('');
    const serialSessions = state.sessions.filter(
      session => ACTIVE_STATES.has(session.state) || session.serial_bytes > 0
    );
    const stateSessions = state.sessions.filter(session => session.device_state_supported);
    await Promise.all([
      ...serialSessions.map(refreshSerial),
      ...stateSessions.map(refreshDeviceState),
    ]);
    startFrameLoop();
  } catch (error) {
    showError(error.message);
  } finally {
    state.busy = false;
  }
}

async function refreshSerial(session) {
  const current = state.serial.get(session.session_id) || { offset: 0, text: '' };
  try {
    const chunk = await api(
      `/api/v1/sessions/${encodeURIComponent(session.session_id)}/serial?offset=${current.offset}&limit=65536`
    );
    if (chunk.next_offset < current.offset) {
      current.offset = 0;
      current.text = '';
    }
    current.offset = chunk.next_offset;
    current.text = (current.text + chunk.data).slice(-120000);
    state.serial.set(session.session_id, current);
    const node = document.querySelector(
      `[data-session-id="${session.session_id}"] [data-field="serial"]`
    );
    if (node) {
      node.textContent = current.text || '等待串口输出…';
      node.scrollTop = node.scrollHeight;
    }
  } catch (error) {
    showError(error.message);
  }
}

async function refreshFrame(session) {
  const visual = state.visuals.get(session.session_id);
  if (!visual || visual.destroyed || visual.frameOwner(session) !== visual.frameOwner()) return;
  if (visual.frameRequest) return;
  const active = ACTIVE_STATES.has(session.state);
  if (!active) {
    if (visual.frameBlob || Date.now() - visual.lastFrameAttemptAt < 5000) return;
    visual.lastFrameAttemptAt = Date.now();
  }
  const headers = new Headers();
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  // Only the QMP-backed lane owns the capture/mutation lock used by previews.
  const preview = session.runtime === 'qemu' || session.runtime?.startsWith('qemu-');
  if (preview && visual.frameEtag && visual.frameBlob) headers.set('If-None-Match', visual.frameEtag);
  const owner = visual.frameOwner(), generation = ++visual.frameGeneration;
  const controller = new AbortController();
  let cancel;
  const cancelled = new Promise(resolve => { cancel = resolve; });
  const request = {
    cancelled: false,
    cancel() {
      if (this.cancelled) return;
      this.cancelled = true;
      controller.abort();
      // A decoder cannot be aborted. Let the next request proceed, while its
      // old commit guard prevents any eventual draw into the current owner.
      if (visual.frameRequest === this) visual.frameApply = Promise.resolve();
      cancel();
    },
  };
  visual.frameRequest = request;
  const current = () => !request.cancelled && !visual.destroyed &&
    state.visuals.get(session.session_id) === visual && visual.frameOwner() === owner &&
    visual.frameRequest === request && visual.frameGeneration === generation;
  const timer = setTimeout(() => request.cancel(), FRAME_REQUEST_TIMEOUT_MS);
  try {
    await Promise.race([cancelled, (async () => {
      const query = preview ? `max_age_ms=${FRAME_INTERVAL_MS}` : `t=${Date.now()}`;
      const response = await fetch(
        `/api/v1/sessions/${encodeURIComponent(session.session_id)}/frame.png?${query}`,
        { headers, signal: controller.signal, cache: 'no-store' }
      );
      if (!current()) return;
      const metadata = Object.fromEntries([...response.headers].filter(([name]) => name.startsWith('x-frame-')));
      if (response.status === 304) {
        if (preview && visual.frameBlob && headers.has('If-None-Match')) visual.frameMetadata = metadata;
        return;
      }
      if (!response.ok) throw new Error(`frame ${response.status}`);
      const blob = await response.blob();
      if (!current()) return;
      const applied = await visual.setFrame(blob, response.headers.get('X-Frame-SHA256'), current);
      if (!current() || !applied) return;
      // Capture context is informational, including executions started by an
      // external agent. It is not an application-ready acknowledgement.
      visual.frameMetadata = metadata;
      visual.frameEtag = preview ? response.headers.get('ETag') : null;
    })()]);
  } catch {
    if (current() && !visual.frameBlob) visual.setMessage(framePlaceholder(visual.session));
  } finally {
    clearTimeout(timer);
    if (visual.frameRequest === request) visual.frameRequest = null;
  }
}

function startFrameLoop() {
  if (state.frameLoopStarted) return;
  state.frameLoopStarted = true;
  const tick = () => {
    const started = performance.now();
    const frameSessions = state.sessions.filter(
      session => ACTIVE_STATES.has(session.state) || session.last_frame_available
    );
    // Each visual has one bounded request. A slow guest never delays another
    // guest's next frame or starts overlapping requests for its own screen.
    for (const session of frameSessions) void refreshFrame(session);
    const interval = document.hidden ? HIDDEN_FRAME_INTERVAL_MS : FRAME_INTERVAL_MS;
    const elapsed = performance.now() - started;
    setTimeout(tick, Math.max(16, interval - elapsed));
  };
  tick();
}

async function refreshDeviceState(session) {
  if (!ACTIVE_STATES.has(session.state) && state.deviceStates.has(session.session_id)) return;
  try {
    const payload = await api(
      `/api/v1/sessions/${encodeURIComponent(session.session_id)}/device-state`
    );
    state.deviceStates.set(session.session_id, payload);
    state.visuals.get(session.session_id)?.shell?.setDeviceState?.(payload);
    const card = document.querySelector(`[data-session-id="${session.session_id}"]`);
    if (card) updateDeviceStateUi(card, payload, session);
  } catch (error) {
    const card = document.querySelector(`[data-session-id="${session.session_id}"]`);
    if (card) {
      updateDeviceStateUi(
        card,
        { supported: true, available: false, reason: error.message },
        session
      );
    }
  }
}

function updateDeviceStateUi(card, payload, session) {
  const runtime = card.querySelector('[data-field="runtime"]');
  const note = card.querySelector('[data-field="runtime-note"]');
  if (!payload) {
    runtime.hidden = true;
    note.hidden = !session.device_state_supported;
    note.textContent = session.device_state_supported ? '等待设备态…' : '该型号尚未接入统一设备态探针';
    return;
  }
  if (!payload.available) {
    runtime.hidden = true;
    note.hidden = false;
    note.textContent = payload.supported
      ? `设备态暂不可用：${payload.reason || '等待首次采样'}`
      : '该型号尚未接入统一设备态探针';
    return;
  }
  const power = payload.components?.power?.properties || {};
  const imu = payload.components?.imu?.properties || {};
  const values = {
    battery: power['vbat-mv'] == null ? '—' : `${formatNumber(power['vbat-mv'] / 1000)} V`,
    power: power.charging
      ? `充电 · ${formatNumber(power['vin-mv'] / 1000)} V`
      : `放电 · USB ${formatNumber(power['vinout-mv'] / 1000)} V`,
    audio: power['pa-enabled'] ? 'PA on' : 'PA off',
    'pmic-inputs': power['gpio-input-bits'] == null
      ? '—'
      : `0x${Number(power['gpio-input-bits']).toString(16).padStart(2, '0')}`,
    accel: ['accel-x', 'accel-y', 'accel-z'].every(key => imu[key] != null)
      ? `${formatNumber(imu['accel-x'])} / ${formatNumber(imu['accel-y'])} / ${formatNumber(imu['accel-z'])} g`
      : '—',
    gyro: ['gyro-x', 'gyro-y', 'gyro-z'].every(key => imu[key] != null)
      ? `${formatNumber(imu['gyro-x'])} / ${formatNumber(imu['gyro-y'])} / ${formatNumber(imu['gyro-z'])} °/s`
      : '—',
  };
  for (const [key, value] of Object.entries(values)) {
    const node = runtime.querySelector(`[data-runtime="${key}"]`);
    if (node) node.textContent = value;
  }
  runtime.hidden = false;
  note.hidden = false;
  const source = payload.source === 'persisted' ? '最后设备态' : '实时设备态';
  note.textContent = `${source} · ${formatTime(payload.captured_at)}${Object.keys(payload.errors || {}).length ? ' · PARTIAL' : ''}`;
}

async function createSession() {
  const deviceId = $('deviceSelect').value;
  const ttl = Number($('ttlInput').value || 600);
  if (!deviceId || state.creating) return;
  try {
    if (state.unitPickerDeviceId !== deviceId || !state.unitPicker) {
      throw new Error('请等待当前设备的 Unit 配置加载完成。');
    }
    const units = state.unitPicker.attachments(deviceId);
    const payload = { device_id: deviceId, ttl_seconds: ttl };
    if ($('programModeInput').checked && !$('programModeInput').disabled) payload.program_mode = 'uiflow-live';
    if (units.length) payload.units = units;
    if (deviceId === 'tab5') {
      payload.ready_marker = 'TAB5_UI_DRAWN';
      payload.ready_timeout_seconds = 240;
    }
    state.creating = true;
    updateCreateControls();
    await api('/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await refreshSessions();
  } catch (error) {
    showError(error.message);
  } finally {
    state.creating = false;
    updateCreateControls();
  }
}

async function sessionAction(sessionId, action) {
  try {
    if (action === 'stop') {
      await api(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
    } else if (action === 'renew') {
      await api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/renew`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ttl_seconds: 600 }),
      });
    } else if (action === 'reset') {
      await api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
    } else if (action === 'wait') {
      const session = state.sessions.find(row => row.session_id === sessionId);
      const display = session?.display || deviceFor(session?.device_id).display;
      const ready = display?.width
        ? { frame_nonblank: true, frame_min_bytes: 1024, frame_min_nonblack_pixels: 16 }
        : undefined;
      await api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/wait`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeout_seconds: 60, ...(ready ? { ready } : {}) }),
      });
    }
    await refreshSessions();
  } catch (error) {
    showError(error.message);
  }
}

$('saveTokenBtn').addEventListener('click', () => {
  state.token = $('tokenInput').value.trim();
  sessionStorage.setItem('m5-service-token', state.token);
  showError('');
  refreshSessions();
});

$('createBtn').addEventListener('click', createSession);
$('programModeInput').addEventListener('change', updateProgramMode);
$('deviceSelect').addEventListener('change', () => {
  updateProgramMode();
  void loadUnitPicker($('deviceSelect').value);
});
$('refreshBtn').addEventListener('click', refreshSessions);
$('historyBtn').addEventListener('click', () => {
  state.showHistory = !state.showHistory;
  $('historyBtn').textContent = state.showHistory ? '仅看近期' : '显示全部历史';
  refreshSessions();
});
$('clearHistoryBtn').addEventListener('click', async () => {
  try {
    const result = await api('/api/v1/sessions?state=stopped&purge=1', {
      method: 'DELETE',
    });
    state.serial.clear();
    state.deviceStates.clear();
    await refreshSessions();
    showError('');
    $('sessionSub').textContent = `已清理 ${result.cleared + (result.orphaned_cleared || 0)} 个历史会话`;
  } catch (error) {
    showError(error.message);
  }
});
$('sessionList').addEventListener('click', event => {
  const button = event.target.closest('button[data-action]');
  if (!button || button.disabled) return;
  const card = button.closest('[data-session-id]');
  if (card) sessionAction(card.dataset.sessionId, button.dataset.action);
});

async function init() {
  $('tokenInput').value = state.token;
  $('reviewDashboardLink').href =
    `${location.protocol}//${location.hostname}:8790/`;
  try {
    await loadCatalog();
    await refreshSessions();
  } catch (error) {
    showError(error.message);
  }
  setInterval(refreshSessions, 2000);
}

window.addEventListener('beforeunload', () => {
  state.unitPickerGeneration += 1;
  state.unitPicker?.dispose();
  for (const visual of state.visuals.values()) visual.destroy();
});

init();
