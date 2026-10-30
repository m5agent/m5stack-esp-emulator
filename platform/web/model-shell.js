import { DeviceViewer } from './vendor/m5stack-models/src/core/DeviceViewer.js';
import * as THREE from 'three';
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
  atoms3: { button: 'button' },
  'atoms3-lite': { button: 'button' },
  'atom-lite': {button:'button'},
  'atom-matrix': {button:'button'},
  'atom-matrix-v11': {button:'button'},
  'stickc-plus': {a:'a',b:'b',power:'power'},
  'stickc-plus2': { a: 'a', b: 'b', power: 'power' },
  stickc: { a: 'a', b: 'b', power: 'power' },
  'stickc-plus-se': { a: 'a', b: 'b', power: 'power' },
  dial: { wake: 'a' },
  atoms3r: { button: 'button' },
  stamplc: { a: 'key1', b: 'key2', c: 'key3' },
};

const RUNTIME_KEYS = { power: 'p', key1: 'a', key2: 'b', key3: 'c', button: 'a' };

// These two upstream Component-based indicators reject color changes instead
// of exposing Led.fixedColor. Their pinned source permits on/brightness only.
const FIXED_BLUE_STATUS_HOSTS = new Set(['m5stack.unit.timercamera-f', 'm5stack.unit.timercamera-f.grove',
  'm5stack.unit.timercamera-x', 'm5stack.unit.timercamera-x.grove']);
const fixedColorIndicator = led => led.fixedColor !== undefined || led.meta.fixedColor !== undefined
  || [led.meta.colorMode, led.meta.color].some(value => String(value || '').startsWith('fixed-'))
  || (led.id === 'status' && FIXED_BLUE_STATUS_HOSTS.has(led.host?.meta?.id));

const QCODE = {
  Enter: 'ret', Space: 'spc', Escape: 'esc', Backspace: 'backspace', Tab: 'tab',
  ShiftLeft: 'shift', ShiftRight: 'shift_r', ControlLeft: 'ctrl', ControlRight: 'ctrl_r',
  AltLeft: 'alt', AltRight: 'alt_r', CapsLock: 'caps_lock', ArrowUp: 'up', ArrowDown: 'down',
  ArrowLeft: 'left', ArrowRight: 'right', Minus: 'minus', Equal: 'equal',
  BracketLeft: 'bracket_left', BracketRight: 'bracket_right', Backslash: 'backslash',
  Semicolon: 'semicolon', Quote: 'apostrophe', Backquote: 'grave_accent',
  Comma: 'comma', Period: 'dot', Slash: 'slash', Delete: 'delete',
};

// The model's component IDs name physical key positions. PC keys with a
// different name still need a focused route to those same switches.
const CARDPUTER_PC_KEYMAP = {
  ShiftLeft: 'key-CapsLock', ShiftRight: 'key-CapsLock',
  AltLeft: 'key-AltRight', AltRight: 'key-AltRight',
  Backquote: 'key-Escape',
};
const CARDPUTER_PC_QCODE = {
  'key:Backquote': 'grave_accent',
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
    const model = await loadModel(device.id, { pixelEffect: true, ...options.modelOptions,
      ...(device.id === 'cardputer-adv' ? {keymap: {...CARDPUTER_PC_KEYMAP, ...options.modelOptions?.keymap}} : {}),
    });
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
      this.installAssemblyCamera();
      this.viewer.mount(model);
      this.unitAnnotations = new UnitAnnotations({container: this.stage, root: this.root, viewer: this.viewer, model});
      this.installButtonFeedback(model);
      this.display = model.find('lcd', 'display');
      // No demo or made-up sensor/frame values. Wait for the real runtime.
      if (this.display) this.display.fill('#000000');
      if (['atoms3-lite','atom-lite','atom-matrix','atom-matrix-v11'].includes(device.id))
        this.applyVisualState(this.model.list('led').map(led=>({type:'led',target:led.id,known:false})));
      this.offInput = model.on('input', event => this.handleInput(event));
      this.viewer.setView('front', { duration: 0 });
      this.viewer.fit({ padding: 1.15, duration: 0 });
      this.setViewMode(!live && device.shell?.reference_image ? 'photo' : 'shell');
    } catch (error) {
      this.cancelCameraAnimation();
      this.unitAnnotations?.dispose();
      this.viewer?.dispose();
      this.root.remove();
      throw error;
    }
  }

  installAssemblyCamera() {
    const viewer = this.viewer, resize = viewer.resize.bind(viewer);
    this.cameraPadding = 1.15;
    // Reuse the viewer's existing ResizeObserver. Only viewport changes and
    // explicit assembly fits alter framing; frame/state readback never does.
    viewer.fit = options => this.fitAssembly(options);
    viewer.resize = () => {
      const width = this.stage.clientWidth, height = this.stage.clientHeight;
      const previous = this.assemblyCameraFrame(this.cameraPadding, viewer.camera.aspect);
      const ratio = previous ? viewer.distance / previous.distance : 1;
      const offset = previous ? viewer.target.clone().sub(previous.target) : new THREE.Vector3();
      const aspect = viewer.camera.aspect;
      resize();
      if (!width || !height || Math.abs(viewer.camera.aspect - aspect) < 1e-9) return;
      const next = this.assemblyCameraFrame(this.cameraPadding);
      if (!next) return;
      // Orbit belongs to the model quaternion. Keep that orientation, the
      // user's zoom relative to fit, and their pan offset across FOV changes.
      this.applyAssemblyCamera(next.target.add(offset), next.distance * ratio);
    };
  }

  cancelCameraAnimation() {
    this.cameraAnimation?.();
    this.cameraAnimation = null;
  }

  assemblyCameraFrame(padding = this.cameraPadding, aspect = this.viewer.camera.aspect) {
    const viewer = this.viewer, bounds = new THREE.Box3();
    for (const device of viewer.devices) bounds.expandByObject(device.root);
    if (bounds.isEmpty()) return null;
    const size = bounds.getSize(new THREE.Vector3());
    const vertical = Math.tan(THREE.MathUtils.degToRad(viewer.camera.fov) / 2);
    const horizontal = vertical * aspect;
    // Fit the entire host/Unit/cable world envelope in both axes, measured
    // from its nearest face. A center-only/sphere estimate can crop deep Units.
    const distance = size.z / 2 + Math.max(size.x * padding / (2 * horizontal), size.y * padding / (2 * vertical));
    return {target: bounds.getCenter(new THREE.Vector3()),
      distance: THREE.MathUtils.clamp(distance, viewer.opts.minDistance, viewer.opts.maxDistance)};
  }

  applyAssemblyCamera(target, distance) {
    const viewer = this.viewer;
    viewer.target.copy(target);
    viewer.distance = THREE.MathUtils.clamp(distance, viewer.opts.minDistance, viewer.opts.maxDistance);
    viewer.camera.position.set(target.x, target.y, target.z + viewer.distance);
    viewer.camera.lookAt(target);
    viewer.camera.near = Math.max(0.5, viewer.distance * 0.05);
    viewer.camera.far = viewer.distance + 2000;
    viewer.camera.updateProjectionMatrix();
    viewer.requestRender();
  }

  fitAssembly({padding = 1.15, duration = 0} = {}) {
    this.cameraPadding = padding;
    this.cancelCameraAnimation();
    const fit = this.assemblyCameraFrame(padding);
    if (!fit) return;
    if (!duration) {this.applyAssemblyCamera(fit.target, fit.distance); return;}
    const target = this.viewer.target.clone(), distance = this.viewer.distance;
    let elapsed = 0;
    this.cameraAnimation = this.viewer.on('render', dt => {
      if (this.disposed) {this.cancelCameraAnimation(); return;}
      // Use the public render delta, after the viewer's rotation tweens have
      // advanced. Its capped clock survives background/CPU RAF stalls; a
      // performance.now() clock can finish fit while rotation is still pending.
      elapsed += dt * 1000;
      const progress = Math.min(1, elapsed / duration);
      const eased = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
      // resetView animates the model orientation concurrently. Recompute the
      // envelope so the final fit belongs to its final pose, not the old pose.
      const current = this.assemblyCameraFrame(padding);
      if (!current) {this.cancelCameraAnimation(); return;}
      this.applyAssemblyCamera(target.clone().lerp(current.target, eased), distance + (current.distance - distance) * eased);
      if (progress === 1) this.cancelCameraAnimation();
    });
    this.viewer.requestRender();
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
    // Standalone catalog previews have no guest or electrical input route.
    if (this.device.visual_only) return;
    if (event.id.includes('/')) {
      this.emit('unit-input', event);
      return;
    }
    if (event.kind === 'display') {
      this.emit('touch', { ...event, x: event.x, y: event.y, down: event.action !== 'end' });
      return;
    }
    if (this.device.id === 'dial' && event.kind === 'joint' && event.id === 'rotation' && event.action === 'rotate') {
      const ring = this.model.find(event.id, 'joint');
      if (ring?.meta?.role === 'visual-rotary-input' && ring.meta.detentsPerTurn === 16
        && Number.isFinite(event.deltaDeg) && Math.abs(event.deltaDeg) <= 180)
        this.emit('encoder', {deltaDegrees:event.deltaDeg, source:event.source});
      return;
    }
    if (event.kind !== 'button' || !['down', 'up'].includes(event.action)) return;
    const component = this.model.find(event.id, 'button');
    if (component?.meta?.electricalBehavior === false) return;
    if (event.id === 'reset') {
      if (event.action === 'down') this.emit('reset', event);
      return;
    }
    if (this.device.id === 'stackchan' && /^touch-[123]$/.test(event.id)) {
      this.emit('capacitive-touch', {zone:Number(event.id.slice(-1)), down:event.action === 'down', source:event.source});
      return;
    }
    let id = CONTROL_MAPS[this.device.id]?.[event.id];
    if (['cardputer-adv', 'cardputer-zero'].includes(this.device.id) && event.id.startsWith('key-')) {
      id = keyboardQcode(event.id);
      if(this.device.id==='cardputer-adv'){
        // The imported model names differ from the original ADV matrix.
        // Route these physical positions to their actual SDK keys. COMPOSE
        // carries physical Fn through QAPI to this board's TCA8418 only.
        id=({'key-Fn':'compose','key-CapsLock':'shift','key-AltLeft':'meta_l','key-AltRight':'alt'})[event.id]||id;
        id=CARDPUTER_PC_QCODE[event.source]||id;
        // The top-left model key is physically grave/Fn-Escape. Keep a PC
        // Escape key logical, while a model press follows the real matrix.
        if(event.id==='key-Escape'&&event.source!=='key:Escape')id='grave_accent';
        // Model buttons aggregate simultaneous pointer/keyboard holds. The
        // final release may come from another source; retain the first code.
        this.keyEdgeQcodes??=new Map();
        if(event.action==='down')this.keyEdgeQcodes.set(event.id,id);
        else {id=this.keyEdgeQcodes.get(event.id)||id;this.keyEdgeQcodes.delete(event.id);}
      }
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

  pauseRendering() {
    this.viewer.pauseRendering();
  }

  resumeRendering() {
    this.viewer.resumeRendering();
  }

  focusInput() {
    return this.viewer.focusInput();
  }

  setDeviceRotation(degrees = 0) {
    const value = Number(degrees);
    if (!Number.isFinite(value)) throw new TypeError('Device presentation rotation must be finite');
    const normalized = ((value % 360) + 360) % 360;
    if (this.presentationRotationDeg === normalized) return false;
    this.presentationRotationDeg = normalized;
    for (const device of this.viewer.devices) {
      if (device.root) device.root.rotation.z = THREE.MathUtils.degToRad(normalized);
    }
    this.viewer.requestRender();
    this.fitAssembly({padding:1.15,duration:0});
    return true;
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
        const payload = { source };
        // Preserve the actuator's post-toggle detent without assigning an
        // electrical on/off meaning. That mapping still needs a binding.
        if (button.isLatching) {
          const position = button.getState().position;
          if (position === 0 || position === 1) payload.position = position;
        }
        input('down', payload);
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

  setFrame(pixels, width, height, sequence = this.frameSeq + 1, {byteOrder = 'big'} = {}) {
    if (!this.display || this.disposed) return false;
    if (!['big', 'little'].includes(byteOrder)) throw new TypeError('Unknown RGB565 byte order');
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
    this.display.writeRGB565(bytes, { x: 0, y: 0, w: this.display.width, h: this.display.height }, { swapBytes: byteOrder === 'big' });
    this.frameSeq = sequence;
    this.hideOverlay();
    return true;
  }

  setFrameLE(pixels, width, height, sequence = this.frameSeq + 1) {
    return this.setFrame(pixels, width, height, sequence, {byteOrder: 'little'});
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
        if (command.type === 'joint') {
          if (command.known !== undefined && typeof command.known !== 'boolean') throw new TypeError('Joint known must be boolean');
          const joint=this.model.find(command.target,'joint');
          if (!joint) throw new TypeError('Joint component is unavailable');
          // Unknown output preserves the last observed pose; it is not a home command.
          const result=command.known===false?joint.getState():this.model.handle(command);
          joint.runtimeKnown=joint.object3d.userData.runtimeKnown=command.known!==false;
          return result;
        }
        if (command.type === 'led') {
          if (command.known !== undefined && typeof command.known !== 'boolean') throw new TypeError('LED known must be boolean');
          const led = this.model.find(command.target, 'led');
          if (!led) throw new TypeError('LED component is unavailable');
          if (command.known !== false) {
            if (command.brightness !== undefined && !Number.isFinite(command.brightness)) throw new TypeError('LED brightness must be finite');
            if (command.on !== undefined && typeof command.on !== 'boolean') throw new TypeError('LED on must be boolean');
            if (command.color !== undefined) {
              if (typeof command.color === 'number' && (!Number.isInteger(command.color) || command.color < 0 || command.color > 0xFFFFFF)) throw new TypeError('LED color must be packed RGB');
              // Three.js may warn and retain the old color for invalid input.
              // Parse on a detached value so that cannot promote unknown output.
              const color = led.color.clone();
              color.r = color.g = color.b = NaN;
              color.set(command.color);
              if (![color.r, color.g, color.b].every(Number.isFinite)) throw new TypeError('LED color is invalid');
            }
          }
          // Zero emission is the neutral appearance of unknown output, not an
          // electrical off observation. Keep that distinction on the component.
          if (command.known === false) {
            led.set(fixedColorIndicator(led) ? {brightness: 0} : {color: 0, brightness: 0});
            led.runtimeKnown = led.object3d.userData.runtimeKnown = false;
            return {known: false};
          }
          const result = this.model.handle(command);
          led.runtimeKnown = led.object3d.userData.runtimeKnown = true;
          return result;
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

  resetView() {
    if (this.disposed) return;
    this.viewer.setView('front', {duration: 0});
    this.viewer.fit({padding: 1.15, duration: 0});
  }

  dispose() {
    if (this.disposed) return;
    this.cancelCameraAnimation();
    // Viewer cancellation emits matching releases before removing subscriptions.
    this.unitAnnotations?.dispose();
    this.viewer.dispose();
    this.applyVisualState(this.model.list('led').filter(led => led.runtimeKnown !== undefined)
      .map(led => ({type: 'led', target: led.path, known: false})));
    this.disposed = true;
    this.clearDriveActivities();
    this.offInput?.();
    this.model.dispose();
    this.listeners.clear();
    this.root.remove();
  }
}

export const createModelShell = (host, device, options) => ModelDeviceShell.create(host, device, options);

// Both controllers and Units are real independent catalog models. Browsing one
// does not manufacture a host, firmware profile, attachment or runtime binding.
export async function createVisualModelShell(host, id, options = {}) {
  const metadata = MODEL_METADATA[id];
  if (!metadata || ![...MODEL_DEVICES, ...UNIT_MODELS].includes(id)) throw new Error(`Unknown visual model: ${id}`);
  const device = {id, name: metadata.name || id, category: metadata.category,
    sku: metadata.sku, hardware: {}, visual_only: true};
  const shell = await ModelDeviceShell.create(host, device, {...options, live: true});
  shell.root.dataset.modelCategory = metadata.category;
  shell.root.dataset.visualOnly = 'true';
  return shell;
}
