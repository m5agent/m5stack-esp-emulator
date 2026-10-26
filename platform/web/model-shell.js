import { DeviceViewer } from './vendor/m5stack-models/src/core/DeviceViewer.js';
import {UnitAnnotations} from './unit-annotations.js';
import {layoutHubAttachments} from './unit-assembly-layout.js';
import { loadModel, loadGroveModule } from './vendor/m5stack-models/src/loaders.js';
import { MODEL_METADATA, MODEL_DEVICES, UNIT_MODELS } from './vendor/m5stack-models/runtime-index.js';

export { MODEL_METADATA, MODEL_DEVICES, UNIT_MODELS };

// These are runtime key names, not arbitrary label-based guesses. Unmapped
// mechanical controls remain observable as model-input and never reach /input.
const CONTROL_MAPS = {
  sticks3: { btnA: 'a', btnB: 'b', btnPWR: 'power' },
  cores3: { power: 'power' },
  stopwatch: { a: 'a', b: 'b', power: 'power' },
  core2: { a: 'a', b: 'b', c: 'c', power: 'power' },
  stackchan: { power: 'power' },
  papermono: { key1: 'key1', key2: 'key2', power: 'power' },
  papercolor: { key1: 'key1', key2: 'key2', key3: 'key3', power: 'power' },
  nanoc6: { button: 'button' },
  atoms3r: { button: 'button' },
  stamplc: { a: 'key1', b: 'key2', c: 'key3' },
};

const RUNTIME_KEYS = { power: 'p', key1: 'a', key2: 'b', key3: 'c', button: 'a' };

const QCODE = {
  Enter: 'ret', Space: 'spc', Escape: 'esc', Backspace: 'backspace', Tab: 'tab',
  ShiftLeft: 'shift', ShiftRight: 'shift_r', ControlLeft: 'ctrl', ControlRight: 'ctrl_r',
  AltLeft: 'alt', AltRight: 'alt_r', CapsLock: 'caps_lock', ArrowUp: 'up', ArrowDown: 'down',
  ArrowLeft: 'left', ArrowRight: 'right', Minus: 'minus', Equal: 'equal',
  BracketLeft: 'bracket_left', BracketRight: 'bracket_right', Backslash: 'backslash',
  Semicolon: 'semicolon', Quote: 'apostrophe', Backquote: 'grave_accent',
  Comma: 'comma', Period: 'dot', Slash: 'slash', Delete: 'delete',
};

export function keyboardQcode(id) {
  const code = id.startsWith('key-') ? id.slice(4) : id;
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-2])$/.test(code)) return code.toLowerCase();
  return QCODE[code] || null;
}

export function supportsModelShell(deviceOrId) {
  return MODEL_DEVICES.includes(typeof deviceOrId === 'string' ? deviceOrId : deviceOrId?.id);
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

export class ModelDeviceShell {
  static async create(host, device, options = {}) {
    const model = await loadModel(device.id, { pixelEffect: true, ...options.modelOptions });
    try {
      return new ModelDeviceShell(host, device, model, options);
    } catch (error) {
      model.dispose();
      throw error;
    }
  }

  constructor(host, device, model, { live = false } = {}) {
    this.host = host;
    this.device = device;
    this.model = model;
    this.listeners = new Map();
    this.attachVersions = new Map();
    this.driveActivities = new Map();
    this.frameSeq = 0;
    this.disposed = false;
    this.feedbackDepth = 0;
    this.root = node('div', 'device-shell-root three-device-root');
    this.root.dataset.device = device.id;
    // Keep existing renderer IDs for integrations querying StickS3/CoreS3.
    this.root.dataset.renderer = `${device.id}-three`;
    this.root.dataset.modelSource = 'm5stack-models';
    this.photoRoot = node('div', 'device-photo-root three-device-photo-root');
    if (!live && device.shell?.reference_image) {
      const photo = node('img', 'device-photo');
      photo.src = device.shell.reference_image;
      photo.alt = `${device.name} 官方实物图`;
      this.photoRoot.append(photo);
    }
    this.stage = node('div', 'three-device-stage');
    this.hint = node('div', 'three-device-hint', '拖拽旋转 · 滚轮缩放 · 双击复位 · 聚焦模型后使用按键');
    this.overlay = node('div', 'three-device-overlay');
    const card = node('div', 'three-device-overlay-card');
    this.overlayTitle = node('b');
    this.overlayBody = node('span');
    card.append(this.overlayTitle, this.overlayBody);
    this.overlay.append(card);
    this.overlay.hidden = true;
    this.root.append(this.photoRoot, this.stage, this.overlay, this.hint);
    host.replaceChildren(this.root);

    try {
      this.viewer = new DeviceViewer(this.stage, {
        keyboard: 'focused', background: null, fov: 25,
        minDistance: 25, maxDistance: 2500,
      });
      this.viewer.mount(model);
      this.unitAnnotations = new UnitAnnotations({container: this.stage, root: this.root, viewer: this.viewer, model});
      this.installButtonFeedback(model);
      this.display = model.find('lcd', 'display');
      // No demo or made-up sensor/frame values. Wait for the real runtime.
      if (this.display) this.display.fill('#000000');
      this.offInput = model.on('input', event => this.handleInput(event));
      this.viewer.setView('front', { duration: 0 });
      this.viewer.fit({ padding: 1.15, duration: 0 });
      this.setViewMode(!live && device.shell?.reference_image ? 'photo' : 'shell');
    } catch (error) {
      this.unitAnnotations?.dispose();
      this.viewer?.dispose();
      this.root.remove();
      throw error;
    }
  }

  on(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(callback);
    return this;
  }

  off(type, callback) { this.listeners.get(type)?.delete(callback); }

  emit(type, event) {
    for (const callback of this.listeners.get(type) || []) callback(event);
  }

  handleInput(event) {
    if (this.feedbackDepth || this.disposed || event.source === 'runtime-readback') return;
    this.emit('model-input', event);
    if (event.id.includes('/')) {
      this.emit('unit-input', event);
      return;
    }
    if (event.kind === 'display') {
      this.emit('touch', { ...event, x: event.x, y: event.y, down: event.action !== 'end' });
      return;
    }
    if (event.kind !== 'button' || !['down', 'up'].includes(event.action)) return;
    const component = this.model.find(event.id, 'button');
    if (component?.meta?.electricalBehavior === false) return;
    if (this.device.id === 'tab5' && event.id === 'reset') {
      if (event.action === 'down') this.emit('reset', event);
      return;
    }
    let id = CONTROL_MAPS[this.device.id]?.[event.id];
    if (['cardputer-adv', 'cardputer-zero'].includes(this.device.id) && event.id.startsWith('key-')) {
      id = keyboardQcode(event.id);
    }
    if (!id) return;
    const gpio = /^G(\d+)$/.exec(component?.meta?.gpio || '');
    this.emit('control', { id, key: RUNTIME_KEYS[id] || id, gpio: gpio ? Number(gpio[1]) : null, down: event.action === 'down', source: event.source });
  }

  setViewMode(mode) {
    this.viewMode = mode;
    this.photoRoot.hidden = mode !== 'photo';
    this.stage.hidden = mode === 'photo';
    this.hint.hidden = mode === 'photo';
    if (mode === 'shell') requestAnimationFrame(() => {
      if (this.disposed) return;
      this.viewer.resize();
      this.viewer.fit({ padding: 1.15, duration: 0 });
    });
  }

  showOverlay(title, detail = '') {
    this.overlayTitle.textContent = title;
    this.overlayBody.textContent = detail;
    this.overlay.hidden = false;
  }

  hideOverlay() { this.overlay.hidden = true; }

  installButtonFeedback(host) {
    // Button's public press sources aggregate visual holds. Feeding backend
    // readback into that same aggregate would swallow a user's final release.
    // Keep input ownership separately and use the original public methods only
    // for mechanical motion. No private fields or geometry assumptions change.
    for (const button of host.list('button')) {
      if (button.runtimeFeedbackInstalled) continue;
      button.runtimeFeedbackInstalled = true;
      const press = button.press.bind(button), release = button.release.bind(button);
      const input = button.input.bind(button), dispose = button.dispose.bind(button);
      const sources = new Set();
      let downAt = 0, cancelled = false, timer = null;
      // The original methods may emit delayed longpress/click events. Only the
      // independently owned user intent below is allowed onto the runtime bus.
      button.input = (action, payload = {}) => ({ kind: 'button', id: button.path, action, time: performance.now(), ...payload });
      button.press = (source = 'sim') => {
        if (source === 'runtime-readback') { press(source); return; }
        const wasDown = sources.size > 0;
        sources.add(source);
        press(source);
        if (wasDown) return;
        downAt = performance.now(); cancelled = false;
        input('down', { source });
        clearTimeout(timer);
        if (button.longPressMs > 0) timer = setTimeout(() => {
          if (sources.size) input('longpress', { source });
        }, button.longPressMs);
      };
      button.release = (source = 'sim', options = {}) => {
        if (source === 'runtime-readback') { release(source, options); return; }
        if (options.cancelled && sources.has(source)) cancelled = true;
        const held = sources.delete(source);
        release(source, options);
        if (!held || sources.size) return;
        clearTimeout(timer);
        const duration = performance.now() - downAt;
        input('up', { source, duration, ...(cancelled ? { cancelled: true } : {}) });
        if (!cancelled && (duration < button.longPressMs || button.longPressMs <= 0)) input('click', { source, duration });
      };
      button.cancel = (source = 'sim') => button.release(source, { cancelled: true });
      button.dispose = () => {
        for (const source of [...sources]) button.cancel(source);
        clearTimeout(timer);
        dispose();
      };
    }
  }

  setFrame(pixels, width, height, sequence = this.frameSeq + 1) {
    if (!this.display || this.disposed) return false;
    const rotated = this.display.meta.nativeRasterRotation === 90 && width === this.display.height && height === this.display.width;
    if (!rotated && (width !== this.display.width || height !== this.display.height)) {
      this.showOverlay('Framebuffer mismatch', `收到 ${width}×${height}，面板为 ${this.display.width}×${this.display.height}`);
      return false;
    }
    let bytes = pixels instanceof Uint8Array ? pixels : new Uint8Array(pixels);
    if (bytes.byteLength !== width * height * 2) throw new RangeError('RGB565 framebuffer size mismatch');
    if (rotated) {
      const source = bytes;
      bytes = new Uint8Array(source.length);
      for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        const from = (y * width + x) * 2;
        const to = (x * this.display.width + this.display.width - 1 - y) * 2;
        bytes[to] = source[from]; bytes[to + 1] = source[from + 1];
      }
    }
    this.display.writeRGB565(bytes, { x: 0, y: 0, w: this.display.width, h: this.display.height }, { swapBytes: true });
    this.frameSeq = sequence;
    this.hideOverlay();
    return true;
  }

  async setImage(image, sequence = this.frameSeq + 1, commitGuard = () => true) {
    if (!this.display || this.disposed || !commitGuard()) return false;
    const bitmap = await createImageBitmap(image);
    try {
      if (this.disposed || !commitGuard()) return false;
      const rotated = this.display.meta.nativeRasterRotation === 90 && bitmap.width === this.display.height && bitmap.height === this.display.width;
      if (!rotated && (bitmap.width !== this.display.width || bitmap.height !== this.display.height)) {
        this.showOverlay('Framebuffer mismatch', `收到 ${bitmap.width}×${bitmap.height}，面板为 ${this.display.width}×${this.display.height}`);
        return false;
      }
      const context = this.display.getContext2D();
      context.clearRect(0, 0, this.display.width, this.display.height);
      context.save();
      if (rotated) { context.translate(this.display.width, 0); context.rotate(Math.PI / 2); }
      context.drawImage(bitmap, 0, 0);
      context.restore();
      this.display.present();
      this.frameSeq = sequence;
      this.hideOverlay();
      return true;
    } finally { bitmap.close(); }
  }

  // Output-only commands must not echo back as runtime input. Caller owns the
  // mapping from controller/device-state evidence to these visual components.
  applyVisualState(commands) {
    if (this.disposed) return [];
    this.feedbackDepth++;
    try {
      return (Array.isArray(commands) ? commands : [commands]).map(command => {
        if (!command || !['led', 'joint', 'display', 'vibrate', 'position', 'button-state', 'drive-activity'].includes(command.type)) {
          throw new TypeError('Expected an output-only visual command');
        }
        if (command.type === 'drive-activity') {
          if (typeof command.active !== 'boolean' || !String(command.target).endsWith('/rotor')) throw new TypeError('Expected a fan drive activity command');
          const joint = this.model.find(command.target, 'joint');
          if (!joint?.continuous) throw new TypeError('Fan rotor joint is unavailable');
          let activity = this.driveActivities.get(command.target);
          if (!activity) {
            activity = {joint, update: joint.update, active: false, angle: joint.getState().angleDeg};
            this.driveActivities.set(command.target, activity);
            joint.update = (dt = 0) => {
              if (!activity.active) return activity.update.call(joint, dt);
              if (!Number.isFinite(dt) || dt < 0) return activity.update.call(joint, dt);
              // A fixed graphical cadence communicates electrical activity.
              // It is deliberately independent of duty/frequency and is never
              // written to the joint's RPM state or claimed as shaft speed.
              activity.angle = (activity.angle + Math.max(0, Math.min(dt, 0.25)) * 180) % 360;
              joint.setAngle(activity.angle);
              return true;
            };
          }
          activity.active = command.active;
          joint.requestRender();
          return {active: activity.active, semantics: 'drive-activity-only; shaft-speed-unmodeled'};
        }
        if (command.type === 'position') {
          return this.model.button(command.target).setPosition(command.position);
        }
        if (command.type === 'button-state') {
          const button = this.model.button(command.target);
          if (button.latching) throw new TypeError('Latching switches use position output');
          if (typeof command.pressed !== 'boolean') throw new TypeError('pressed must be boolean');
          if (command.pressed) button.press('runtime-readback');
          else button.cancel('runtime-readback');
          return button.getState();
        }
        return this.model.handle(command);
      });
    } finally { this.feedbackDepth--; }
  }

  setDeviceState(payload) {
    this.deviceState = payload;
    if (payload?.available && Array.isArray(payload.visual_commands)) this.applyVisualState(payload.visual_commands);
    this.emit('device-state', payload);
  }

  setLed(color) {
    const target = this.model.list('led').find(component => !component.path.includes('/'));
    if (color && target) this.applyVisualState({ type: 'led', target: target.path, color, on: true });
  }

  listPorts() {
    return this.model.list('port').filter(port => port.connector === 'grove').map(port => ({
      id: port.path, label: port.label, connector: port.connector,
      pins: port.pins, attached: port.module?.meta.id || null,
    }));
  }

  updateUnitAnnotation(unit, {port, definition, running, source, frozenDefinitions}) {
    this.unitAnnotations?.set(port, unit, definition, {running, source, frozenDefinitions});
  }

  clearDriveActivities(port = null) {
    for (const [target, activity] of this.driveActivities) {
      if (port !== null && !target.startsWith(`${port}/`)) continue;
      activity.active = false;
      activity.joint.update = activity.update;
      this.driveActivities.delete(target);
    }
  }

  updateUnitAssemblyLayout() {
    // Layout is optional presentation. A failed bounds/snapshot/restore must
    // never turn a successful Port attachment into disposal or lost ownership.
    try { this.unitAssemblyLayout = layoutHubAttachments(this.model); }
    catch (error) {
      this.unitAssemblyLayout = [{policy: 'direct-hub-full-size-row', status: 'unavailable', reason: error.message}];
    }
    return this.unitAssemblyLayout;
  }

  async attachUnit(unitId, { port = 'grove', ...options } = {}) {
    if (!UNIT_MODELS.includes(unitId)) throw new Error(`Unknown visual Unit: ${unitId}`);
    if (this.disposed) throw new Error('Shell is disposed');
    const target = this.model.port(port);
    if (target.connector !== 'grove') throw new Error(`Port ${port} is not Grove`);
    const version = (this.attachVersions.get(port) || 0) + 1;
    this.attachVersions.set(port, version);
    const module = await loadGroveModule(unitId, options);
    if (this.disposed || this.attachVersions.get(port) !== version || this.model.find(port) !== target) {
      module.dispose();
      return null;
    }
    try {
      this.clearDriveActivities(port);
      this.unitAnnotations?.clear(port);
      target.attach(module);
      this.installButtonFeedback(module);
      this.updateUnitAssemblyLayout();
      this.viewer.fit();
      return module;
    } catch (error) { module.dispose(); throw error; }
  }

  detachUnit(port = 'grove') {
    this.attachVersions.set(port, (this.attachVersions.get(port) || 0) + 1);
    this.clearDriveActivities(port);
    this.unitAnnotations?.clear(port);
    const result = this.model.port(port).detach();
    this.updateUnitAssemblyLayout();
    this.viewer.fit();
    return result;
  }

  frameDataUrl() { return this.viewer.screenshot(); }

  dispose() {
    if (this.disposed) return;
    // Viewer cancellation emits matching releases before removing subscriptions.
    this.unitAnnotations?.dispose();
    this.viewer.dispose();
    this.disposed = true;
    this.clearDriveActivities();
    this.offInput?.();
    this.model.dispose();
    this.listeners.clear();
    this.root.remove();
  }
}

export const createModelShell = (host, device, options) => ModelDeviceShell.create(host, device, options);
