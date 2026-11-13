import {SerialChannelState, renderSerialChannelSelect} from './serial-channel-state.js';
import {ObservatoryScene} from './observatory-scene.js';
import {ObservatoryAPI} from './observatory-client.js';
import {ObservatoryState, ACTIVE, STATE_NAMES, sessionIdentity, duration, bytes} from './observatory-state.js';
import {createPreviewClient} from './preview-client.js';
import {Sha256} from './sha256.js';
import {ObservatoryTour} from './observatory-tour.js';

const $ = id => document.getElementById(id);
const node = (tag, className, text) => { const n = document.createElement(tag); if (className) n.className = className; if (text != null) n.textContent = text; return n; };
const shortTime = value => { const at = new Date(value); return Number.isFinite(at.valueOf()) ? at.toLocaleTimeString('zh-CN', {hour12: false}) : '—'; };
const store = new ObservatoryState();
const tour = new ObservatoryTour();
let token = '';
try { token = sessionStorage.getItem('m5-service-token') || ''; } catch {}
const api = new ObservatoryAPI({token});
const metadata = new Map(), catalog = new Map(), loadingMetadata = new Set(), observers = new Map();
let scene, selected = null, stopped = false, authorized = true, syncing = false, lastSnapshot = 0, lastLive = 0;
let pollingTimer, frameTimer, clockTimer, renderTimer, serialUrl = null, noticeText = '', generation = 0;
let cameraTarget = '';

function notice(message = '') { noticeText = message; $('notice').textContent = message; $('notice').hidden = !message; }
function failure(error) {
  if (stopped || error?.name === 'AbortError') return;
  store.connected = false;
  if (error?.status === 401 || error?.status === 403) { authorized = false; notice('服务访问未获授权，等待访问配置恢复。'); }
  else notice(`连接暂时中断，正在重试。${error?.message || ''}`);
  renderConnection();
}
function renderConnection() {
  const fresh = store.connected && Date.now() - (store.lastSync || 0) < 10000;
  const status = $('connectionState');
  status.replaceChildren(node('i'), document.createTextNode(fresh ? '中心已连接' : store.lastSync ? '连接已中断' : '正在连接'));
  status.classList.toggle('is-online', fresh);
  $('syncTime').textContent = store.lastSync ? `${fresh ? '同步于' : '最后同步'} ${shortTime(store.lastSync)}` : '等待首次同步';
}
function observer(row) {
  const key = sessionIdentity(row), previous = observers.get(row.session_id), pid = row.pid ?? null;
  if (previous?.identity === key && previous.pid === pid) { previous.preview?.updateSession(row); return previous; }
  if (previous) { disposeObserver(previous); scene?.clearObservations?.(row.session_id); }
  const entry = {identity: key, pid, row, pending: new Set(), last: {}, frame: null, frameKey: null, etag: null, serial: '', offset: 0, serialChannels: new SerialChannelState(row.session_id, 64000), preview: null, disposed: false};
  observers.set(row.session_id, entry);
  if (row.management_binding != null && ACTIVE.has(row.state)) {
    entry.preview = createPreviewClient({session: row, api: (path, options) => api.json(path, options)});
    entry.unsubscribe = entry.preview.subscribe(snapshot => {
      const nextKey = snapshot.frameContext?.key || null;
      if (nextKey !== entry.contextKey) {
        entry.contextKey = nextKey; entry.frame = null; entry.etag = null;
        scene?.clearObservations?.(row.session_id);
        entry.units = null;
        if (selected === row.session_id) renderFrame(entry);
      }
    });
  }
  return entry;
}
function disposeObserver(entry) {
  entry.disposed = true; entry.unsubscribe?.(); entry.preview?.dispose();
  for (const controller of entry.pending) controller.abort();
  entry.pending.clear();
}
function current(entry, row) { const owner = store.entries.get(row.session_id); return !stopped && !entry.disposed && !owner?.session.purged && observers.get(row.session_id) === entry && owner?.identity === entry.identity && (owner?.session.pid ?? null) === entry.pid; }
function getContext(entry, row) {
  if (row.management_binding != null && ACTIVE.has(row.state)) return entry.preview?.snapshot().frameContext || null;
  return {key: entry.identity};
}
function contextMatches(entry, context, row) {
  return current(entry, row) && (row.management_binding == null || !ACTIVE.has(row.state) || entry.preview?.matches(context, 'frame'));
}

async function readTask(entry, row, kind, interval, task) {
  if (entry.pendingKinds?.has(kind) || Date.now() - (entry.last[kind] || 0) < interval) return;
  entry.pendingKinds ||= new Set(); entry.pendingKinds.add(kind); entry.last[kind] = Date.now();
  const controller = new AbortController(); entry.pending.add(controller);
  try { await task(controller.signal); }
  catch (error) {
    if (current(entry, row) && error?.name !== 'AbortError') {
      entry.errors ||= {}; entry.errors[kind] = error.message;
      if (error.status === 401) failure(error);
    }
  } finally { entry.pendingKinds.delete(kind); entry.pending.delete(controller); }
}

function updateObservers() {
  for (const entry of store.entries.values()) {
    const row = entry.session;
    const previous = observers.get(row.session_id);
    // Managed coordination requires the complete authoritative session including
    // PID; it is never constructed from a retained metadata-only projection.
    if (row.management_binding != null && ACTIVE.has(row.state) && !Object.hasOwn(row, 'pid')) continue;
    const target = observer(row); target.row = row; target.serialChannels.update(row);
    if (row.purged && !target.contentCleared) {
      for (const c of target.pending) c.abort();
      target.preview?.dispose(); target.frame = null; target.serial = ''; target.offset = 0; target.serialChannels = new SerialChannelState(row.session_id, 64000); target.serialChannels.update({...row, serial_channels: []}); target.units = null;
      target.contentCleared = true; scene?.clearObservations?.(row.session_id);
    }
    if (!ACTIVE.has(row.state) && target.preview) { target.unsubscribe?.(); target.preview.dispose(); target.preview = null; }
    if (previous && previous !== target && selected === row.session_id) renderDetail();
  }
  const kept = new Set([...store.visible().map(row => row.session_id), ...store.recent().map(row => row.session_id), selected].filter(Boolean));
  for (const [id, entry] of observers) if (!kept.has(id)) { disposeObserver(entry); observers.delete(id); }
}

async function ensureMetadata(rows) {
  for (const id of new Set(rows.map(row => row.device_id))) {
    const source = catalog.get(id);
    if (metadata.get(id)?.shell && typeof metadata.get(id).shell === 'object' || loadingMetadata.has(id) || !source?.path) continue;
    loadingMetadata.add(id);
    void api.json(`/devices/${source.path}/device.json`).then(value => {
      if (!stopped) { metadata.set(id, value); render(); }
    }).catch(() => {}).finally(() => loadingMetadata.delete(id));
  }
}

function render() {
  if (stopped) return;
  const counts = store.counts(), ready = store.lastSync !== null;
  $('metricRunning').textContent = ready ? counts.running : '—';
  $('metricStarting').textContent = ready ? counts.starting : '—';
  $('metricQueued').textContent = store.jobs.available ? store.jobs.counts?.queued ?? 0 : '—';
  $('metricEnded').textContent = ready ? counts.ended : '—';
  $('metricFailed').textContent = ready ? counts.failed : '—';
  $('queueNote').textContent = store.jobs.available ? '设备服务任务队列' : '任务队列暂不可用';
  $('capacityNote').textContent = store.capacity ? `${store.capacity.active_sessions} / ${store.capacity.max_sessions} 运行配额${counts.ending ? ` · ${counts.ending} 台正在结束` : ''}` : '正在读取中心容量';
  renderConnection();
  const rows = store.visible();
  void ensureMetadata(rows);
  if (scene) void scene.setSessions(rows, metadata).catch(error => { if (!stopped) { $('sceneError').textContent = `模型显示暂不可用：${error.message}`; $('sceneError').hidden = false; } });
  const presentation = tour.update(rows);
  selected = presentation.selectedId;
  const target = `${presentation.phase}:${presentation.phase === 'device' ? selected : presentation.groupId || ''}`;
  if (target !== cameraTarget) {
    cameraTarget = target;
    if (presentation.phase === 'device') scene?.focus(selected);
    else if (presentation.phase === 'group') scene?.focusGroup(presentation.groupId);
    else scene?.home();
  }
  $('presentationMode').textContent = ({idle: '等待任务', overview: '全景观察', group: '设备组巡展', device: '设备特写'})[presentation.phase];
  $('presentationCountdown').textContent = presentation.remaining ? `${presentation.remaining}s` : '';
  $('emptySpace').hidden = rows.length > 0;
  $('spaceSummary').textContent = rows.length ? `${rows.filter(row => ACTIVE.has(row.state)).length} 台正在执行 · ${rows.filter(row => !ACTIVE.has(row.state)).length} 台刚刚结束` : store.entries.size ? '当前视图没有设备 · 最近活动保留在下方' : '等待设备进入空间';
  const groups = new Map();
  for (const row of rows) groups.set(row.device_id, (groups.get(row.device_id) || 0) + 1);
  const chips = [...groups].map(([id, count]) => {
    const chip = node('div', 'group-chip');
    chip.append(node('span', '', metadata.get(id)?.name || id), node('b', '', `${count} 台`));
    return chip;
  });
  $('groupStrip').replaceChildren(...(chips.length ? chips : [node('span', 'group-empty', '同型号设备会自动组成阵列')]));
  renderActivity(); renderDetail();
}

function renderActivity() {
  const rows = store.recent(20), pageSize = matchMedia('(max-width: 760px)').matches ? 1 : 3;
  const pageCount = Math.max(1, Math.ceil((rows.length - 1) / pageSize));
  const page = Math.floor(Date.now() / 8000) % pageCount;
  $('activityPage').textContent = rows.length ? `真实活动 · ${page + 1} / ${pageCount} 自动轮播` : '保留真实时间与结束状态';
  const displayed = rows.length ? [rows[0], ...rows.slice(1 + page * pageSize, 1 + (page + 1) * pageSize)] : [];
  const content = displayed.map(row => {
    const item = node('article', `activity-item${row.state === 'failed' ? ' is-failed' : ''}`); item.dataset.activitySession = row.session_id;
    const heading = node('div'); heading.append(node('strong', '', `${metadata.get(row.device_id)?.name || row.device_id} · ${row.session_id.slice(0, 6)}`), node('time', '', shortTime(row.completed_at || row.created_at)));
    const info = node('p'); info.append(node('span', '', STATE_NAMES[row.state] || row.state), node('span', '', duration(row, store.now())), node('span', '', row.purged ? '详情已清理' : bytes(row.serial_bytes)));
    item.append(heading, info); return item;
  });
  $('activityList').replaceChildren(...(content.length ? content : [node('p', 'activity-empty', '这里会记录设备的出现与结束。')]));
}
function renderFrame(entry) {
  if (serialUrl) URL.revokeObjectURL(serialUrl);
  serialUrl = null;
  const row = store.entries.get(selected)?.session;
  const image = $('detailFrame'); image.removeAttribute('src'); image.hidden = true;
  if (!row) return;
  if (entry?.frame && !row.purged) {
    serialUrl = URL.createObjectURL(entry.frame.blob); image.src = serialUrl; image.hidden = false;
    $('detailFrameNote').textContent = `${ACTIVE.has(row.state) ? '实际屏幕' : '结束前最后观测'} · ${shortTime(entry.frame.capturedAt)}${!store.connected ? ' · 连接中断' : ''}`;
  } else $('detailFrameNote').textContent = row.purged ? '详情已清理' : !row.display?.width ? '此设备没有屏幕' : row.management_binding && ACTIVE.has(row.state) ? '等待当前运行的画面' : ACTIVE.has(row.state) ? '等待实际屏幕帧 · 黑屏不代表异常' : '结束时未保留可用画面';
}
function renderDetail() {
  const row = store.entries.get(selected)?.session;
  $('deviceDetail').hidden = !row; $('detailEmpty').hidden = !!row;
  if (!row) { if (serialUrl) URL.revokeObjectURL(serialUrl); serialUrl = null; return; }
  const entry = observers.get(selected);
  $('detailTitle').textContent = metadata.get(row.device_id)?.name || row.device_id;
  $('detailState').textContent = STATE_NAMES[row.state] || row.state;
  $('detailState').classList.toggle('is-failed', row.state === 'failed');
  $('detailId').textContent = `#${row.session_id.slice(-6)}`;
  $('detailDuration').textContent = duration(row, store.now());
  $('detailBytes').textContent = bytes(row.serial_bytes);
  // Keep the image URL stable across timestamp-only renders.
  const frameOwner = `${selected}:${entry?.contextKey || ''}:${entry?.frame?.hash || entry?.frame?.capturedAt || 'none'}:${row.purged}`;
  if ($('detailFrame').dataset.owner !== frameOwner) {
    $('detailFrame').dataset.owner = frameOwner;
    renderFrame(entry);
  }
  const observed = new Map((entry?.units?.units || []).map(unit => [unit.id, unit]));
  $('detailUnitCount').textContent = `${(row.units || []).length} 个`;
  const attachments = row.units || [], unitPage = Math.floor(Date.now() / 6000) % Math.max(1, Math.ceil(attachments.length / 3));
  const units = attachments.slice(unitPage * 3, unitPage * 3 + 3).map(unit => {
    const status = observed.get(unit.id), n = node('div', 'unit-row');
    n.append(node('strong', '', `${unit.unit_id} · ${unit.id}`), node('small', '', `${unit.parent_id ? `${unit.parent_id} / ` : ''}${unit.port_id || unit.visual_port || '连接端口未记录'} · ${row.purged ? '详情已清理' : !ACTIVE.has(row.state) ? '会话已结束' : status?.available ? '已取得运行观察' : '等待运行观察'}`));
    return n;
  });
  $('detailUnits').replaceChildren(...(units.length ? units : [node('span', '', '未连接外部 Unit')]));
  if (entry) renderSerialChannelSelect($('detailSerialChannel'), entry.serialChannels, !!row.purged);
  $('detailSerial').textContent = row.purged ? '详情已清理。此处只保留生命周期与字节数。' : entry?.serialChannels.view().text || (entry?.errors?.serial ? `串口暂不可读：${entry.errors.serial}` : '等待串口输出…');
  $('detailSerial').scrollTop = $('detailSerial').scrollHeight;
  $('serialStatus').textContent = row.purged ? '内容已清理' : '实时尾部 · 自动跟随';
}

async function refreshSnapshot() {
  const epoch = generation;
  const payload = await api.json('/api/v1/observatory/snapshot');
  if (stopped || epoch !== generation) return;
  store.snapshot(payload); lastSnapshot = Date.now();
  if (payload.status?.state === 'degraded' || payload.status?.gap_possible) notice('观测记录不完整。当前可用设备继续显示，部分历史活动可能缺失。');
  else if (noticeText) notice();
  updateObservers(); render();
}
async function poll() {
  if (stopped || syncing) return;
  syncing = true; const epoch = generation;
  try {
    if (!store.journalId || Date.now() - lastSnapshot > 15000) await refreshSnapshot();
    if (epoch !== generation) return;
    let pages = 0, hasMore = true;
    while (hasMore && pages++ < 20 && epoch === generation && !stopped) {
      const payload = await api.json(`/api/v1/observatory/events?journal_id=${encodeURIComponent(store.journalId)}&after=${store.cursor}&limit=200`);
      if (epoch !== generation) return;
      if (!store.events(payload)) { await refreshSnapshot(); break; }
      hasMore = payload.has_more;
    }
    if (Date.now() - lastLive >= (document.hidden ? 5000 : 2000)) {
      const payload = await api.json('/api/v1/sessions');
      if (epoch !== generation) return;
      store.live(payload.sessions); lastLive = Date.now();
    }
    updateObservers(); render();
    authorized = true;
    if (store.status?.state === 'degraded' || store.status?.gap_possible) notice('观测记录不完整。当前可用设备继续显示，部分历史活动可能缺失。');
    else if (noticeText) notice();
  } catch (error) { if (epoch === generation) failure(error); }
  finally { syncing = false; if (!stopped) pollingTimer = setTimeout(poll, !authorized ? 10000 : document.hidden ? 5000 : 1000); }
}

function contentTick() {
  if (stopped) return;
  if (authorized && store.connected && !document.hidden) {
    const ids = new Set([selected, ...(scene?.visibleSessionIds || [])].filter(Boolean));
    for (const id of ids) {
      const row = store.entries.get(id)?.session, entry = observers.get(id);
      if (!row || !entry || row.purged) continue;
      const active = ACTIVE.has(row.state), focused = selected === id, context = getContext(entry, row);
      if (!context) continue;
      const root = `/api/v1/sessions/${encodeURIComponent(id)}`;
      if (row.display?.width && (active || row.last_frame_available) && (active || !entry.frame)) void readTask(entry, row, 'frame', focused ? 125 : 500, async signal => {
        const headers = new Headers(); if (entry.etag) headers.set('If-None-Match', entry.etag);
        const managed = row.management_binding != null && active;
        const path = managed ? `/api/v1/previews/${context.previewId}/runs/${context.runId}/frame.png` : `${root}/frame.png`;
        const response = await api.response(`${path}?max_age_ms=125`, {signal, headers});
        if (!contextMatches(entry, context, row)) return;
        if (managed && (response.headers.get('X-Preview-ID') !== context.previewId || response.headers.get('X-Run-ID') !== context.runId || response.headers.get('X-Frame-Execution-ID') !== context.executionId || response.headers.get('X-Frame-Revision-ID') !== context.revisionId)) throw new Error('运行画面身份不匹配。');
        if (response.status === 304) return;
        const hash = response.headers.get('X-Frame-SHA256');
        if (managed && new Sha256().update(new Uint8Array(await response.blob.arrayBuffer())).hex() !== hash) throw new Error('运行画面校验失败。');
        if (!contextMatches(entry, context, row)) return;
        const guard = () => contextMatches(entry, context, row);
        if (scene) await scene.setFrame(id, response.blob, guard);
        if (!guard()) return;
        entry.frame = {blob: response.blob, hash, capturedAt: response.headers.get('X-Frame-Captured-At')}; entry.etag = response.headers.get('ETag');
        if (focused) renderDetail();
      });
      if (active && row.device_state_supported) void readTask(entry, row, 'device', focused ? 500 : 2000, async signal => {
        const payload = entry.preview ? await entry.preview.readSession(context, 'device-state') : await api.json(`${root}/device-state`, {signal});
        if (!contextMatches(entry, context, row) || payload.session_id !== id) return;
        scene?.setDeviceState(id, payload);
      });
      if (active && row.units?.length) void readTask(entry, row, 'units', focused ? 500 : 2000, async signal => {
        const payload = entry.preview ? await entry.preview.readSession(context, 'units') : await api.json(`${root}/units`, {signal});
        if (!contextMatches(entry, context, row) || payload.session_id !== id) return;
        entry.units = payload; scene?.setUnits(id, payload); if (focused) renderDetail();
      });
      const serialRequest = entry.serialChannels.request(16384);
      const serialSize = entry.serialChannels.channels.find(item => item.channel === serialRequest?.channel)?.bytes || 0;
      if (focused && serialRequest && (active || entry.serialChannels.view().bytes < serialSize)) void readTask(entry, row, 'serial', 500, async signal => {
        let payload;
        try {payload = await api.json(`${root}/serial?offset=${serialRequest.offset}&limit=16384&channel=${encodeURIComponent(serialRequest.channel)}`, {signal});}
        catch (error) {if (entry.serialChannels.matches(serialRequest)) throw error; return;}
        if (!current(entry, row) || selected !== id) return;
        const accepted = entry.serialChannels.accept(serialRequest, payload); if (!accepted) return;
        entry.offset = accepted.bytes; entry.serial = accepted.text;
        if (entry.errors) delete entry.errors.serial;
        renderDetail();
      });
    }
  }
  frameTimer = setTimeout(contentTick, 100);
}

function dispose() {
  if (stopped) return; stopped = true; generation++;
  clearTimeout(pollingTimer); clearTimeout(frameTimer); clearInterval(clockTimer); clearInterval(renderTimer);
  for (const entry of observers.values()) disposeObserver(entry);
  observers.clear(); api.dispose(); scene?.dispose(); if (serialUrl) URL.revokeObjectURL(serialUrl);
}

document.addEventListener('visibilitychange', () => { scene?.setVisible(!document.hidden); if (!document.hidden) { clearTimeout(pollingTimer); if (!syncing) void poll(); } });
window.addEventListener('pagehide', dispose, {once: true});
window.addEventListener('beforeunload', dispose, {once: true});

try {
  scene = new ObservatoryScene($('sceneMount'), {onError: error => { $('sceneError').textContent = `模型加载受限：${error.message || error}`; $('sceneError').hidden = false; }});
} catch (error) {
  $('sceneError').textContent = `3D 场景暂不可用，设备信息继续自动展示。${error.message}`; $('sceneError').hidden = false;
}
// Read-only inspection references for reproducible UI/runtime acceptance.
Object.defineProperty(globalThis, '__observatoryProbe', {value: Object.freeze({store, tour, get scene() { return scene; }, api, get selectedSessionId() { return selected; }}), configurable: true});
clockTimer = setInterval(() => { $('wallClock').textContent = new Date().toLocaleTimeString('zh-CN', {hour12: false}); }, 1000);
renderTimer = setInterval(render, 1000);
void Promise.allSettled([api.json('/devices/catalog.json'), api.json('/api/v1/devices')]).then(([deviceCatalog, serviceCatalog]) => {
  if (stopped) return;
  if (deviceCatalog.status === 'fulfilled') for (const row of deviceCatalog.value.devices || []) { catalog.set(row.id, row); metadata.set(row.id, row); }
  if (serviceCatalog.status === 'fulfilled') for (const row of serviceCatalog.value.devices || []) if (!metadata.has(row.device_id)) metadata.set(row.device_id, {id: row.device_id, name: row.name || row.device_id});
  render();
});
void poll(); contentTick(); render();

$('detailSerialChannel').addEventListener('change', event => {
  const entry = observers.get(selected); if (!entry) return;
  entry.serialChannels.select(event.target.value); delete entry.last.serial;
  if (entry.errors) delete entry.errors.serial;
  renderDetail();
});
