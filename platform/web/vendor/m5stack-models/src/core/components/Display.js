// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { Component } from '../Component.js';
import { materials } from '../materials.js';

/**
 * Pixel styles. `lcd` = RGB-stripe TFT/IPS, `oled` = square emitters with a
 * thin gap, `led` = discrete round LEDs (matrices), `flat` = no pixel structure.
 */
const STYLES = { lcd: 0, oled: 1, led: 2, flat: 3 };

const vertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

// The framebuffer is sampled with nearest filtering at texel centres, then
// modulated by a procedural pixel mask with two levels of detail driven by
// fwidth (texels per screen pixel):
//   - pixel grid (black matrix) once a texel spans >= ~2-4 screen pixels,
//   - RGB sub-pixel stripes once a texel spans >= ~5-10 screen pixels.
// Below that the mask fades out, so zoomed-out views stay moire-free. One
// texture fetch per fragment: cheap even for large panels.
const fragmentShader = /* glsl */ `
uniform sampler2D map;
uniform vec2 res;
uniform float brightness;
uniform float effect;
uniform int style;
uniform vec3 blackLevel;
uniform vec3 offColor;
varying vec2 vUv;

float band(float s, float a, float b, float aw) {
  return smoothstep(a - aw, a + aw, s) * (1.0 - smoothstep(b - aw, b + aw, s));
}

void main() {
  vec2 p = vec2(vUv.x * res.x, (1.0 - vUv.y) * res.y);
  vec2 cell = clamp(floor(p), vec2(0.0), res - 1.0);
  vec2 f = p - cell;
  vec3 c = texture2D(map, (cell + 0.5) / res).rgb;
  vec2 fw = max(fwidth(p), vec2(1e-5));
  float fwm = max(fw.x, fw.y);
  float gridDetail = effect * (1.0 - smoothstep(0.25, 0.5, fwm));
  float stripeDetail = 1.0 - smoothstep(0.1, 0.2, fwm);
  vec3 col;

  if (style == 2) {
    // Discrete LEDs: round emitter on a dark PCB, with a soft halo.
    vec2 d2 = f - 0.5;
    float d = length(d2);
    float aw = max(fw.x, fw.y);
    float core = 1.0 - smoothstep(0.34 - aw, 0.34 + aw, d);
    vec3 lit = c * brightness;
    vec3 emitter = offColor + lit * 1.8;
    float halo = exp(-d * d * 10.0) * 0.45;
    col = mix(vec3(0.012), emitter, core) + lit * halo;
  } else {
    vec3 lit = c * brightness;
    vec3 mask = vec3(1.0);
    float aw = fwm * 0.75;
    if (style == 0) {
      float row = band(f.y, 0.07, 0.93, aw);
      vec3 grid = vec3(row * band(f.x, 0.04, 0.96, aw)) * 1.2;
      float s = f.x * 3.0;
      float aws = fw.x * 1.5;
      vec3 stripes = vec3(band(s, 0.12, 0.88, aws), band(s, 1.12, 1.88, aws), band(s, 2.12, 2.88, aws)) * row * 2.4;
      mask = mix(grid, stripes, stripeDetail);
    } else if (style == 1) {
      mask = vec3(band(f.x, 0.08, 0.92, aw) * band(f.y, 0.08, 0.92, aw)) * 1.3;
    }
    col = lit * mix(vec3(1.0), mask, gridDetail);
    // Backlight bleed: an LCD never reaches true black while lit.
    col = max(col, blackLevel * brightness);
    col = mix(offColor, col, clamp(brightness * 8.0, 0.0, 1.0));
  }
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

const tmpColor = new THREE.Color();

/**
 * A pixel-accurate display panel.
 *
 * The panel is a `width × height` RGBA framebuffer mapped onto a plane of the
 * real active-area size (`size`, mm). Pixel (0,0) is the top-left corner as
 * seen from the front, rows go downwards — same as the panel's native memory
 * order. Upload is lazy: writes mark the texture dirty and the GPU copy happens
 * once per rendered frame at most.
 *
 * Writing pixels:
 *   display.writeRGB565(u16, { x, y, w, h, swapBytes })  // ESP32-style framebuffers
 *   display.writeRGBA(u8, rect) / display.writeRGB888(u8, rect)
 *   display.fill('#000')
 *   const ctx = display.getContext2D(); … ; display.present()  // canvas drawing
 *
 * Touch: `touch: true` turns the panel into a touch surface; events are
 * reported in panel pixel coordinates: { action: 'start'|'move'|'end', x, y, pointerId }.
 */
export class Display extends Component {
  static kind = 'display';

  constructor({
    width, height, size, style = 'lcd', pixelEffect = true, touch = false,
    backlight = 1, offColor = 0x07080a, blackLevel = 0.004, glass = true, ...rest
  }) {
    super(rest);
    if (!width || !height || !size) throw new Error('Display needs width, height and size [mm, mm]');
    this.width = width;
    this.height = height;
    this.size = size;
    this.buffer = new Uint8Array(width * height * 4);
    for (let i = 3; i < this.buffer.length; i += 4) this.buffer[i] = 255;

    this.texture = new THREE.DataTexture(this.buffer, width, height, THREE.RGBAFormat, THREE.UnsignedByteType);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.magFilter = THREE.NearestFilter;
    this.texture.minFilter = THREE.NearestFilter;
    this.texture.generateMipmaps = false;
    this.texture.needsUpdate = true;

    this.material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      toneMapped: false,
      uniforms: {
        map: { value: this.texture },
        res: { value: new THREE.Vector2(width, height) },
        brightness: { value: backlight },
        effect: { value: pixelEffect ? 1 : 0 },
        style: { value: STYLES[style] ?? 0 },
        blackLevel: { value: new THREE.Color(blackLevel, blackLevel, blackLevel * 1.15) },
        offColor: { value: new THREE.Color(offColor) },
      },
    });
    this.panel = this.hit(new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), this.material));
    this.panel.name = 'display-panel';
    this.object3d.add(this.panel);

    if (glass) {
      const g = glass === true ? {} : glass;
      const [gw, gh] = g.size ?? size;
      this.glass = new THREE.Mesh(new THREE.PlaneGeometry(gw, gh), materials.coverGlass(g));
      this.glass.position.z = g.offset ?? 0.02;
      this.glass.raycast = () => {};
      this.glass.renderOrder = 2;
      this.object3d.add(this.glass);
    }

    this.style = style;
    this.backlight = backlight;
    this.powered = true;
    this.touchEnabled = touch;
    /** Active touch points: pointerId → { x, y } */
    this.touches = new Map();
    this.#touchMarkers = new Map();
    this.#ctx = null;
  }

  #dirty = false;
  #ctx;
  #touchMarkers;
  #clearingTouches = false;
  #disposed = false;

  get interactive() {
    return this.touchEnabled;
  }

  get cursor() {
    return 'crosshair';
  }

  /** Mark the framebuffer as changed (call after mutating `buffer` directly). */
  invalidate() {
    this.#dirty = true;
    this.requestRender();
  }

  #rect(rect = {}) {
    const x = rect.x ?? 0, y = rect.y ?? 0;
    const w = rect.w ?? rect.width ?? this.width - x;
    const h = rect.h ?? rect.height ?? this.height - y;
    return { x, y, w, h };
  }

  /** Write a block of RGB565 pixels. Accepts Uint16Array or raw bytes (little-endian). */
  writeRGB565(data, rect, { swapBytes = rect?.swapBytes ?? false } = {}) {
    const { x, y, w, h } = this.#rect(rect);
    const src = data instanceof Uint16Array ? data : new Uint16Array(data.buffer ?? data, data.byteOffset ?? 0, w * h);
    const buf = this.buffer, W = this.width;
    for (let row = 0; row < h; row++) {
      const py = y + row;
      if (py < 0 || py >= this.height) continue;
      let o = (py * W + x) * 4, s = row * w;
      for (let col = 0; col < w; col++, o += 4, s++) {
        const px = x + col;
        if (px < 0 || px >= W) continue;
        let v = src[s];
        if (swapBytes) v = ((v & 0xff) << 8) | (v >> 8);
        const r = (v >> 11) & 0x1f, g = (v >> 5) & 0x3f, b = v & 0x1f;
        buf[o] = (r << 3) | (r >> 2);
        buf[o + 1] = (g << 2) | (g >> 4);
        buf[o + 2] = (b << 3) | (b >> 2);
      }
    }
    this.invalidate();
  }

  /** Write a block of RGBA8888 pixels. */
  writeRGBA(data, rect) {
    if (data instanceof ArrayBuffer) data = new Uint8Array(data);
    const { x, y, w, h } = this.#rect(rect);
    if (x === 0 && y === 0 && w === this.width && h === this.height) {
      this.buffer.set(data.subarray ? data.subarray(0, this.buffer.length) : data);
    } else {
      for (let row = 0; row < h; row++) {
        const py = y + row;
        if (py < 0 || py >= this.height) continue;
        const x0 = Math.max(0, x), x1 = Math.min(this.width, x + w);
        if (x1 <= x0) continue;
        const s = (row * w + (x0 - x)) * 4;
        this.buffer.set(data.subarray(s, s + (x1 - x0) * 4), (py * this.width + x0) * 4);
      }
    }
    this.invalidate();
  }

  /** Write a block of packed RGB888 pixels. */
  writeRGB888(data, rect) {
    if (data instanceof ArrayBuffer) data = new Uint8Array(data);
    const { x, y, w, h } = this.#rect(rect);
    for (let row = 0; row < h; row++) {
      const py = y + row;
      if (py < 0 || py >= this.height) continue;
      for (let col = 0; col < w; col++) {
        const px = x + col;
        if (px < 0 || px >= this.width) continue;
        const s = (row * w + col) * 3, o = (py * this.width + px) * 4;
        this.buffer[o] = data[s];
        this.buffer[o + 1] = data[s + 1];
        this.buffer[o + 2] = data[s + 2];
      }
    }
    this.invalidate();
  }

  /** Fill a rect (default: whole panel) with a CSS colour / hex number. */
  fill(color, rect) {
    tmpColor.set(color);
    // DataTexture stores sRGB bytes; THREE.Color holds linear-light channels.
    tmpColor.convertLinearToSRGB();
    const r = Math.round(tmpColor.r * 255), g = Math.round(tmpColor.g * 255), b = Math.round(tmpColor.b * 255);
    const { x, y, w, h } = this.#rect(rect);
    for (let py = Math.max(0, y); py < Math.min(this.height, y + h); py++) {
      for (let px = Math.max(0, x); px < Math.min(this.width, x + w); px++) {
        const o = (py * this.width + px) * 4;
        this.buffer[o] = r; this.buffer[o + 1] = g; this.buffer[o + 2] = b;
      }
    }
    this.invalidate();
  }

  /** Read back a pixel as [r, g, b]. */
  getPixel(x, y) {
    const o = (y * this.width + x) * 4;
    return [this.buffer[o], this.buffer[o + 1], this.buffer[o + 2]];
  }

  /**
   * A native-resolution 2D canvas context for convenience drawing. Call
   * `present()` to copy it into the framebuffer.
   */
  getContext2D() {
    if (!this.#ctx) {
      const canvas = typeof OffscreenCanvas !== 'undefined'
        ? new OffscreenCanvas(this.width, this.height)
        : Object.assign(document.createElement('canvas'), { width: this.width, height: this.height });
      this.#ctx = canvas.getContext('2d', { willReadFrequently: true });
      this.#ctx.imageSmoothingEnabled = false;
    }
    return this.#ctx;
  }

  present() {
    if (!this.#ctx) return;
    const img = this.#ctx.getImageData(0, 0, this.width, this.height);
    this.writeRGBA(img.data);
  }

  setBacklight(level) {
    this.backlight = Math.max(0, Math.min(1, level));
    this.#syncBrightness();
  }

  setPower(on) {
    this.powered = !!on;
    this.#syncBrightness();
  }

  #syncBrightness() {
    this.material.uniforms.brightness.value = this.powered ? this.backlight : 0;
    this.requestRender();
  }

  setStyle(style) {
    if (!(style in STYLES)) throw new Error(`Unknown display style "${style}"`);
    this.style = style;
    this.material.uniforms.style.value = STYLES[style];
    this.requestRender();
  }

  /** Toggle the sub-pixel simulation (keeps nearest-neighbour pixels either way). */
  setPixelEffect(on) {
    this.material.uniforms.effect.value = on ? 1 : 0;
    this.requestRender();
  }

  setTouchEnabled(on) {
    if (this.#disposed) return;
    this.touchEnabled = !!on;
    if (!on) this.#clearTouches();
  }

  /** Convert a panel UV to integer pixel coordinates. */
  uvToPixel(uv) {
    return {
      x: Math.min(this.width - 1, Math.max(0, Math.floor(uv.x * this.width))),
      y: Math.min(this.height - 1, Math.max(0, Math.floor((1 - uv.y) * this.height))),
    };
  }

  /** Inject a touch from the simulator side or tests: action 'start' | 'move' | 'end'. */
  touch(action, x, y, pointerId = 0) {
    if (this.#disposed || this.#clearingTouches) return;
    if (action === 'end') return this.#touchEnd(pointerId);
    this.touches.set(pointerId, { x, y });
    this.#marker(pointerId, x, y);
    this.input(action, { x, y, pointerId, points: [...this.touches.values()] });
  }

  #touchEnd(pointerId, notify = true) {
    const p = this.touches.get(pointerId);
    this.touches.delete(pointerId);
    const marker = this.#touchMarkers.get(pointerId);
    this.#touchMarkers.delete(pointerId);
    if (marker) {
      marker.removeFromParent();
      marker.geometry.dispose();
      marker.material.dispose();
    }
    if (!p) return;
    if (notify) this.input('end', { ...p, pointerId, points: [...this.touches.values()] });
    this.requestRender();
  }

  #clearTouches(notify = true) {
    if (this.#clearingTouches) return;
    this.#clearingTouches = true;
    try {
      // End listeners run synchronously; they cannot recreate a point while
      // disable/dispose is clearing the collection. Markers are owned here,
      // even if a caller has already cleared the public touches Map.
      for (const id of new Set([...this.touches.keys(), ...this.#touchMarkers.keys()])) this.#touchEnd(id, notify);
    } finally {
      this.#clearingTouches = false;
    }
  }

  #marker(pointerId, x, y) {
    let m = this.#touchMarkers.get(pointerId);
    if (!m) {
      const r = Math.min(this.size[0], this.size[1]) * 0.06;
      m = new THREE.Mesh(new THREE.RingGeometry(r * 0.55, r, 32), new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: 0.55, depthWrite: false, toneMapped: false,
      }));
      m.renderOrder = 3;
      m.raycast = () => {};
      this.object3d.add(m);
      this.#touchMarkers.set(pointerId, m);
    }
    m.position.set(((x + 0.5) / this.width - 0.5) * this.size[0], (0.5 - (y + 0.5) / this.height) * this.size[1], 0.05);
    this.requestRender();
  }

  onPointerDown({ pointerId, uv }) {
    if (!uv) return;
    const { x, y } = this.uvToPixel(uv);
    this.touch('start', x, y, pointerId);
  }

  onPointerMove({ pointerId, uv }) {
    if (!this.touches.has(pointerId)) return;
    if (!uv) return this.#touchEnd(pointerId); // finger slid off the glass
    const { x, y } = this.uvToPixel(uv);
    const prev = this.touches.get(pointerId);
    if (prev.x !== x || prev.y !== y) this.touch('move', x, y, pointerId);
  }

  onPointerUp({ pointerId }) {
    this.#touchEnd(pointerId);
  }

  describe(intersection) {
    const d = super.describe();
    d.resolution = [this.width, this.height];
    if (intersection?.uv) d.pixel = this.uvToPixel(intersection.uv);
    return d;
  }

  /**
   * Command form, e.g. over a worker/WebSocket bridge:
   *   { type:'display', target:'lcd', format:'rgb565'|'rgba'|'rgb888', x,y,w,h, data, swapBytes }
   *   { type:'display', target:'lcd', fill:'#000' }
   *   { type:'display', target:'lcd', backlight:0.5 } / { power:false } / { style:'oled' } / { touch:true }
   */
  handle(cmd) {
    if (cmd.type !== 'display') return super.handle(cmd);
    if (cmd.data) {
      const fmt = cmd.format ?? 'rgb565';
      if (fmt === 'rgb565') this.writeRGB565(cmd.data, cmd, { swapBytes: !!cmd.swapBytes });
      else if (fmt === 'rgba' || fmt === 'rgba8888') this.writeRGBA(cmd.data, cmd);
      else if (fmt === 'rgb888' || fmt === 'rgb') this.writeRGB888(cmd.data, cmd);
      else throw new Error(`Unknown pixel format "${fmt}"`);
    }
    if (cmd.fill != null) this.fill(cmd.fill, cmd.rect);
    if (cmd.backlight != null) this.setBacklight(cmd.backlight);
    if (cmd.power != null) this.setPower(cmd.power);
    if (cmd.style != null) this.setStyle(cmd.style);
    if (cmd.pixelEffect != null) this.setPixelEffect(cmd.pixelEffect);
    if (cmd.touch != null) this.setTouchEnabled(cmd.touch);
  }

  update() {
    if (this.#dirty) {
      this.#dirty = false;
      this.texture.needsUpdate = true;
    }
    return false;
  }

  getState() {
    return {
      width: this.width, height: this.height, backlight: this.backlight, powered: this.powered,
      style: this.style, touch: this.touchEnabled, touches: [...this.touches.values()],
    };
  }

  dispose() {
    if (this.#disposed) return;
    this.#disposed = true;
    this.touchEnabled = false;
    this.#clearTouches(false);
    // This class owns the framebuffer texture. Reflective displays also use
    // it as a material map, which Component.dispose() would otherwise dispose
    // a second time while traversing the panel.
    this.object3d.traverse((object) => {
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of materials) if (material?.map === this.texture) material.map = null;
    });
    this.texture.dispose();
    super.dispose();
  }
}
