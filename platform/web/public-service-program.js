// Native UIFlow programming through the existing Preview/Run API. This adapter
// owns only the Preview it creates; attaching never grants lifecycle ownership.
import {createPreviewClient} from './preview-client.js';
import {Sha256} from './sha256.js';

const ID = /^[0-9a-f]{32}$/;
const SHA = /^[0-9a-f]{64}$/;
const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'superseded', 'interrupted']);
const copy = value => JSON.parse(JSON.stringify(value));
const digest = value => new Sha256().update(new TextEncoder().encode(value)).hex();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const fail = (message, code = 'native_program_invalid') => Object.assign(new Error(message), {code});
const check = (condition, message) => {if (!condition) throw fail(message);};
const aborted = () => new DOMException('设备会话已改变。', 'AbortError');
const owner = session => JSON.stringify([session.session_id, session.created_at, session.firmware_sha256, session.management_binding]);
const canonical = value => JSON.stringify(value, (_key, child) => child && typeof child === 'object' && !Array.isArray(child)
  ? Object.fromEntries(Object.keys(child).sort().map(key => [key, child[key]])) : child);

export class PublicServiceProgram {
  constructor({service, controller = null, onState = () => {}, onOutput = () => {}, onPhase = () => {},
    createKey = () => `public-preview-${globalThis.crypto.randomUUID()}`, pollIntervalMs = 350,
    readyTimeoutMs = 120000, requestTimeoutMs = 30000, stopTimeoutMs = 45000} = {}) {
    check(typeof service?.request === 'function', '缺少原生设备服务。');
    Object.assign(this, {service, controller, onState, onOutput, onPhase, createKey, pollIntervalMs,
      readyTimeoutMs, requestTimeoutMs, stopTimeoutMs});
    this.generation = 0; this.busy = false; this.disposed = false; this.owned = false;
    // PreviewClient uses the ordinary fetch-style JSON body, whereas the public
    // service takes an object. Keep that adaptation in one place.
    this.api = (path, options = {}) => this.request(path, {...options,
      ...(typeof options.body === 'string' ? {body: JSON.parse(options.body)} : {})});
  }

  async request(path, options = {}) {
    const controller = new AbortController();
    const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal;
    let timer;
    try {return await Promise.race([this.service.request(path, {...options, signal}), new Promise((_, reject) => {
      timer = setTimeout(() => {controller.abort(); reject(fail('设备服务请求超时；请同步或停止以确认结果。', 'native_program_timeout'));}, this.requestTimeoutMs);
    })]);} finally {clearTimeout(timer);}
  }

  get ready() {
    return !this.disposed && !this.stopping && this.session?.state === 'running'
      && (this.plain ? this.plainSynchronized === true : this.previewClient?.snapshot().canSubmit === true);
  }
  get canInterrupt() {return !this.plain && !!this.previewClient;}
  get canReplace() {return this.plain === true && this.execution?.phase === 'running';}
  snapshot() {
    return {owned: this.owned, busy: this.busy, ready: this.ready, canInterrupt: this.canInterrupt, canReplace: this.canReplace, session: this.session ? copy(this.session) : null,
      preview: this.previewClient?.snapshot() || null, createPending: !!this.createIntent, stopping: !!this.stopping};
  }
  current(generation) {
    if (this.disposed || this.stopping || generation !== this.generation || !this.session) throw aborted();
    if (this.controller && (!this.controller.current || owner(this.controller.current) !== this.ownerKey)) throw aborted();
  }
  bindSession(session) {
    check(this.session && owner(session) === this.ownerKey, '编程状态不属于当前原生会话。');
    this.session = copy(session);
    this.previewClient?.updateSession(session);
  }

  async bind(session, {owned}) {
    const generation = this.generation;
    check(ID.test(session?.session_id || '') && SHA.test(session?.firmware_sha256 || '')
      && session.program_transport === 'uart-repl' && ID.test(session.management_binding?.preview_id || '')
      && ID.test(session.management_binding?.owner_epoch || '') && SHA.test(session.management_binding?.expected_reference_sha256 || ''),
    '该会话没有可验证的 UIFlow Preview 编程绑定。');
    this.session = copy(session); this.ownerKey = owner(session); this.owned = owned; this.plain = false;
    this.previewClient = createPreviewClient({session, api: this.api});
    this.unsubscribe = this.previewClient.subscribe(state => this.onState(state));
    await this.previewClient.refresh();
    if (generation !== this.generation || this.stopping || this.disposed) throw aborted();
    if (this.controller) await this.controller.adoptManagedSession(session, this.previewClient, {owned, stop: () => this.stop()});
    return {session: copy(this.session), previewClient: this.previewClient};
  }

  start(options = {}) {
    if (this.starting || this.session || this.createIntent || this.disposed) return Promise.reject(fail('请先停止当前编程设备。'));
    this.controller?.setManagedStop(() => this.stop());
    const operation = this.startOwned(options);
    this.starting = operation;
    return operation.finally(() => {if (this.starting === operation) this.starting = null;});
  }
  async startOwned({deviceId, units = [], signal, ttlSeconds = 600} = {}) {
    const generation = ++this.generation;
    check(Number.isSafeInteger(ttlSeconds) && ttlSeconds >= 30 && ttlSeconds <= 3600, '租约需要在 30–3600 秒之间。');
    if (signal?.aborted) throw aborted();
    const devices = await this.request('/api/v1/devices', {signal});
    const device = devices.devices?.find(row => row.device_id === deviceId);
    check(device?.creatable === true && device.program_modes?.includes('uiflow-live'), '当前后端未开放此型号的 UIFlow 实时编程。');
    if (signal?.aborted || generation !== this.generation) throw aborted();
    const body = copy({device_id: deviceId, units, ttl_seconds: ttlSeconds});
    const key = this.createKey(); check(typeof key === 'string' && /^[\x21-\x7e]{1,128}$/.test(key), '创建请求标识无效。');
    this.createIntent = {body, key, attempts: 0, uncertain: false}; this.owned = true;
    // Do not abort a create after dispatch and lose its allocated identity.
    const receipt = await this.recoverCreation();
    const deadline = Date.now() + this.readyTimeoutMs;
    let preview = receipt;
    for (;;) {
      this.validateCreation(preview, body);
      if (preview.state === 'failed' || preview.state === 'closed') throw fail(preview.error?.message || '编程设备未能启动。');
      if (signal?.aborted || generation !== this.generation) throw aborted();
      if (preview.state === 'ready' && preview.allocation_state === 'bound' && ID.test(preview.session_id || '')) {
        const session = await this.request(`/api/v1/sessions/${preview.session_id}`);
        check(session.device_id === deviceId && session.management_binding?.preview_id === preview.preview_id
          && session.management_binding?.owner_epoch === preview.owner_epoch, '创建的 Preview 与设备会话身份不符。');
        if (signal?.aborted || generation !== this.generation) throw aborted();
        return this.bind(session, {owned: true});
      }
      if (Date.now() >= deadline) throw fail('等待 UIFlow 编程设备启动超时。', 'native_program_boot_timeout');
      await delay(this.pollIntervalMs);
      preview = await this.request(`/api/v1/previews/${receipt.preview_id}`);
    }
  }
  validateCreation(preview, body = this.createIntent?.body) {
    check(ID.test(preview?.preview_id || '') && ID.test(preview.owner_epoch || '') && preview.owner === 'local-control'
      && preview.request?.device_id === body?.device_id && canonical(preview.request?.units || []) === canonical(body?.units || []), 'Preview 创建收据身份无效。');
    if (this.creation) check(preview.preview_id === this.creation.preview_id && preview.owner_epoch === this.creation.owner_epoch,
      'Preview 创建身份发生变化。');
    if (this.creation?.session_id) check(preview.session_id === this.creation.session_id, 'Preview 已分配的会话发生变化。');
    this.creation = copy(preview);
  }
  async recoverCreation() {
    check(this.createIntent, '缺少原始创建意图。');
    const intent = this.createIntent, {body, key} = intent;
    const firstKnownAttempt = ++intent.attempts === 1 && !intent.uncertain;
    try {
      const receipt = await this.request('/api/v1/previews', {method: 'POST', headers: {'Idempotency-Key': key}, body: copy(body)});
      this.validateCreation(receipt, body);
      return receipt;
    } catch (error) {
      // serve._handle_v1 rejects unauthorized requests before routing; its
      // _handle_preview rejects missing configured control credentials before
      // opening PreviewService or reading a create body. The latter is an
      // explicit 503, despite the public client's generic 5xx uncertainty flag.
      // No other 5xx, transport failure, or recovery attempt can retire intent.
      const rejectedBeforeAllocation = error.status === 401 && error.code === 'unauthorized'
        || error.status === 503 && error.code === 'preview_auth_unavailable';
      if (firstKnownAttempt && rejectedBeforeAllocation) {this.createIntent = null; this.owned = false;}
      else intent.uncertain = true;
      throw error;
    }
  }
  async attach(session) {
    check(!this.session && !this.createIntent && !this.disposed, '请先离开当前设备。');
    this.controller?.setManagedStop(() => this.stop());
    ++this.generation;
    if (!session.management_binding) {
      check(ID.test(session.session_id || '') && SHA.test(session.firmware_sha256 || '')
        && session.program_transport === 'uart-repl' && session.state === 'running', '该会话没有可用的 UART 编程入口。');
      this.session = copy(session); this.ownerKey = owner(session); this.owned = false; this.plain = true;
      await this.refresh();
      if (this.controller) await this.controller.adoptSession(session, {owned: false, stop: () => this.stop()});
      return {session: copy(session), previewClient: null};
    }
    return this.bind(session, {owned: false});
  }
  async refresh() {
    if (!this.plain) return this.previewClient?.refresh();
    const session = this.session, generation = this.generation;
    const result = await this.request(`/api/v1/sessions/${session.session_id}/program`);
    if (generation !== this.generation || this.stopping || this.disposed || owner(this.session) !== owner(session)) throw aborted();
    check(result.session_id === session.session_id && result.program_transport === 'uart-repl'
      && !result.history_error && (result.program === null || ID.test(result.program?.execution_id || '')), '程序状态与当前会话不符或历史不可验证。');
    this.plainProgram = result.program; this.plainSynchronized = true;
    return result;
  }

  run(source, {onOutput = this.onOutput, onPhase = this.onPhase, signal} = {}) {
    if (this.busy && !this.canReplace || !this.ready) return Promise.reject(fail('设备尚未就绪或代码仍在运行。'));
    check(typeof source === 'string' && !!source.trim(), '请输入 MicroPython 源码。');
    check(new TextEncoder().encode(source).length <= 65536, '源码超过 64 KiB。');
    check(!/[\x00-\x08\x0b\x0e-\x1f\x7f]/.test(source), '源码包含原始控制字符。');
    if (this.execution) this.execution.replaced = true;
    const operation = this.execution = {generation: this.generation, onPhase, onOutput, phase: 'uploading', output: '', serial: '', emitted: 0};
    this.busy = true; onPhase('uploading');
    return (this.plain ? this.runPlain(source, operation, signal) : this.runSource(source, operation, signal))
      .catch(error => {if (operation.replaced) return {state: 'superseded', output: operation.output, channel: 'serial'}; throw error;})
      .finally(() => {if (this.execution === operation) {this.busy = false; this.execution = null;}});
  }
  async runPlain(source, operation, signal) {
    const valid = () => {this.current(operation.generation); if (signal?.aborted || this.execution !== operation) throw aborted();};
    valid(); await this.refresh(); valid();
    const expected = this.plainProgram?.execution_id ?? null;
    this.plainSynchronized = false;
    const result = await this.request(`/api/v1/sessions/${this.session.session_id}/program`, {method: 'POST',
      body: {source, expected_execution_id: expected}});
    valid();
    check(result.session_id === this.session.session_id && result.program_transport === 'uart-repl' && ID.test(result.program?.execution_id || ''), '程序提交收据身份无效。');
    operation.executionId = result.program.execution_id; operation.revisionId = result.program.revision_id;
    const sourceHash = digest(source);
    for (;;) {
      valid(); const state = await this.refresh(); valid(); const program = state.program;
      check(program?.execution_id === operation.executionId && program.revision_id === operation.revisionId
        && program.firmware_sha256 === this.session.firmware_sha256 && program.pid === this.session.pid
        && program.source_sha256 === sourceHash, '当前程序已被替换或执行身份不符。');
      if (operation.offset === undefined && Number.isSafeInteger(program.serial_offset) && program.serial_offset >= 0) operation.offset = program.serial_offset;
      if (operation.offset !== undefined) await this.readOutput(operation, TERMINAL.has(program.state));
      valid();
      if (program.state === 'running' && operation.phase !== 'running') {operation.phase = 'running'; operation.onPhase('running');}
      if (TERMINAL.has(program.state)) {
        operation.onPhase(['interrupted', 'cancelled', 'superseded'].includes(program.state) ? 'interrupted' : program.state === 'failed' ? 'error' : 'complete');
        return {state: program.state, output: operation.output, channel: 'serial', program: copy(program)};
      }
      if (!['submitting', 'running'].includes(program.state)) throw fail(program.error?.message || '程序执行结果未确认。');
      await delay(this.pollIntervalMs);
    }
  }
  async runSource(source, operation, signal) {
    const valid = () => {this.current(operation.generation); if (signal?.aborted) throw aborted();};
    valid();
    const sourceHash = digest(source), hashes = {'main.py': sourceHash};
    const revisionId = digest(JSON.stringify({entrypoint: 'main.py', files: hashes, source_kind: 'uiflow2-package'}));
    const result = await this.request('/api/v1/program-revisions', {method: 'POST', body: {
      source_kind: 'uiflow2-package', entrypoint: 'main.py', files: {'main.py': {encoding: 'utf8', data: source}}}});
    valid();
    check(result.revision?.revision_id === revisionId && result.revision.source_kind === 'uiflow2-package'
      && result.revision.entrypoint === 'main.py' && result.revision.total_file_bytes === new TextEncoder().encode(source).length
      && result.revision.files?.length === 1 && result.revision.files[0].path === 'main.py'
      && result.revision.files[0].sha256 === sourceHash, '源码 revision 收据与提交字节不符。');
    const receipt = await this.previewClient.runRevision(revisionId, {beforeAdmission: valid});
    valid(); operation.runId = receipt.run_id; operation.revisionId = revisionId; operation.executionId = receipt.execution_id;
    const deadline = Date.now() + this.readyTimeoutMs;
    for (;;) {
      valid();
      const state = await this.previewClient.refresh(); valid();
      const run = [state.activeRun, state.desiredRun, state.transitionRun].find(row => row?.run_id === operation.runId)
        || await this.request(`/api/v1/previews/${this.session.management_binding.preview_id}/runs/${operation.runId}`);
      valid();
      check(run.run_id === operation.runId && run.execution_id === operation.executionId && run.revision_id === revisionId
        && run.preview_id === this.session.management_binding.preview_id && run.generation === receipt.generation
        && ['queued', 'preparing', 'starting', 'running', 'completed', 'failed', 'unknown', 'cancelling', 'cancelled', 'superseded', 'interrupted'].includes(run.state), 'Run 响应不属于本次代码。');
      const observed = run.last_observation;
      if (observed) {
        check(observed.execution_id === operation.executionId && observed.revision_id === revisionId
          && observed.firmware_sha256 === this.session.firmware_sha256 && observed.pid === this.session.pid, '程序输出会话身份不符。');
        if (operation.offset === undefined && Number.isSafeInteger(observed.serial_offset) && observed.serial_offset >= 0) operation.offset = observed.serial_offset;
        if (operation.offset !== undefined) await this.readOutput(operation, TERMINAL.has(run.state));
        valid();
      }
      if (run.state === 'running' && operation.phase !== 'running') {operation.phase = 'running'; operation.onPhase('running');}
      if (TERMINAL.has(run.state)) {
        const phase = ['cancelled', 'interrupted', 'superseded'].includes(run.state) ? 'interrupted' : run.state === 'failed' ? 'error' : 'complete';
        operation.onPhase(phase);
        return {state: run.state, output: operation.output, channel: 'serial', run: copy(run)};
      }
      if (run.state === 'unknown' || state.error) throw fail(run.error?.message || state.error || '程序结果未确认。');
      if (operation.phase !== 'running' && Date.now() >= deadline) throw fail('程序开始执行未确认。');
      await delay(this.pollIntervalMs);
    }
  }
  async readOutput(operation, terminal) {
    const serial = await this.request(`/api/v1/sessions/${this.session.session_id}/serial?offset=${operation.offset}&limit=65536`);
    this.current(operation.generation);
    if (this.execution !== operation) throw aborted();
    check(Number.isSafeInteger(serial.next_offset) && serial.next_offset >= operation.offset && typeof serial.data === 'string', '串口输出位置无效。');
    operation.offset = serial.next_offset; operation.serial += serial.data;
    check(operation.serial.length <= 131072, '串口输出超过缓冲区上限。');
    const prefix = `__M5_EXEC_${operation.executionId}__:`;
    const start = operation.serial.indexOf(prefix + 'START');
    if (start < 0) return;
    let text = operation.serial.slice(start + prefix.length + 5).replace(/^\r?\n/, '');
    // A replacing external Run must never have its serial attributed to ours.
    const end = text.search(/__M5_EXEC_[0-9a-f]{32}__:/);
    if (end >= 0) text = text.slice(0, end);
    else if (!terminal) {
      let hold = text.match(/__M5_EXEC_[0-9a-f]{0,32}(?:_{0,2}:?)?$/)?.[0].length || 0;
      const beginning = '__M5_EXEC_';
      for (let size = 1; size < beginning.length; size++) if (text.endsWith(beginning.slice(0, size))) hold = Math.max(hold, size);
      if (hold) text = text.slice(0, -hold);
    }
    if (text.length > operation.emitted) {const chunk = text.slice(operation.emitted); operation.output += chunk; operation.emitted = text.length; operation.onOutput(chunk, 'serial');}
  }
  interrupt() {
    if (this.plain) return Promise.reject(fail('此普通会话的 API 不提供独立中断；可运行新代码替换当前程序，或使用设备会话控制台。', 'native_interrupt_unavailable'));
    const operation = this.execution;
    if (!this.busy || !operation) return Promise.resolve();
    this.current(operation.generation);
    check(operation.phase === 'running' && operation.runId, '代码正在传输，请稍后中断。');
    if (!operation.interruptPromise) operation.interruptPromise = Promise.resolve().then(() => {
      this.current(operation.generation); return this.previewClient.cancel(operation.runId);
    });
    return operation.interruptPromise;
  }

  stop() {
    if (this.stopping) return this.stopping;
    ++this.generation;
    const operation = this.stopOwned();
    this.stopping = operation;
    return operation.finally(() => {if (this.stopping === operation) this.stopping = null;});
  }
  async stopOwned() {
    if (this.starting) await this.starting.catch(() => {});
    if (this.owned && this.createIntent) {
      if (!this.creation) await this.recoverCreation();
      const previewId = this.creation.preview_id, ownerEpoch = this.creation.owner_epoch;
      let preview = await this.request(`/api/v1/previews/${previewId}`);
      this.validateCreation(preview);
      const sessionId = preview.session_id;
      if (sessionId) {
        check(ID.test(sessionId), '停止收据中的会话身份无效。');
        let evidenceTimer;
        const evidenceAbort = new AbortController();
        try {this.lastEvidence = await Promise.race([this.service.evidence(sessionId, {signal: evidenceAbort.signal}), new Promise((_, reject) => {
          evidenceTimer = setTimeout(() => {evidenceAbort.abort(); reject(fail('证据 ZIP 导出超时。'));}, this.requestTimeoutMs);
        })]);} catch (error) {this.evidenceError = error;} finally {clearTimeout(evidenceTimer);}
      }
      if (this.previewClient) await this.previewClient.close();
      else await this.request(`/api/v1/previews/${previewId}/close`, {method: 'POST', body: {expected_owner_epoch: ownerEpoch}});
      const deadline = Date.now() + this.stopTimeoutMs;
      for (;;) {
        preview = await this.request(`/api/v1/previews/${previewId}`); this.validateCreation(preview);
        const id = preview.session_id;
        const session = id ? await this.request(`/api/v1/sessions/${id}`) : null;
        if (session) check(session.session_id === id && session.device_id === this.createIntent.body.device_id
          && session.management_binding?.preview_id === previewId && session.management_binding?.owner_epoch === ownerEpoch, '停止状态属于其他会话。');
        if (preview.state === 'closed' && (!id || ['stopped', 'failed'].includes(session.state) && !session.stop_pending && session.worker?.lease_active === false)) break;
        if (Date.now() >= deadline) throw fail('服务未确认停止，已保留会话身份，请重试停止。');
        await delay(this.pollIntervalMs);
      }
    }
    this.unsubscribe?.(); this.previewClient?.dispose(); this.previewClient = null;
    this.session = null; this.creation = null; this.createIntent = null; this.owned = false;
    this.plain = false; this.plainSynchronized = false; this.plainProgram = null;
  }
  async dispose() {await this.stop(); this.disposed = true;}
}
