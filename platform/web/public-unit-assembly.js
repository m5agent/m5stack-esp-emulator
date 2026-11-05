import {createUnitPicker} from './unit-panel.js';

// This component owns configuration and appearance only. It never sends a
// runtime input, invents readback or grants browser/native execution admission.
const copy = value => structuredClone(value);
const ready = unit => ['implemented', 'validated'].includes(unit?.runtime?.status);
const fail = (code, message) => Object.assign(new Error(message), {code});
const portsFor = (catalog, id) => (catalog.hosts.find(host => host.device_id === id)?.ports || [])
  .filter(port => port.wiring_status === 'confirmed' && port.physical_presence === 'main-device');

function inventory(value) {
  if (!value || !Array.isArray(value.units) || !Array.isArray(value.hosts))
    throw fail('assembly_catalog_invalid', '装配目录需要真实 Unit 与主机接口合同。');
  if (value.units.some(unit => !unit || typeof unit.id !== 'string' || !unit.id)
      || value.hosts.some(host => !host || typeof host.device_id !== 'string' || !Array.isArray(host.ports)))
    throw fail('assembly_catalog_invalid', '装配目录缺少有效身份或接口。');
  if (new Set(value.units.map(unit => unit.id)).size !== value.units.length
      || new Set(value.hosts.map(host => host.device_id)).size !== value.hosts.length)
    throw fail('assembly_catalog_invalid', '装配目录包含重复身份。');
  return copy(value);
}

function compatible(catalog, deviceId, unit, port, child = false) {
  return ready(unit) && unit.runtime.hosts?.includes(deviceId)
    && (child || !port.admitted_unit_ids || port.admitted_unit_ids.includes(unit.id))
    && (child || !unit.host_admission || unit.host_admission.device_id === deviceId
      && unit.host_admission.port_ids?.includes(port.id));
}

/** Validate a draft, not a running guest. The service remains authoritative. */
export function validateUnitAssemblyDraft(catalog, deviceId, attachments) {
  if (!Array.isArray(attachments) || attachments.length > 16)
    throw fail('assembly_invalid', '装配草稿最多包含 16 个 Unit。');
  const hostPorts = portsFor(catalog, deviceId), byId = new Map(), occupied = new Set();
  for (const row of attachments) {
    if (!row || !/^[a-z][a-z0-9_-]{0,47}$/.test(row.id || '') || byId.has(row.id))
      throw fail('assembly_invalid', 'Unit 实例身份无效或重复。');
    byId.set(row.id, row);
  }
  const resolved = new Map(), visiting = new Set();
  function resolve(row) {
    if (resolved.has(row.id)) return resolved.get(row.id);
    if (visiting.has(row.id)) throw fail('assembly_topology_invalid', 'Unit 连接关系存在循环。');
    visiting.add(row.id);
    const unit = catalog.units.find(unit => unit.id === row.unit_id);
    if (!unit) throw fail('assembly_unit_unknown', 'Unit 不在当前合同目录中。');
    const parent = row.parent_id && byId.get(row.parent_id);
    if (row.parent_id && (!parent || parent.unit_id !== 'hub' || !/^grove-[123]$/.test(row.port_id)))
      throw fail('assembly_topology_invalid', '子 Unit 需要已连接的 HUB 接口。');
    const upstream = parent ? resolve(parent) : null;
    const port = upstream?.port || hostPorts.find(port => port.id === row.port_id);
    if (!port || !compatible(catalog, deviceId, unit, port, !!parent)
        || !['yellow', 'white'].every(wire => Number.isInteger(port.pins?.[wire]) && port.pins[wire] >= 0))
      throw fail('assembly_incompatible', '此 Unit 与当前主机接口的合同不兼容。');
    const connector = JSON.stringify([row.parent_id || null, row.port_id]);
    if (occupied.has(connector)) throw fail('assembly_port_conflict', '一个接口只能连接一个 Unit。');
    occupied.add(connector);
    const result = {row, unit, port, visualPort: upstream
      ? upstream.visualPort && `${upstream.visualPort}/${row.port_id}` : port.visual_port};
    resolved.set(row.id, result); visiting.delete(row.id); return result;
  }
  attachments.forEach(resolve);
  const buses = new Map();
  for (const item of resolved.values()) {
    if (item.unit.id === 'hub') continue;
    const key = JSON.stringify([item.port.pins.yellow, item.port.pins.white]), peers = buses.get(key) || [];
    peers.push(item); buses.set(key, peers);
  }
  for (const peers of buses.values()) if (peers.length > 1) {
    const addresses = new Set();
    for (const {unit, row} of peers) {
      if (unit.interface?.bus !== 'i2c')
        throw fail('assembly_bus_conflict', '共享 HUB 总线仅允许已建模的 I2C 组合。');
      const addressInput = unit.runtime.address_input;
      const values = addressInput ? [row.initial?.[addressInput] ?? unit.runtime.default_address_7bit]
        : unit.interface.address_7bit || [];
      for (const value of values) {
        if (addresses.has(value)) throw fail('assembly_address_conflict', 'HUB 无法隔离重复 I2C 地址。');
        addresses.add(value);
      }
    }
  }
  return [...resolved.values()]; // parents before children
}

export class PublicUnitAssembly {
  constructor(container, {deviceId, catalog, onChange = () => {}, onError = () => {}, pickerFactory = createUnitPicker}) {
    Object.assign(this, {container, deviceId, onChange, onError, pickerFactory});
    this.catalog = inventory(catalog); this.drafts = new Map(); this.locked = false;
    this.disposed = false; this.epoch = 0; this.visualEpoch = 0; this.mounted = new Map();
    this.visualQueue = Promise.resolve();
    const doc = container.ownerDocument || document;
    this.root = doc.createElement('section'); this.root.className = 'public-unit-assembly';
    this.root.dataset.unitAssembly = 'draft';
    this.note = doc.createElement('p'); this.note.className = 'field-help'; this.note.setAttribute('role', 'status');
    this.fields = doc.createElement('fieldset'); this.fields.className = 'unit-assembly-fields';
    this.root.append(this.note, this.fields); container.replaceChildren(this.root);
    this.changed = () => { void this.readPicker().catch(error => this.reportError(error)); };
    this.relabel = () => this.labelDraft();
    this.fields.addEventListener('change', this.changed);
    this.fields.addEventListener('input', this.relabel);
  }

  requireOpen() { if (this.disposed) throw fail('assembly_disposed', '装配面板已关闭。'); }
  requireEditable() { this.requireOpen(); if (this.locked) throw fail('assembly_locked', '运行期间不能修改 Unit 接线，请先确认停止。'); }
  rows() { return this.drafts.get(this.deviceId) || []; }
  issues() { try { validateUnitAssemblyDraft(this.catalog, this.deviceId, this.rows()); return []; } catch (error) { return [{code: error.code, message: error.message}]; } }
  snapshot() { return {scope: 'assembly-draft', deviceId: this.deviceId, attachments: copy(this.rows()), locked: this.locked, valid: !this.issues().length, issues: this.issues()}; }
  notify() { const value = this.snapshot(); this.note.textContent = this.locked
    ? this.lockReason || '运行期间接线已锁定；输入与读回由当前设备会话提供。'
    : value.valid ? '接线草稿与模型装配；实际执行需由所选内核或服务另行确认。'
      : `草稿需要调整：${value.issues[0].message}`; this.onChange(value); return value; }
  reportError(error) { this.note.textContent = error.message; this.onError(error); }
  attachments(deviceId = this.deviceId) {
    this.requireOpen();
    if (deviceId !== this.deviceId) throw fail('assembly_device_mismatch', '装配草稿不属于当前设备。');
    validateUnitAssemblyDraft(this.catalog, deviceId, this.rows()); return copy(this.rows());
  }

  async init() { await this.render(); this.notify(); return this; }
  async setDevice(id) {
    this.requireEditable(); this.deviceId = id; await this.render();
    const result = this.notify(); await this.syncShell(); return result;
  }
  async updateInventory(catalog) {
    this.requireOpen(); const next = inventory(catalog);
    if (this.locked) { this.pendingCatalog = next; return this.snapshot(); }
    this.catalog = next; await this.render(); const result = this.notify(); await this.syncShell(); return result;
  }
  async setLocked(locked, reason = '') {
    this.requireOpen(); this.locked = !!locked; this.lockReason = reason;
    this.fields.disabled = this.locked; this.visualEpoch++;
    if (this.locked) {
      await this.visualQueue.catch(() => {});
      // Handoff without detaching: the actual UnitPanel now owns these ports.
      this.mounted.clear(); return this.notify();
    }
    if (this.pendingCatalog) { this.catalog = this.pendingCatalog; this.pendingCatalog = null; }
    await this.render(); const result = this.notify(); await this.syncShell(); return result;
  }

  async render() {
    const epoch = ++this.epoch, doc = this.container.ownerDocument || document;
    this.picker?.dispose(); this.picker = null;
    const mount = doc.createElement('div'); this.fields.replaceChildren(mount);
    const picker = await this.pickerFactory(mount, {deviceId: this.deviceId, api: async () => copy(this.catalog)});
    if (this.disposed || epoch !== this.epoch) { picker.dispose(); return; }
    if (picker.loadError) { picker.dispose(); throw fail('assembly_picker_unavailable', picker.loadError); }
    this.picker = picker; this.mount = mount; this.fields.disabled = this.locked;
    this.hydrate(); this.labelDraft();
  }
  hydrate() {
    if (!this.picker || !this.mount) return;
    this.hydrating = true;
    try {
      const rows = [...this.mount.querySelectorAll('.unit-picker-port')];
      const ports = portsFor(this.catalog, this.deviceId);
      for (const [index, port] of ports.entries()) {
        const element = rows[index]; if (!element) continue;
        const attachment = this.rows().find(row => !row.parent_id && row.port_id === port.id);
        const selects = [...element.querySelectorAll('select')];
        this.choose(selects[0], attachment?.unit_id || '');
        for (let slot = 1; slot <= 3; slot++) {
          const child = attachment && this.rows().find(row => row.parent_id === attachment.id && row.port_id === `grove-${slot}`);
          this.choose(selects[slot], child?.unit_id || '');
        }
        for (const row of [attachment, ...(attachment ? this.rows().filter(child => child.parent_id === attachment.id) : [])].filter(Boolean)) {
          const scope = row.parent_id ? element.querySelectorAll('.unit-picker-fixtures')[Number(row.port_id.at(-1))] : element.querySelector('.unit-picker-fixtures');
          for (const control of scope?.querySelectorAll('[data-creation-field]') || []) {
            if (Object.hasOwn(row.initial || {}, control.dataset.creationField)) {
              control.checked = row.initial[control.dataset.creationField] === true;
              control.dispatchEvent(new Event('change', {bubbles: true}));
            }
          }
        }
      }
    } finally { this.hydrating = false; }
  }
  choose(select, value) { if (select) { select.value = value; select.dispatchEvent(new Event('change', {bubbles: true})); } }
  labelDraft() {
    if (!this.mount) return;
    for (const group of this.mount.querySelectorAll('optgroup')) if (group.label.startsWith('可运行')) group.label = '草稿可连接 · 执行能力另验';
    const ports = portsFor(this.catalog, this.deviceId);
    for (const [index, row] of [...this.mount.querySelectorAll('.unit-picker-port')].entries()) {
      for (const [slot, select] of [...row.querySelectorAll('select')].entries()) {
        for (const option of select.querySelectorAll('option')) {
          if (!option.value) continue;
          const unit = this.catalog.units.find(unit => unit.id === option.value);
          option.disabled = !ports[index] || !compatible(this.catalog, this.deviceId, unit, ports[index], slot > 0)
            || slot > 0 && unit?.interface?.bus !== 'i2c';
        }
      }
    }
    for (const badge of this.mount.querySelectorAll('.unit-capability')) badge.textContent = '连接草稿';
    for (const result of this.mount.querySelectorAll('.unit-picker-results')) result.textContent = result.textContent.replace(/个可运行/g, '个草稿兼容');
  }
  async readPicker() {
    if (this.disposed || this.locked || this.hydrating || !this.picker) return;
    const next = this.picker.attachments(this.deviceId);
    try { validateUnitAssemblyDraft(this.catalog, this.deviceId, next); }
    catch (error) { this.hydrate(); this.labelDraft(); throw error; }
    this.drafts.set(this.deviceId, copy(next)); this.labelDraft(); this.notify(); await this.syncShell();
  }

  focusUnit(unitId) {
    this.requireOpen();
    const select = [...(this.mount?.querySelectorAll('select') || [])].find(select => select.value === unitId);
    if (!select) return false;
    select.focus(); select.scrollIntoView?.({block: 'nearest'}); return true;
  }
  async addUnit(unitId, {portId, parentId} = {}) {
    this.requireEditable();
    if (!portId && !parentId && this.rows().some(row => row.unit_id === unitId)) { this.focusUnit(unitId); return this.snapshot(); }
    const unit = this.catalog.units.find(unit => unit.id === unitId);
    if (!unit) throw fail('assembly_unit_unknown', 'Unit 不在当前合同目录中。');
    const ports = portsFor(this.catalog, this.deviceId);
    const parent = parentId && this.rows().find(row => row.id === parentId && row.unit_id === 'hub');
    if (parentId && !parent) throw fail('assembly_topology_invalid', '指定的 HUB 尚未连接。');
    let next;
    for (const [index, port] of ports.entries()) {
      if (parent && parent.port_id !== port.id || !parent && portId && port.id !== portId) continue;
      const slots = parent ? [1, 2, 3].map(n => `grove-${n}`) : [port.id];
      for (const slot of slots) {
        if (parent && portId && slot !== portId || this.rows().some(row => (row.parent_id || null) === (parent?.id || null) && row.port_id === slot)) continue;
        const candidate = {id: parent ? `${parent.id}-${slot.at(-1)}` : `external${index + 1}`, unit_id: unitId, port_id: slot,
          ...(parent ? {parent_id: parent.id} : {})};
        try { validateUnitAssemblyDraft(this.catalog, this.deviceId, [...this.rows(), candidate]); next = candidate; break; } catch { /* try another compatible free connector */ }
      }
      if (next) break;
    }
    if (!next) throw fail('assembly_no_compatible_port', '没有可用的兼容接口；请在接线面板选择接口或先移除其它 Unit。');
    this.drafts.set(this.deviceId, [...this.rows(), next]); this.hydrate(); this.labelDraft();
    // The existing picker owns creation-only defaults. Capture exactly what its
    // controls show, instead of dropping a default=true configuration on Add.
    if (this.picker) {
      const rendered = this.picker.attachments(this.deviceId);
      validateUnitAssemblyDraft(this.catalog, this.deviceId, rendered);
      this.drafts.set(this.deviceId, copy(rendered));
    }
    const result = this.notify(); await this.syncShell(); this.focusUnit(unitId); return result;
  }

  async attachShell(shell) {
    this.requireOpen(); this.shell = shell; this.visualEpoch++;
    if (this.locked) return;
    return this.syncShell();
  }
  syncShell() {
    const epoch = ++this.visualEpoch, shell = this.shell;
    const task = this.visualQueue.catch(() => {}).then(async () => {
      const current = () => !this.disposed && !this.locked && epoch === this.visualEpoch && shell === this.shell;
      if (!current()) return;
      const desired = this.issues().length ? [] : validateUnitAssemblyDraft(this.catalog, this.deviceId, this.rows()).filter(item => item.visualPort);
      const wanted = new Map(desired.map(item => [item.visualPort, item]));
      for (const [port, old] of [...this.mounted].sort(([a], [b]) => b.length - a.length)) {
        if (!current()) return;
        if (old.shell === shell && wanted.get(port)?.row.unit_id === old.unitId) continue;
        await old.shell.detachUnit(port); this.mounted.delete(port);
      }
      for (const item of desired) {
        if (!current() || !shell?.attachUnit) return;
        const port = item.visualPort;
        if (this.mounted.get(port)?.shell === shell && this.mounted.get(port).unitId === item.row.unit_id) continue;
        const module = await shell.attachUnit(item.row.unit_id, {port});
        if (module !== null) this.mounted.set(port, {shell, unitId: item.row.unit_id});
      }
    });
    this.visualQueue = task; return task;
  }
  async dispose() {
    if (this.disposed) return;
    if (!this.locked) { this.drafts.set(this.deviceId, []); await this.syncShell(); }
    this.disposed = true; this.epoch++; this.visualEpoch++;
    this.picker?.dispose(); this.fields.removeEventListener('change', this.changed);
    this.fields.removeEventListener('input', this.relabel); this.container.replaceChildren();
  }
}

export async function createPublicUnitAssembly(container, options) { return new PublicUnitAssembly(container, options).init(); }
