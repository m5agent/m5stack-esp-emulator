// Same-guest source execution. Program state comes only from the Device API;
// the editor is a local draft and is never replaced by a polling response.
const POLL_INTERVAL_MS = 1000;
const SOURCE_LIMIT_BYTES = 65536;
const DEFAULT_SOURCE = 'print("Hello from UIFlow")\n';
const STATES = {
  submitting: '提交中', running: '运行中', completed: '已完成', failed: '执行失败',
  unknown: '执行结果未确认', interrupted: '已中断', cancelled: '已取消',
  'interrupt-requested': '正在中断',
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function ownerKey(session) {
  return JSON.stringify([session.session_id, session.created_at ?? null, session.firmware_sha256 ?? null]);
}

class ProgramPanel {
  constructor(container, {session, api}) {
    this.api = api;
    this.session = null;
    this.sessionEpoch = 0;
    this.operationEpoch = 0;
    this.disposed = false;
    this.synchronized = false;
    this.pending = null;
    this.refreshing = null;
    this.program = null;
    this.historyError = '';
    this.submissionError = '';
    this.pollError = '';
    this.root = element('section', 'program-panel');
    this.root.dataset.programPanelRoot = '';
    const heading = element('div', 'program-heading');
    heading.append(element('h4', '', '实时编程'));
    this.status = element('span', 'status-chip');
    this.status.dataset.programState = '';
    this.status.setAttribute('role', 'status');
    this.status.setAttribute('aria-live', 'polite');
    heading.append(this.status);
    this.help = element('p', 'program-help', '在当前虚拟设备中运行 UIFlow / MicroPython 代码。运行会中断当前程序；结果显示在屏幕、串口和 Unit 面板中。');
    const label = element('label', 'program-source-label', '程序源码 · main.py');
    this.source = element('textarea', 'program-source');
    this.source.dataset.programSource = '';
    this.source.rows = 8;
    this.source.spellcheck = false;
    this.source.setAttribute('autocapitalize', 'off');
    this.source.setAttribute('autocomplete', 'off');
    this.source.setAttribute('aria-label', 'UIFlow 程序源码');
    label.append(this.source);
    const actions = element('div', 'program-actions');
    this.runButton = element('button', 'btn primary', '运行程序');
    this.runButton.type = 'button';
    this.runButton.dataset.programRun = '';
    this.refreshButton = element('button', 'btn', '同步状态');
    this.refreshButton.type = 'button';
    this.refreshButton.dataset.programRefresh = '';
    this.bytes = element('span', 'program-bytes');
    actions.append(this.runButton, this.refreshButton, this.bytes);
    this.detail = element('p', 'program-detail');
    this.detail.dataset.programDetail = '';
    this.error = element('p', 'program-error');
    this.error.dataset.programError = '';
    this.error.setAttribute('role', 'alert');
    this.root.append(heading, this.help, label, actions, this.detail, this.error);
    container.replaceChildren(this.root);
    this.runButton.addEventListener('click', () => { void this.run(); });
    this.refreshButton.addEventListener('click', () => { void this.refresh(); });
    this.source.addEventListener('input', () => this.render());
    this.updateSession(session);
  }

  active() {
    return !this.disposed && this.session?.state === 'running' && this.session.program_transport === 'uart-repl';
  }

  current(sessionId, sessionEpoch, operationEpoch) {
    return this.active() && sessionId === this.session.session_id
      && sessionEpoch === this.sessionEpoch && operationEpoch === this.operationEpoch;
  }

  updateSession(session) {
    if (this.disposed) return;
    const changed = !this.session || ownerKey(session) !== ownerKey(this.session);
    const wasActive = this.active();
    const stateChanged = this.session?.state !== session.state
      || this.session?.program_transport !== session.program_transport;
    this.session = {...session};
    if (changed || stateChanged) {
      this.sessionEpoch += 1;
      this.operationEpoch += 1;
      clearTimeout(this.timer);
      this.refreshing = null;
      this.pending = null;
      this.synchronized = false;
      this.historyError = '';
      this.submissionError = '';
      this.pollError = '';
      this.program = session.program || null;
      if (changed) this.source.value = DEFAULT_SOURCE;
    }
    this.render();
    if (this.active() && (changed || !wasActive)) void this.refresh();
  }

  render() {
    const supported = this.session?.program_transport === 'uart-repl';
    this.root.hidden = !supported;
    const bytes = new TextEncoder().encode(this.source.value).byteLength;
    const ready = this.active() && this.synchronized && !this.pending && !this.historyError;
    this.source.disabled = !ready;
    this.runButton.disabled = !ready || bytes > SOURCE_LIMIT_BYTES;
    this.refreshButton.disabled = !this.active() || !!this.pending || !!this.refreshing;
    this.root.setAttribute('aria-busy', String(!!this.pending));
    this.bytes.textContent = `${bytes.toLocaleString('zh-CN')} B / 64 KiB`;
    const state = this.pending ? 'submitting' : this.program?.state;
    if (!this.active()) this.status.textContent = this.session?.state === 'booting' ? '等待设备启动' : '设备未运行';
    else if (this.pending) this.status.textContent = STATES.submitting;
    else this.status.textContent = this.synchronized ? STATES[state] || state || '尚未运行' : '等待状态确认';
    this.status.dataset.state = state || 'idle';
    this.detail.textContent = this.program?.execution_id
      ? `${this.active() ? '执行' : '最后执行'} ${this.program.execution_id} · ${STATES[this.program.state] || this.program.state}`
      : this.active() ? this.synchronized ? '草稿仅保留在此页面。' : '状态同步后可运行源码。' : '设备运行后可编辑并执行源码。';
    this.error.textContent = this.submissionError || this.pollError || this.historyError
      || this.program?.error?.message || this.program?.error?.code
      || (bytes > SOURCE_LIMIT_BYTES ? '源码超过 64 KiB，请缩短后运行。' : '');
    this.error.hidden = !this.error.textContent;
  }

  apply(payload, sessionId) {
    if (payload?.session_id !== sessionId || payload.program_transport !== 'uart-repl'
      || payload.program !== null && (typeof payload.program !== 'object'
        || typeof payload.program?.execution_id !== 'string' || typeof payload.program?.state !== 'string')) {
      throw new Error('程序状态响应与当前设备不匹配，请重新同步。');
    }
    this.program = payload.program;
    this.historyError = payload.history_error || '';
    this.synchronized = !this.historyError;
    this.pollError = '';
  }

  schedule() {
    clearTimeout(this.timer);
    if (this.active() && !this.pending) this.timer = setTimeout(() => { void this.refresh(); }, document.hidden ? 3000 : POLL_INTERVAL_MS);
  }

  async refresh() {
    clearTimeout(this.timer);
    if (!this.active() || this.pending || this.refreshing) return;
    const sessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    const operationEpoch = this.operationEpoch;
    const request = this.refreshing = {};
    const current = () => this.current(sessionId, sessionEpoch, operationEpoch) && this.refreshing === request;
    this.render();
    try {
      const payload = await this.api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/program`);
      if (!current()) return;
      this.apply(payload, sessionId);
    } catch (error) {
      if (!current()) return;
      this.pollError = `状态同步失败：${error.message}`;
      this.synchronized = false;
    } finally {
      if (current()) {
        this.refreshing = null;
        this.render();
        this.schedule();
      }
    }
  }

  async run() {
    if (this.runButton.disabled || !this.active() || this.pending || !this.synchronized || this.historyError) return;
    clearTimeout(this.timer);
    const sessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    const operationEpoch = ++this.operationEpoch;
    const request = this.pending = {};
    // A pre-submit GET cannot restore its older execution after this mutation.
    this.refreshing = null;
    const current = () => this.current(sessionId, sessionEpoch, operationEpoch) && this.pending === request;
    const payload = {source: this.source.value, expected_execution_id: this.program?.execution_id ?? null};
    this.submissionError = '';
    this.pollError = '';
    this.render();
    try {
      const result = await this.api(`/api/v1/sessions/${encodeURIComponent(sessionId)}/program`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      if (!current()) return;
      this.apply(result, sessionId);
    } catch (error) {
      if (!current()) return;
      this.submissionError = `运行失败：${error.message}`;
      this.synchronized = false;
    } finally {
      if (current()) {
        this.pending = null;
        this.operationEpoch += 1;
        this.render();
        // A conflict or timed-out POST can still have changed the actual guest.
        // Read the current execution before admitting another Run.
        void this.refresh();
      }
    }
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.sessionEpoch += 1;
    this.operationEpoch += 1;
    clearTimeout(this.timer);
    this.root.remove();
  }
}

export function createProgramPanel(container, options) {
  return new ProgramPanel(container, options);
}
