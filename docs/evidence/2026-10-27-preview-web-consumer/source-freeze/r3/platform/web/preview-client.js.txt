// One ownership-aware Preview coordinator shared by all panels of a session.
// Receipts acknowledge requests; only fresh authoritative GETs publish state.
const ID = /^[0-9a-f]{32}$/;
const SHA = /^[0-9a-f]{64}$/;
const PREVIEW_STATES = new Set(['preparing', 'ready', 'closing', 'closed', 'failed', 'unknown']);
const ALLOCATION_STATES = new Set(['pending', 'creating', 'bound', 'failed', 'unknown']);
const RUN_STATES = new Set(['queued', 'preparing', 'starting', 'running', 'completed', 'failed', 'unknown', 'cancelling', 'cancelled', 'superseded', 'interrupted']);
const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'superseded', 'interrupted']);
const PROGRAM_STATES = new Set(['submitting', 'running', 'completed', 'failed', 'unknown', 'interrupted', 'interrupt-requested', 'cancelled']);
const CAPABILITIES = {
  execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only',
  latest_wins: true, run_cancellation: true, input: true, frame: 'on-demand',
  events: 'polling', application_ready: 'unknown', main_mpy: false,
  hotplug: false, gc_enabled: false, principal_mode: 'shared-control-bearer-local-control',
};
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const clone = value => JSON.parse(JSON.stringify(value));
const integer = value => Number.isSafeInteger(value) && value >= 0;
const date = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const nullableId = value => value === null || typeof value === 'string' && ID.test(value);
const identity = value => typeof value === 'string' && ID.test(value);
const digest = value => typeof value === 'string' && SHA.test(value);
const canonical = value => JSON.stringify(value, (_key, child) => object(child)
  ? Object.fromEntries(Object.keys(child).sort().map(key => [key, child[key]])) : child);

function freeze(value) {
  if (object(value) || Array.isArray(value)) {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

function error(message, code = 'preview_response_invalid', effectPossible = false) {
  return Object.assign(new Error(message), {code, effectPossible});
}

function require(value, message = 'Preview 响应无法验证。') {
  if (!value) throw error(message);
}

function stale() {
  return error('Preview 上下文已变化，请同步当前 Run。', 'preview_context_changed');
}

function randomKey() {
  const crypto = globalThis.crypto;
  if (typeof crypto?.randomUUID === 'function') return crypto.randomUUID();
  if (typeof crypto?.getRandomValues !== 'function') throw error('当前环境不能生成安全的请求标识。', 'preview_random_unavailable');
  return [...crypto.getRandomValues(new Uint8Array(24))].map(value => value.toString(16).padStart(2, '0')).join('');
}

function bindingOf(session) {
  const binding = session?.management_binding;
  require(object(binding) && Object.keys(binding).sort().join(',') === 'expected_reference_sha256,owner_epoch,preview_id', 'Preview 管理绑定缺失或格式无效，已禁用写入。');
  require(identity(binding.preview_id) && identity(binding.owner_epoch) && digest(binding.expected_reference_sha256));
  require(identity(session.session_id) && digest(session.firmware_sha256));
  require(typeof session.device_id === 'string' && !!session.device_id);
  require(['booting', 'running', 'stopped', 'failed'].includes(session.state));
  return clone(binding);
}

function validatePreview(row, session, binding) {
  require(object(row));
  require(row.preview_id === binding.preview_id && row.owner_epoch === binding.owner_epoch && row.owner === 'local-control');
  require(integer(row.generation) && PREVIEW_STATES.has(row.state) && ALLOCATION_STATES.has(row.allocation_state));
  require(date(row.created_at) && date(row.updated_at) && date(row.expires_at));
  require(['active_run_id', 'desired_run_id', 'transition_run_id'].every(key => key in row && nullableId(row[key])));
  require(row.session_id === session.session_id && row.allocation_state === 'bound', 'Preview 未绑定到当前设备会话。');
  require(object(row.session_identity) && row.session_identity.session_id === session.session_id && row.session_identity.firmware_sha256 === session.firmware_sha256);
  require(object(row.request) && row.request.device_id === session.device_id);
  require(object(row.session_request) && row.session_request.device_id === session.device_id && row.session_request.reference_sha256 === binding.expected_reference_sha256);
  require(row.allocation_key === `preview:${binding.preview_id}:allocation:1`);
  require(object(row.capabilities) && Object.entries(CAPABILITIES).every(([key, value]) => row.capabilities[key] === value));
  require(object(row.limits) && row.limits.gc_enabled === false && row.limits.retention_mode === 'retention-only'
    && Number.isSafeInteger(row.limits.max_previews) && row.limits.max_previews > 0
    && Number.isSafeInteger(row.limits.max_runs_per_preview) && row.limits.max_runs_per_preview > 0);
  require(row.error === null || object(row.error) && typeof row.error.code === 'string' && typeof row.error.message === 'string');
  require(!('blocked_reason' in row) || row.blocked_reason === null || typeof row.blocked_reason === 'string');
  require(row.state !== 'closed' || row.active_run_id === null && row.transition_run_id === null);
  return clone(row);
}

function validateRun(row, preview, session, binding, maximumGeneration = preview.generation) {
  require(object(row) && row.preview_id === binding.preview_id && identity(row.run_id) && identity(row.execution_id) && digest(row.revision_id));
  require(integer(row.generation) && row.generation > 0 && row.generation <= maximumGeneration && RUN_STATES.has(row.state));
  require(row.source_kind === 'uiflow2-package' && row.execution_mode === 'same-guest-uart-repl' && row.cleanup_mode === 'interrupt-only');
  require(typeof row.cancel_intent === 'boolean' && ['unknown', 'confirmed', 'not-required'].includes(row.interrupt_ack) && row.application_ready === 'unknown');
  require(date(row.created_at) && date(row.updated_at));
  require(typeof row.timeout_seconds === 'number' && Number.isFinite(row.timeout_seconds) && row.timeout_seconds >= 1 && row.timeout_seconds <= 120);
  require(row.client_generation === null || typeof row.client_generation === 'string' && row.client_generation.length > 0 && new TextEncoder().encode(row.client_generation).length <= 256);
  require(object(row.request) && row.request.revision_id === row.revision_id && row.request.expected_owner_epoch === binding.owner_epoch
    && row.request.expected_generation === row.generation - 1
    && (row.request.timeout_seconds ?? 120) === row.timeout_seconds && (row.request.client_generation ?? null) === row.client_generation);
  require(Object.keys(row.request).every(key => ['revision_id', 'expected_generation', 'expected_owner_epoch', 'client_generation', 'timeout_seconds'].includes(key)));
  require(row.error === null || object(row.error) && typeof row.error.code === 'string' && typeof row.error.message === 'string');
  require(!row.cancel_intent || !['queued', 'preparing', 'starting', 'running'].includes(row.state));
  require(!['cancelled', 'superseded'].includes(row.state) || row.cancel_intent);
  require(row.state !== 'cancelled' || ['confirmed', 'not-required'].includes(row.interrupt_ack));
  if (row.last_observation != null) {
    const observed = row.last_observation;
    require(object(observed) && observed.execution_id === row.execution_id && observed.revision_id === row.revision_id
      && observed.firmware_sha256 === session.firmware_sha256 && observed.pid === session.pid
      && observed.execution_mode === 'same-guest-uart-repl' && PROGRAM_STATES.has(observed.state));
  }
  return clone(row);
}

function runIdentity(run) {
  return canonical([run.preview_id, run.run_id, run.execution_id, run.revision_id, run.generation,
    run.source_kind, run.request, run.created_at, run.client_generation, run.timeout_seconds, run.execution_mode, run.cleanup_mode]);
}

class PreviewClient {
  constructor({session, api}) {
    if (typeof api !== 'function') throw new TypeError('api must be a function');
    this.api = api;
    this.listeners = new Set();
    this.pending = new Set();
    this.runIntents = new Map();
    this.watermarks = new Map();
    this.admissions = Promise.resolve();
    this.bindingEpoch = 0;
    this.effectEpoch = 0;
    this.readSequence = 0;
    this.minimumGeneration = 0;
    this.disposed = false;
    this.updateSession(session);
  }

  updateSession(session) {
    if (this.disposed) return;
    let binding = null, fault = '';
    try { binding = bindingOf(session); } catch (cause) { fault = cause.message; }
    const key = JSON.stringify([session?.session_id, session?.created_at, session?.firmware_sha256, session?.management_binding]);
    const changed = key !== this.bindingKey;
    const stateChanged = session?.state !== this.session?.state || session?.pid !== this.session?.pid;
    this.session = clone(session || {});
    this.binding = binding;
    this.bindingFault = fault;
    if (changed) {
      this.bindingKey = key;
      this.bindingEpoch += 1;
      this.effectEpoch += 1;
      this.invalidateReads();
      this.preview = null;
      this.runs = new Map();
      this.watermarks.clear();
      this.runIntents.clear();
      this.minimumGeneration = 0;
      this.pending.clear();
      this.admissions = Promise.resolve();
      this.closing = false;
      this.synchronized = false;
      this.fault = '';
    } else if (stateChanged) {
      this.effectEpoch += 1;
      this.invalidateReads();
      this.synchronized = false;
    }
    this.emit();
    if (binding && (changed || stateChanged)) void this.refresh().catch(() => {});
  }

  invalidateReads() {
    this.readSequence += 1;
    this.reading?.controller.abort();
    this.reading = null;
    clearTimeout(this.timer);
  }

  current(epoch) { return !this.disposed && !!this.binding && epoch === this.bindingEpoch; }

  snapshot() {
    const preview = this.preview || null;
    const active = preview && this.runs?.get(preview.active_run_id) || null;
    const desired = preview && this.runs?.get(preview.desired_run_id) || null;
    const transition = preview && this.runs?.get(preview.transition_run_id) || null;
    const pending = this.pending.size > 0;
    const expired = !!preview && Date.parse(preview.expires_at) <= Date.now();
    const synchronized = !!this.binding && !!this.synchronized && !this.disposed;
    const fault = this.bindingFault || this.fault || (expired ? 'Preview 租约已过期。' : '')
      || preview?.error?.message || preview?.blocked_reason || '';
    const writable = synchronized && !fault && !expired && !this.closing && ['booting', 'running'].includes(this.session.state)
      && ['preparing', 'ready'].includes(preview?.state);
    const stable = writable && !pending && preview.state === 'ready' && preview.allocation_state === 'bound'
      && this.session.state === 'running' && !!active && !active.cancel_intent
      && ['running', 'completed'].includes(active.state) && !transition
      && (!desired || desired.run_id === active.run_id);
    let context = null;
    if (stable) {
      context = {previewId: preview.preview_id, ownerEpoch: preview.owner_epoch, sessionId: preview.session_id,
        runId: active.run_id, executionId: active.execution_id, revisionId: active.revision_id};
      context.key = JSON.stringify([this.bindingKey, this.bindingEpoch, preview.generation, active.run_id, active.execution_id,
        active.revision_id, active.state, active.cancel_intent, preview.transition_run_id, preview.desired_run_id]);
    }
    const cancelRun = [desired, transition, active].find(run => run && !TERMINAL.has(run.state));
    return freeze(clone({managed: true, synchronized, error: fault, pending, preview,
      activeRun: active, desiredRun: desired, transitionRun: transition,
      frameContext: context, inputContext: active?.state === 'running' ? context : null,
      canSubmit: !!writable, canInput: !!context && active.state === 'running',
      canCancel: !!this.binding && !this.disposed && !!cancelRun && preview?.state !== 'closed',
      canRenew: !!writable && !pending, canClose: !!this.binding && !this.disposed && !this.closing && preview?.state !== 'closed',
      cancelRunId: cancelRun?.run_id || null}));
  }

  emit() {
    const snapshot = this.snapshot();
    for (const listener of this.listeners) { try { listener(snapshot); } catch { /* A panel must not break another panel's fence. */ } }
  }

  subscribe(listener) {
    if (typeof listener !== 'function') throw new TypeError('listener must be a function');
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  schedule() {
    clearTimeout(this.timer);
    if (this.disposed || !this.binding) return;
    const busy = this.pending.size || this.preview?.transition_run_id || this.preview?.desired_run_id || this.preview?.active_run_id;
    const delay = globalThis.document?.hidden ? 3000 : busy ? 500 : 1000;
    this.timer = setTimeout(() => { void this.refresh().catch(() => {}); }, delay);
    this.timer?.unref?.();
  }

  refresh() { return this.read(false); }

  read(force) {
    if (this.disposed || !this.binding) return Promise.reject(error(this.bindingFault || 'Preview 客户端已关闭。', 'preview_binding_invalid'));
    if (force) this.invalidateReads();
    if (this.reading) return this.reading.promise;
    clearTimeout(this.timer);
    const epoch = this.bindingEpoch, sequence = ++this.readSequence;
    const controller = new AbortController();
    const binding = clone(this.binding), session = clone(this.session);
    const valid = () => this.current(epoch) && sequence === this.readSequence;
    const request = (async () => {
      try {
        const value = await Promise.resolve().then(() => this.api(`/api/v1/previews/${binding.preview_id}`, {signal: controller.signal}));
        if (!valid()) throw stale();
        const preview = validatePreview(value, session, binding);
        require(preview.generation >= this.minimumGeneration, 'Preview 代际倒退，已停止应用旧响应。');
        if (this.preview) {
          require(['preview_id', 'owner', 'owner_epoch', 'created_at', 'request', 'session_request', 'limits', 'allocation_key']
            .every(key => canonical(preview[key]) === canonical(this.preview[key])), 'Preview 不可变字段发生变化。');
          require(preview.generation >= this.preview.generation);
          require(this.preview.state !== 'closed' || preview.state === 'closed');
          require(preview.generation !== this.preview.generation || Date.parse(preview.updated_at) >= Date.parse(this.preview.updated_at));
        }
        const ids = [...new Set([preview.active_run_id, preview.desired_run_id, preview.transition_run_id].filter(Boolean))];
        const records = await Promise.all(ids.map(async id => {
          const row = await this.api(`/api/v1/previews/${binding.preview_id}/runs/${id}`, {signal: controller.signal});
          if (!valid()) throw stale();
          const run = validateRun(row, preview, session, binding);
          require(run.run_id === id);
          const previous = this.watermarks.get(id);
          if (previous) {
            require(runIdentity(previous) === runIdentity(run));
            require(!previous.cancel_intent || run.cancel_intent);
            require(!TERMINAL.has(previous.state) || run.state === previous.state);
            require(previous.state !== 'cancelling' || ['cancelling', 'cancelled', 'interrupted'].includes(run.state));
            require(Date.parse(run.updated_at) >= Date.parse(previous.updated_at));
          }
          return [id, run];
        }));
        if (!valid()) throw stale();
        const runs = new Map(records);
        if (preview.desired_run_id) require(runs.get(preview.desired_run_id).generation === preview.generation);
        if (preview.transition_run_id) require(!TERMINAL.has(runs.get(preview.transition_run_id).state));
        if (preview.active_run_id) {
          const active = runs.get(preview.active_run_id);
          require(['running', 'completed', 'cancelling'].includes(active.state));
          if (active.state !== 'cancelling') require(!active.cancel_intent && active.last_observation?.acknowledged === true
            && active.last_observation.state === active.state);
        }
        this.preview = preview;
        this.runs = runs;
        for (const [id, run] of runs) this.watermarks.set(id, run);
        this.minimumGeneration = Math.max(this.minimumGeneration, preview.generation);
        this.synchronized = true;
        this.fault = '';
        this.emit();
        return this.snapshot();
      } catch (cause) {
        if (valid()) {
          this.synchronized = false;
          this.fault = cause.message || 'Preview 同步失败。';
          this.emit();
        }
        throw cause;
      } finally {
        if (valid()) { this.reading = null; this.schedule(); }
      }
    })();
    this.reading = {promise: request, controller, sequence};
    return request;
  }

  async freshRead(epoch, effect) {
    const barrier = this.readSequence;
    for (;;) {
      if (!this.current(epoch) || effect !== this.effectEpoch) throw stale();
      const existing = this.reading;
      // Join only a request issued after this bracket was requested. Waiting
      // for an earlier poll avoids two panels repeatedly aborting each other.
      if (existing && existing.sequence > barrier) return existing.promise;
      if (!existing) return this.read(false);
      try { await existing.promise; } catch { /* An older poll cannot supply this bracket's fresh result. */ }
    }
  }

  captureInput() { return this.snapshot().inputContext; }

  matches(context, kind = 'input') {
    if (!['input', 'frame'].includes(kind)) return false;
    const current = this.snapshot()[kind === 'input' ? 'inputContext' : 'frameContext'];
    return !!context && !!current && Object.keys(current).every(key => current[key] === context[key]);
  }

  async input(context, kind, command, options = {}) {
    if (!['input', 'unit_input'].includes(kind) || !object(command)) throw error('输入命令格式无效。', 'invalid_input');
    if (!this.matches(context)) throw stale();
    const captured = clone(context), epoch = this.bindingEpoch, effect = this.effectEpoch;
    try {
      const receipt = await this.api(`/api/v1/previews/${captured.previewId}/input`, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, keepalive: options.keepalive === true,
        body: JSON.stringify({expected_owner_epoch: captured.ownerEpoch, expected_run_id: captured.runId, [kind]: clone(command)})});
      require(object(receipt) && receipt.preview_id === captured.previewId && receipt.run_id === captured.runId
        && receipt.execution_id === captured.executionId && receipt.revision_id === captured.revisionId
        && date(receipt.captured_at) && object(receipt.result), '输入回执身份不匹配。');
      if (!this.current(epoch) || effect !== this.effectEpoch || !this.matches(captured)) throw stale();
      return freeze(clone(receipt));
    } catch (cause) {
      if (cause.effectPossible !== false) cause.effectPossible = true;
      // A wrong or late successful receipt can follow a real input effect.
      if (cause.code === 'preview_response_invalid' || cause.code === 'preview_context_changed') cause.effectPossible = true;
      if (this.current(epoch) && effect === this.effectEpoch) {
        this.synchronized = false;
        this.fault = cause.effectPossible ? '输入效果未确认；请同步状态，不会自动重放。' : cause.message;
        this.invalidateReads();
        this.emit();
        this.schedule();
      }
      throw cause;
    }
  }

  async readSession(context, action) {
    if (!['units', 'device-state'].includes(action)) throw error('不支持的会话读取。', 'invalid_preview_read');
    if (!this.matches(context, 'frame')) throw stale();
    const captured = clone(context), epoch = this.bindingEpoch, effect = this.effectEpoch;
    const check = () => { if (!this.current(epoch) || effect !== this.effectEpoch || !this.matches(captured, 'frame')) throw stale(); };
    try {
      await this.freshRead(epoch, effect);
      check();
      const result = await this.api(`/api/v1/sessions/${captured.sessionId}/${action}`);
      check();
      require(object(result) && result.session_id === captured.sessionId, '会话读取响应身份不匹配。');
      await this.freshRead(epoch, effect);
      check();
      return clone(result);
    } catch (cause) {
      if (this.current(epoch) && effect === this.effectEpoch && cause.code !== 'preview_context_changed') {
        this.synchronized = false;
        this.fault = cause.message || 'Preview 会话读取未确认。';
        this.emit();
        this.schedule();
      }
      throw cause;
    }
  }

  begin() {
    if (this.disposed || !this.binding) throw error(this.bindingFault || 'Preview 管理绑定无效。', 'preview_binding_invalid');
    const token = {epoch: this.bindingEpoch};
    this.pending.add(token);
    this.effectEpoch += 1;
    this.emit();
    return token;
  }

  finish(token) {
    this.pending.delete(token);
    if (this.current(token.epoch)) {
      this.synchronized = false;
      this.emit();
      void this.read(true).catch(() => {});
    }
  }

  runRevision(revisionId, options = {}) {
    if (typeof revisionId !== 'string' || !SHA.test(revisionId)) return Promise.reject(error('revision_id 必须为 SHA256。', 'invalid_revision_id'));
    let token, key;
    try {
      require(object(options));
      options = {...options};
      key = options.idempotencyKey ?? randomKey();
      require(typeof key === 'string' && /^[\x21-\x7e]{1,128}$/.test(key));
      if (options.clientGeneration !== undefined) require(typeof options.clientGeneration === 'string' && new TextEncoder().encode(options.clientGeneration).length > 0 && new TextEncoder().encode(options.clientGeneration).length <= 256);
      if (options.beforeAdmission !== undefined) require(typeof options.beforeAdmission === 'function');
      token = this.begin();
    } catch (cause) { return Promise.reject(cause); }
    const task = async () => {
      let dispatched = false;
      try {
        if (!this.current(token.epoch)) throw stale();
        await this.read(true);
        if (!this.current(token.epoch) || !this.snapshot().canSubmit) throw stale();
        const guard = options.beforeAdmission?.(this.snapshot());
        require(!guard || typeof guard.then !== 'function', 'beforeAdmission 必须同步执行。');
        if (!this.current(token.epoch) || !this.snapshot().canSubmit) throw stale();
        const binding = clone(this.binding), preview = this.preview;
        const old = this.runIntents.get(key);
        if (old) require(old.revisionId === revisionId && old.clientGeneration === options.clientGeneration, '相同请求标识不能用于不同程序。');
        const payload = old?.payload || {revision_id: revisionId, expected_generation: preview.generation, expected_owner_epoch: binding.owner_epoch,
          ...(options.clientGeneration === undefined ? {} : {client_generation: options.clientGeneration})};
        this.runIntents.set(key, {revisionId, clientGeneration: options.clientGeneration, payload});
        this.invalidateReads();
        // Polling and cancel remain independent while the POST response waits.
        this.schedule();
        dispatched = true;
        const receipt = await this.api(`/api/v1/previews/${binding.preview_id}/runs`, {method: 'POST',
          headers: {'Content-Type': 'application/json', 'Idempotency-Key': key}, body: JSON.stringify(payload)});
        if (!this.current(token.epoch)) throw stale();
        const run = validateRun(receipt, preview, this.session, binding, Math.max(preview.generation + 1, payload.expected_generation + 1));
        require(run.state === 'queued' && run.revision_id === revisionId && canonical(run.request) === canonical(payload));
        this.minimumGeneration = Math.max(this.minimumGeneration, run.generation);
        return freeze(run);
      } catch (cause) {
        if (dispatched && (cause.effectPossible === undefined || ['preview_response_invalid', 'preview_context_changed'].includes(cause.code))) cause.effectPossible = true;
        throw cause;
      } finally { this.finish(token); }
    };
    const result = this.admissions.then(task, task);
    this.admissions = result.catch(() => {});
    return result;
  }

  async control(action, value) {
    const before = this.snapshot();
    const runId = action === 'cancel' ? value ?? before.cancelRunId : null;
    if (action === 'cancel' && (!ID.test(runId || '') || ![before.activeRun, before.desiredRun, before.transitionRun].some(run => run?.run_id === runId))) throw stale();
    if (action === 'renew' && (!Number.isSafeInteger(value) || value < 30 || value > 3600)) throw error('租约需要在 30–3600 秒之间。', 'invalid_preview_request');
    if (action === 'close' && before.preview?.state === 'closed') return before.preview;
    const token = this.begin(), binding = clone(this.binding), preview = this.preview;
    if (action === 'close') this.closing = true;
    this.invalidateReads();
    this.schedule();
    this.emit();
    const path = action === 'cancel' ? `runs/${runId}/cancel` : action;
    try {
      const response = await this.api(`/api/v1/previews/${binding.preview_id}/${path}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({expected_owner_epoch: binding.owner_epoch, ...(action === 'renew' ? {ttl_seconds: value} : {})})});
      if (!this.current(token.epoch)) throw stale();
      if (action === 'cancel') {
        const run = validateRun(response, preview, this.session, binding);
        require(run.run_id === runId && (TERMINAL.has(run.state) || run.state === 'cancelling'));
      } else validatePreview(response, this.session, binding);
      return freeze(clone(response));
    } catch (cause) {
      if (action === 'close' && this.current(token.epoch)) this.closing = false;
      if (cause.effectPossible === undefined || ['preview_response_invalid', 'preview_context_changed'].includes(cause.code)) cause.effectPossible = true;
      throw cause;
    } finally { this.finish(token); }
  }

  cancel(runId) { return this.control('cancel', runId); }
  renew(ttl = 600) { return this.control('renew', ttl); }
  close() { return this.control('close'); }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.bindingEpoch += 1;
    this.effectEpoch += 1;
    this.invalidateReads();
    this.pending.clear();
    this.synchronized = false;
    this.emit();
    this.listeners.clear();
  }
}

export function createPreviewClient(options) { return new PreviewClient(options); }
