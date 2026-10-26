// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EventEmitter } from './EventEmitter.js';
import { Speaker } from './components/Speaker.js';

const VIEWS = {
  front: [0, 0, 0],
  back: [0, Math.PI, 0],
  left: [0, Math.PI / 2, 0],
  right: [0, -Math.PI / 2, 0],
  top: [Math.PI / 2, 0, 0],
  bottom: [-Math.PI / 2, 0, 0],
  iso: [0.42, -0.62, 0.1],
  'iso-back': [0.35, Math.PI + 0.6, -0.08],
};

const TONE = {
  neutral: THREE.NeutralToneMapping, aces: THREE.ACESFilmicToneMapping, agx: THREE.AgXToneMapping, none: THREE.NoToneMapping,
};

function isEditable(el) {
  return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
}

function effectivelyVisible(o) {
  for (; o; o = o.parent) if (!o.visible) return false;
  return true;
}

/**
 * Renders devices and turns pointer / keyboard / wheel input into either
 * component interaction (press a button, touch a screen) or view control
 * (drag to rotate the device, wheel / pinch to zoom, right-drag or
 * shift-drag to pan, double-click empty space to reset).
 *
 * The camera stays put; dragging rotates the *device*, so its IMU sees the
 * motion. Rendering is on demand: a frame is drawn only when something changed.
 *
 * Events: `hover` (info|null), `select` (info) — click without drag on any part,
 * `render`, `viewchange`.
 */
export class DeviceViewer extends EventEmitter {
  constructor(container, {
    background = null, environment = true, shadows = true, ground = true,
    pixelRatio = Math.min(globalThis.devicePixelRatio || 1, 2), fov = 26,
    keyboard = true, inertia = true, rotateSpeed = 0.0085, toneMapping = 'neutral', exposure = 1,
    minDistance = 25, maxDistance = 600,
  } = {}) {
    super();
    this.container = container;
    this.opts = { inertia, rotateSpeed, keyboard, minDistance, maxDistance, ground };
    this.devices = new Set();

    const renderer = (this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: background == null }));
    renderer.setPixelRatio(pixelRatio);
    renderer.toneMapping = TONE[toneMapping] ?? THREE.NeutralToneMapping;
    renderer.toneMappingExposure = exposure;
    renderer.shadowMap.enabled = shadows;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    const canvas = renderer.domElement;
    Object.assign(canvas.style, { width: '100%', height: '100%', display: 'block', touchAction: 'none', outline: 'none' });
    canvas.tabIndex = 0;
    container.appendChild(canvas);

    const scene = (this.scene = new THREE.Scene());
    if (background != null) scene.background = new THREE.Color(background);
    if (environment) {
      const pmrem = new THREE.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      scene.environmentIntensity = 0.7;
      pmrem.dispose();
    }
    const key = (this.keyLight = new THREE.DirectionalLight(0xffffff, 1.6));
    key.position.set(-40, 120, 80);
    key.castShadow = shadows;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = key.shadow.camera.bottom = -90;
    key.shadow.camera.right = key.shadow.camera.top = 90;
    key.shadow.camera.near = 10;
    key.shadow.camera.far = 400;
    key.shadow.radius = 6;
    key.shadow.bias = -0.0005;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xbfd4ff, 0.6);
    rim.position.set(60, 30, -80);
    scene.add(rim);

    this.ground = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.ShadowMaterial({ opacity: 0.18 }));
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.ground.visible = ground && shadows;
    this.ground.raycast = () => {};
    scene.add(this.ground);

    this.camera = new THREE.PerspectiveCamera(fov, 1, 1, 5000);
    this.target = new THREE.Vector3();
    this.distance = 160;
    this.#applyCamera();

    this.raycaster = new THREE.Raycaster();
    this.raycaster.camera = this.camera;

    this.#bindEvents();
    this.#resizeObserver = new ResizeObserver(() => this.resize());
    this.#resizeObserver.observe(container);
    this.resize();
    this.#last = performance.now();
    this.#raf = requestAnimationFrame(this.#loop);
  }

  #raf = 0;
  #last = 0;
  #needsRender = true;
  #resizeObserver;
  #captures = new Map(); // pointerId → { component }
  #drags = new Map(); // pointerId → { x, y, sx, sy, pan, device }
  #pinch = null;
  #angularVel = new THREE.Vector3();
  #hover = null;
  #tweens = [];
  #keysDown = new Map(); // code → button
  #listeners = [];
  #deviceOff = new Map(); // device → subscriptions owned by this viewer
  #disposing = false;
  #disposed = false;

  // ───────────────────────────── devices ─────────────────────────────

  /** Add a device to the scene. The first mounted device is the primary one. */
  mount(device, { position, fit = true } = {}) {
    if (this.#disposing) return device; // cancelled-up cannot revive a dying viewer
    if (this.#disposed) throw new Error('Cannot mount a device on a disposed DeviceViewer');
    // A scene Object3D has one parent; its update loop and input subscriptions
    // must have the same single owner. Unmount first while old paths still work.
    if (device.viewer && device.viewer !== this) {
      device.viewer.unmount(device);
      // A cancelled-up consumer may have chosen a new owner synchronously.
      // The outer, older mount request must not steal it back and double-tick.
      if (device.viewer && device.viewer !== this && device.viewer.devices?.has(device)) return device;
    }
    if (this.devices.has(device)) {
      if (position) device.root.position.fromArray(position);
      if (fit) this.fit();
      this.#layoutGround();
      this.requestRender();
      return device;
    }
    device.viewer = this;
    if (position) device.root.position.fromArray(position);
    this.scene.add(device.root);
    this.devices.add(device);
    device.root.traverse((o) => {
      if (o.isMesh && !o.material?.transparent) { o.castShadow = true; }
    });
    const refresh = () => { this.#updateShadowCasters(device); this.#layoutGround(); };
    this.#deviceOff.set(device, [device.on('input', event => {
      // Input paths bubble through nested modules. Port propagates the separate
      // will-detach lifecycle before removing the old parent/path ownership.
      if (event.kind !== 'port' || !['attach', 'detach'].includes(event.action)) return;
      refresh();
    }), device.on('module:will-detach', ({module}) => this.#cancelInputs(module))]);
    if (fit) this.fit();
    this.#layoutGround();
    this.requestRender();
    return device;
  }

  unmount(device) {
    const primary = device === this.device;
    if (!this.devices.delete(device)) return;
    // A focus/fit animation for the old scene must not override the next mount.
    this.#tweens = [];
    if (primary) {
      this.#angularVel.set(0, 0, 0);
      this.#pinch = null;
    }
    this.#deviceOff.get(device)?.forEach((off) => off());
    this.#deviceOff.delete(device);
    this.#cancelInputs(device);
    // An input consumer may synchronously mount the device during cancelled up.
    // Do not unlink the new scene owner or clear its newly installed listeners.
    if (device.viewer === this && !this.devices.has(device)) {
      device.root.removeFromParent();
      device.viewer = null;
    }
    this.requestRender();
  }

  get device() {
    return this.devices.values().next().value ?? null;
  }

  #updateShadowCasters(device) {
    device.root.traverse((o) => {
      if (o.isMesh && !o.material?.transparent) o.castShadow = true;
    });
  }

  #layoutGround() {
    const box = new THREE.Box3();
    for (const d of this.devices) box.expandByObject(d.root);
    if (box.isEmpty()) return;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    this.ground.position.y = Math.min(-30, sphere.center.y - sphere.radius - 4);
  }

  /** Frame all devices. */
  fit({ padding = 1.35, duration = 0 } = {}) {
    const f = this.#fitParams(padding);
    if (!f) return;
    if (duration) this.#animateCamera(f.target, f.distance, duration);
    else {
      this.target.copy(f.target);
      this.distance = f.distance;
      this.#applyCamera();
    }
  }

  #fitParams(padding = 1.35) {
    const box = new THREE.Box3();
    for (const d of this.devices) box.expandByObject(d.root);
    if (box.isEmpty()) return null;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const fov = THREE.MathUtils.degToRad(this.camera.fov);
    const fitH = sphere.radius / Math.sin(fov / 2);
    const fitW = sphere.radius / Math.sin(Math.atan(Math.tan(fov / 2) * this.camera.aspect));
    return {
      target: new THREE.Vector3(sphere.center.x, sphere.center.y, 0),
      distance: THREE.MathUtils.clamp(Math.max(fitH, fitW) * padding * 0.8, this.opts.minDistance, this.opts.maxDistance),
    };
  }

  // ───────────────────────────── view control ─────────────────────────────

  /**
   * Animate the (primary) device to a named orientation:
   * front | back | left | right | top | bottom | iso | iso-back, or a Quaternion.
   */
  setView(view, { device = this.device, duration = 450 } = {}) {
    if (!device) return;
    const q = view?.isQuaternion ? view.clone()
      : new THREE.Quaternion().setFromEuler(new THREE.Euler(...(VIEWS[view] ?? VIEWS.front), 'YXZ'));
    this.#angularVel.set(0, 0, 0);
    const from = device.root.quaternion.clone();
    this.#tween(duration, (k) => device.root.quaternion.slerpQuaternions(from, q, k));
    this.emit('viewchange', { view });
  }

  /** Reset orientation, zoom and pan. */
  resetView({ duration = 450 } = {}) {
    this.setView('front', { duration });
    this.fit({ duration });
  }

  /** Zoom/pan the camera onto a component (e.g. `focus('lcd')` to inspect pixels). */
  focus(path, { device = this.device, distance = 45, duration = 500 } = {}) {
    const c = device.get(path);
    const capBox = c.cap ? new THREE.Box3().setFromObject(c.cap) : null;
    const p = capBox && !capBox.isEmpty() ? capBox.getCenter(new THREE.Vector3()) : c.object3d.getWorldPosition(new THREE.Vector3());
    this.#animateCamera(p, distance, duration);
  }

  /** Set zoom distance (mm from target). */
  zoomTo(distance, { duration = 300 } = {}) {
    this.#animateCamera(this.target.clone(), distance, duration);
  }

  #animateCamera(target, distance, duration) {
    const t0 = this.target.clone(), d0 = this.distance;
    const d1 = THREE.MathUtils.clamp(distance, this.opts.minDistance, this.opts.maxDistance);
    this.#tween(duration, (k) => {
      this.target.lerpVectors(t0, target, k);
      this.distance = d0 + (d1 - d0) * k;
      this.#applyCamera();
    });
  }

  #tween(duration, apply) {
    const tw = { t: 0, duration: Math.max(1, duration), apply };
    this.#tweens.push(tw);
    this.requestRender();
    return tw;
  }

  #applyCamera() {
    this.camera.position.set(this.target.x, this.target.y, this.target.z + this.distance);
    this.camera.lookAt(this.target);
    this.camera.near = Math.max(0.5, this.distance * 0.05);
    this.camera.far = this.distance + 2000;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  // ───────────────────────────── loop ─────────────────────────────

  requestRender() {
    this.#needsRender = true;
  }

  #loop = (now) => {
    this.#raf = requestAnimationFrame(this.#loop);
    const dt = Math.min(0.1, Math.max(0, (now - this.#last) / 1000));
    this.#last = now;
    let animating = false;

    if (this.#tweens.length) {
      animating = true;
      this.#tweens = this.#tweens.filter((tw) => {
        tw.t += dt * 1000;
        const k = Math.min(1, tw.t / tw.duration);
        tw.apply(k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
        return k < 1;
      });
    }

    if (!this.#drags.size && this.#angularVel.lengthSq() > 1e-8) {
      animating = true;
      const dev = this.device;
      if (dev) this.#rotate(dev, this.#angularVel.clone().multiplyScalar(dt));
      this.#angularVel.multiplyScalar(Math.exp(-dt * 5));
      if (this.#angularVel.lengthSq() < 1e-6) this.#angularVel.set(0, 0, 0);
    }

    for (const d of this.devices) if (d.update(dt, now / 1000)) animating = true;

    if (animating || this.#needsRender) {
      this.#needsRender = false;
      this.renderer.render(this.scene, this.camera);
      this.emit('render', dt);
    }
  };

  resize() {
    const w = this.container.clientWidth || 1, h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  /** PNG data URL of the current view. */
  screenshot() {
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement.toDataURL('image/png');
  }

  // ───────────────────────────── input ─────────────────────────────

  #ndc(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  }

  /** Raycast the devices; returns { component, intersection, device } of the first visible hit. */
  pick(e, roots) {
    this.raycaster.setFromCamera(this.#ndc(e), this.camera);
    const objs = roots ?? [...this.devices].map((d) => d.root);
    const hits = this.raycaster.intersectObjects(objs, true);
    for (const hit of hits) {
      if (!effectivelyVisible(hit.object)) continue;
      let o = hit.object, component = null;
      for (; o; o = o.parent) if (o.userData.component) { component = o.userData.component; break; }
      const device = [...this.devices].find((d) => isDescendant(hit.object, d.root)) ?? null;
      return { component, intersection: hit, device };
    }
    return null;
  }

  #info(e, intersection) {
    return {
      pointerId: e.pointerId, event: e, intersection,
      uv: intersection?.uv ?? null, point: intersection?.point ?? null,
      // Captured sliders keep following the pointer after it leaves the cap.
      ray: this.raycaster.ray.clone(),
    };
  }

  #on(target, type, fn, opts) {
    target.addEventListener(type, fn, opts);
    this.#listeners.push(() => target.removeEventListener(type, fn, opts));
  }

  #bindEvents() {
    const canvas = this.renderer.domElement;
    this.#on(canvas, 'contextmenu', (e) => e.preventDefault());
    this.#on(canvas, 'pointerdown', (e) => this.#pointerDown(e));
    this.#on(canvas, 'pointermove', (e) => this.#pointerMove(e));
    this.#on(canvas, 'pointerup', (e) => this.#pointerUp(e, false));
    this.#on(canvas, 'pointercancel', (e) => this.#pointerUp(e, true));
    this.#on(canvas, 'lostpointercapture', (e) => {
      if (this.#captures.has(e.pointerId) || this.#drags.has(e.pointerId)) this.#pointerUp(e, true);
    });
    this.#on(canvas, 'pointerleave', () => this.#setHover(null));
    this.#on(canvas, 'wheel', (e) => {
      e.preventDefault();
      const k = Math.exp(e.deltaY * (e.ctrlKey ? 0.01 : 0.0012));
      this.distance = THREE.MathUtils.clamp(this.distance * k, this.opts.minDistance, this.opts.maxDistance);
      this.#applyCamera();
    }, { passive: false });
    this.#on(canvas, 'dblclick', (e) => {
      const hit = this.pick(e);
      if (!hit) this.resetView();
    });
    this.#on(window, 'blur', () => this.#cancelInputs());
    this.#on(document, 'visibilitychange', () => { if (document.hidden) this.#cancelInputs(); });
    this.#on(canvas, 'blur', () => this.#cancelInputs());
    if (this.opts.keyboard) {
      this.#on(window, 'keydown', (e) => this.#key(e, true));
      this.#on(window, 'keyup', (e) => this.#key(e, false));
    }
  }

  /** Release captured input before a device disappears or its canvas loses focus. */
  #cancelInputs(device = null) {
    const belongs = component => !device || isDescendant(component.object3d, device.root);
    for (const [code, button] of [...this.#keysDown]) {
      if (!belongs(button)) continue;
      this.#keysDown.delete(code);
      if (button.cancel) button.cancel(`key:${code}`); else button.release(`key:${code}`);
    }
    for (const [id, capture] of [...this.#captures]) {
      if (!belongs(capture.component)) continue;
      this.#captures.delete(id);
      capture.component.onPointerCancel({pointerId: id, intersection: null});
      if (this.renderer.domElement.hasPointerCapture(id)) this.renderer.domElement.releasePointerCapture(id);
    }
    let removedDrag = false;
    for (const [id, drag] of this.#drags) {
      if (device && drag.device !== device && !isDescendant(drag.hit?.intersection?.object, device.root)) continue;
      this.#drags.delete(id);
      removedDrag = true;
      if (this.renderer.domElement.hasPointerCapture(id)) this.renderer.domElement.releasePointerCapture(id);
    }
    if (!device || removedDrag || device === this.device) {
      this.#pinch = null;
      this.#angularVel.set(0, 0, 0);
    }
    if (!device || (this.#hover && belongs(this.#hover))) this.#setHover(null);
    this.requestRender();
  }

  #pointerDown(e) {
    Speaker.unlock();
    const canvas = this.renderer.domElement;
    canvas.focus({preventScroll: true});
    canvas.setPointerCapture(e.pointerId);
    const hit = this.pick(e);
    if (hit?.component?.interactive && e.button === 0 && !this.#drags.size) {
      this.#captures.set(e.pointerId, { component: hit.component, sx: e.clientX, sy: e.clientY });
      hit.component.onPointerDown(this.#info(e, hit.intersection));
      return;
    }
    this.#angularVel.set(0, 0, 0);
    this.#drags.set(e.pointerId, {
      x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, t: performance.now(),
      pan: e.button === 2 || e.button === 1 || e.shiftKey, device: hit?.device ?? this.device, hit,
    });
    if (this.#drags.size === 2) {
      const [a, b] = [...this.#drags.values()];
      this.#pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), distance: this.distance };
    }
    canvas.style.cursor = 'grabbing';
  }

  #pointerMove(e) {
    const cap = this.#captures.get(e.pointerId);
    if (cap) {
      const hit = this.pick(e, [cap.component.object3d]);
      cap.component.onPointerMove(this.#info(e, hit?.component === cap.component ? hit.intersection : null));
      return;
    }
    const drag = this.#drags.get(e.pointerId);
    if (!drag) return this.#updateHover(e);

    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    const now = performance.now();
    const dtMove = Math.max(1, now - drag.t) / 1000;
    drag.x = e.clientX; drag.y = e.clientY; drag.t = now;

    if (this.#drags.size >= 2 && this.#pinch) {
      const [a, b] = [...this.#drags.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      this.distance = THREE.MathUtils.clamp(this.#pinch.distance * (this.#pinch.dist / Math.max(1, dist)),
        this.opts.minDistance, this.opts.maxDistance);
      this.#pan(dx / 2, dy / 2);
      return;
    }
    if (drag.pan) return this.#pan(dx, dy);
    if (!drag.device) return;
    const s = this.opts.rotateSpeed;
    const rot = new THREE.Vector3(dy * s, dx * s, 0);
    this.#rotate(drag.device, rot);
    if (this.opts.inertia) this.#angularVel.lerp(rot.clone().divideScalar(dtMove), 0.6);
  }

  #pointerUp(e, cancelled) {
    const canvas = this.renderer.domElement;
    const cap = this.#captures.get(e.pointerId);
    const drag = this.#drags.get(e.pointerId);
    this.#captures.delete(e.pointerId);
    this.#drags.delete(e.pointerId);
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    if (cap) {
      const info = this.#info(e, null);
      if (cancelled) cap.component.onPointerCancel(info);
      else cap.component.onPointerUp(info);
      if (!cancelled && Math.hypot(e.clientX - cap.sx, e.clientY - cap.sy) < 5) this.#select(cap.component, null);
      return;
    }
    if (!drag) return;
    if (this.#drags.size < 2) this.#pinch = null;
    if (performance.now() - drag.t > 80) this.#angularVel.set(0, 0, 0); // paused before release
    const moved = Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy);
    if (!cancelled && moved < 5) {
      this.#angularVel.set(0, 0, 0);
      if (drag.hit?.component) this.#select(drag.hit.component, drag.hit.intersection);
    }
    canvas.style.cursor = '';
    this.#updateHover(e);
  }

  #select(component, intersection) {
    this.emit('select', { component, ...component.describe(intersection) });
  }

  #rotate(device, rot) {
    const angle = rot.length();
    if (angle < 1e-9) return;
    const q = new THREE.Quaternion().setFromAxisAngle(rot.clone().normalize(), angle);
    device.root.quaternion.premultiply(q).normalize();
    this.requestRender();
  }

  #pan(dx, dy) {
    const h = 2 * Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) * this.distance;
    const k = h / this.renderer.domElement.clientHeight;
    this.target.x -= dx * k;
    this.target.y += dy * k;
    this.#applyCamera();
  }

  #updateHover(e) {
    if (this.#drags.size || this.#captures.size) return;
    this.#setHover(this.pick(e));
  }

  #setHover(hit) {
    const c = hit?.component ?? null;
    if (this.#hover !== c) {
      this.#hover?.setHover(false);
      this.#hover = c;
      c?.setHover(true);
    }
    this.renderer.domElement.style.cursor = c?.interactive ? c.cursor : hit ? 'grab' : '';
    this.emit('hover', c ? { component: c, ...c.describe(hit.intersection) } : null);
  }

  #key(e, down) {
    // Key-up can arrive over a form field after focus changed while held.
    if (!down && this.#keysDown.has(e.code)) {
      const button = this.#keysDown.get(e.code);
      this.#keysDown.delete(e.code);
      button.release(`key:${e.code}`);
      return;
    }
    if (isEditable(e.target) || e.metaKey || e.ctrlKey) return;
    const focused = document.activeElement === this.renderer.domElement;
    if (this.opts.keyboard === 'focused' && !focused) return;
    // A physical Alt key may be an explicitly mapped model key (CardKB Sym).
    // Only its own focused keydown can reach keymap lookup; Alt combinations
    // and unowned modifier releases keep their browser defaults untouched.
    const altKey = e.code === 'AltLeft' || e.code === 'AltRight';
    if (altKey && !down) return;
    if (e.altKey && !(altKey && focused)) return;
    for (const device of this.devices) {
      const path = device.keymap[e.code] ?? device.keymap[e.key];
      if (!path) continue;
      const btn = device.find(path, 'button');
      if (!btn) continue;
      e.preventDefault();
      if (down) {
        if (e.repeat || this.#keysDown.has(e.code)) return;
        this.#keysDown.set(e.code, btn);
        btn.press(`key:${e.code}`);
      } else {
        this.#keysDown.delete(e.code);
        btn.release(`key:${e.code}`);
      }
      return;
    }
  }

  dispose() {
    if (this.#disposing || this.#disposed) return;
    this.#disposing = true;
    try {
      cancelAnimationFrame(this.#raf);
      this.#resizeObserver.disconnect();
      for (const off of this.#listeners) off();
      for (const d of [...this.devices]) this.unmount(d);
      this.scene.environment?.dispose();
      this.renderer.dispose();
      this.renderer.domElement.remove();
      this.removeAllListeners();
    } finally {
      this.#disposing = false;
      this.#disposed = true;
    }
  }
}

function isDescendant(o, root) {
  for (; o; o = o.parent) if (o === root) return true;
  return false;
}
