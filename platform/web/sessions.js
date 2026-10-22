const ACTIVE_STATES = new Set(['provisioning', 'flashing', 'booting', 'running']);
const THREE_PREVIEW_LIMIT = 4;
const FRAME_INTERVAL_MS = 125;
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
    this.lastFrameAt = 0;
    this.lastFrameAttemptAt = 0;
    this.frameApply = Promise.resolve();
    this.controlQueues = new Map();
    this.activeControls = new Set();
    this.controlReleaseTimers = new Map();
    this.destroyed = false;
    this.allowThree = allowThree;
    this.threeAttempted = false;
    this.placeholder = framePlaceholder(session);
    this.container.innerHTML = `<span class="no-frame">${escapeHtml(this.placeholder)}</span>`;
    this.init().catch(error => {
      console.warn('Session preview initialization failed.', error);
      this.setMessage(this.placeholder);
    });
  }

  updateSession(session) {
    this.session = session;
    if (!ACTIVE_STATES.has(session.state)) this.releaseActiveControls();
    if (!this.frameBlob && !this.shell) {
      this.placeholder = framePlaceholder(session);
      this.setMessage(this.placeholder);
    }
  }

  setThreeAllowed(allowThree) {
    this.allowThree = allowThree;
    if (allowThree && !this.threeAttempted) {
      this.init().catch(error => {
        console.warn('Session preview initialization failed.', error);
        this.setMessage(this.placeholder);
      });
    }
  }

  async init() {
    if (!this.allowThree || this.threeAttempted) return;
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
    const renderer = profile.shell?.renderer;
    if (this.destroyed || !['sticks3-three', 'cores3-three'].includes(renderer)) return;
    try {
      const module = renderer === 'cores3-three'
        ? await import('/platform/web/cores3-viewer.js?v=20261022e')
        : await import('/platform/web/sticks3-viewer.js?v=20261022e');
      const Shell = renderer === 'cores3-three'
        ? module.CoreS3ThreeShell
        : module.StickS3ThreeShell;
      if (this.destroyed) return;
      this.container.replaceChildren();
      this.container.classList.add('is-three');
      this.shell = new Shell(this.container, profile);
      this.shell.setViewMode('shell');
      this.shell.on('control', event => this.handleControl(event));
      this.shell.on('touch', ({ x, y, action }) => {
        if (action !== 'start' || this.session.state !== 'running') return;
        api(`/api/v1/sessions/${encodeURIComponent(this.session.session_id)}/input`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: 'touch', x, y, settle_seconds: 0.05 }),
        }).catch(error => console.warn('Session touch injection failed.', error));
      });
      if (this.frameBlob) await this.applyThreeFrame();
    } catch (error) {
      console.warn('3D session preview unavailable; using the framebuffer image.', error);
      this.shell = null;
      this.container.classList.remove('is-three');
      this.setMessage(this.placeholder);
      if (this.frameBlob) this.setGenericFrame(this.frameBlob);
    }
  }

  setMessage(message) {
    if (this.shell || this.frameBlob) return;
    this.container.innerHTML = `<span class="no-frame">${escapeHtml(message)}</span>`;
  }

  setFrame(blob, hash = null) {
    this.frameBlob = blob;
    this.lastFrameHash = hash;
    this.lastFrameAt = Date.now();
    if (this.shell) return this.applyThreeFrame();
    this.setGenericFrame(blob);
    return Promise.resolve();
  }

  applyThreeFrame() {
    this.frameApply = this.frameApply
      .catch(() => {})
      .then(async () => {
        if (this.destroyed || !this.shell || !this.frameBlob) return;
        await this.shell.setImage(this.frameBlob);
      });
    return this.frameApply;
  }

  setGenericFrame(blob) {
    if (this.frameUrl) URL.revokeObjectURL(this.frameUrl);
    this.frameUrl = URL.createObjectURL(blob);
    let image = this.container.querySelector('img.session-frame');
    if (!image) {
      this.container.replaceChildren();
      image = document.createElement('img');
      image.className = 'session-frame';
      image.alt = `${this.session.device_id} live frame`;
      this.container.append(image);
    }
    image.src = this.frameUrl;
    this.container.classList.add('has-frame');
  }

  controlKey(id) {
    return id === 'power' ? 'p' : id;
  }

  handleControl({ id, down }) {
    if (this.session.state !== 'running') return;
    const key = this.controlKey(id);
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
    const previous = this.controlQueues.get(key) || Promise.resolve();
    const request = previous
      .catch(() => {})
      .then(() => api(`/api/v1/sessions/${encodeURIComponent(this.session.session_id)}/input`, {
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
    this.releaseActiveControls();
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
  if (!visual) return;
  const active = ACTIVE_STATES.has(session.state);
  if (!active) {
    if (visual.frameBlob || Date.now() - visual.lastFrameAttemptAt < 5000) return;
    visual.lastFrameAttemptAt = Date.now();
  }
  const headers = new Headers();
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  try {
    const response = await fetch(
      `/api/v1/sessions/${encodeURIComponent(session.session_id)}/frame.png?t=${Date.now()}`,
      { headers }
    );
    if (!response.ok) throw new Error(`frame ${response.status}`);
    const hash = response.headers.get('X-Frame-SHA256');
    if (hash && hash === visual.lastFrameHash) return;
    await visual.setFrame(await response.blob(), hash);
  } catch {
    if (!visual.frameBlob) visual.setMessage(framePlaceholder(session));
  }
}

function startFrameLoop() {
  if (state.frameLoopStarted) return;
  state.frameLoopStarted = true;
  const tick = async () => {
    const started = performance.now();
    const frameSessions = state.sessions.filter(
      session => ACTIVE_STATES.has(session.state) || session.last_frame_available
    );
    await Promise.allSettled(frameSessions.map(refreshFrame));
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
  if (!deviceId) return;
  const payload = { device_id: deviceId, ttl_seconds: ttl };
  if (deviceId === 'tab5') {
    payload.ready_marker = 'TAB5_UI_DRAWN';
    payload.ready_timeout_seconds = 240;
  }
  try {
    await api('/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await refreshSessions();
  } catch (error) {
    showError(error.message);
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
  for (const visual of state.visuals.values()) visual.destroy();
});

init();
