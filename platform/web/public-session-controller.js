import { createUnitPanel } from './unit-panel.js';

const ACTIVE = new Set(['provisioning', 'flashing', 'booting', 'running']);
const abortError = () => new DOMException('已取消启动。', 'AbortError');
// Only explicit pre-allocation rejections may retire a never-ambiguous intent.
// Generic handler errors can be returned after a session was allocated.
const PRECREATE_REJECTIONS = {
  400: new Set(['invalid_idempotency_key', 'invalid_ttl', 'invalid_ready', 'invalid_worker_owner',
    'invalid_runtime_env', 'unsupported_runtime', 'invalid_units', 'invalid_unit_topology', 'invalid_unit_input']),
  401: new Set(['unauthorized']),
  404: new Set(['unknown_device', 'unknown_firmware', 'unknown_unit']),
  409: new Set(['unsupported_device', 'firmware_device_mismatch', 'reference_firmware_missing',
    'reference_firmware_too_large', 'unsupported_firmware_capability', 'units_not_supported',
    'runtime_model_gap', 'unit_port_conflict', 'unit_port_not_supported', 'unit_bus_conflict', 'unit_address_conflict']),
  429: new Set(['capacity_exhausted', 'device_capacity_exhausted']),
};

/** Owns only the session it creates, never another user's Live session. */
export class PublicSessionController {
  constructor({service, shell = null, unitContainer = null, onSerial = () => {}, onState = () => {}, onError = () => {}, onFrame = () => {}, pollIntervalMs = 350,
    createKey = () => `public-${globalThis.crypto.randomUUID()}`, createTimeoutMs = 30000, stopConfirmAttempts = 30, stopPollIntervalMs = 350, stopRequestTimeoutMs = 10000}) {
    Object.assign(this, {service, shell, unitContainer, onSerial, onState, onError, onFrame, pollIntervalMs,
      createKey, createTimeoutMs, stopConfirmAttempts, stopPollIntervalMs, stopRequestTimeoutMs});
    this.generation = 0;
    this.current = null;
    this.held = new Set();
    this.inputQueues = new Map();
    this.disposed = false;
    this.api = (path, options = {}) => service.request(path, {...options,
      ...(typeof options.body === 'string' ? {body: JSON.parse(options.body)} : {})});
  }

  matches(generation, id) { return !this.disposed && !this.closing && generation === this.generation && this.current?.session_id === id; }

  async start({deviceId, firmwareId, units = [], signal}) {
    if (this.disposed) throw new Error('会话控制器已关闭。');
    if (this.pendingCreate) throw new Error('正在创建虚拟设备，请等待或取消。');
    if (this.stopOperation) await this.stopOperation;
    if (this.pendingCreate) throw new Error('正在创建虚拟设备，请等待或取消。');
    if (this.current || this.createIntent) await this.stop();
    if (signal?.aborted) throw abortError();
    const generation = ++this.generation;
    this.serialOffset = 0;
    this.frameReady = false;
    this.frameSequence = 0;
    this.etag = null;
    this.pollAbort = new AbortController();
    // Keep the create response observable even when the UI cancels. Aborting
    // a POST after dispatch can lose the identity of a lease already created.
    const cancel = () => { if (generation === this.generation) {this.generation++; this.pollAbort.abort();} };
    signal?.addEventListener('abort', cancel, {once: true});
    // Store bytes, not the caller's mutable Unit selection. Recovery must replay
    // exactly the same body and key, even after cancellation or UI edits.
    const intent = {request: JSON.stringify({deviceId, firmwareId, units, idempotencyKey: this.createKey()}), attempts: 0, uncertain: false};
    this.createIntent = intent;
    const pending = this.acquireIntent(intent);
    this.pendingCreate = pending;
    let session;
    try {
      session = await pending;
      // Keep ownership until DELETE succeeds, including a late create whose
      // cancellation cleanup fails. A later stop can retry the same identity.
      this.current = session;
      if (generation !== this.generation || this.disposed || signal?.aborted) {
        await this.stopOwnedSession(session);
        throw abortError();
      }
      this.onState({status: session.state, sessionId: session.session_id, session, frameReady: false});
      if (this.unitContainer && units.length) {
        const panel = await createUnitPanel(this.unitContainer, {session, shell: this.shell, api: this.api});
        if (!this.matches(generation, session.session_id)) {panel.dispose(); throw abortError();}
        this.unitPanel = panel;
      }
      void this.poll(generation, session.session_id);
      return session;
    } finally {
      if (this.pendingCreate === pending) this.pendingCreate = null;
      signal?.removeEventListener('abort', cancel);
    }
  }

  async acquireIntent(intent) {
    const request = JSON.parse(intent.request), controller = new AbortController();
    const firstKnownAttempt = ++intent.attempts === 1 && !intent.uncertain;
    let timer;
    try {
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => {
          const error = new Error('创建收据超时；请重试停止以恢复同一会话。');
          error.code = 'create_receipt_timeout'; error.outcomeUnknown = true;
          reject(error); controller.abort();
        }, this.createTimeoutMs);
      });
      const session = await Promise.race([this.service.create({...request, signal: controller.signal}), timeout]);
      if (typeof session?.session_id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(session.session_id) || session.device_id !== request.deviceId) {
        throw new Error('创建收据缺少有效的设备会话身份；请恢复收据后停止。');
      }
      this.current = session;
      if (this.createIntent === intent) this.createIntent = null;
      return session;
    } catch (error) {
      if (firstKnownAttempt && error.outcomeUnknown !== true && PRECREATE_REJECTIONS[error.status]?.has(error.code)) {
        if (this.createIntent === intent) this.createIntent = null;
      } else intent.uncertain = true;
      throw error;
    } finally {clearTimeout(timer);}
  }

  async poll(generation, id) {
    if (!this.matches(generation, id)) return;
    const signal = this.pollAbort.signal;
    try {
      const session = await this.service.session(id, {signal});
      if (!this.matches(generation, id)) return;
      if (session.session_id !== id || session.device_id !== this.current.device_id) throw new Error('服务返回了其他设备的会话数据。');
      this.current = session;
      this.unitPanel?.updateSession(session);
      const serial = await this.service.serial(id, this.serialOffset, {signal});
      if (!this.matches(generation, id)) return;
      if (!Number.isSafeInteger(serial.next_offset) || typeof serial.data !== 'string') throw new Error('串口收据无效。');
      if (serial.next_offset < this.serialOffset) this.onSerial('\n[串口已重置]\n');
      this.serialOffset = serial.next_offset;
      if (serial.data) this.onSerial(serial.data);
      if (session.state === 'running' && session.display?.width) await this.readFrame(generation, id, signal);
      if (!this.matches(generation, id)) return;
      this.onState({status: session.state, sessionId: id, session, frameReady: this.frameReady});
    } catch (error) {
      if (this.matches(generation, id) && error.name !== 'AbortError') this.onError(error);
    } finally {
      if (this.matches(generation, id) && ACTIVE.has(this.current.state)) this.timer = setTimeout(() => void this.poll(generation, id), this.pollIntervalMs);
    }
  }

  async readFrame(generation, id, signal) {
    const response = await this.service.fetch(`/api/v1/sessions/${encodeURIComponent(id)}/frame.png?max_age_ms=500`, {
      signal, headers: this.etag ? {'If-None-Match': this.etag} : {},
    });
    if (response.status === 304) return;
    if (!response.ok) {if (response.status >= 500 || response.status === 409) return; throw new Error(`画面读取失败（${response.status}）`);}
    const image = await response.blob();
    if (!this.matches(generation, id)) return;
    const shell = this.shell;
    const current = () => this.matches(generation, id) && this.shell === shell;
    const sequence = ++this.frameSequence;
    const applied = shell?.setImage ? await shell.setImage(image, sequence, current) : false;
    if (!current()) return;
    this.etag = response.headers.get('ETag');
    this.frameReady = applied !== false;
    this.onFrame({blob: image, sequence, sessionId: id, applied: this.frameReady});
  }

  input(command) {
    const session = this.current;
    if (!session || session.state !== 'running' || this.disposed || this.closing) return Promise.resolve(null);
    const id = session.session_id, generation = this.generation;
    const key = command.kind === 'key' ? command.key : 'touch';
    if (command.kind === 'key') {
      if (command.action === 'down') this.held.add(key);
      else this.held.delete(key);
    }
    const previous = this.inputQueues.get(key) || Promise.resolve();
    const request = previous.catch(() => {}).then(() => {
      if (!this.matches(generation, id)) return null;
      return this.service.input(id, {...command, settle_seconds: 0.02});
    });
    this.inputQueues.set(key, request);
    request.finally(() => {if (this.inputQueues.get(key) === request) this.inputQueues.delete(key);}).catch(() => {});
    return request;
  }

  async reset() {
    if (this.closing) throw new Error('正在停止会话，请等待。');
    const id = this.current?.session_id;
    if (!id) return;
    const generation = ++this.generation;
    clearTimeout(this.timer);
    this.pollAbort?.abort();
    await this.releaseInputs(id);
    this.etag = null;
    this.frameReady = false;
    try {return await this.api(`/api/v1/sessions/${encodeURIComponent(id)}/reset`, {method: 'POST', body: {}});}
    finally {
      if (this.matches(generation, id)) {this.pollAbort = new AbortController(); void this.poll(generation, id);}
    }
  }

  async releaseInputs(id) {
    const held = [...this.held];
    this.held.clear();
    await Promise.allSettled([...this.inputQueues.values()]);
    await Promise.allSettled(held.map(key => this.service.input(id, {kind: 'key', key, action: 'up', settle_seconds: 0.02})));
  }

  async closeSession(id) {
    let evidenceError;
    try { this.lastEvidence = await this.boundedStopRequest(signal => this.service.evidence(id, {signal}), '证据导出'); }
    catch (error) { evidenceError = error; }
    let result = await this.boundedStopRequest(signal => this.service.stop(id, {signal}), '停止请求');
    const terminal = session => session && session.session_id === id && session.device_id === this.current?.device_id
      && ['stopped', 'failed'].includes(session.state) && !session.stop_pending && session.worker?.lease_active === false;
    for (let attempt = 0; !terminal(result) && attempt < this.stopConfirmAttempts; attempt++) {
      if (result?.session_id !== id || result.device_id !== this.current?.device_id) throw new Error('停止收据不属于当前设备会话。');
      await new Promise(resolve => setTimeout(resolve, this.stopPollIntervalMs));
      result = await this.boundedStopRequest(signal => this.service.session(id, {signal}), '停止状态查询');
    }
    if (!terminal(result)) throw new Error('服务尚未确认停止；会话身份已保留，请重试停止。');
    if (evidenceError) this.onError(new Error(`会话已停止并保留历史，证据 ZIP 未取得：${evidenceError.message}`));
    return result;
  }

  async boundedStopRequest(request, label) {
    const controller = new AbortController();
    let timer;
    try {
      return await Promise.race([
        Promise.resolve().then(() => request(controller.signal)),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            reject(new Error(`${label}超时；请重试停止以确认清理。`));
            controller.abort();
          }, this.stopRequestTimeoutMs);
        }),
      ]);
    } finally {clearTimeout(timer);}
  }

  stop() {
    if (this.stopOperation) return this.stopOperation;
    this.generation++;
    clearTimeout(this.timer);
    this.pollAbort?.abort();
    const operation = (async () => {
      if (this.pendingCreate) await this.pendingCreate.catch(() => {});
      if (this.stopPromise) return this.stopPromise;
      if (!this.current && this.createIntent) {
        try {await this.acquireIntent(this.createIntent);}
        catch (error) {
          this.onState({status: 'stop_pending', sessionId: null, frameReady: false, createPending: true, error});
          throw error;
        }
      }
      return this.stopOwnedSession(this.current);
    })();
    this.stopOperation = operation.finally(() => {this.stopOperation = null;});
    return this.stopOperation;
  }

  stopOwnedSession(session) {
    if (this.stopPromise) return this.stopPromise;
    if (!session) return Promise.resolve();
    this.closing = true;
    this.stopPromise = (async () => {
      this.unitPanel?.dispose();
      this.unitPanel = null;
      try {await this.boundedStopRequest(() => this.releaseInputs(session.session_id), '输入释放');}
      catch (error) {this.onError(error);}
      finally {this.inputQueues.clear();}
      const result = await this.closeSession(session.session_id);
      if (this.current?.session_id === session.session_id) this.current = null;
      this.onState({status: 'stopped', sessionId: session.session_id, frameReady: false, session});
      return result;
    })().catch(error => {
      this.onState({status: 'stop_pending', sessionId: session.session_id, frameReady: false, session, error});
      throw error;
    }).finally(() => {
      this.closing = false;
      this.stopPromise = null;
    });
    return this.stopPromise;
  }

  setShell(shell) {this.shell = shell; this.etag = null; this.unitPanel?.setShell(shell);}

  async dispose() {await this.stop(); this.disposed = true;}
}
