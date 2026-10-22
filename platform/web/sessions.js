const state = {
  devices: [],
  sessions: [],
  serial: new Map(),
  frames: new Map(),
  lastFrameAt: new Map(),
  token: sessionStorage.getItem('m5-service-token') || '',
  busy: false,
  showHistory: false,
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

function sessionCard(session) {
  const device = deviceFor(session.device_id);
  const display = session.display || device.display;
  const hasDisplay = Boolean(display?.width && display?.height);
  const serialState = state.serial.get(session.session_id) || { text: '' };
  const frameUrl = state.frames.get(session.session_id);
  const warning = (device.warnings || []).join(' ');
  const frameText = hasDisplay
    ? (session.last_frame_available ? '加载最后一帧…' : '等待应用首帧…')
    : '该设备无 framebuffer';
  return `
    <article class="panel session-card" data-session-id="${escapeHtml(session.session_id)}">
      <div class="session-visual" id="visual-${escapeHtml(session.session_id)}">
        ${hasDisplay
          ? `${frameUrl ? `<img src="${escapeHtml(frameUrl)}" alt="${escapeHtml(session.device_id)} live frame">` : `<span class="no-frame">${frameText}</span>`}`
          : `<span class="no-frame">serial-only device</span>`}
      </div>
      <div class="session-body">
        <div class="session-title-row">
          <span class="session-title">${escapeHtml(device.name || session.device_id)}</span>
          <span class="status-chip ${statusClass(session.state)}">${escapeHtml(session.state)}</span>
          <span class="session-id">${escapeHtml(session.session_id)}</span>
        </div>
        <div class="session-meta">
          <span>${escapeHtml(session.device_id)}</span>
          <span>${escapeHtml(session.firmware_source || 'firmware')}</span>
          <span>${escapeHtml((session.firmware_sha256 || '').slice(0, 12))}</span>
          <span>${escapeHtml(session.serial_bytes || 0)} bytes</span>
        </div>
        ${warning ? `<div class="session-warning">partial: ${escapeHtml(warning.slice(0, 260))}</div>` : ''}
        <div class="session-actions">
          <button class="btn" data-action="wait" type="button">等待运行</button>
          <button class="btn" data-action="renew" type="button">续期</button>
          <button class="btn" data-action="reset" type="button">复位</button>
          <button class="btn" data-action="stop" type="button">停止</button>
        </div>
        <pre class="session-serial" id="serial-${escapeHtml(session.session_id)}">${escapeHtml(serialState.text || '等待串口输出…')}</pre>
      </div>
    </article>`;
}

function render() {
  const list = $('sessionList');
  if (!state.sessions.length) {
    list.innerHTML = `<div class="panel empty-state">${state.showHistory ? '还没有虚拟设备会话记录。' : '当前没有活动或近期完成的虚拟设备会话。'}</div>`;
    return;
  }
  list.innerHTML = state.sessions
    .slice()
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .map(sessionCard)
    .join('');
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
  const payload = await api('/api/v1/devices');
  state.devices = payload.devices || [];
  renderDevices();
}

async function refreshSessions() {
  if (state.busy) return;
  state.busy = true;
  try {
    const sessionPath = '/api/v1/sessions';
    const [sessionsPayload, capacity] = await Promise.all([
      api(sessionPath),
      api('/api/v1/capacity'),
    ]);
    const allSessions = sessionsPayload.sessions || [];
    const recentCutoff = Date.now() - 30 * 60 * 1000;
    state.sessions = state.showHistory
      ? allSessions
      : allSessions.filter(session =>
          !['stopped', 'failed'].includes(session.state)
          || Date.parse(session.completed_at || session.created_at) >= recentCutoff
        );
    renderCapacity(capacity);
    render();
    showError('');
    const serialSessions = state.sessions.filter(
      session => session.state === 'running' || session.serial_bytes > 0
    );
    const frameSessions = state.sessions.filter(
      session => session.state === 'running' || session.last_frame_available
    );
    await Promise.all(serialSessions.map(refreshSerial));
    await Promise.all(frameSessions.map(refreshFrame));
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
    const node = $(`serial-${session.session_id}`);
    if (node) {
      node.textContent = current.text || '等待串口输出…';
      node.scrollTop = node.scrollHeight;
    }
  } catch (error) {
    showError(error.message);
  }
}

async function refreshFrame(session) {
  const device = deviceFor(session.device_id);
  const display = session.display || device.display;
  if (!display?.width || !display?.height) return;
  const node = $(`visual-${session.session_id}`);
  if (!node) return;
  if (session.state !== 'running' && state.frames.has(session.session_id)) return;
  const last = state.lastFrameAt.get(session.session_id) || 0;
  if (state.frames.has(session.session_id) && Date.now() - last < 5000) return;
  const headers = new Headers();
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  try {
    const response = await fetch(
      `/api/v1/sessions/${encodeURIComponent(session.session_id)}/frame.png?t=${Date.now()}`,
      { headers }
    );
    if (!response.ok) throw new Error(`frame ${response.status}`);
    const blob = await response.blob();
    const old = state.frames.get(session.session_id);
    if (old) URL.revokeObjectURL(old);
    const url = URL.createObjectURL(blob);
    state.frames.set(session.session_id, url);
    state.lastFrameAt.set(session.session_id, Date.now());
    node.innerHTML = `<img alt="${escapeHtml(session.device_id)} live frame">`;
    node.querySelector('img').src = url;
  } catch {
    // A session that is still booting may not have a readable frame yet.
    if (!node.querySelector('img')) {
      node.innerHTML = '<span class="no-frame">等待应用首帧…</span>';
    }
  }
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
    for (const url of state.frames.values()) URL.revokeObjectURL(url);
    state.frames.clear();
    state.lastFrameAt.clear();
    await refreshSessions();
    showError('');
    $('sessionSub').textContent = `已清理 ${result.cleared + (result.orphaned_cleared || 0)} 个历史会话`;
  } catch (error) {
    showError(error.message);
  }
});
$('sessionList').addEventListener('click', event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const card = button.closest('[data-session-id]');
  if (card) sessionAction(card.dataset.sessionId, button.dataset.action);
});

$('tokenInput').value = state.token;
loadCatalog().catch(error => showError(error.message));
refreshSessions();
setInterval(refreshSessions, 2500);
window.addEventListener('beforeunload', () => {
  for (const url of state.frames.values()) URL.revokeObjectURL(url);
});
