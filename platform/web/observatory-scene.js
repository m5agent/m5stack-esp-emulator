import * as THREE from 'three';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {loadModel, loadGroveModule} from './vendor/m5stack-models/src/loaders.js';
import {MODEL_DEVICES} from './vendor/m5stack-models/runtime-index.js';
import {setModelImage, applyModelVisualState, clearModelDriveActivities} from './model-output.js';
import {layoutHubAttachments} from './unit-assembly-layout.js';
import {visualCommands} from './unit-visual-mappings.js';

const ACTIVE = new Set(['provisioning', 'flashing', 'booting', 'running', 'stopping']);
const STATES = {provisioning: '准备中', flashing: '烧录中', booting: '启动中', running: '运行中',
  stopping: '正在结束', stopped: '已结束', failed: '异常', cancelled: '已取消'};
// A bare host is normalised to at most 110 scene units. Reserve the same bay
// before and after model admission so loading a model cannot shift its slot.
const HOST_ENVELOPE = Object.freeze({width: 160, depth: 140, height: 110, centreX: 0, centreZ: 0});
const COLUMNS = 4, SLOT_X = HOST_ENVELOPE.width + 38, SLOT_Z = HOST_ENVELOPE.depth + 64;
const MODEL_BUDGET = 32, LOAD_CONCURRENCY = 2;
const identity = session => JSON.stringify([session.session_id, session.created_at, session.device_id,
  session.firmware_sha256, session.pid, session.management_binding ?? null], (_key, value) =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right))) : value);

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function attachmentOrder(attachments) {
  const result = [], seen = new Set(), visiting = new Set();
  const byId = new Map(attachments.map(unit => [unit.id, unit]));
  function visit(unit) {
    if (seen.has(unit.id)) return;
    if (visiting.has(unit.id)) throw new Error('Unit 连接关系存在循环');
    visiting.add(unit.id);
    if (unit.parent_id) {
      const parent = byId.get(unit.parent_id);
      if (!parent) throw new Error('Unit 上游 HUB 不存在');
      visit(parent);
    }
    visiting.delete(unit.id); seen.add(unit.id); result.push(unit);
  }
  attachments.forEach(visit);
  return result;
}

function disposeObject(object) {
  const geometries = new Set(), materials = new Set();
  object.traverse(child => {
    if (child.geometry) geometries.add(child.geometry);
    for (const material of [child.material].flat().filter(Boolean)) materials.add(material);
  });
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(material => material.dispose());
}

/** A read-only, single-context view of externally owned Device Service guests.
 * This class has no service client and never forwards model inputs or audio.
 * Every displayed framebuffer and actuator observation belongs to one record.
 */
export class ObservatoryScene {
  constructor(container, {onError = () => {}} = {}) {
    Object.assign(this, {container, onError});
    this.records = new Map(); this.groups = new Map();
    this.disposed = false; this.visible = true; this.modelQueue = []; this.modelActive = 0;
    this.selectedSessionId = null; this.selectedGroupId = null; this.dirty = true;
    this.target = new THREE.Vector3(0, 45, 0); this.distance = 650;
    this.yaw = 0.18; this.polar = 1.08; this.lastTick = performance.now();
    this.reducedMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0xf3f7fa);
    this.camera = new THREE.PerspectiveCamera(36, 1, 1, 30000);
    this.labels = element('div', 'observatory-scene-labels');
    Object.assign(this.labels.style, {position: 'absolute', inset: '0', pointerEvents: 'none', overflow: 'hidden'});
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    this.container.classList.add('observatory-scene');
    try {
      this.renderer = new THREE.WebGLRenderer({antialias: true, alpha: false, powerPreference: 'low-power'});
      this.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 1.5));
      this.renderer.toneMapping = THREE.NeutralToneMapping;
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
      this.renderer.domElement.className = 'observatory-scene-canvas';
      this.renderer.domElement.setAttribute('role', 'img');
      this.renderer.domElement.setAttribute('aria-label', '虚拟设备实验室，自动展示运行状态与设备画面');
      Object.assign(this.renderer.domElement.style, {width: '100%', height: '100%', display: 'block', pointerEvents: 'none'});
      this.container.append(this.renderer.domElement);
      this.scene.add(new THREE.HemisphereLight(0xffffff, 0xc5d0dc, 2.5));
      const light = new THREE.DirectionalLight(0xffffff, 3.2); light.position.set(-300, 500, 700); this.scene.add(light);
      const fill = new THREE.DirectionalLight(0xd7edff, 1.5); fill.position.set(400, 100, -200); this.scene.add(fill);
      const generator = new THREE.PMREMGenerator(this.renderer), room = new RoomEnvironment();
      this.environment = generator.fromScene(room, 0.05).texture;
      this.scene.environment = this.environment;
      room.dispose(); generator.dispose();
      this.floor = new THREE.Mesh(new THREE.PlaneGeometry(20000, 20000),
        new THREE.MeshStandardMaterial({color: 0xf1f5f8, roughness: 1}));
      this.floor.rotation.x = -Math.PI / 2; this.floor.position.y = -5; this.scene.add(this.floor);
      this.grid = new THREE.GridHelper(16000, 200, 0xd6e2eb, 0xe2eaf0);
      this.grid.position.y = -4.8; this.scene.add(this.grid);
      this.podiumGeometry = new THREE.BoxGeometry(HOST_ENVELOPE.width, 7, HOST_ENVELOPE.depth);
      this.outlineGeometry = new THREE.EdgesGeometry(this.podiumGeometry);
    } catch (error) {
      this.renderer?.dispose(); this.renderer?.domElement.remove(); this.renderer = null;
      this.container.classList.add('is-fallback');
      Object.assign(this.labels.style, {position: 'relative', inset: 'auto', display: 'flex', flexWrap: 'wrap', gap: '12px', overflow: 'auto'});
      queueMicrotask(() => { if (!this.disposed) this.onError(new Error(`3D 暂不可用，保留设备状态视图：${error.message}`)); });
    }
    this.container.append(this.labels);
    this.resizeObserver = new ResizeObserver(() => this._resize()); this.resizeObserver.observe(container);
    this._resize(); this._tick();
  }

  get visibleSessionIds() {
    if (!this.visible || !this.renderer) return [];
    return [...this.records.values()].filter(record => record.model && !record.leavingAt && this._inView(record)).map(record => record.id);
  }

  get rendererInfo() {
    return {contexts: this.renderer ? 1 : 0, detailedModels: [...this.records.values()].filter(record => record.model).length,
      geometries: this.renderer?.info.memory.geometries ?? 0, textures: this.renderer?.info.memory.textures ?? 0,
      drawCalls: this.renderer?.info.render.calls ?? 0, disposed: this.disposed};
  }

  snapshot() {
    return {renderer: this.rendererInfo, selectedSessionId: this.selectedSessionId, selectedGroupId: this.selectedGroupId,
      sessions: [...this.records.values()].map(record => ({session_id: record.id, device_id: record.session.device_id,
        group_id: record.group.id, slot: record.slot, position: record.object.position.toArray(),
        state: record.session.state, frame_seq: record.surface?.frameSeq ?? 0, frame_known: record.frameKnown === true, has_model: Boolean(record.model),
        leaving: Boolean(record.leavingAt), units: (record.unitPayload?.units || []).map(unit => ({id: unit.id,
          unit_id: unit.unit_id, available: unit.available, properties: unit.properties})),
        attached_units: [...record.mountedUnits.keys()], visual_error: record.visualError || null}))};
  }

  _newGroup(id, metadata) {
    const occupied = new Set([...this.groups.values()].map(group => group.index));
    let index = 0; while (occupied.has(index)) index++;
    const object = new THREE.Group();
    this.scene.add(object);
    const label = element('div', 'observatory-group-label'); label.dataset.groupId = id;
    Object.assign(label.style, {position: this.renderer ? 'absolute' : 'relative', pointerEvents: 'none'});
    const group = {id, index, object, label, name: metadata?.name || id, slots: new Set(),
      columnWidths: Array(COLUMNS).fill(SLOT_X), rowDepths: new Map(), labelAnchor: new THREE.Vector3()};
    this.labels.append(label); this.groups.set(id, group); return group;
  }

  _newRecord(session, metadata) {
    const group = this.groups.get(session.device_id) || this._newGroup(session.device_id, metadata);
    let slot = 0; while (group.slots.has(slot)) slot++;
    group.slots.add(slot);
    const object = new THREE.Group();
    object.position.set((slot % COLUMNS - (COLUMNS - 1) / 2) * SLOT_X, 0, -Math.floor(slot / COLUMNS) * SLOT_Z);
    object.userData.observatorySessionId = session.session_id; group.object.add(object);
    const label = element('div', 'observatory-device-label'); label.dataset.sessionId = session.session_id;
    Object.assign(label.style, {position: this.renderer ? 'absolute' : 'relative', pointerEvents: 'none',
      display: 'flex', flexDirection: 'column', gap: '3px', padding: '6px 9px', textAlign: 'center'});
    const title = element('span', 'observatory-device-label-title'), status = element('span', 'observatory-device-label-status');
    label.append(title, status); this.labels.append(label);
    const record = {id: session.session_id, session, metadata, owner: identity(session), group, slot, object, label,
      title, status, generation: 0, bornAt: performance.now(), mountedUnits: new Map(), unitGeneration: 0,
      envelope: {...HOST_ENVELOPE}, frameQueue: Promise.resolve()};
    if (this.renderer) {
      record.podiumMaterial = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.7, metalness: 0.03});
      record.podium = new THREE.Mesh(this.podiumGeometry, record.podiumMaterial); record.podium.position.y = 1;
      record.edgeMaterial = new THREE.LineBasicMaterial({color: 0xcbdbe6});
      record.edges = new THREE.LineSegments(this.outlineGeometry, record.edgeMaterial); record.edges.position.y = 1;
      object.add(record.podium, record.edges);
    }
    this.records.set(record.id, record); this._layoutGroups(); return record;
  }

  async setSessions(sessions, deviceMetadataMap = new Map()) {
    if (this.disposed) return;
    const lookup = id => deviceMetadataMap instanceof Map ? deviceMetadataMap.get(id) : deviceMetadataMap[id];
    const wanted = new Set();
    for (const session of sessions || []) {
      if (!session?.session_id || !session.device_id || wanted.has(session.session_id)) continue;
      wanted.add(session.session_id);
      let record = this.records.get(session.session_id);
      if (record && record.owner !== identity(session)) { this._removeRecord(record); record = null; }
      const metadata = lookup(session.device_id);
      if (!record) record = this._newRecord(session, metadata);
      const previousBytes = Number(record.session.serial_bytes) || 0;
      record.session = session; record.metadata = metadata || record.metadata; record.leavingAt = null;
      clearTimeout(record.leaveTimer); record.leaveTimer = null;
      if (record.metadata?.name) record.group.name = record.metadata.name;
      if (Number(session.serial_bytes) > previousBytes) record.activityUntil = performance.now() + 1400;
      if (!ACTIVE.has(session.state)) clearModelDriveActivities(record.surface || {driveActivities: new Map()});
      this._updateLabel(record);
    }
    for (const record of this.records.values()) if (!wanted.has(record.id) && !record.leavingAt) {
      record.leavingAt = performance.now(); record.label.hidden = true;
      if (this.reducedMotion || !this.visible) this._removeRecord(record);
      else record.leaveTimer = setTimeout(() => {
        if (!this.disposed && this.records.get(record.id) === record && record.leavingAt) {
          this._removeRecord(record); this._updateGroups();
        }
      }, 300);
    }
    this._updateGroups(); this._markSelected(); this.dirty = true;
    if (!this.hasFitted && wanted.size) { this.hasFitted = true; this._fit(false); }
    else if (!this.selectedSessionId && !this.selectedGroupId
      && [...this.records.values()].some(record => !record.leavingAt && !this._inView(record))) this._fit();
    await this._refreshModelBudget();
    if (!this.disposed && this.framingDirty) { this.framingDirty = false; this._fit(); }
  }

  _updateLabel(record) {
    const session = record.session, bytes = Math.max(0, Number(session.serial_bytes) || 0);
    const short = record.id.length > 6 ? record.id.slice(-6) : record.id;
    record.title.textContent = `${record.metadata?.name || session.device_id} · ${short}`;
    const units = session.units?.length || 0;
    record.status.textContent = `${STATES[session.state] || session.state} · ${bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`} 日志${units ? ` · ${units} Unit` : ''}${!record.model && this.renderer ? ' · 模型按需加载' : ''}`;
    record.label.title = `${record.title.textContent}\n${record.status.textContent}${record.visualError ? `\n${record.visualError}` : ''}`;
    record.label.classList.toggle('is-terminal', !ACTIVE.has(session.state));
    record.label.classList.toggle('is-failed', session.state === 'failed');
    record.label.dataset.state = session.state;
    const color = session.state === 'failed' ? 0xcf6565 : ACTIVE.has(session.state) ? 0x0282cb : 0xbdcad4;
    record.edgeMaterial?.color.setHex(color);
  }

  _updateGroups() {
    for (const group of this.groups.values()) {
      const records = [...this.records.values()].filter(record => record.group === group && !record.leavingAt);
      group.label.textContent = `${group.name}  ·  ${records.length} 台`;
      group.label.hidden = records.length === 0 || Boolean(this.selectedSessionId)
        || Boolean(this.selectedGroupId && group.id !== this.selectedGroupId);
      group.label.style.display = group.label.hidden ? 'none' : '';
    }
  }

  _refreshModelBudget() {
    if (!this.renderer || this.disposed || !this.visible) return Promise.resolve();
    const candidates = [...this.records.values()].filter(record => !record.leavingAt).sort((a, b) => {
      const priority = record => record.id === this.selectedSessionId ? 0 : record.group.id === this.selectedGroupId ? 1 : ACTIVE.has(record.session.state) ? 2 : 3;
      return priority(a) - priority(b) || a.group.index - b.group.index || a.slot - b.slot;
    });
    const admitted = new Set(candidates.slice(0, MODEL_BUDGET).map(record => record.id));
    for (const record of this.records.values()) {
      record.admitted = admitted.has(record.id);
      if (!record.admitted && record.model) this._disposeModel(record);
    }
    return Promise.allSettled(candidates.slice(0, MODEL_BUDGET).map(record => this._queueModel(record)));
  }

  _queueModel(record) {
    if (record.model || record.loadPromise || record.modelFailed || !record.admitted) return record.loadPromise || Promise.resolve();
    record.loadPromise = new Promise(resolve => this.modelQueue.push({record, resolve})); this._drainModels(); return record.loadPromise;
  }

  _drainModels() {
    while (!this.disposed && this.visible && this.modelActive < LOAD_CONCURRENCY && this.modelQueue.length) {
      const item = this.modelQueue.shift(); this.modelActive++;
      this._loadModel(item.record).catch(error => {
        if (this.records.get(item.record.id) === item.record && !this.disposed) {
          item.record.visualError = error.message; item.record.modelFailed = true; this._updateLabel(item.record);
          this.onError(new Error(`${item.record.session.device_id} 模型暂不可用：${error.message}`));
        }
      }).finally(() => { item.record.loadPromise = null; this.modelActive--; item.resolve(); this._drainModels(); });
    }
  }

  async _loadModel(record) {
    if (!record.admitted || this.records.get(record.id) !== record || this.disposed) return;
    const generation = ++record.generation, modelId = record.metadata?.id || record.session.device_id;
    if (!MODEL_DEVICES.includes(modelId)) throw new Error('该设备暂无对应 3D 模型');
    const model = await loadModel(modelId, {pixelEffect: true});
    const current = () => !this.disposed && this.records.get(record.id) === record && record.generation === generation && record.admitted;
    if (!current()) { model.dispose(); return; }
    try {
      model.viewer = {requestRender: () => { this.dirty = true; }};
      // Explicitly neutralise demonstration defaults before runtime observations.
      for (const display of model.list('display')) display.fill('#000000');
      for (const speaker of model.list('speaker')) speaker.enabled = false;
      const surface = {model, display: model.find('lcd', 'display'), frameSeq: 0, disposed: false,
        feedbackDepth: 0, driveActivities: new Map(), showOverlay: (_title, message) => { record.visualError = message; },
        hideOverlay: () => { record.visualError = null; }};
      applyModelVisualState(surface, model.list('led').map(led => ({type: 'led', target: led.path, known: false})));
      record.model = model; record.surface = surface; record.object.add(model.root);
      // Freeze scale/anchor from the bare host. Units are attached afterwards
      // and inherit this same physical scale instead of shrinking the host.
      this._normaliseModel(record);
      await this._mountUnits(record);
      if (!current()) { if (record.model === model) this._disposeModel(record); else model.dispose(); return; }
      this._normaliseModel(record); this._applyDeviceState(record); this._applyUnits(record);
      this._updateLabel(record); this.dirty = true;
      if (record.latestFrame) await this._applyFrame(record, record.latestFrame);
    } catch (error) { if (record.model === model) this._disposeModel(record); else model.dispose(); throw error; }
  }

  async _mountUnits(record) {
    const model = record.model, generation = ++record.unitGeneration;
    if (!model) return;
    const current = () => !this.disposed && record.model === model && record.unitGeneration === generation && this.records.get(record.id) === record;
    const attachments = attachmentOrder(record.session.units || []), ports = new Map();
    const valid = new Set(attachments.map(unit => unit.id));
    for (const [id, mounted] of [...record.mountedUnits].reverse()) if (!valid.has(id)) {
      clearModelDriveActivities(record.surface, mounted.port);
      model.find(mounted.port, 'port')?.detach(); record.mountedUnits.delete(id);
    }
    for (const unit of attachments) {
      const parentPort = ports.get(unit.parent_id);
      const port = unit.visual_port || (unit.parent_id && parentPort ? `${parentPort}/${unit.port_id}` : null);
      if (port) ports.set(unit.id, port);
      // A null visual_port is an honest catalog boundary, not a guessed Grove wire.
      const mounted = record.mountedUnits.get(unit.id);
      if (!port || mounted?.port === port && mounted.unit_id === unit.unit_id) continue;
      const target = model.find(port, 'port');
      if (!target) continue;
      let module;
      try { module = await loadGroveModule(unit.unit_id); }
      catch (error) { record.visualError = `${unit.unit_id} 连接模型暂不可用：${error.message}`; continue; }
      if (!current()) { module.dispose(); return; }
      try {
        for (const display of module.list('display')) display.fill('#000000');
        for (const speaker of module.list('speaker')) speaker.enabled = false;
        target.attach(module); record.mountedUnits.set(unit.id, {port, unit_id: unit.unit_id});
        applyModelVisualState(record.surface, module.list('led').map(led => ({type: 'led', target: led.path, known: false})));
      } catch (error) {
        if (target.module === module) target.detach(); else module.dispose();
        record.mountedUnits.delete(unit.id); record.visualError = `${unit.unit_id} 连接模型暂不可用：${error.message}`;
      }
    }
    if (current()) {
      try { layoutHubAttachments(model); }
      catch (error) { record.visualError = `Unit 排布暂不可用：${error.message}`; }
    }
  }

  _normaliseModel(record) {
    const root = record.model.root, parent = root.parent;
    // Measure in the model's own space. The session's stable bay translation
    // must never be folded into its local normalisation transform.
    root.removeFromParent(); root.position.set(0, 0, 0); root.scale.setScalar(1);
    root.rotation.set(-0.08, -0.12, 0); root.updateWorldMatrix(true, true);
    if (!record.hostBasis) {
      const bounds = new THREE.Box3().setFromObject(root), size = bounds.getSize(new THREE.Vector3());
      record.hostBasis = {bounds, centre: bounds.getCenter(new THREE.Vector3()), scale: 110 / Math.max(size.x, size.y, size.z, 1)};
    }
    const {bounds, centre, scale} = record.hostBasis;
    root.scale.setScalar(scale); root.position.set(-centre.x * scale, 8 - bounds.min.y * scale, -centre.z * scale);
    root.updateWorldMatrix(true, true);
    const assembly = new THREE.Box3().setFromObject(root), size = assembly.getSize(new THREE.Vector3());
    const middle = assembly.getCenter(new THREE.Vector3());
    const hasUnits = (record.session.units || []).length > 0;
    record.envelope = {width: Math.max(HOST_ENVELOPE.width, size.x + 26), depth: Math.max(HOST_ENVELOPE.depth, size.z + 26), height: size.y,
      centreX: hasUnits ? middle.x : 0, centreZ: hasUnits ? middle.z : 0};
    if (record.podium) {
      for (const base of [record.podium, record.edges]) {
        base.scale.set(record.envelope.width / HOST_ENVELOPE.width, 1, record.envelope.depth / HOST_ENVELOPE.depth);
        base.position.set(record.envelope.centreX, 1, record.envelope.centreZ);
      }
    }
    parent?.add(root);
    root.updateWorldMatrix(true, true);
    this._layoutGroups();
  }

  _layoutGroups() {
    let previousRight = null;
    for (const group of [...this.groups.values()].sort((left, right) => left.index - right.index)) {
      const records = [...this.records.values()].filter(record => record.group === group);
      for (const record of records) {
        const envelope = record.envelope || HOST_ENVELOPE;
        const column = record.slot % COLUMNS, row = Math.floor(record.slot / COLUMNS);
        group.columnWidths[column] = Math.max(group.columnWidths[column], envelope.width + 38);
        group.rowDepths.set(row, Math.max(group.rowDepths.get(row) || SLOT_Z, envelope.depth + 64,
          envelope.height * 0.7 + envelope.depth * 0.5 + 40));
      }
      let left = Infinity, right = -Infinity, front = -Infinity;
      for (const record of records) {
        const envelope = record.envelope || HOST_ENVELOPE;
        const column = record.slot % COLUMNS, row = Math.floor(record.slot / COLUMNS);
        const x = group.columnWidths.slice(0, column).reduce((sum, width) => sum + width, 0) + group.columnWidths[column] / 2;
        let z = 0; for (let index = 0; index < row; index++) z -= group.rowDepths.get(index) || SLOT_Z;
        record.object.position.x = x - envelope.centreX; record.object.position.z = z - envelope.centreZ;
        left = Math.min(left, x - envelope.width / 2); right = Math.max(right, x + envelope.width / 2);
        front = Math.max(front, z + envelope.depth / 2);
      }
      if (!Number.isFinite(left)) continue;
      group.object.position.x = previousRight === null ? 0 : previousRight + 160 - left;
      previousRight = group.object.position.x + right;
      group.labelAnchor.set((left + right) / 2, 4, front + 88);
    }
    this.framingDirty = true; this.dirty = true;
  }

  setFrame(id, blob, guard = () => true) {
    const record = this.records.get(id);
    if (!record || record.leavingAt || this.disposed || !guard()) return Promise.resolve(false);
    const frame = {blob, guard, owner: record.owner}; record.latestFrame = frame;
    if (!record.model) return Promise.resolve(false);
    record.frameQueue = record.frameQueue.catch(() => {}).then(() => this._applyFrame(record, frame));
    return record.frameQueue;
  }

  async _applyFrame(record, frame) {
    const surface = record.surface, generation = record.generation;
    const current = () => !this.disposed && this.records.get(record.id) === record && !record.leavingAt
      && record.surface === surface && record.generation === generation && record.owner === frame.owner
      && record.latestFrame === frame && frame.guard();
    if (!surface || !current()) return false;
    const applied = await setModelImage(surface, frame.blob, surface.frameSeq + 1, current);
    if (applied && current()) { record.frameAt = Date.now(); record.frameKnown = true; this.dirty = true; }
    return applied;
  }

  clearFrame(id) {
    const record = this.records.get(id); if (!record || this.disposed) return;
    record.latestFrame = null; record.frameAt = null; record.frameKnown = false;
    if (record.surface) {
      record.surface.frameSeq = 0;
      record.surface.display?.fill('#000000');
    }
    this.dirty = true;
  }

  clearObservations(id) {
    const record = this.records.get(id); if (!record || this.disposed) return;
    this.clearFrame(id); record.devicePayload = null; record.unitPayload = null;
    if (record.surface) {
      clearModelDriveActivities(record.surface);
      for (const display of record.model.list('display')) display.fill('#000000');
      const commands = [
        ...record.model.list('led').map(led => ({type: 'led', target: led.path, known: false})),
        ...record.model.list('joint').map(joint => ({type: 'joint', target: joint.path, known: false})),
      ];
      try { applyModelVisualState(record.surface, commands); } catch (error) { record.visualError = error.message; }
    }
    this.dirty = true;
  }

  setDeviceState(id, payload) {
    const record = this.records.get(id);
    if (!record || this.disposed || payload?.session_id !== undefined && payload.session_id !== id) return false;
    record.devicePayload = payload; this._applyDeviceState(record); return true;
  }

  _applyDeviceState(record) {
    if (!record.surface || !record.devicePayload?.available || !Array.isArray(record.devicePayload.visual_commands)) return;
    try { applyModelVisualState(record.surface, record.devicePayload.visual_commands); this.dirty = true; }
    catch (error) { record.visualError = error.message; }
  }

  setUnits(id, payload) {
    const record = this.records.get(id);
    if (!record || this.disposed || payload?.session_id !== undefined && payload.session_id !== id) return false;
    const expected = new Map((record.session.units || []).map(unit => [unit.id, unit.unit_id]));
    if (!Array.isArray(payload?.units) || payload.units.some(unit => expected.get(unit.id) !== unit.unit_id)) return false;
    record.unitPayload = payload; this._applyUnits(record); return true;
  }

  _applyUnits(record) {
    if (!record.surface || !record.unitPayload) return;
    const observations = new Map(record.unitPayload.units.map(unit => [unit.id, unit]));
    for (const attachment of record.session.units || []) {
      const mounted = record.mountedUnits.get(attachment.id); if (!mounted) continue;
      const observed = observations.get(attachment.id) || {...attachment, available: false, properties: {}};
      try {
        applyModelVisualState(record.surface, visualCommands(observed, mounted.port, {running: ACTIVE.has(record.session.state)}));
      } catch (error) { record.visualError = error.message; }
    }
    this.dirty = true;
  }

  focus(id = null) {
    if (this.disposed) return;
    this.selectedSessionId = this.records.has(id) ? id : null; this.selectedGroupId = null;
    this._markSelected(); this._fit(); void this._refreshModelBudget();
  }

  focusGroup(id) {
    if (this.disposed || !this.groups.has(id)) return;
    this.selectedSessionId = null; this.selectedGroupId = id;
    this._markSelected(); this._fit(); void this._refreshModelBudget();
  }

  home() { if (this.disposed) return; this.selectedSessionId = this.selectedGroupId = null; this._markSelected(); this._fit(); void this._refreshModelBudget(); }

  _markSelected() {
    for (const record of this.records.values()) {
      const selected = record.id === this.selectedSessionId;
      record.object.visible = (!this.selectedSessionId || selected) && (!this.selectedGroupId || record.group.id === this.selectedGroupId);
      record.label.hidden = !record.object.visible || Boolean(record.leavingAt);
      record.label.style.display = record.label.hidden ? 'none' : 'flex';
      record.label.classList.toggle('is-selected', selected); record.label.setAttribute('aria-current', String(selected));
      record.podiumMaterial?.color.setHex(selected ? 0xe3f3fc : 0xffffff);
    }
    for (const group of this.groups.values()) {
      group.label.classList.toggle('is-selected', group.id === this.selectedGroupId);
      group.label.hidden = Boolean(this.selectedSessionId) || Boolean(this.selectedGroupId && group.id !== this.selectedGroupId)
        || ![...this.records.values()].some(record => record.group === group && !record.leavingAt);
      group.label.style.display = group.label.hidden ? 'none' : '';
    }
    this.dirty = true;
  }

  _fit(animate = true) {
    const box = new THREE.Box3();
    const records = [...this.records.values()].filter(record => !record.leavingAt
      && (!this.selectedSessionId || record.id === this.selectedSessionId)
      && (!this.selectedGroupId || record.group.id === this.selectedGroupId));
    for (const record of records) {
      record.object.updateWorldMatrix(true, true); box.expandByObject(record.object);
      // Pending or fallback models still reserve an honest full device envelope.
      const centre = record.object.getWorldPosition(new THREE.Vector3());
      box.expandByPoint(centre.clone().add(new THREE.Vector3(-78, 0, -60)));
      box.expandByPoint(centre.clone().add(new THREE.Vector3(78, 130, 68)));
    }
    if (box.isEmpty()) box.set(new THREE.Vector3(-150, 0, -80), new THREE.Vector3(150, 100, 80));
    const centre = box.getCenter(new THREE.Vector3()), fov = THREE.MathUtils.degToRad(this.camera.fov);
    const direction = new THREE.Vector3(Math.sin(this.polar) * Math.sin(this.yaw), Math.cos(this.polar), Math.sin(this.polar) * Math.cos(this.yaw));
    const right = new THREE.Vector3(0, 1, 0).cross(direction).normalize(), up = direction.clone().cross(right).normalize();
    const vertical = Math.tan(fov / 2), horizontal = vertical * this.camera.aspect;
    let distance = 0;
    // Fit the actual view-space corners. A sphere would waste most of the
    // vertical viewport for a wide row of devices or a host-plus-Unit assembly.
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
      const corner = new THREE.Vector3(x, y, z).sub(centre), toward = corner.dot(direction);
      distance = Math.max(distance, toward + Math.abs(corner.dot(right)) / horizontal, toward + Math.abs(corner.dot(up)) / vertical);
    }
    const next = {target: centre, distance: THREE.MathUtils.clamp(distance * 1.16, 270, 16000)};
    if (animate && !this.reducedMotion) this.cameraTween = {from: this.target.clone(), fromDistance: this.distance, ...next, started: performance.now()};
    else { this.target.copy(next.target); this.distance = next.distance; this.cameraTween = null; this._applyCamera(); }
    this.dirty = true;
  }

  _applyCamera() {
    this.camera.position.set(this.target.x + this.distance * Math.sin(this.polar) * Math.sin(this.yaw),
      this.target.y + this.distance * Math.cos(this.polar), this.target.z + this.distance * Math.sin(this.polar) * Math.cos(this.yaw));
    this.camera.lookAt(this.target); this.camera.updateMatrixWorld(); this.dirty = true;
  }

  _resize() {
    if (this.disposed) return;
    const width = this.container.clientWidth || 1, height = this.container.clientHeight || 1;
    this.camera.aspect = width / height; this.camera.updateProjectionMatrix();
    this.renderer?.setSize(width, height, false); this._fit(false);
  }

  _inView(record) {
    if (!record.object.visible) return false;
    const point = record.object.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 45, 0)).project(this.camera);
    return point.z > -1 && point.z < 1 && Math.abs(point.x) < 1.2 && Math.abs(point.y) < 1.2;
  }

  _positionLabel(node, world, force = false) {
    if (!this.renderer) return;
    const projected = world.project(this.camera), x = (projected.x + 1) * this.container.clientWidth / 2,
      y = (-projected.y + 1) * this.container.clientHeight / 2;
    const visible = projected.z > -1 && projected.z < 1 && x > -80 && x < this.container.clientWidth + 80 && y > -40 && y < this.container.clientHeight + 40;
    node.style.visibility = visible ? 'visible' : 'hidden';
    node.style.left = `${x}px`; node.style.top = `${y}px`; node.style.transform = 'translate(-50%, -50%)';
    node.style.zIndex = force ? '3' : '1';
  }

  _projectLabels() {
    for (const record of this.records.values()) {
      if (record.leavingAt || !record.object.visible) continue;
      const envelope = record.envelope || HOST_ENVELOPE;
      const position = record.object.getWorldPosition(new THREE.Vector3())
        .add(new THREE.Vector3(envelope.centreX, -2, envelope.centreZ + envelope.depth / 2 + 10));
      this._positionLabel(record.label, position, record.id === this.selectedSessionId);
      // Keep the overview legible: individual identity labels expand on focus.
      const left = position.clone().add(new THREE.Vector3(-70, 0, 0)).project(this.camera);
      const right = position.clone().add(new THREE.Vector3(70, 0, 0)).project(this.camera);
      const width = Math.abs(right.x - left.x) * this.container.clientWidth / 2;
      const expanded = this.selectedSessionId === record.id || width >= 125;
      record.label.classList.toggle('is-compact', !expanded);
      record.title.textContent = expanded ? `${record.metadata?.name || record.session.device_id} · ${record.id.slice(-6)}` : `#${record.id.slice(-6)}`;
      record.status.hidden = !expanded;
    }
    for (const group of this.groups.values()) this._positionLabel(group.label,
      group.object.getWorldPosition(new THREE.Vector3()).add(group.labelAnchor), true);
  }

  _tick = () => {
    this.raf = 0;
    if (this.disposed || !this.visible) return;
    const now = performance.now(), dt = Math.min(0.1, Math.max(0, (now - this.lastTick) / 1000)); this.lastTick = now;
    let animating = false;
    if (this.cameraTween) {
      const tween = this.cameraTween, progress = Math.min(1, (now - tween.started) / 400), ease = 1 - (1 - progress) ** 3;
      this.target.lerpVectors(tween.from, tween.target, ease); this.distance = THREE.MathUtils.lerp(tween.fromDistance, tween.distance, ease);
      this._applyCamera(); animating = progress < 1;
      if (!animating) this.cameraTween = null;
    }
    for (const record of [...this.records.values()]) {
      if (record.leavingAt) {
        const progress = Math.min(1, (now - record.leavingAt) / 280);
        if (progress >= 1) { this._removeRecord(record); this._updateGroups(); continue; }
        record.object.scale.setScalar(1 - progress * 0.12); record.object.position.y = -progress * 12; animating = true;
      } else if (!this.reducedMotion && now - record.bornAt < 350) {
        const progress = Math.min(1, (now - record.bornAt) / 350);
        record.object.scale.setScalar(0.92 + progress * 0.08); record.object.position.y = -8 * (1 - progress); animating = true;
      } else { record.object.scale.setScalar(1); record.object.position.y = 0; }
      if (record.object.visible && record.model?.update(dt, now / 1000)) animating = true;
      const activity = ACTIVE.has(record.session.state) && now < (record.activityUntil || 0);
      if (record.label.classList.contains('has-activity') !== activity) { record.label.classList.toggle('has-activity', activity); this.dirty = true; }
    }
    if (this.dirty || animating) {
      this.dirty = false; this.scene.updateMatrixWorld();
      this.renderer?.render(this.scene, this.camera); this._projectLabels();
    }
    this.raf = requestAnimationFrame(this._tick);
  };

  setVisible(visible) {
    if (this.disposed || this.visible === Boolean(visible)) return;
    this.visible = Boolean(visible);
    if (!this.visible) {
      cancelAnimationFrame(this.raf); this.raf = 0;
      for (const item of this.modelQueue.splice(0)) { item.record.loadPromise = null; item.resolve(); }
    } else {
      this.lastTick = performance.now(); this.dirty = true; this._tick(); void this._refreshModelBudget();
    }
  }

  _disposeModel(record) {
    record.generation++; record.unitGeneration++;
    if (record.surface) { record.surface.disposed = true; clearModelDriveActivities(record.surface); }
    if (record.model) { record.model.viewer = null; record.model.dispose(); }
    record.model = record.surface = null; record.mountedUnits.clear(); this._updateLabel(record); this.dirty = true;
  }

  _removeRecord(record) {
    if (this.records.get(record.id) !== record) return;
    clearTimeout(record.leaveTimer); record.leaveTimer = null;
    this._disposeModel(record); record.latestFrame = null; record.label.remove(); record.object.removeFromParent();
    record.podiumMaterial?.dispose(); record.edgeMaterial?.dispose(); record.group.slots.delete(record.slot); this.records.delete(record.id);
    if (!record.group.slots.size) {
      record.group.label.remove(); record.group.object.removeFromParent(); this.groups.delete(record.group.id);
    }
    const lostFocus = this.selectedSessionId === record.id || this.selectedGroupId && !this.groups.has(this.selectedGroupId);
    if (this.selectedSessionId === record.id) this.selectedSessionId = null;
    if (this.selectedGroupId && !this.groups.has(this.selectedGroupId)) this.selectedGroupId = null;
    if (lostFocus && !this.disposed) { this._markSelected(); this._fit(); }
    this.dirty = true;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true; cancelAnimationFrame(this.raf); this.resizeObserver.disconnect();
    for (const item of this.modelQueue.splice(0)) item.resolve();
    for (const record of [...this.records.values()]) this._removeRecord(record);
    this.environment?.dispose(); if (this.floor) disposeObject(this.floor); if (this.grid) disposeObject(this.grid);
    this.podiumGeometry?.dispose(); this.outlineGeometry?.dispose();
    this.renderer?.dispose(); this.renderer?.domElement.remove(); this.labels.remove(); this.container.classList.remove('observatory-scene');
  }
}
