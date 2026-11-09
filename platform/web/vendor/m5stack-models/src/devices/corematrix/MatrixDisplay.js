import {Display} from '../../core/index.js';

// One draw call and one framebuffer upload for all 256 independent emitters.
// The dark molded lens and the slightly softened white squares follow C158's
// front view. This is a visual transfer function, not TM1680 PWM timing.
const fragmentShader = /* glsl */ `
uniform sampler2D map;
uniform vec2 res;
uniform float brightness;
varying vec2 vUv;

void main() {
  vec2 pixel = vec2(vUv.x, 1.0 - vUv.y) * res;
  vec2 cell = clamp(floor(pixel), vec2(0.0), res - 1.0);
  vec3 rgb = texture2D(map, (cell + 0.5) / res).rgb;
  float light = dot(rgb, vec3(0.2126, 0.7152, 0.0722)) * brightness;
  vec2 d = abs(pixel - cell - 0.5);
  float aa = max(fwidth(pixel.x), fwidth(pixel.y)) * 0.5;
  float center = 1.0 - smoothstep(0.145 - aa, 0.145 + aa, max(d.x, d.y));
  float halo = exp(-dot(d, d) * 38.0);
  vec3 shade = vec3(0.013, 0.014, 0.016);
  gl_FragColor = vec4(shade + light * (center * 1.1 + halo * 0.27), 1.0);
  #include <colorspace_fragment>
}`;

export class MatrixDisplay extends Display {
  constructor(options) {
    super({...options, style: 'led', glass: false});
    this.material.fragmentShader = fragmentShader;
  }

  /** Write 8-bit intensities in front-view row-major order (0,0 is top left). */
  writeGray8(data, rect = {}) {
    const x = rect.x ?? 0;
    const y = rect.y ?? 0;
    const w = rect.w ?? rect.width ?? this.width - x;
    const h = rect.h ?? rect.height ?? this.height - y;
    if (![x, y, w, h].every(Number.isSafeInteger) || w < 1 || h < 1
      || w > this.width || h > this.height) {
      throw new RangeError('Invalid CoreMatrix gray8 rectangle');
    }
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    if (bytes.length !== w * h) throw new RangeError('Expected one gray8 byte per pixel');
    const rgb = new Uint8Array(bytes.length * 3);
    for (let i = 0; i < bytes.length; i++) rgb.fill(bytes[i], i * 3, i * 3 + 3);
    this.writeRGB888(rgb, {x, y, w, h});
  }

  handle(command) {
    if (command.type === 'display' && command.format === 'gray8' && command.data != null) {
      this.writeGray8(command.data, command);
      return super.handle({...command, data: undefined});
    }
    return super.handle(command);
  }

  setStyle(style) {
    if (style !== 'led') throw new RangeError('CoreMatrix display style is fixed to led');
  }
}
