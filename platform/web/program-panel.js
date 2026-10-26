// Same-guest source execution. Program state comes only from the Device API;
// the editor is a local draft and is never replaced by a polling response.
import {Sha256} from './sha256.js';

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

const managedBinding = session => session?.management_binding !== undefined && session.management_binding !== null;

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
    return !this.disposed && !managedBinding(this.session) && this.session?.state === 'running' && this.session.program_transport === 'uart-repl';
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
    this.error.textContent = (managedBinding(this.session) ? '此会话由 Preview 管理，请重新加载控制面。' : '') || this.submissionError || this.pollError || this.historyError
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

const PACKAGE_LIMITS = {files: 64, fileBytes: 262144, totalBytes: 1048576};
const HASH = /^[0-9a-f]{64}$/;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true});
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const check = (condition, message) => { if (!condition) throw new Error(message); };
const hash = bytes => new Sha256().update(bytes).hex();
function compareCodePoints(left, right) {
  const a = [...left], b = [...right];
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const difference = a[index].codePointAt(0) - b[index].codePointAt(0);
    if (difference) return difference;
  }
  return a.length - b.length;
}
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort(compareCodePoints).map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
function decodeFile(file) {
  check(object(file) && Object.keys(file).sort().join(',') === 'data,encoding' && typeof file.data === 'string', '文件包编码格式无效。');
  if (file.encoding === 'utf8') {
    const bytes = encoder.encode(file.data);
    check(decoder.decode(bytes) === file.data, '源码含无效 UTF-8 字符。');
    return bytes;
  }
  check(file.encoding === 'base64' && file.data.length <= 4 * Math.ceil(PACKAGE_LIMITS.fileBytes / 3)
    && /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(file.data), '文件包 Base64 无效。');
  const binary = atob(file.data);
  check(btoa(binary) === file.data, '文件包 Base64 非标准编码。');
  return Uint8Array.from(binary, character => character.charCodeAt(0));
}
function inspectFiles(files) {
  check(object(files), '完整文件包缺失。');
  const paths = Object.keys(files);
  check(paths.length > 0 && paths.length <= PACKAGE_LIMITS.files && paths.includes('main.py'), '文件包必须含 main.py，且不超过 64 个文件。');
  const inventory = Object.create(null), hashes = Object.create(null), seen = new Set(), namespace = new Map();
  let total = 0, main = '';
  for (const path of paths.sort(compareCodePoints)) {
    const parts = path.split('/');
    check(path && decoder.decode(encoder.encode(path)) === path && path.normalize('NFC') === path
      && !/[\\:\u0000-\u001f\u007f-\u009f]/u.test(path) && encoder.encode(path).length <= 192
      && parts.length <= 8 && parts.every(part => part && part !== '.' && part !== '..')
      && parts.at(-1).toLowerCase() !== 'boot.py', '文件包路径无效。');
    const key = path.toLowerCase();
    check(!seen.has(key), '文件包路径发生大小写冲突。');
    seen.add(key);
    for (let length = 1; length <= parts.length; length += 1) {
      const prefix = parts.slice(0, length).join('/'), normalized = prefix.toLowerCase();
      check(!namespace.has(normalized) || namespace.get(normalized) === prefix, '文件包目录名称发生大小写冲突。');
      namespace.set(normalized, prefix);
    }
    const bytes = decodeFile(files[path]);
    check(bytes.length <= PACKAGE_LIMITS.fileBytes, '单个文件超过 256 KiB。');
    total += bytes.length;
    check(total <= PACKAGE_LIMITS.totalBytes, '完整文件包超过 1 MiB。');
    const kind = path.endsWith('.py') ? 'python' : path.endsWith('.mpy') ? 'mpy' : 'resource';
    if (kind === 'python') {
      const source = decoder.decode(bytes);
      check(!source.includes('\0'), 'Python 文件含 NUL 字节。');
      if (path === 'main.py') main = source;
    }
    if (kind === 'mpy') check(bytes.length >= 4 && bytes[0] === 77 && !(bytes[2] & 128), 'MPY 文件头无效。');
    inventory[path] = {path, size: bytes.length, sha256: hash(bytes), kind};
    hashes[path] = inventory[path].sha256;
  }
  for (const path of paths) {
    const parts = path.toLowerCase().split('/');
    for (let count = 1; count < parts.length; count += 1) check(!seen.has(parts.slice(0, count).join('/')), '文件包目录与文件冲突。');
  }
  return {main, total, inventory, revisionId: hash(encoder.encode(canonical({source_kind: 'uiflow2-package', entrypoint: 'main.py', files: hashes}))),
    sourceHash: hash(encoder.encode(canonical(hashes)))};
}
function verifyPackage(revision, files, expectedId = null) {
  check(object(revision) && revision.source_kind === 'uiflow2-package' && revision.entrypoint === 'main.py'
    && HASH.test(revision.revision_id) && (!expectedId || revision.revision_id === expectedId), '文件包 revision 身份不符。');
  const result = inspectFiles(files);
  check(revision.revision_id === result.revisionId && revision.source_sha256 === result.sourceHash
    && revision.total_file_bytes === result.total && Number.isInteger(revision.total_file_bytes)
    && Array.isArray(revision.files) && revision.files.length === Object.keys(result.inventory).length, '文件包内容摘要不符。');
  const rows = Object.create(null);
  for (const row of revision.files) {
    check(object(row) && typeof row.path === 'string' && !Object.hasOwn(rows, row.path), '文件包清单重复或无效。');
    rows[row.path] = row;
  }
  check(canonical(rows) === canonical(result.inventory), '文件包路径、大小、类型或 SHA256 不符。');
  check(typeof revision.created_at === 'string' && Number.isFinite(Date.parse(revision.created_at)), '文件包创建时间无效。');
  return result;
}

class PreviewProgramPanel {
  constructor(container, {session, api, previewClient}) {
    this.api = api;
    this.previewClient = previewClient;
    this.session = session;
    this.bindingKey = this.owner(session);
    this.epoch = this.click = this.edit = this.loadEpoch = 0;
    this.workspace = this.staged = this.saving = null;
    this.loadPending = this.cancelPending = this.disposed = false;
    this.localGenerations = new Map();
    this.dispatches = new Map();
    this.cancelTargets = new Map();
    this.problem = this.notice = '';
    this.state = null;
    try {
      const random = globalThis.crypto.getRandomValues(new Uint8Array(16));
      this.clientTag = `editor-${Array.from(random, byte => byte.toString(16).padStart(2, '0')).join('')}`;
    } catch { this.randomFault = '浏览器安全随机源不可用，已禁用运行。'; }
    this.root = element('section', 'program-panel');
    this.root.dataset.programPanelRoot = '';
    this.root.dataset.programManaged = '';
    const heading = element('div', 'program-heading');
    this.status = element('span', 'status-chip');
    this.status.dataset.programState = '';
    this.status.setAttribute('role', 'status');
    this.status.setAttribute('aria-live', 'polite');
    heading.append(element('h4', '', '实时编程'), this.status);
    this.help = element('p', 'program-help', '编辑 main.py，运行时保留完整包内的模块、MPY 与资源。运行状态由 Preview 同步；启动标记不代表应用已就绪。');
    const label = element('label', 'program-source-label', '程序源码 · main.py');
    this.source = element('textarea', 'program-source');
    this.source.dataset.programSource = '';
    this.source.value = DEFAULT_SOURCE;
    this.source.rows = 8;
    this.source.spellcheck = false;
    this.source.setAttribute('aria-label', 'Preview main.py 草稿');
    this.source.setAttribute('autocapitalize', 'off');
    this.source.setAttribute('autocomplete', 'off');
    label.append(this.source);
    const actions = element('div', 'program-actions');
    this.runButton = this.button('运行完整包', 'programRun', 'btn primary');
    this.cancelButton = this.button('请求取消', 'programCancel');
    this.refreshButton = this.button('同步状态', 'programRefresh');
    this.loadButton = this.button('加载当前文件包', 'programLoad');
    this.bytes = element('span', 'program-bytes');
    actions.append(this.runButton, this.cancelButton, this.refreshButton, this.loadButton, this.bytes);
    this.packageInfo = element('p', 'program-package');
    this.packageInfo.dataset.programPackage = '';
    this.draftInfo = element('p', 'program-draft');
    this.draftInfo.dataset.programDraft = '';
    this.choices = element('div', 'program-actions program-load-choices');
    this.adoptButton = this.button('加载并替换 main.py', 'programAdopt');
    this.mergeButton = this.button('保留 main.py，更新依赖', 'programMerge');
    this.choices.append(this.adoptButton, this.mergeButton);
    this.detail = element('p', 'program-detail');
    this.detail.dataset.programDetail = '';
    this.error = element('p', 'program-error');
    this.error.dataset.programError = '';
    this.error.setAttribute('role', 'alert');
    this.root.append(heading, this.help, label, actions, this.packageInfo, this.draftInfo, this.choices, this.detail, this.error);
    container.replaceChildren(this.root);
    this.source.addEventListener('input', () => { this.edit += 1; this.render(); });
    this.runButton.addEventListener('click', () => { void this.run(); });
    this.cancelButton.addEventListener('click', () => { void this.cancel(); });
    this.refreshButton.addEventListener('click', () => { void this.refresh(); });
    this.loadButton.addEventListener('click', () => { void this.loadCurrentPackage(); });
    this.adoptButton.addEventListener('click', () => this.applyStaged(false));
    this.mergeButton.addEventListener('click', () => this.applyStaged(true));
    this.unsubscribe = previewClient?.subscribe(state => this.receive(state));
    this.render();
  }

  button(text, field, className = 'btn') { const node = element('button', className, text); node.type = 'button'; node.dataset[field] = ''; return node; }
  owner(session) { return JSON.stringify([ownerKey(session), session?.management_binding ?? null]); }
  current(epoch, binding = this.bindingKey) { return !this.disposed && this.epoch === epoch && this.bindingKey === binding; }
  latest(state = this.state) { return state?.desiredRun || state?.transitionRun || state?.activeRun || null; }
  own(run) { return !!run && this.localGenerations.get(run.request?.client_generation ?? run.client_generation) === run.revision_id; }
  external(state = this.state, baseline = this.workspace?.revisionId ?? null) {
    const run = this.latest(state);
    return !!run && run.revision_id !== baseline && !this.own(run);
  }
  dirty() { return this.source.value !== (this.workspace?.main ?? DEFAULT_SOURCE).replace(/\r\n?/g, '\n'); }
  currentSource() { return this.workspace && !this.dirty() ? this.workspace.main : this.source.value; }
  receive(state) {
    if (this.disposed) return;
    const binding = this.session?.management_binding;
    if (state.synchronized && (!object(binding) || state.preview?.preview_id !== binding.preview_id
      || state.preview?.owner_epoch !== binding.owner_epoch || state.preview?.session_id !== this.session.session_id)) {
      this.state = null;
      this.problem = 'Preview 状态不属于当前会话，已禁用运行。';
      this.render();
      return;
    }
    this.state = state;
    if (!this.workspace && state.synchronized && state.preview?.generation === 0 && !this.latest(state)) {
      this.workspace = {revisionId: null, main: DEFAULT_SOURCE, files: {'main.py': {encoding: 'utf8', data: DEFAULT_SOURCE}}, total: encoder.encode(DEFAULT_SOURCE).length};
    }
    if (this.staged && this.staged.revisionId !== this.latest()?.revision_id) this.staged = null;
    this.drainCancellations();
    this.render();
  }
  updateSession(session) {
    if (this.disposed) return;
    const owner = this.owner(session);
    this.session = session;
    if (owner !== this.bindingKey) {
      this.bindingKey = owner;
      this.epoch += 1; this.click += 1; this.loadEpoch += 1;
      this.workspace = this.staged = this.saving = null;
      this.loadPending = this.cancelPending = false;
      this.localGenerations.clear();
      this.dispatches.clear(); this.cancelTargets.clear();
      this.state = null;
      this.problem = '会话身份已变化；当前草稿保留，请重新同步并加载完整包。';
      this.notice = '';
    }
    this.render();
  }
  render() {
    if (this.disposed) return;
    const state = this.state, run = this.latest(), bytes = encoder.encode(this.currentSource()).length;
    const total = this.workspace ? this.workspace.total - decodeFile(this.workspace.files['main.py']).length + bytes : bytes;
    const external = this.external();
    this.source.disabled = false;
    this.runButton.disabled = !!this.randomFault || !this.previewClient || !state?.canSubmit || !this.workspace || external || !!this.staged
      || bytes > PACKAGE_LIMITS.fileBytes || total > PACKAGE_LIMITS.totalBytes;
    this.cancelButton.disabled = !this.previewClient || this.cancelPending || (!this.saving && !state?.canCancel);
    this.refreshButton.disabled = !this.previewClient;
    this.loadButton.disabled = !this.previewClient || !state?.synchronized || !run || this.loadPending;
    this.choices.hidden = !this.staged;
    this.root.setAttribute('aria-busy', String(!!this.saving || this.loadPending || !!state?.pending));
    this.bytes.textContent = `${bytes.toLocaleString('zh-CN')} B · 完整包 ${total.toLocaleString('zh-CN')} B / 1 MiB`;
    const labels = {queued: '等待运行', preparing: '准备文件包', starting: '等待启动确认', running: '运行中', completed: '已完成',
      failed: '执行失败', unknown: '执行结果未确认', cancelling: '等待中断确认', cancelled: '已取消', superseded: '已被新运行替代', interrupted: '已中断'};
    this.status.textContent = !state?.synchronized ? '等待 Preview 状态确认' : this.saving ? '保存完整文件包' : labels[run?.state] || (state.preview?.state === 'ready' ? '尚未运行' : '等待设备准备');
    this.status.dataset.state = run?.state || state?.preview?.state || 'unknown';
    this.packageInfo.textContent = this.workspace ? `${Object.keys(this.workspace.files).length} 个文件 · 包 ${this.workspace.revisionId || '尚未保存，仅 main.py'}` : '尚未加载完整文件包。先加载当前包，再编辑或运行。';
    this.draftInfo.textContent = this.staged ? '完整包已校验；草稿尚未覆盖，请选择如何加载。'
      : external ? `外部文件包已变化：${run.revision_id}。当前草稿保留；加载并明确同步依赖后才能运行。`
        : this.dirty() ? 'main.py 有本地修改；状态同步不会覆盖草稿。' : '草稿与已加载的 main.py 一致。';
    this.detail.textContent = run ? `Run ${run.run_id} · 执行 ${run.execution_id} · ${labels[run.state] || run.state}${this.notice ? ' · ' + this.notice : ''}` : this.notice || '草稿仅保留在当前页面。';
    this.error.textContent = !this.previewClient ? 'Preview 控制面不可用；此托管会话不能使用旧程序接口。'
      : this.randomFault || this.problem || state?.error || run?.error?.message
        || (bytes > PACKAGE_LIMITS.fileBytes ? 'main.py 超过 256 KiB。' : total > PACKAGE_LIMITS.totalBytes ? '完整文件包超过 1 MiB。' : '');
    this.error.hidden = !this.error.textContent;
  }
  async refresh() {
    if (!this.previewClient || this.disposed) return;
    const epoch = this.epoch;
    try { await this.previewClient.refresh(); }
    catch (error) { if (this.current(epoch)) this.problem = `状态同步未确认：${error.message}`; }
    if (this.current(epoch)) this.render();
  }
  async loadCurrentPackage() {
    if (this.loadButton.disabled || this.disposed) return;
    const epoch = this.epoch, request = ++this.loadEpoch, edit = this.edit;
    const current = () => this.current(epoch) && request === this.loadEpoch;
    this.loadPending = true; this.problem = ''; this.render();
    try {
      await this.previewClient.refresh();
      if (!current()) return;
      const revisionId = this.latest()?.revision_id;
      check(HASH.test(revisionId || ''), '当前没有可加载的完整文件包。');
      const response = await this.api(`/api/v1/program-revisions/${revisionId}/files`);
      if (!current()) return;
      check(this.state?.synchronized && this.latest()?.revision_id === revisionId, '当前文件包已变化，请重新加载。');
      check(object(response) && object(response.files) && Object.values(response.files).every(row => row?.encoding === 'base64'), '完整包下载格式无效。');
      const verified = verifyPackage(response.revision, response.files, revisionId);
      const workspace = {revisionId, main: verified.main, total: verified.total, files: structuredClone(response.files)};
      if (this.dirty() || edit !== this.edit) this.staged = workspace;
      else this.install(workspace, false);
    } catch (error) { if (current()) this.problem = `加载完整包失败：${error.message}`; }
    finally { if (current()) { this.loadPending = false; this.render(); } }
  }
  install(workspace, keepMain) {
    this.workspace = workspace;
    if (!keepMain) { this.source.value = workspace.main; this.edit += 1; }
    this.staged = null; this.problem = ''; this.notice = keepMain ? '已采用当前完整包依赖，保留本地 main.py。' : '已加载并校验当前完整包。';
    this.render();
  }
  applyStaged(keepMain) {
    if (!this.staged || !this.state?.synchronized || this.staged.revisionId !== this.latest()?.revision_id) return;
    this.install(this.staged, keepMain);
  }
  async run() {
    if (this.runButton.disabled || this.disposed) return;
    const epoch = this.epoch, click = ++this.click, baseline = this.workspace.revisionId;
    const source = this.currentSource(), files = structuredClone(this.workspace.files);
    files['main.py'] = {encoding: 'utf8', data: source};
    const current = () => this.current(epoch) && click === this.click;
    const request = this.saving = {click};
    this.problem = ''; this.notice = ''; this.render();
    try {
      const response = await this.api('/api/v1/program-revisions', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source_kind: 'uiflow2-package', entrypoint: 'main.py', files})});
      if (!current()) return;
      const verified = verifyPackage(response?.revision, files);
      const revisionId = response.revision.revision_id, generation = `${this.clientTag}-${click}`;
      Object.assign(request, {revisionId, generation, epoch});
      this.localGenerations.set(generation, revisionId);
      const receipt = await this.previewClient.runRevision(revisionId, {clientGeneration: generation, beforeAdmission: state => {
        check(current(), '此运行已被更新的点击或取消替代。');
        check(!this.external(state, baseline), '外部完整包已变化，请先加载并同步依赖。');
        request.expectedGeneration = state.preview.generation + 1;
        this.dispatches.set(generation, request);
      }});
      if (this.current(epoch) && request.cancelRequested) void this.refresh();
      if (!current()) return;
      check(receipt?.revision_id === revisionId, '运行收据的文件包身份不符。');
      this.workspace = {revisionId, main: source, total: verified.total, files};
      this.notice = 'Run 已接收；执行结果以同步状态为准。';
    } catch (error) {
      if (request.generation && error.effectPossible === false) this.dispatches.delete(request.generation);
      if (this.current(epoch) && request.cancelRequested) void this.refresh();
      if (current()) this.problem = `运行未确认：${error.message}。不会自动重试；请同步状态后核对。`;
    } finally {
      if (current() && this.saving === request) { this.saving = null; this.render(); }
    }
  }
  async cancel() {
    if (this.cancelButton.disabled || this.disposed) return;
    const epoch = this.epoch, runId = this.state?.cancelRunId;
    // Freeze only the logical operations which passed admission before this
    // click. A later Run must never inherit this cancellation intent.
    for (const operation of this.dispatches.values()) operation.cancelRequested = true;
    if (runId) {
      const target = this.rememberCancelTarget(runId);
      if (!target.pending) target.attempted = false;
    }
    this.click += 1; this.saving = null; this.cancelPending = true; this.problem = '';
    this.notice = '已撤销尚未提交的本地运行并记录取消意图；已提交的 Run 需要服务器确认中断。';
    this.render();
    this.drainCancellations();
    // Refresh is independent of a slow Run POST. Polling can identify an
    // admitted Run by its exact logical generation even if its receipt is lost.
    try { await this.previewClient.refresh(); this.drainCancellations(); }
    catch (error) {
      // A concurrent cancellation can intentionally replace this read; its
      // independent control request and following poll still own the outcome.
      if (this.current(epoch) && error.code !== 'preview_context_changed') this.problem = `取消结果未确认：${error.message}。请同步状态核对。`;
    }
    finally { if (this.current(epoch)) { this.cancelPending = false; this.render(); } }
  }
  rememberCancelTarget(runId) {
    if (!this.cancelTargets.has(runId)) this.cancelTargets.set(runId, {runId, epoch: this.epoch, attempted: false, pending: false});
    return this.cancelTargets.get(runId);
  }
  drainCancellations() {
    if (!this.state?.synchronized || this.disposed) return;
    const runs = [this.state.activeRun, this.state.desiredRun, this.state.transitionRun].filter(Boolean);
    const terminal = new Set(['completed', 'failed', 'cancelled', 'superseded', 'interrupted']);
    for (const [generation, operation] of this.dispatches) {
      const run = runs.find(row => row.revision_id === operation.revisionId
        && (row.request?.client_generation ?? row.client_generation) === generation);
      if (run) {
        if (terminal.has(run.state)) this.dispatches.delete(generation);
        else if (operation.cancelRequested) this.rememberCancelTarget(run.run_id);
      } else if (this.state.preview.generation > operation.expectedGeneration) this.dispatches.delete(generation);
    }
    for (const [runId, target] of this.cancelTargets) {
      const run = runs.find(row => row.run_id === runId);
      if (run && terminal.has(run.state)) { this.cancelTargets.delete(runId); continue; }
      if (!run || target.attempted || target.pending || !this.current(target.epoch)) continue;
      target.attempted = target.pending = true;
      void this.previewClient.cancel(runId).catch(error => {
        if (this.current(target.epoch)) this.problem = `取消结果未确认：${error.message}。请同步状态核对。`;
      }).finally(() => {
        if (this.current(target.epoch)) { target.pending = false; this.render(); }
      });
    }
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true; this.epoch += 1; this.click += 1; this.loadEpoch += 1;
    this.unsubscribe?.();
    this.root.remove();
  }
}

export function createProgramPanel(container, options) {
  return options.previewClient || managedBinding(options.session)
    ? new PreviewProgramPanel(container, options) : new ProgramPanel(container, options);
}
