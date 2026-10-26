import {CARDKB_KEY_IDS, physicalInput, visualCommands} from './unit-visual-mappings.js?v=20261026f';
import {UnitAudio} from './unit-audio.js';
export {physicalInput, visualCommands} from './unit-visual-mappings.js?v=20261026f';

const ACTIVE = new Set(['booting', 'running']);
const inputId = (id, field, index) => `unit-${id}-${field}${index === undefined ? '' : `-${index}`}`;
const copy = value => structuredClone(value);
const text = value => typeof value === 'object' ? JSON.stringify(value) : String(value);
const pressField = (field, schema) => schema.type === 'boolean' && (field === 'pressed' || field.endsWith('-pressed'));
const pressArray = (field, schema) => schema.type === 'array' && schema.items?.type === 'boolean' && ['keys', 'pressed'].includes(field);
const rgbValue = value => Number.isInteger(value) && value >= 0 && value <= 0xFFFFFF;

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function observedValue(field, value) {
  const output = element('dd');
  const colors = Array.isArray(value) ? value : [value];
  if (field !== 'led-rgb' || !colors.length || !colors.every(rgbValue)) {
    output.textContent = text(value);
    return output;
  }
  output.className = 'unit-rgb-values';
  colors.forEach((color, index) => {
    const hex = `#${color.toString(16).padStart(6, '0')}`;
    const chip = element('span', 'unit-rgb-value');
    chip.dataset.unitRgb = index;
    chip.setAttribute('aria-label', `LED[${index}] ${hex}`);
    const swatch = element('span', 'unit-rgb-swatch');
    swatch.setAttribute('aria-hidden', 'true');
    swatch.style.setProperty('--unit-led-color', hex);
    chip.append(swatch, element('code', '', `${Array.isArray(value) ? `LED[${index}] ` : ''}${hex}`));
    output.append(chip);
  });
  // Electrical array order is explicit. This does not claim a mapping to
  // unconfirmed LED locations in the physical shell.
  return output;
}

function valid(value, schema) {
  if (schema.type === 'boolean' && typeof value !== 'boolean') return false;
  if (['number', 'integer'].includes(schema.type) && (!Number.isFinite(value) || schema.type === 'integer' && !Number.isInteger(value))) return false;
  if (schema.type === 'string' && (typeof value !== 'string' || schema.maxLength !== undefined && value.length > schema.maxLength || schema.pattern && !new RegExp(`^(?:${schema.pattern})$`).test(value))) return false;
  if (schema.type === 'array' && (!Array.isArray(value) || schema.minItems !== undefined && value.length < schema.minItems || schema.maxItems !== undefined && value.length > schema.maxItems || schema.items && !value.every(item => valid(item, schema.items)))) return false;
  if (schema.minimum !== undefined && value < schema.minimum || schema.maximum !== undefined && value > schema.maximum) return false;
  if (schema.enum && !schema.enum.includes(value)) return false;
  return true;
}

function ordered(attachments) {
  const result = [], visited = new Set(), visiting = new Set();
  const byId = new Map(attachments.map(unit => [unit.id, unit]));
  const visit = unit => {
    if (visited.has(unit.id)) return;
    if (visiting.has(unit.id)) throw new Error('Unit 连接关系存在循环');
    visiting.add(unit.id);
    if (unit.parent_id) {
      const parent = byId.get(unit.parent_id);
      if (!parent) throw new Error('Unit 上游 HUB 不存在');
      visit(parent);
    }
    visiting.delete(unit.id);
    visited.add(unit.id);
    result.push(unit);
  };
  attachments.forEach(visit);
  return result;
}

class UnitPanel {
  constructor(container, {session, shell, api, bindingsByUnit = {}}) {
    Object.assign(this, {container, session, shell, api, bindingsByUnit});
    this.disposed = false;
    this.generation = 0;
    this.sessionEpoch = 0;
    this.inputEpoch = 0;
    this.queues = new Map();
    this.pending = new Map();
    this.revision = 0;
    this.pressSources = new Map();
    this.releaseIntents = new Map();
    this.cards = new Map();
    this.states = new Map();
    this.definitions = new Map();
    this.audio = new Map();
    this.audioDefinitions = new Map();
    this.mounted = new Map();
    this.attaching = new Map();
    this.release = () => this.releaseHeld();
    window.addEventListener('blur', this.release);
  }

  currentSession(sessionId, epoch) {
    return !this.disposed && sessionId === this.session.session_id && epoch === this.sessionEpoch;
  }

  async init() {
    if (!(this.session.units || []).length) return this;
    const observedSessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    const inputEpoch = this.inputEpoch;
    try {
      const [state, inventory] = await Promise.allSettled([
        this.api(`/api/v1/sessions/${encodeURIComponent(this.session.session_id)}/units`),
        this.api(`/api/v1/units?device_id=${encodeURIComponent(this.session.device_id)}`),
      ]);
      if (!this.currentSession(observedSessionId, sessionEpoch) || inputEpoch !== this.inputEpoch || state.status === 'fulfilled' && state.value.session_id !== undefined && state.value.session_id !== observedSessionId) return this;
      this.inventory = inventory.status === 'fulfilled' ? inventory.value : {units: [], hosts: []};
      // Session snapshots own the schema. Live inventory is only a legacy
      // fallback and must never replace a captured session's input contract.
      const payload = state.status === 'fulfilled' ? state.value : null;
      const definitions = Array.isArray(payload?.definitions) ? payload.definitions : this.inventory.units;
      this.frozenDefinitions = Array.isArray(payload?.definitions);
      this.definitions = new Map(definitions.map(unit => [unit.id, unit]));
      this.render();
      if (payload) this.apply(payload, observedSessionId, sessionEpoch);
      else for (const id of this.cards.keys()) this.note(id, `状态请求失败：${state.reason?.message || '模型状态不可用'}`);
      await this.setShell(this.shell);
      this.schedule();
    } catch (error) {
      if (this.currentSession(observedSessionId, sessionEpoch)) this.container.textContent = `Unit 状态不可用：${error.message}`;
    }
    return this;
  }

  safeDetach({shell, port, id}) {
    this.audio.get(id)?.observe(null, null, {sessionId: this.session.session_id});
    try { Promise.resolve(shell.detachUnit?.(port)).catch(() => {}); }
    catch { /* the renderer may already have disposed the port */ }
  }

  async setShell(shell) {
    if (this.disposed) return;
    if (this.shell !== shell) {
      for (const audio of this.audio.values()) audio.observe(null, null, {sessionId: this.session.session_id});
      this.generation += 1;
      this.releaseHeld('shell:');
      const previous = [...this.mounted.values(), ...this.attaching.values()];
      this.mounted.clear();
      this.attaching.clear();
      // Clear ownership before detach. Nested children release before parents.
      previous.sort((a, b) => b.port.length - a.port.length).forEach(item => this.safeDetach(item));
    }
    this.shell = shell;
    if (!shell?.attachUnit) return;
    const generation = this.generation;
    const host = this.inventory?.hosts?.find(item => item.device_id === this.session.device_id);
    const ports = new Map();
    for (const unit of ordered(this.session.units || [])) {
      const parentPort = ports.get(unit.parent_id);
      const port = unit.visual_port || (unit.parent_id ? parentPort && `${parentPort}/${unit.port_id}` : host?.ports.find(item => item.id === unit.port_id)?.visual_port);
      if (port) ports.set(unit.id, port);
      if (!port || this.mounted.get(unit.id)?.shell === shell || this.attaching.get(unit.id)?.generation === generation) continue;
      const item = {shell, port, generation, id: unit.id};
      this.attaching.set(unit.id, item);
      try {
        const module = await shell.attachUnit(unit.unit_id, {port});
        if (this.attaching.get(unit.id) === item) this.attaching.delete(unit.id);
        if (this.disposed || generation !== this.generation || this.shell !== shell) {
          // Same-shell replacement may own this port now. The model loader's
          // attachment generation cancels stale loads without detaching it.
          if (this.shell !== shell) this.safeDetach(item);
          return;
        }
        if (module === null) continue;
        this.mounted.set(unit.id, item);
        const state = this.states.get(unit.id);
        if (state) this.paint(state);
      } catch (error) {
        if (this.attaching.get(unit.id) === item) this.attaching.delete(unit.id);
        if (!this.disposed && generation === this.generation) this.note(unit.id, `外壳连接失败：${error.message}`);
      }
    }
  }

  updateSession(session) {
    const wasActive = ACTIVE.has(this.session.state);
    const changed = session.session_id !== this.session.session_id;
    if (changed) {
      // Release ownership while sends still capture the original session.
      this.releaseHeld();
      this.sessionEpoch += 1;
      this.inputEpoch += 1;
      this.generation += 1;
      const previous = [...this.mounted.values(), ...this.attaching.values()];
      this.mounted.clear();
      this.attaching.clear();
      previous.sort((a, b) => b.port.length - a.port.length).forEach(item => this.safeDetach(item));
      this.remountOnObservation = true;
      this.refreshing = null;
      this.pending.clear();
      this.queues.clear();
      this.pressSources.clear();
      this.releaseIntents.clear();
      this.states.clear();
      this.stateSource = 'unavailable';
      this.frozenDefinitions = false;
      this.definitions = new Map((this.inventory?.units || []).map(unit => [unit.id, unit]));
      this.audioPayload = null;
      this.audioDefinitions.clear();
      this.audioDefinitionSessionId = null;
    }
    this.session = session;
    if (changed) this.render();
    this.observeAudio(this.audioPayload);
    if (!ACTIVE.has(session.state)) {
      clearTimeout(this.timer);
      this.releaseHeld();
      this.releaseIntents.clear();
    } else if (changed || !wasActive) {
      this.schedule();
    }
    this.enableControls();
    for (const state of this.states.values()) this.paint(state);
  }

  enableControls() {
    for (const [id, card] of this.cards) {
      const ready = this.session.state === 'running' && this.states.get(id)?.available === true;
      for (const control of card.querySelectorAll('input, button, textarea, select')) control.disabled = !ready;
      const audio = this.audio.get(id);
      const button = card.querySelector('[data-unit-audio-toggle]');
      if (button) button.disabled = !audio?.signal || audio.disposed;
    }
  }

  makePress(id, field, index, label) {
    const button = element('button', 'btn unit-press', label);
    button.type = 'button';
    button.id = inputId(id, field, index);
    button.dataset.pressField = field;
    if (index !== undefined) button.dataset.pressIndex = index;
    button.setAttribute('aria-pressed', 'false');
    const down = (event, source) => {
      event.preventDefault();
      if (this.disposed || this.session.state !== 'running') return;
      if (event.pointerId !== undefined) {
        try { button.setPointerCapture(event.pointerId); } catch { /* synthetic events have no captured pointer */ }
      }
      this.setHeld(id, field, index, source, true);
    };
    button.addEventListener('pointerdown', event => down(event, `form:pointer:${event.pointerId}`));
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) button.addEventListener(name, event => this.setHeld(id, field, index, `form:pointer:${event.pointerId}`, false));
    button.addEventListener('keydown', event => {
      if (![' ', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (!event.repeat) down(event, `form:key:${event.code}`);
    });
    button.addEventListener('keyup', event => {
      if ([' ', 'Enter'].includes(event.key)) this.setHeld(id, field, index, `form:key:${event.code}`, false);
    });
    button.addEventListener('blur', () => this.releaseHeld('form:key:', id, field, index));
    return button;
  }

  render() {
    for (const audio of this.audio.values()) audio.dispose();
    this.audio.clear();
    this.container.replaceChildren();
    this.cards.clear();
    this.container.classList.add('unit-panel');
    this.container.append(element('h3', 'unit-panel-title', '连接的 Unit'));
    for (const attachment of ordered(this.session.units || [])) {
      const definition = this.definitions.get(attachment.unit_id);
      if (!definition) continue;
      const card = element('section', 'unit-card');
      card.dataset.unitId = attachment.id;
      card.append(element('h4', '', `${definition.name} · ${attachment.parent_id ? `${attachment.parent_id}/` : ''}${attachment.port_id}`));
      const status = element('div', 'unit-note', '等待模型状态…');
      status.dataset.unitNote = '';
      status.setAttribute('aria-live', 'polite');
      card.append(status);
      if (attachment.unit_id === 'fan') card.append(element('p', 'unit-note', '动画表示 PWM 驱动活动；转速与机电过程未建模。'));
      if (attachment.unit_id === 'buzzer') {
        const controls = element('div', 'unit-audio-controls');
        const toggle = element('button', 'btn', '启用声音试听');
        toggle.type = 'button';
        toggle.dataset.unitAudioToggle = '';
        toggle.setAttribute('aria-label', `${definition.name} · 声音试听`);
        const status = element('span', 'unit-note', '默认静音');
        status.dataset.unitAudioStatus = '';
        status.setAttribute('aria-live', 'polite');
        const audio = new UnitAudio({onChange: state => {
          toggle.textContent = state.enabled ? '静音' : '启用声音试听';
          toggle.setAttribute('aria-pressed', String(state.enabled));
          toggle.disabled = !state.signal || state.disposed;
          if (status.textContent !== state.message) status.textContent = state.message;
        }});
        toggle.setAttribute('aria-pressed', 'false');
        toggle.disabled = true;
        toggle.addEventListener('click', () => {
          if (audio.enabled) audio.mute();
          else void audio.enable();
        });
        this.audio.set(attachment.id, audio);
        controls.append(toggle, status);
        card.append(controls, element('p', 'unit-note', '电气 PWM 波形试听（带限、低音量），不代表实物音色或声压。'));
      }
      for (const [field, schema] of Object.entries(definition.inputs || {})) {
        if (!definition.runtime?.inputs?.[field] || schema.readOnly) continue;
        const row = element('div', 'unit-control');
        const label = element('label', '', schema.label || field);
        label.htmlFor = inputId(attachment.id, field);
        row.append(label);
        if (pressField(field, schema)) {
          row.append(this.makePress(attachment.id, field, undefined, '按住'));
        } else if (pressArray(field, schema)) {
          const group = element('div', 'unit-key-grid');
          group.id = label.htmlFor;
          group.setAttribute('role', 'group');
          group.setAttribute('aria-label', schema.label || field);
          for (let index = 0; index < schema.maxItems; index++) {
            const name = attachment.unit_id === 'cardkb' ? CARDKB_KEY_IDS[index]?.slice(4) : `CH${index + 1}`;
            group.append(this.makePress(attachment.id, field, index, name || String(index + 1)));
          }
          row.append(group);
        } else {
          const multiline = schema.type === 'array' || schema.type === 'string' && schema.maxLength > 160;
          const input = element(multiline ? 'textarea' : 'input', 'field');
          input.id = label.htmlFor;
          input.dataset.inputField = field;
          input.dataset.schemaType = schema.type;
          if (multiline) { input.rows = 3; input.spellcheck = false; }
          else input.type = schema.type === 'boolean' ? 'checkbox' : schema.type === 'string' ? 'text' : 'number';
          if (schema.minimum !== undefined) input.min = schema.minimum;
          if (schema.maximum !== undefined) input.max = schema.maximum;
          if (schema.maxLength !== undefined) input.maxLength = schema.maxLength;
          if (schema.pattern && !multiline) input.pattern = schema.pattern;
          if (input.type === 'number') input.step = schema.type === 'integer' ? '1' : 'any';
          if (schema.type === 'array') input.setAttribute('aria-description', '输入 JSON 数组');
          input.addEventListener('input', () => input.setCustomValidity(''));
          input.addEventListener('change', () => {
            try {
              const value = schema.type === 'array' ? JSON.parse(input.value) : schema.type === 'boolean' ? input.checked : ['number', 'integer'].includes(schema.type) ? input.valueAsNumber : input.value;
              if (!valid(value, schema)) throw new Error('输入不符合此 Unit 的字段类型、范围或格式');
              input.setCustomValidity('');
              this.send(attachment.id, {[field]: value});
            } catch (error) {
              input.setCustomValidity(error.message);
              input.reportValidity();
            }
          });
          row.append(input);
        }
        card.append(row);
      }
      const output = element('dl', 'unit-values');
      output.dataset.unitValues = '';
      card.append(output);
      this.cards.set(attachment.id, card);
      this.container.append(card);
    }
    this.enableControls();
  }

  note(id, message) {
    const node = this.cards.get(id)?.querySelector('[data-unit-note]');
    if (node) node.textContent = message;
  }

  projected(id, field) {
    const pending = this.pending.get(id)?.get(field);
    return pending ? pending.value : this.states.get(id)?.properties?.[field];
  }

  send(id, values, releaseIntent = null) {
    if (this.disposed || this.session.state !== 'running') return Promise.resolve();
    const revision = ++this.revision;
    const observedSessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    this.inputEpoch += 1;
    const pending = this.pending.get(id) || new Map();
    for (const [field, value] of Object.entries(values)) pending.set(field, {revision, value: copy(value)});
    this.pending.set(id, pending);
    const previous = this.queues.get(id) || Promise.resolve();
    const next = previous.catch(() => {}).then(async () => {
      // Necessary releases may outlive the panel. They only target the session
      // that owned the hold; ordinary queued inputs cannot cross its boundary.
      if (!this.currentSession(observedSessionId, sessionEpoch) && !releaseIntent) return;
      const payload = await this.api(
        `/api/v1/sessions/${encodeURIComponent(observedSessionId)}/unit-input`,
        {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, values})},
      );
      if (this.currentSession(observedSessionId, sessionEpoch)) this.inputEpoch += 1;
      const applied = revision === this.revision && this.apply(payload, observedSessionId, sessionEpoch);
      if (this.currentSession(observedSessionId, sessionEpoch) && releaseIntent && this.releaseIntents.get(releaseIntent.key) === releaseIntent) releaseIntent.uncertain = !applied || !this.confirmRelease(releaseIntent);
    }).catch(error => {
      if (!this.currentSession(observedSessionId, sessionEpoch)) return;
      this.inputEpoch += 1;
      if (releaseIntent && this.releaseIntents.get(releaseIntent.key) === releaseIntent) releaseIntent.uncertain = true;
      this.note(id, `输入未确认：${error.message}`);
    }).finally(() => {
      if (this.currentSession(observedSessionId, sessionEpoch)) this.inputEpoch += 1;
      for (const field of Object.keys(values)) if (pending.get(field)?.revision === revision) pending.delete(field);
    });
    this.queues.set(id, next);
    return next;
  }

  releaseValue(intent) {
    const unit = this.states.get(intent.id);
    if (unit?.available !== true || Object.keys(unit.errors || {}).length) return undefined;
    const value = unit.properties?.[intent.field];
    if (intent.index === undefined) return typeof value === 'boolean' ? value : undefined;
    return Number.isInteger(intent.index) && intent.index >= 0 && Array.isArray(value) && value.every(item => typeof item === 'boolean') && intent.index < value.length ? value[intent.index] : undefined;
  }

  confirmRelease(intent) {
    if (this.releaseIntents.get(intent.key) !== intent || this.releaseValue(intent) !== false) return false;
    this.releaseIntents.delete(intent.key);
    return true;
  }

  recoverReleases(intents) {
    if (this.disposed || this.session.state !== 'running') return;
    const observedSessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    const byId = new Map();
    for (const intent of intents) {
      if (this.releaseIntents.get(intent.key) !== intent || !intent.uncertain || this.pressSources.has(intent.key) || this.confirmRelease(intent)) continue;
      if (this.releaseValue(intent) !== true) continue;
      if (intent.retried) { this.note(intent.id, '松开仍未确认，请重新按下并松开。'); continue; }
      if (intent.queued) continue;
      intent.queued = true;
      if (!byId.has(intent.id)) byId.set(intent.id, []);
      byId.get(intent.id).push(intent);
    }
    for (const [id, releases] of byId) {
      const revision = ++this.revision;
      this.inputEpoch += 1;
      const previous = this.queues.get(id) || Promise.resolve();
      const next = previous.catch(() => {}).then(async () => {
        if (!this.currentSession(observedSessionId, sessionEpoch) || this.session.state !== 'running') return;
        const active = releases.filter(intent => this.releaseIntents.get(intent.key) === intent && !this.pressSources.has(intent.key) && this.releaseValue(intent) === true);
        const values = {};
        for (const intent of active) {
          if (intent.index === undefined) values[intent.field] = false;
          else {
            const value = values[intent.field] ||= [...this.states.get(id).properties[intent.field]];
            for (const released of this.releaseIntents.values()) if (released.id === id && released.field === intent.field && Number.isInteger(released.index) && released.index >= 0 && released.index < value.length && !this.pressSources.has(released.key)) value[released.index] = false;
            for (const held of this.pressSources.values()) if (held.id === id && held.field === intent.field && Number.isInteger(held.index) && held.index >= 0 && held.index < value.length) value[held.index] = true;
          }
        }
        if (!Object.keys(values).length) return;
        for (const intent of active) intent.retried = true;
        const payload = await this.api(`/api/v1/sessions/${encodeURIComponent(observedSessionId)}/unit-input`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, values})});
        if (this.currentSession(observedSessionId, sessionEpoch)) this.inputEpoch += 1;
        if (revision === this.revision && this.apply(payload, observedSessionId, sessionEpoch)) for (const intent of active) this.confirmRelease(intent);
      }).catch(error => { if (this.currentSession(observedSessionId, sessionEpoch)) this.note(id, `松开补偿未确认：${error.message}`); }).finally(() => {
        if (this.currentSession(observedSessionId, sessionEpoch)) this.inputEpoch += 1;
        for (const intent of releases) intent.queued = false;
      });
      this.queues.set(id, next);
    }
  }

  setHeld(id, field, index, source, pressed) {
    const key = JSON.stringify([id, field, index ?? null]);
    const entry = this.pressSources.get(key) || {id, field, index, sources: new Set()};
    const before = entry.sources.size > 0;
    if (pressed) entry.sources.add(source);
    else entry.sources.delete(source);
    const after = entry.sources.size > 0;
    if (after) this.pressSources.set(key, entry);
    else this.pressSources.delete(key);
    if (before === after) return;
    let releaseIntent = null;
    if (after) this.releaseIntents.delete(key);
    else if (!this.disposed && this.session.state === 'running') {
      releaseIntent = {key, id, field, index, uncertain: false, retried: false, queued: false};
      this.releaseIntents.set(key, releaseIntent);
    }
    let value = after;
    if (index !== undefined) {
      const base = this.projected(id, field);
      if (!Array.isArray(base) || index >= base.length || !base.every(item => typeof item === 'boolean')) {
        entry.sources.delete(source);
        this.pressSources.delete(key);
        if (releaseIntent) releaseIntent.uncertain = true;
        this.note(id, '等待控制器提供按键数组状态');
        return;
      }
      value = [...base];
      // A poll started before the previous POST may arrive after its ACK. Keep
      // every locally owned hold when patching another index, even if that
      // authoritative response contains an older released array.
      for (const released of this.releaseIntents.values()) if (released.id === id && released.field === field && Number.isInteger(released.index) && released.index >= 0 && released.index < value.length && !this.pressSources.has(released.key)) value[released.index] = false;
      for (const held of this.pressSources.values()) {
        if (held.id === id && held.field === field && Number.isInteger(held.index) && held.index >= 0 && held.index < value.length) value[held.index] = true;
      }
      value[index] = after;
    }
    const card = this.cards.get(id);
    for (const button of card?.querySelectorAll('[data-press-field]') || []) {
      if (button.dataset.pressField === field && (index === undefined ? button.dataset.pressIndex === undefined : Number(button.dataset.pressIndex) === index)) button.setAttribute('aria-pressed', String(after));
    }
    this.send(id, {[field]: value}, releaseIntent);
  }

  // Compatibility entry point for callers owning a single Unit Button.
  setPressed(id, source, pressed) { this.setHeld(id, 'pressed', undefined, source, pressed); }

  handleInput(event) {
    if (this.disposed || this.session.state !== 'running') return;
    const attachments = [...(this.session.units || [])].sort((a, b) => (this.mounted.get(b.id)?.port.length || 0) - (this.mounted.get(a.id)?.port.length || 0));
    for (const attachment of attachments) {
      const mounted = this.mounted.get(attachment.id);
      if (!mounted || !String(event.id).startsWith(`${mounted.port}/`)) continue;
      const state = this.states.get(attachment.id);
      if (state?.available !== true) return;
      const values = physicalInput(event, attachment, {port: mounted.port, properties: state?.properties, bindings: this.bindingsByUnit[attachment.unit_id]});
      if (!values) continue;
      const source = `shell:${event.source || 'pointer'}`;
      for (const [field, value] of Object.entries(values)) {
        if (typeof value === 'boolean' && field !== 'switch-on') this.setHeld(attachment.id, field, undefined, source, value);
        else if (Array.isArray(value)) {
          const component = event.id.slice(mounted.port.length + 1);
          const index = field === 'keys' ? CARDKB_KEY_IDS.indexOf(component) : Number(/^press-([1-8])$/.exec(component)?.[1]) - 1;
          if (index >= 0) this.setHeld(attachment.id, field, index, source, event.action === 'down');
        } else this.send(attachment.id, {[field]: value});
      }
      return;
    }
  }

  paint(unit) {
    const mounted = this.mounted.get(unit.id);
    if (!mounted) return;
    try { mounted.shell.updateUnitAnnotation?.(unit, {port: mounted.port, definition: this.definitions.get(unit.unit_id), running: this.session.state === 'running', source: this.stateSource, frozenDefinitions: this.frozenDefinitions === true}); }
    catch (error) { this.note(unit.id, `读数显示失败：${error.message}`); }
    try { mounted.shell.applyVisualState(visualCommands(unit, mounted.port, {bindings: this.bindingsByUnit[unit.unit_id], running: this.session.state === 'running'})); }
    catch (error) { this.note(unit.id, `外壳状态更新失败：${error.message}`); }
  }

  observeAudio(payload, observedSessionId = this.session.session_id) {
    if (observedSessionId !== this.session.session_id) return;
    if (Array.isArray(payload?.definitions) && this.audioDefinitionSessionId !== observedSessionId) {
      this.audioDefinitions = new Map(copy(payload.definitions).map(unit => [unit.id, unit]));
      this.audioDefinitionSessionId = observedSessionId;
    }
    const units = new Map((payload?.units || []).map(unit => [unit.id, unit]));
    for (const [id, audio] of this.audio) {
      const attachment = this.session.units?.find(unit => unit.id === id && unit.unit_id === 'buzzer');
      const unit = units.get(id);
      audio.observe(unit?.unit_id === attachment?.unit_id ? unit : null, this.audioDefinitions.get('buzzer'), {
        sessionId: observedSessionId, running: this.session.state === 'running', source: payload?.source,
        frozenDefinitions: this.audioDefinitionSessionId === observedSessionId, attached: Boolean(attachment),
      });
    }
  }

  apply(payload, observedSessionId = this.session.session_id, sessionEpoch = this.sessionEpoch) {
    if (!this.currentSession(observedSessionId, sessionEpoch) || payload.session_id !== undefined && payload.session_id !== observedSessionId) return false;
    this.stateSource = payload.source || 'unavailable';
    if (Array.isArray(payload.definitions) && !this.frozenDefinitions) {
      this.releaseHeld();
      this.definitions = new Map(payload.definitions.map(unit => [unit.id, unit]));
      this.frozenDefinitions = true;
      this.render();
    }
    for (const unit of payload.units || []) {
      this.states.set(unit.id, unit);
      const card = this.cards.get(unit.id);
      if (!card) continue;
      this.note(unit.id, !unit.available ? `状态不完整：${Object.values(unit.errors || {}).join('; ')}` : payload.source === 'persisted' ? '已停止 · 最后模型状态' : '实时模型状态');
      const output = card.querySelector('[data-unit-values]');
      output.replaceChildren();
      for (const [field, value] of Object.entries(unit.properties || {})) {
        const definition = this.definitions.get(unit.unit_id);
        const direction = Object.hasOwn(definition?.inputs || {}, field) ? '输入 fixture' : Object.hasOwn(definition?.outputs || {}, field) ? '固件输出观测' : '控制器状态';
        const label = element('dt', '', field);
        label.append(element('small', 'unit-value-source', direction));
        output.append(label, observedValue(field, value));
        const input = [...card.querySelectorAll('[data-input-field]')].find(node => node.dataset.inputField === field);
        if (input && document.activeElement !== input) {
          if (input.type === 'checkbox') input.checked = value === true;
          else input.value = input.dataset.schemaType === 'array' ? JSON.stringify(value) : value;
        }
      }
      this.paint(unit);
    }
    if (observedSessionId === this.session.session_id) {
      this.audioPayload = payload;
      this.observeAudio(payload, observedSessionId);
    }
    this.enableControls();
    if (this.remountOnObservation) {
      this.remountOnObservation = false;
      void this.setShell(this.shell);
    }
    return true;
  }

  schedule() {
    clearTimeout(this.timer);
    if (!this.disposed && ACTIVE.has(this.session.state)) this.timer = setTimeout(() => this.refresh(), document.hidden ? 2000 : 500);
  }

  async refresh() {
    clearTimeout(this.timer);
    if (this.disposed || this.refreshing || !(this.session.units || []).length) return;
    const observedSessionId = this.session.session_id;
    const sessionEpoch = this.sessionEpoch;
    const inputEpoch = this.inputEpoch;
    const request = this.refreshing = {};
    const current = () => this.currentSession(observedSessionId, sessionEpoch) && inputEpoch === this.inputEpoch;
    // Only a GET started after uncertainty can confirm/retry that release.
    const recoverable = [...this.releaseIntents.values()].filter(intent => intent.uncertain);
    try {
      const payload = await this.api(`/api/v1/sessions/${encodeURIComponent(observedSessionId)}/units`);
      if (current() && this.apply(payload, observedSessionId, sessionEpoch)) this.recoverReleases(recoverable);
    } catch (error) {
      if (!current()) return;
      this.audioPayload = null;
      this.observeAudio(null, observedSessionId);
      for (const [id, unit] of this.states) {
        const unavailable = {...unit, available: false, errors: {...unit.errors, transport: error.message}};
        this.states.set(id, unavailable);
        this.paint(unavailable);
        this.note(id, `状态请求失败：${error.message}`);
      }
      this.enableControls();
    } finally {
      if (this.refreshing === request) {
        this.refreshing = null;
        this.schedule();
      }
    }
  }

  releaseHeld(prefix = '', id, field, index) {
    for (const entry of [...this.pressSources.values()]) {
      if (id !== undefined && (entry.id !== id || entry.field !== field || entry.index !== index)) continue;
      for (const source of [...entry.sources]) if (source.startsWith(prefix)) this.setHeld(entry.id, entry.field, entry.index, source, false);
    }
  }

  dispose() {
    if (this.disposed) return;
    this.releaseHeld();
    this.disposed = true;
    for (const audio of this.audio.values()) audio.dispose();
    this.audio.clear();
    this.releaseIntents.clear();
    this.generation += 1;
    clearTimeout(this.timer);
    window.removeEventListener('blur', this.release);
    const previous = [...this.mounted.values(), ...this.attaching.values()];
    this.mounted.clear();
    this.attaching.clear();
    previous.sort((a, b) => b.port.length - a.port.length).forEach(item => this.safeDetach(item));
    this.shell = null;
    this.container.replaceChildren();
  }
}

export async function createUnitPanel(container, options) { return new UnitPanel(container, options).init(); }

export async function createUnitPicker(container, {api, deviceId}) {
  const picker = {
    generation: 0,
    deviceId: null,
    readyDeviceId: null,
    loadError: '',
    selections: [],
    async loadDevice(id) {
      const generation = ++this.generation;
      this.deviceId = id;
      this.readyDeviceId = null;
      this.loadError = '';
      this.selections = [];
      container.textContent = '正在读取 Unit 支持情况…';
      try {
        const inventory = await api(`/api/v1/units?device_id=${encodeURIComponent(id)}`);
        if (generation !== this.generation) return;
        const host = inventory.hosts.find(host => host.device_id === id);
        const ports = host?.ports.filter(port => port.wiring_status === 'confirmed' && port.physical_presence === 'main-device') || [];
        container.replaceChildren(element('label', 'field-label', '连接 Unit'));
        const ready = unit => ['implemented', 'validated'].includes(unit.runtime?.status) && unit.runtime.hosts?.includes(id);
        const makeSelect = (label, i2cOnly = false) => {
          const select = element('select', 'field');
          select.setAttribute('aria-label', label);
          select.append(new Option('不连接 Unit', ''));
          for (const unit of inventory.units) {
            if (i2cOnly && unit.interface.bus !== 'i2c') continue;
            const enabled = ready(unit);
            const option = new Option(`${unit.name}${enabled ? '' : '（暂未支持）'}`, unit.id);
            option.disabled = !enabled;
            select.append(option);
          }
          return select;
        };
        for (const [index, port] of ports.entries()) {
          const row = element('div', 'unit-picker-port');
          row.append(element('label', 'field-label', port.label));
          const select = makeSelect(`Unit · ${port.label}`);
          if (index === 0) select.id = 'unitModelSelect';
          const children = element('div', 'unit-hub-children');
          children.hidden = true;
          const childSelects = Array.from({length: 3}, (_, slot) => {
            const label = `HUB · Grove ${slot + 1}`;
            const child = makeSelect(label, true);
            const labelNode = element('label', 'field-label', label);
            labelNode.append(child);
            children.append(labelNode);
            child.addEventListener('change', () => update());
            return child;
          });
          children.append(element('p', 'unit-note', 'HUB 的三个接口共享 I2C 总线；相同地址的设备不能同时连接。'));
          const update = () => {
            children.hidden = select.value !== 'hub';
            const instance = `external${index + 1}`;
            this.selections[index] = select.value ? [
              {id: instance, unit_id: select.value, port_id: port.id},
              ...(select.value === 'hub' ? childSelects.flatMap((child, slot) => child.value ? [{id: `${instance}-${slot + 1}`, parent_id: instance, unit_id: child.value, port_id: `grove-${slot + 1}`}] : []) : []),
            ] : [];
          };
          select.addEventListener('change', update);
          row.append(select, children);
          container.append(row);
        }
        if (!ports.length) container.append(element('p', 'unit-note', '此设备暂无已确认接线的主机接口。'));
        this.readyDeviceId = id;
      } catch (error) {
        if (generation === this.generation) {
          this.loadError = error.message;
          container.textContent = `Unit 目录读取失败：${error.message}`;
        }
      }
    },
    attachments(deviceId) {
      if (deviceId !== undefined && (deviceId !== this.deviceId || deviceId !== this.readyDeviceId)) {
        throw new Error('Unit 配置与当前设备不匹配，请等待当前设备的配置加载完成。');
      }
      return copy(this.selections.flat());
    },
    dispose() { this.generation += 1; this.readyDeviceId = null; this.selections = []; container.replaceChildren(); },
  };
  await picker.loadDevice(deviceId);
  return picker;
}
