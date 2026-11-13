import { createUnitPanel } from './unit-panel.js';
import {validateQemuServoOutputProfile, validateQemuServoState} from './public-qemu-servo.js';
import {Sha256} from './sha256.js';

const ACTIVE = new Set(['provisioning', 'flashing', 'booting', 'running']);
const abortError = () => new DOMException('已取消启动。', 'AbortError');
// Only explicit pre-allocation rejections may retire a never-ambiguous intent.
// Generic handler errors can be returned after a session was allocated.
const PRECREATE_REJECTIONS = {
  400: new Set(['invalid_idempotency_key', 'invalid_ttl', 'invalid_ready', 'invalid_worker_owner',
    'invalid_runtime_env', 'unsupported_runtime', 'invalid_units', 'invalid_unit_topology', 'invalid_unit_input', 'invalid_uiflow_startup']),
  401: new Set(['unauthorized']),
  404: new Set(['unknown_device', 'unknown_firmware', 'unknown_unit']),
  409: new Set(['unsupported_device', 'firmware_device_mismatch', 'reference_firmware_missing',
    'reference_firmware_too_large', 'unsupported_firmware_capability', 'units_not_supported',
    'runtime_model_gap', 'unit_port_conflict', 'unit_port_not_supported', 'unit_bus_conflict', 'unit_address_conflict',
    'uiflow_startup_conflict', 'uiflow_startup_unavailable', 'uiflow_startup_reference_mismatch']),
  429: new Set(['capacity_exhausted', 'device_capacity_exhausted']),
};

/** Owns only the session it creates, never another user's Live session. */
export class PublicSessionController {
  constructor({service, shell = null, unitContainer = null, onSerial = () => {}, onState = () => {}, onError = () => {}, onFrame = () => {}, onDeviceState = () => {}, onOutputState = () => {}, outputProfile = null, pollIntervalMs = 350, frameIntervalMs = 33, outputIntervalMs = 50,
    createKey = () => `public-${globalThis.crypto.randomUUID()}`, createTimeoutMs = 30000, stopConfirmAttempts = 30, stopPollIntervalMs = 350, stopRequestTimeoutMs = 10000, onManagedStop = null}) {
    Object.assign(this, {service, shell, unitContainer, onSerial, onState, onError, onFrame, onDeviceState, onOutputState, pollIntervalMs, frameIntervalMs, outputIntervalMs,
      createKey, createTimeoutMs, stopConfirmAttempts, stopPollIntervalMs, stopRequestTimeoutMs});
    if (outputProfile) {
      validateQemuServoOutputProfile(outputProfile);
      if (typeof outputProfile.firmwareSHA256 !== 'string' || !/^[a-f0-9]{64}$/.test(outputProfile.firmwareSHA256)) throw new Error('Native servo output requires an explicit firmware SHA-256');
    }
    // Geometry/readback metadata only. Native execution never borrows a
    // browser clock profile, admission or runtime receipt.
    this.outputProfile = outputProfile ? structuredClone(outputProfile) : null;
    this.generation = 0;
    this.current = null;
    this.owned = true;
    this.onManagedStop = onManagedStop;
    this.held = new Set();
    this.heldContexts = new Map();
    this.inputQueues = new Map();
    this.disposed = false;
    this.frameEpoch = 0;
    this.api = (path, options = {}) => service.request(path, {...options,
      ...(typeof options.body === 'string' ? {body: JSON.parse(options.body)} : {})});
  }

  matches(generation, id) { return !this.disposed && !this.closing && generation === this.generation && this.current?.session_id === id; }

  setManagedStop(stop) {
    if (typeof stop !== 'function' || this.current || this.pendingCreate || this.stopOperation) throw new Error('当前控制器不能准备托管会话。');
    this.pendingManagedStop = stop;
  }

  async adoptManagedSession(session, previewClient, options = {}) {
    if (!previewClient || previewClient.session?.session_id !== session?.session_id
      || previewClient.session?.firmware_sha256 !== session.firmware_sha256
      || JSON.stringify(previewClient.session?.management_binding) !== JSON.stringify(session.management_binding)) throw new Error('Preview 不属于当前原生会话。');
    return this.adoptSession(session, {...options, previewClient});
  }

  /** Attach a captured session without gaining ownership of another page's VM. */
  async adoptSession(session, {owned = false, previewClient = null, stop = this.onManagedStop} = {}) {
    if (this.disposed || this.pendingCreate) throw new Error('当前控制器不能接入会话。');
    if (!session || typeof session.session_id !== 'string' || typeof session.device_id !== 'string') throw new Error('会话身份无效。');
    if (session.management_binding && !previewClient) throw new Error('托管会话需要 Preview 上下文。');
    if (owned && session.management_binding && typeof stop !== 'function') throw new Error('托管会话缺少停止回调。');
    if (this.current || this.createIntent) await this.stop();
    this.generation++; this.current = structuredClone(session); this.owned = owned;
    this.previewClient = previewClient; this.managedStop = stop;
    this.pendingManagedStop = null;
    this.serialOffset = 0; this.frameReady = false; this.frameSequence = 0; this.etag = null;
    this.frameContextKey = null; this.pollAbort = new AbortController();
    const generation = this.generation, id = session.session_id;
    if (this.unitContainer && session.units?.length) {
      this.unitPanel = await createUnitPanel(this.unitContainer, {session, shell: this.shell, api: this.api, previewClient});
      if (!this.matches(generation, id)) {await this.unitPanel.dispose(); this.unitPanel = null; throw abortError();}
    }
    this.onState({status: session.state, sessionId: id, session, frameReady: false});
    void this.poll(generation, id); void this.pollFrames(generation, id);
    return session;
  }

  async start({deviceId, firmwareId, uiflowStartup, units = [], signal}) {
    if (this.disposed) throw new Error('会话控制器已关闭。');
    if (this.outputProfile && this.outputProfile.deviceId !== deviceId) throw new Error('舵机输出配置不属于当前设备。');
    if (this.pendingCreate) throw new Error('正在创建虚拟设备，请等待或取消。');
    if (this.stopOperation) await this.stopOperation;
    if (this.pendingCreate) throw new Error('正在创建虚拟设备，请等待或取消。');
    if (this.current || this.createIntent) await this.stop();
    if (signal?.aborted) throw abortError();
    const generation = ++this.generation;
    this.owned = true; this.previewClient = null; this.managedStop = null;
    this.serialOffset = 0;
    this.frameReady = false;
    this.frameSequence = 0;
    this.etag = null;
    this.outputStatus = null;
    this.outputUnavailable = false;
    this.outputCapabilityChecked = false;
    this.lastDeviceState = null;
    this.outputObservation = null;
    this.previousOutputs = null;
    this.pollAbort = new AbortController();
    // Keep the create response observable even when the UI cancels. Aborting
    // a POST after dispatch can lose the identity of a lease already created.
    const cancel = () => { if (generation === this.generation) {this.generation++; this.stopPolling();} };
    signal?.addEventListener('abort', cancel, {once: true});
    // Store bytes, not the caller's mutable Unit selection. Recovery must replay
    // exactly the same body and key, even after cancellation or UI edits.
    const intent = {request: JSON.stringify({deviceId, firmwareId, uiflowStartup, units, idempotencyKey: this.createKey()}), attempts: 0, uncertain: false};
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
      void this.pollFrames(generation, session.session_id);
      void this.pollOutputs(generation, session.session_id);
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
    if (!this.matches(generation, id) || this.metadataFlight?.generation === generation) return;
    const flight = this.metadataFlight = {generation};
    const signal = this.pollAbort.signal;
    try {
      const session = await this.service.session(id, {signal});
      if (!this.matches(generation, id)) return;
      if (session.session_id !== id || session.device_id !== this.current.device_id) throw new Error('服务返回了其他设备的会话数据。');
      if (this.previewClient && (session.firmware_sha256 !== this.current.firmware_sha256
        || session.created_at !== this.current.created_at
        || JSON.stringify(session.management_binding) !== JSON.stringify(this.current.management_binding))) throw new Error('托管会话的身份发生变化。');
      this.current = session;
      this.previewClient?.updateSession(session);
      this.unitPanel?.updateSession(session);
      this.onState({status: session.state, sessionId: id, session, frameReady: this.frameReady});
      const serial = await this.service.serial(id, this.serialOffset, {signal});
      if (!this.matches(generation, id)) return;
      if (!Number.isSafeInteger(serial.next_offset) || typeof serial.data !== 'string') throw new Error('串口收据无效。');
      if (serial.next_offset < this.serialOffset) this.onSerial('\n[串口已重置]\n');
      this.serialOffset = serial.next_offset;
      if (serial.data) this.onSerial(serial.data);
    } catch (error) {
      if (this.matches(generation, id) && error.name !== 'AbortError') this.onError(error);
    } finally {
      if (this.metadataFlight === flight) this.metadataFlight = null;
      if (this.matches(generation, id) && ACTIVE.has(this.current.state)) this.timer = setTimeout(() => void this.poll(generation, id), this.pollIntervalMs);
    }
  }

  async pollFrames(generation, id) {
    if (!this.matches(generation, id) || this.frameFlight?.generation === generation) return;
    const flight = this.frameFlight = {generation}, started = performance.now();
    const signal = this.pollAbort.signal;
    try {
      if (this.current.state === 'running' && this.current.display?.width) await this.readFrame(generation, id, signal);
    } catch (error) {
      if (this.matches(generation, id) && error.name !== 'AbortError') this.onError(error);
    } finally {
      if (this.frameFlight === flight) this.frameFlight = null;
      // One capture/decode at a time: slow frames reduce this lane's rate,
      // without queuing stale images or delaying session/serial observations.
      if (this.matches(generation, id) && ACTIVE.has(this.current.state)) {
        this.frameTimer = setTimeout(() => void this.pollFrames(generation, id), Math.max(0, this.frameIntervalMs - (performance.now() - started)));
      }
    }
  }

  stopPolling() {
    clearTimeout(this.timer);
    clearTimeout(this.frameTimer);
    clearTimeout(this.outputTimer);
    this.pollAbort?.abort();
  }

  async pollOutputs(generation, id) {
    if (!this.outputProfile || this.outputUnavailable || !this.matches(generation, id) || this.outputFlight?.generation === generation) return;
    const flight = this.outputFlight = {generation}, started = performance.now();
    const signal = this.pollAbort.signal, shell = this.shell, epoch = this.frameEpoch;
    const current = () => !signal.aborted && this.matches(generation, id) && this.current.state === 'running' && this.shell === shell && this.frameEpoch === epoch;
    try {
      if (this.current.state !== 'running') return;
      const profile = this.outputProfile, output = profile.outputs;
      if (this.current.firmware_sha256 !== profile.firmwareSHA256) throw new Error('Native servo firmware binding differs');
      if (!this.outputCapabilityChecked) {
        const capability = await this.api(`/api/v1/sessions/${encodeURIComponent(id)}/qom/list?path=${encodeURIComponent(output.path)}`, {signal});
        if (!current()) return;
        if (capability.session_id !== id || capability.path !== output.path || !Array.isArray(capability.properties)
          || !capability.properties.some(property => property.name === output.property && typeof property.type === 'string')) throw new Error('Native servo state capability is unavailable');
        this.outputCapabilityChecked = true;
      }
      const receipt = await this.api(`/api/v1/sessions/${encodeURIComponent(id)}/qom?path=${encodeURIComponent(output.path)}&property=${output.property}`, {signal});
      if (!current()) return;
      if (receipt.session_id !== id || receipt.path !== output.path || receipt.property !== output.property) throw new Error('Native servo receipt does not belong to this session');
      const value = validateQemuServoState(profile, {...receipt.value, device_id: profile.deviceId, path: output.path});
      this.lastDeviceState = structuredClone(value);
      this.outputObservation = {transport: 'native-service-qom-v1', session_id: id, firmware_sha256: this.current.firmware_sha256,
        observed_at: new Date().toISOString(), path: output.path, property: output.property};
      if (this.outputStatus !== 'available') {this.outputStatus = 'available'; this.onOutputState({status: 'available', ...this.outputObservation});}
      const identity = JSON.stringify(value);
      if (identity !== this.previousOutputs) {this.previousOutputs = identity; this.onDeviceState(this.lastDeviceState);}
    } catch (error) {
      if (current() && error.name !== 'AbortError') {
        // Unsupported or unverified readback stays unknown. Disable only this
        // optional lane, once, instead of spamming errors or fabricating motion.
        this.outputUnavailable = true;
        this.outputStatus = 'unavailable';
        this.onOutputState({status: 'unavailable', session_id: id, transport: 'native-service-qom-v1', reason: error.message});
      }
    } finally {
      if (this.outputFlight === flight) this.outputFlight = null;
      if (this.matches(generation, id) && !this.outputUnavailable && ACTIVE.has(this.current.state)) {
        this.outputTimer = setTimeout(() => void this.pollOutputs(generation, id), Math.max(0, this.outputIntervalMs - (performance.now() - started)));
      }
    }
  }

  async readFrame(generation, id, signal) {
    const shell = this.shell, epoch = this.frameEpoch;
    const client = this.previewClient, context = client?.snapshot().frameContext;
    if (client && !context) {this.etag = null; this.frameHash = null; this.frameReady = false; return;}
    if (client && this.frameContextKey !== context.key) {this.frameContextKey = context.key; this.etag = null; this.frameHash = null; this.frameReady = false;}
    const current = () => !signal.aborted && this.matches(generation, id) && this.current.state === 'running' && this.shell === shell && this.frameEpoch === epoch
      && (!client || this.previewClient === client && client.matches(context, 'frame'));
    // A positive bound selects the service's conditional frame API. Keep it
    // below the display cadence so a 500ms preview never throttles animation.
    const path = client ? `/api/v1/previews/${encodeURIComponent(context.previewId)}/runs/${encodeURIComponent(context.runId)}/frame.png`
      : `/api/v1/sessions/${encodeURIComponent(id)}/frame.png`;
    const response = await this.service.fetch(`${path}?max_age_ms=1`, {
      signal, cache: 'no-store', headers: this.etag ? {'If-None-Match': this.etag} : {},
    });
    if (!current()) return;
    if (client && (response.headers.get('X-Preview-ID') !== context.previewId || response.headers.get('X-Run-ID') !== context.runId
      || response.headers.get('X-Frame-Execution-ID') !== context.executionId || response.headers.get('X-Frame-Revision-ID') !== context.revisionId)) throw new Error('Run 画面身份不匹配。');
    if (response.status === 304) {
      if (client && (!this.etag || !this.frameReady || response.headers.get('X-Frame-SHA256') !== this.frameHash)) throw new Error('Run 条件画面响应没有匹配的缓存。');
      return;
    }
    if (!response.ok) {if (response.status >= 500 || response.status === 409) return; throw new Error(`画面读取失败（${response.status}）`);}
    const image = await response.blob();
    if (!current()) return;
    if (client && new Sha256().update(new Uint8Array(await image.arrayBuffer())).hex() !== response.headers.get('X-Frame-SHA256')) throw new Error('Run 画面摘要不匹配。');
    if (!current()) return;
    const sequence = ++this.frameSequence;
    const applied = shell?.setImage ? await shell.setImage(image, sequence, current) : false;
    if (!current()) return;
    this.etag = applied === false ? null : response.headers.get('ETag');
    this.frameHash = applied === false ? null : response.headers.get('X-Frame-SHA256');
    const wasReady = this.frameReady;
    this.frameReady = applied !== false;
    this.onFrame({blob: image, sequence, sessionId: id, applied: this.frameReady});
    if (this.frameReady !== wasReady) this.onState({status: this.current.state, sessionId: id, session: this.current, frameReady: this.frameReady});
  }

  input(command) {
    const session = this.current;
    if (!session || session.state !== 'running' || this.disposed || this.closing) return Promise.resolve(null);
    const id = session.session_id, generation = this.generation;
    const key = command.kind === 'key' ? command.key : 'touch';
    const previewClient = this.previewClient, context = command.kind === 'key' && command.action === 'up'
      ? this.heldContexts.get(key) || previewClient?.captureInput() : previewClient?.captureInput();
    if (previewClient && !context) return Promise.reject(new Error('当前 Run 尚未确认输入归属。'));
    if (command.kind === 'key') {
      if (command.action === 'down') {this.held.add(key); if (context) this.heldContexts.set(key, context);}
      else {this.held.delete(key); this.heldContexts.delete(key);}
    }
    const previous = this.inputQueues.get(key) || Promise.resolve();
    const request = previous.catch(() => {}).then(() => {
      if (!this.matches(generation, id)) return null;
      if (previewClient) return previewClient.input(context, 'input', {...command, settle_seconds: 0.02});
      return this.service.input(id, {...command, settle_seconds: 0.02});
    });
    this.inputQueues.set(key, request);
    request.finally(() => {if (this.inputQueues.get(key) === request) this.inputQueues.delete(key);}).catch(() => {});
    return request;
  }

  async reset() {
    if (this.closing) throw new Error('正在停止会话，请等待。');
    if (this.previewClient) throw new Error('此编程会话由 Preview 管理；请重新运行代码，或停止后重新启动设备。');
    if (this.owned === false) throw new Error('当前视图不拥有此会话，请在设备会话控制台重置。');
    const id = this.current?.session_id;
    if (!id) return;
    const generation = ++this.generation;
    this.stopPolling();
    await this.releaseInputs(id);
    if (!this.matches(generation, id)) return;
    this.etag = null;
    this.frameReady = false;
    this.outputCapabilityChecked = false;
    this.outputUnavailable = false;
    this.outputStatus = this.outputProfile ? 'pending' : null;
    this.lastDeviceState = null;
    this.outputObservation = null;
    this.previousOutputs = null;
    if (this.outputProfile) this.onOutputState({status: 'pending', session_id: id, transport: 'native-service-qom-v1'});
    try {return await this.api(`/api/v1/sessions/${encodeURIComponent(id)}/reset`, {method: 'POST', body: {}});}
    finally {
      if (this.matches(generation, id)) {
        this.pollAbort = new AbortController();
        void this.poll(generation, id);
        void this.pollFrames(generation, id);
        void this.pollOutputs(generation, id);
      }
    }
  }

  async releaseInputs(id) {
    const held = [...this.held];
    const contexts = this.heldContexts; this.heldContexts = new Map();
    this.held.clear();
    await Promise.allSettled([...this.inputQueues.values()]);
    await Promise.allSettled(held.map(key => {
      const command = {kind: 'key', key, action: 'up', settle_seconds: 0.02};
      const context = contexts.get(key);
      return this.previewClient ? context ? this.previewClient.input(context, 'input', command, {keepalive: true}) : Promise.resolve()
        : this.service.input(id, command);
    }));
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
    this.stopPolling();
    const operation = (async () => {
      if (this.pendingCreate) await this.pendingCreate.catch(() => {});
      if (this.stopPromise) return this.stopPromise;
      if (!this.current && this.pendingManagedStop) {
        await this.pendingManagedStop(); this.pendingManagedStop = null;
        return;
      }
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
      const panel = this.unitPanel;
      this.unitPanel = null;
      if (panel) {
        try {await this.boundedStopRequest(() => panel.dispose(), 'Unit 输入释放');}
        catch (error) {this.onError(error);}
      }
      try {await this.boundedStopRequest(() => this.releaseInputs(session.session_id), '输入释放');}
      catch (error) {this.onError(error);}
      finally {this.inputQueues.clear();}
      let result;
      if (this.previewClient) {
        if (this.owned && !this.managedStop) throw new Error('托管会话缺少停止回调。');
        if (this.managedStop) await this.managedStop();
        else this.previewClient.dispose();
        result = session;
      } else if (this.owned === false) {if (this.managedStop) await this.managedStop(); result = session;}
      else result = await this.closeSession(session.session_id);
      if (this.current?.session_id === session.session_id) this.current = null;
      this.previewClient = null; this.managedStop = null;
      this.onState({status: 'stopped', sessionId: session.session_id, frameReady: false, session, detached: this.owned === false});
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

  setShell(shell) {
    this.shell = shell; this.frameEpoch++; this.etag = null; this.frameReady = false;
    this.previousOutputs = null; this.lastDeviceState = null; this.outputObservation = null;
    if (this.outputProfile && !this.outputUnavailable && this.current && !this.closing) {
      this.outputStatus = 'pending';
      this.onOutputState({status: 'pending', session_id: this.current.session_id, transport: 'native-service-qom-v1'});
    }
    this.unitPanel?.setShell(shell);
  }

  async dispose() {await this.stop(); this.disposed = true;}
}
