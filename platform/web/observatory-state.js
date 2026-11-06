// Presentation state only. A display lifetime never changes a guest lifetime.
export const ACTIVE = new Set(['provisioning', 'flashing', 'booting', 'running', 'stopping']);
export const STATE_NAMES = Object.freeze({provisioning: '准备中', flashing: '加载固件', booting: '启动中', running: '运行中', stopping: '正在结束', stopped: '已结束', failed: '异常结束'});
const orderedBinding = binding => binding == null ? null : Object.fromEntries(Object.entries(binding).sort(([a], [b]) => a.localeCompare(b)));
export const sessionIdentity = row => JSON.stringify([row.session_id, row.created_at, row.firmware_sha256, orderedBinding(row.management_binding)]);
export const terminalDwell = row => row.state === 'failed' ? 30000 : 8000;
export function duration(row, now = Date.now()) {
  const start = Date.parse(row.created_at), end = Date.parse(row.completed_at);
  if (!Number.isFinite(start)) return '—';
  const seconds = Math.max(0, ((Number.isFinite(end) ? end : now) - start) / 1000);
  return seconds < 60 ? `${seconds.toFixed(seconds < 10 ? 1 : 0)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`;
}
export function bytes(value = 0) {
  return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : value >= 1024 ? `${(value / 1024).toFixed(1)} KB` : `${value} B`;
}

export class ObservatoryState {
  constructor({clock = Date.now} = {}) {
    this.clock = clock;
    this.clockOffset = 0;
    this.entries = new Map();
    this.seenTerminals = new Map();
    this.cursor = 0;
    this.journalId = null;
    this.status = {state: 'ok', gap_possible: false};
    this.capacity = null;
    this.jobs = {available: false};
    this.connected = false;
    this.lastSync = null;
  }

  apply(row, {initial = false} = {}) {
    if (!row?.session_id || !row.device_id || !row.state) return;
    const now = this.now(), key = sessionIdentity(row), old = this.entries.get(row.session_id);
    const same = old?.identity === key;
    const entry = same ? old : {identity: key, firstSeen: now, activityUntil: 0, terminalUntil: 0};
    const previous = same ? old.session : null;
    const ended = !ACTIVE.has(row.state);
    if (Number(row.serial_bytes || 0) > Number(previous?.serial_bytes || 0)) entry.activityUntil = now + 1500;
    if (ended && !this.seenTerminals.has(key)) {
      const completed = Date.parse(row.completed_at);
      // A fresh page does not restage old work. A newly received terminal event
      // can be shown after the fact, always explicitly labelled as ended.
      const remaining = initial ? terminalDwell(row) - Math.max(0, now - (Number.isFinite(completed) ? completed : 0)) : terminalDwell(row);
      entry.terminalUntil = now + Math.max(0, remaining);
      this.seenTerminals.set(key, entry.terminalUntil);
    } else if (ended) entry.terminalUntil = this.seenTerminals.get(key) || 0;
    else entry.terminalUntil = 0;
    entry.session = {...previous, ...row};
    if (entry.session.management_binding != null) entry.session.management_binding = orderedBinding(entry.session.management_binding);
    this.entries.set(row.session_id, entry);
  }

  snapshot(payload) {
    if (!payload || !Array.isArray(payload.active) || !Array.isArray(payload.recent) || !Number.isSafeInteger(payload.cursor)) throw new Error('展示快照格式无效。');
    const serverTime = Date.parse(payload.server_time);
    if (Number.isFinite(serverTime)) this.clockOffset = serverTime - this.clock();
    const firstLoad = this.lastSync === null;
    const previous = this.entries;
    this.entries = new Map();
    for (const row of [...payload.active, ...payload.recent]) {
      if (previous.get(row.session_id)?.identity === sessionIdentity(row)) this.entries.set(row.session_id, previous.get(row.session_id));
      this.apply(row, {initial: firstLoad});
    }
    this.cursor = payload.cursor;
    this.journalId = payload.journal_id;
    this.status = payload.status || this.status;
    this.capacity = payload.capacity ?? this.capacity;
    this.jobs = payload.jobs || {available: false};
    this.synced();
    this.prune();
  }

  events(payload) {
    if (payload.resync || payload.journal_id !== this.journalId) return false;
    if (!Array.isArray(payload.events) || !Number.isSafeInteger(payload.next_cursor) || payload.next_cursor < this.cursor) throw new Error('展示事件游标无效。');
    let previous = this.cursor;
    for (const event of payload.events) {
      if (!Number.isSafeInteger(event.seq) || event.seq < 0) throw new Error('展示事件序号无效。');
      if (event.seq <= this.cursor) continue;
      if (event.seq <= previous || event.seq > payload.next_cursor) throw new Error('展示事件顺序无效。');
      this.apply(event.session);
      previous = event.seq;
    }
    this.cursor = payload.next_cursor;
    this.status = payload.status || this.status;
    this.synced();
    this.prune();
    return true;
  }

  live(rows) {
    for (const row of rows || []) {
      const old = this.entries.get(row.session_id);
      // List enrichment supplies PID/Preview contracts and current byte counts;
      // it cannot resurrect a terminal projection or cleared content.
      if (old && ACTIVE.has(old.session.state) && !old.session.purged && sessionIdentity(row) === old.identity) this.apply(row);
    }
  }

  synced() { this.connected = true; this.lastSync = this.clock(); }
  now() { return this.clock() + this.clockOffset; }
  visible(filter = 'all') {
    const now = this.now(), active = [], terminal = [];
    for (const entry of this.entries.values()) {
      const row = entry.session;
      if (ACTIVE.has(row.state)) active.push(entry);
      else if (entry.terminalUntil > now) terminal.push(entry);
    }
    terminal.sort((a, b) => b.terminalUntil - a.terminalUntil);
    return [...active, ...terminal.slice(0, 12)].filter(entry => filter === 'all'
      || filter === 'active' && ACTIVE.has(entry.session.state)
      || filter === 'ended' && !ACTIVE.has(entry.session.state)
      || filter === 'failed' && entry.session.state === 'failed').map(entry => ({...entry.session, display_activity: entry.activityUntil > now}));
  }
  recent(limit = 40) {
    return [...this.entries.values()].map(entry => entry.session)
      .sort((a, b) => String(b.completed_at || b.created_at).localeCompare(String(a.completed_at || a.created_at))).slice(0, limit);
  }
  counts() {
    const rows = [...this.entries.values()].map(entry => entry.session), now = this.now();
    return {running: rows.filter(row => row.state === 'running').length,
      starting: rows.filter(row => ['provisioning', 'flashing', 'booting'].includes(row.state)).length,
      ending: rows.filter(row => row.state === 'stopping').length,
      ended: rows.filter(row => !ACTIVE.has(row.state) && now - Date.parse(row.completed_at) <= 3600000).length,
      failed: rows.filter(row => row.state === 'failed' && now - Date.parse(row.completed_at) <= 3600000).length};
  }
  prune() {
    const cutoff = this.now() - 86400000;
    for (const [id, entry] of this.entries) if (!ACTIVE.has(entry.session.state) && Date.parse(entry.session.completed_at || entry.session.created_at) < cutoff) this.entries.delete(id);
    for (const [key, until] of this.seenTerminals) if (until < cutoff) this.seenTerminals.delete(key);
  }
}
