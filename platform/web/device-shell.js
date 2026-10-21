const DEVICE_LAYOUTS = {
  sticks3: { bodyW: 240, bodyH: 480, radius: '30px', bezel: 12 },
  cores3: { bodyW: 430, bodyH: 430, radius: '30px', bezel: 18 },
  stopwatch: { bodyW: 500, bodyH: 500, radius: '50%', bezel: 20 },
  'cardputer-adv': { bodyW: 620, bodyH: 400, radius: '24px', bezel: 10 },
  'cardputer-zero': { bodyW: 620, bodyH: 400, radius: '24px', bezel: 10 },
  papermono: { bodyW: 360, bodyH: 586, radius: '22px', bezel: 12 },
  core2: { bodyW: 430, bodyH: 430, radius: '28px', bezel: 18 },
  papercolor: { bodyW: 380, bodyH: 560, radius: '22px', bezel: 12 },
  nanoc6: { bodyW: 230, bodyH: 451, radius: '34px', bezel: 0 },
  stackchan: { bodyW: 470, bodyH: 410, radius: '36px', bezel: 14 },
  tab5: { bodyW: 380, bodyH: 608, radius: '24px', bezel: 16 },
  atoms3r: { bodyW: 300, bodyH: 300, radius: '32px', bezel: 12 },
  'nesso-n1': { bodyW: 360, bodyH: 480, radius: '32px', bezel: 12 },
  stamplc: { bodyW: 450, bodyH: 500, radius: '14px', bezel: 9 }
};

const DECORATIONS = {
  sticks3: `<div class="deco-logo top">M5</div><div class="deco-stick-blue"></div><div class="deco-speaker small"></div>`,
  cores3: `<div class="deco-camera"></div><div class="deco-core-buttons"><i class="red"></i><i></i><i></i></div><div class="deco-logo bottom">M5STACK</div>`,
  stopwatch: `<div class="deco-crown"></div><div class="deco-logo bottom">STOPWATCH</div>`,
  'cardputer-adv': `<div class="deco-trackball orange"></div><div class="deco-speaker wide"></div><div class="deco-logo bottom">M5STACK · CARDPUTER ADV</div>`,
  'cardputer-zero': `<div class="deco-trackball silver"></div><div class="deco-speaker wide"></div><div class="deco-logo bottom">M5STACK · CARDPUTER ZERO</div>`,
  papermono: `<div class="deco-paper-buttons"><i></i><i class="orange"></i></div><div class="deco-paper-logo">PAPER · MONO</div>`,
  core2: `<div class="deco-core2-buttons"><i class="blue"></i><i></i><i class="red"></i></div><div class="deco-logo bottom">CORE2</div>`,
  papercolor: `<div class="deco-paper-buttons"><i></i><i></i><i class="orange"></i></div><div class="deco-paper-logo color">M5 · PAPER COLOR</div>`,
  nanoc6: `<div class="deco-usb-a"></div><div class="deco-rgb-orb"></div><div class="deco-logo bottom">M5 NANO C6</div>`,
  stackchan: `<div class="deco-servo-base"></div><div class="deco-arm left"></div><div class="deco-arm right"></div><div class="deco-camera"></div><div class="deco-logo bottom">STACKCHAN</div>`,
  tab5: `<div class="deco-tablet-edge"></div><div class="deco-camera right"></div><div class="deco-logo bottom">M5 TAB5</div>`,
  atoms3r: `<div class="deco-atom-button"></div><div class="deco-usb-c"></div><div class="deco-atom-pins"></div><div class="deco-logo bottom">ATOM S3R</div>`,
  'nesso-n1': `<div class="deco-rugged-stripe"></div><div class="deco-antenna"></div><div class="deco-nesso-buttons"><i></i><i></i></div><div class="deco-logo bottom">NESSO N1</div>`,
  stamplc: `<div class="deco-plc-label">STAMPLC</div><div class="deco-terminal left"></div><div class="deco-terminal right"></div><div class="deco-led-strip"></div>`
};

const LAYOUTS = {
  'watch-round': { bodyW: 500, bodyH: 500, radius: '50%', bezel: 20 },
  stick: { bodyW: 270, bodyH: 500, radius: '34px', bezel: 10 },
  core: { bodyW: 510, bodyH: 390, radius: '28px', bezel: 12 },
  cardputer: { bodyW: 620, bodyH: 410, radius: '26px', bezel: 10 },
  paper: { bodyW: 390, bodyH: 590, radius: '18px', bezel: 12 },
  tab: { bodyW: 700, bodyH: 460, radius: '24px', bezel: 14 },
  atom: { bodyW: 310, bodyH: 310, radius: '32px', bezel: 10 },
  robot: { bodyW: 480, bodyH: 540, radius: '34% 34% 22% 22%', bezel: 12 },
  industrial: { bodyW: 520, bodyH: 390, radius: '14px', bezel: 9 },
  'console-only': { bodyW: 220, bodyH: 360, radius: '28px', bezel: 0 }
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function drawIdle(canvas, device) {
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas;
  if (!width || !height) return;
  const grad = ctx.createLinearGradient(0, 0, width, height);
  grad.addColorStop(0, '#07111a');
  grad.addColorStop(.5, '#111827');
  grad.addColorStop(1, '#1f2937');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = 'rgba(255,255,255,.08)';
  for (let x = 0; x < width; x += 18) ctx.fillRect(x, 0, 1, height);
  for (let y = 0; y < height; y += 18) ctx.fillRect(0, y, width, 1);
  ctx.fillStyle = '#e6edf3';
  ctx.font = `700 ${Math.max(14, Math.round(width / 15))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(device.name, width / 2, height * .44);
  ctx.fillStyle = '#93a4b8';
  ctx.font = `500 ${Math.max(9, Math.round(width / 34))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.fillText(`${device.hardware.soc} · ${device.runtime.status}`, width / 2, height * .53);
  ctx.fillStyle = 'rgba(255,255,255,.12)';
  ctx.fillRect(width * .28, height * .6, width * .44, 1);
  ctx.fillStyle = '#7d8da1';
  ctx.font = `500 ${Math.max(8, Math.round(width / 42))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  const hint = device.runtime.status === 'reference-ready' ? 'Open the reference runtime for live firmware' : device.uiflow2?.supported ? 'Load UIFlow2 firmware to begin' : 'No UIFlow2 firmware for this target';
  ctx.fillText(hint, width / 2, height * .66);
}

export class M5DeviceShell {
  constructor(host, device) {
    this.host = host;
    this.device = device;
    this.listeners = { control: [], touch: [] };
    this.frameSeq = 0;
    this.mount();
  }

  mount() {
    const { device } = this;
    const display = device.hardware.display;
    const layout = DEVICE_LAYOUTS[device.id] || LAYOUTS[device.shell.preset] || LAYOUTS.core;
    this.host.innerHTML = '';
    const root = el('div', 'device-shell-root');
    const photoRoot = el('div', 'device-photo-root');
    if (device.shell.reference_image) {
      const photo = el('img', 'device-photo');
      photo.src = device.shell.reference_image;
      photo.alt = `${device.name} 官方实物图`;
      photoRoot.append(photo);
    } else {
      photoRoot.hidden = true;
    }
    const body = el('div', 'device-body');
    body.dataset.preset = device.shell.preset;
    body.dataset.device = device.id;
    body.dataset.theme = device.shell.body_theme || 'graphite';
    const scale = device.shell.screen_scale || 1;
    const screenW = display ? Math.round(display.width * scale) : 0;
    const screenH = display ? Math.round(display.height * scale) : 0;
    body.style.setProperty('--body-w', `${layout.bodyW}px`);
    body.style.setProperty('--body-h', `${layout.bodyH}px`);
    body.style.setProperty('--body-radius', layout.radius);
    body.style.setProperty('--screen-w', `${screenW}px`);
    body.style.setProperty('--screen-h', `${screenH}px`);
    body.style.setProperty('--screen-radius', display?.shape === 'circle' ? '50%' : '8px');
    body.style.setProperty('--bezel', `${layout.bezel}px`);
    body.style.setProperty('--screen-cursor', display?.touch ? 'crosshair' : 'default');
    body.style.setProperty('--device-accent', device.shell.accent || '#58a6ff');

    if (display) {
      const frame = el('div', 'device-screen-frame');
      this.canvas = el('canvas', 'device-screen');
      this.canvas.width = display.width;
      this.canvas.height = display.height;
      this.canvas.setAttribute('aria-label', `${device.name} display`);
      frame.append(this.canvas, el('div', 'device-glare'));
      this.overlay = el('div', 'device-screen-overlay');
      frame.append(this.overlay);
      this.overlay.innerHTML = `<div><b>${device.name}</b>${this.runtimeText()}<small>${display.width}×${display.height} ${display.type}</small></div>`;
      this.overlay.hidden = device.runtime.status === 'reference-ready';
      body.append(frame);
      drawIdle(this.canvas, device);
      if (display.touch) {
        const emitTouch = (event, down) => {
          const rect = this.canvas.getBoundingClientRect();
          const x = Math.max(0, Math.min(display.width - 1, Math.round((event.clientX - rect.left) * display.width / rect.width)));
          const y = Math.max(0, Math.min(display.height - 1, Math.round((event.clientY - rect.top) * display.height / rect.height)));
          for (const cb of this.listeners.touch) cb({ x, y, down });
        };
        this.canvas.addEventListener('pointerdown', event => {
          this.canvas.setPointerCapture(event.pointerId);
          emitTouch(event, true);
        });
        this.canvas.addEventListener('pointermove', event => {
          if (event.buttons) emitTouch(event, true);
        });
        this.canvas.addEventListener('pointerup', event => emitTouch(event, false));
        this.canvas.addEventListener('pointercancel', () => {
          for (const cb of this.listeners.touch) cb({ x: 0, y: 0, down: false });
        });
      }
    }

    const controls = el('div', 'device-controls');
    controls.dataset.preset = device.shell.preset;
    const buttons = (device.hardware.controls || []).filter(item => item.type === 'button');
    buttons.forEach((item, index) => {
      const button = el('button', 'device-control', item.label || item.id);
      button.dataset.slot = String(index);
      button.dataset.controlId = item.id;
      const down = event => {
        event.preventDefault();
        button.classList.add('on');
        for (const cb of this.listeners.control) cb({ id: item.id, gpio: item.gpio ?? null, down: true });
      };
      const up = () => {
        button.classList.remove('on');
        for (const cb of this.listeners.control) cb({ id: item.id, gpio: item.gpio ?? null, down: false });
      };
      button.addEventListener('pointerdown', down);
      button.addEventListener('pointerup', up);
      button.addEventListener('pointercancel', up);
      button.addEventListener('pointerleave', event => { if (event.buttons) up(); });
      controls.append(button);
    });

    if ((device.hardware.controls || []).some(item => item.type === 'keyboard')) {
      const keyboard = el('div', 'device-keyboard');
      const count = Math.min(device.hardware.keyboard?.keys || 56, 70);
      for (let i = 0; i < count; i++) keyboard.append(el('span'));
      controls.append(keyboard);
    }

    const led = el('div', 'device-led');
    controls.append(led, el('div', 'device-label', device.name));
    body.append(controls);
    const decorations = el('div', 'device-decorations');
    decorations.innerHTML = DECORATIONS[device.id] || '';
    body.append(decorations);
    root.append(photoRoot, body);
    this.host.append(root);
    this.photoRoot = photoRoot;
    this.body = body;
    this.controls = controls;
    this.setViewMode(device.shell.reference_image ? 'photo' : 'shell');
  }

  runtimeText() {
    const runtime = this.device.runtime;
    if (runtime.execution === 'native-qemu' || runtime.backend?.startsWith('qemu-')) {
      return runtime.status === 'reference-ready' ? 'QEMU 虚拟主机已验证' : '本地 QEMU 虚拟主机';
    }
    if (runtime.status === 'reference-ready') return '真实固件参考运行时';
    if (runtime.status === 'boot-capable') return '固件启动后端已就绪';
    return runtime.reason || '需要独立后端';
  }

  setViewMode(mode) {
    this.viewMode = mode;
    if (this.photoRoot) this.photoRoot.hidden = mode !== 'photo';
    if (this.body) this.body.hidden = mode === 'photo';
  }

  on(event, callback) {
    (this.listeners[event] ||= []).push(callback);
    return this;
  }

  showOverlay(title, detail) {
    if (!this.overlay) return;
    this.overlay.hidden = false;
    this.overlay.innerHTML = `<div><b>${title}</b>${detail || ''}</div>`;
  }

  hideOverlay() {
    if (this.overlay) this.overlay.hidden = true;
  }

  setFrame(pixels, width, height, sequence = ++this.frameSeq) {
    if (!this.canvas) return;
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    const ctx = this.canvas.getContext('2d');
    const image = ctx.createImageData(width, height);
    const data = image.data;
    const source = pixels instanceof Uint8Array ? pixels : new Uint8Array(pixels);
    for (let i = 0, j = 0; i + 1 < source.length; i += 2, j += 4) {
      const value = (source[i] << 8) | source[i + 1];
      data[j] = ((value >> 11) & 31) * 255 / 31;
      data[j + 1] = ((value >> 5) & 63) * 255 / 63;
      data[j + 2] = (value & 31) * 255 / 31;
      data[j + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
    this.frameSeq = sequence;
    this.hideOverlay();
  }

  setLed(color) {
    const led = this.controls?.querySelector('.device-led');
    if (led && color) {
      led.style.background = color;
      led.style.boxShadow = `0 0 18px ${color}, 0 0 4px #fff inset`;
    }
  }

  frameDataUrl() {
    return this.canvas ? this.canvas.toDataURL('image/png') : null;
  }
}
