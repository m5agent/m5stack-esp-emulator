import { DeviceViewer } from './vendor/sticks3/src/core/DeviceViewer.js';

function node(tag, className, text = null) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function drawIdle(display, device) {
  const context = display.getContext2D();
  const width = display.width;
  const height = display.height;
  const gradient = context.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, '#07111a');
  gradient.addColorStop(.55, '#111827');
  gradient.addColorStop(1, '#1f2937');
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
  context.fillStyle = 'rgba(255,255,255,.09)';
  for (let x = 0; x < width; x += 18) context.fillRect(x, 0, 1, height);
  for (let y = 0; y < height; y += 18) context.fillRect(0, y, width, 1);
  context.fillStyle = '#f3f6fa';
  context.font = `700 ${Math.max(18, Math.round(width / 12))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  context.textAlign = 'center';
  context.fillText(device.name, width / 2, height * .4);
  context.fillStyle = '#9fb0c3';
  context.font = `600 ${Math.max(10, Math.round(width / 24))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  context.fillText('3D 结构模型', width / 2, height * .49);
  context.fillText(`${display.width} × ${display.height}`, width / 2, height * .56);
  context.fillStyle = 'rgba(255,255,255,.16)';
  context.fillRect(width * .2, height * .63, width * .6, 1);
  context.fillStyle = '#7f91a6';
  context.font = `500 ${Math.max(9, Math.round(width / 30))}px -apple-system, BlinkMacSystemFont, sans-serif`;
  context.fillText('实时画面由 QEMU 会话接入', width / 2, height * .7);
  display.present();
}

export class ThreeDeviceShell {
  constructor(host, device, {
    rendererId,
    modelFactory,
    controlMap = {},
    ledTarget = null,
    defaultView = 'front',
    fitPadding = 1.15,
    hint = '拖拽旋转 · 滚轮缩放 · 双击复位'
  }) {
    this.host = host;
    this.device = device;
    this.rendererId = rendererId;
    this.modelFactory = modelFactory;
    this.controlMap = controlMap;
    this.ledTarget = ledTarget;
    this.defaultView = defaultView;
    this.fitPadding = fitPadding;
    this.hintText = hint;
    this.listeners = { control: [], touch: [] };
    this.frameSeq = 0;
    this.mount();
  }

  mount() {
    const { device, host } = this;
    const root = node('div', 'device-shell-root three-device-root');
    root.dataset.device = device.id;
    root.dataset.renderer = this.rendererId;

    const photoRoot = node('div', 'device-photo-root three-device-photo-root');
    if (device.shell.reference_image) {
      const photo = node('img', 'device-photo');
      photo.src = device.shell.reference_image;
      photo.alt = `${device.name} 官方实物图`;
      photoRoot.append(photo);
    } else {
      photoRoot.hidden = true;
    }

    const stage = node('div', 'three-device-stage');
    const overlay = node('div', 'three-device-overlay');
    const overlayCard = node('div', 'three-device-overlay-card');
    const overlayTitle = node('b');
    const overlayBody = node('span');
    overlayCard.append(overlayTitle, overlayBody);
    overlay.append(overlayCard);
    overlay.hidden = true;

    const hint = node('div', 'three-device-hint', this.hintText);
    root.append(photoRoot, stage, overlay, hint);
    host.replaceChildren(root);

    this.photoRoot = photoRoot;
    this.stage = stage;
    this.overlay = overlay;
    this.overlayTitle = overlayTitle;
    this.overlayBody = overlayBody;
    this.hint = hint;
    this.viewer = new DeviceViewer(stage, {
      background: null,
      shadows: true,
      ground: true,
      keyboard: false,
      fov: 25,
      minDistance: 36,
      maxDistance: 500
    });
    this.model = this.modelFactory();
    this.viewer.mount(this.model);
    this.display = this.model.display('lcd');
    this.model.on('input', event => this.handleInput(event));
    this.viewer.setView(this.defaultView, { duration: 0 });
    this.viewer.fit({ padding: this.fitPadding, duration: 0 });
    drawIdle(this.display, device);
    this.setViewMode(device.shell.reference_image ? 'photo' : 'shell');
  }

  handleInput(event) {
    if (event.kind === 'display') {
      const down = event.action !== 'end';
      for (const callback of this.listeners.touch) {
        callback({ x: event.x, y: event.y, down, action: event.action });
      }
      return;
    }
    if (event.kind !== 'button') return;
    const id = this.controlMap[event.id] || event.id;
    if (event.action !== 'down' && event.action !== 'up') return;
    const down = event.action === 'down';
    const gpioLabel = this.model.button(event.id)?.meta?.gpio;
    const gpioMatch = /^G(\d+)$/.exec(gpioLabel || '');
    for (const callback of this.listeners.control) {
      callback({ id, gpio: gpioMatch ? Number(gpioMatch[1]) : null, down, source: event.source });
    }
  }

  on(event, callback) {
    (this.listeners[event] ||= []).push(callback);
    return this;
  }

  setViewMode(mode) {
    this.viewMode = mode;
    this.photoRoot.hidden = mode !== 'photo';
    this.stage.hidden = mode === 'photo';
    this.hint.hidden = mode === 'photo';
    if (mode === 'shell') {
      requestAnimationFrame(() => {
        this.viewer.resize();
        this.viewer.fit({ padding: this.fitPadding, duration: 0 });
      });
    }
  }

  showOverlay(title, detail = '') {
    this.overlayTitle.textContent = title;
    this.overlayBody.innerHTML = detail;
    this.overlay.hidden = false;
  }

  hideOverlay() {
    this.overlay.hidden = true;
  }

  setFrame(pixels, width, height, sequence = ++this.frameSeq) {
    if (width !== this.display.width || height !== this.display.height) {
      this.showOverlay(
        'Framebuffer mismatch',
        `收到 ${width}×${height}，${this.device.name} 面板为 ${this.display.width}×${this.display.height}`
      );
      return;
    }
    const bytes = pixels instanceof Uint8Array ? pixels : new Uint8Array(pixels);
    this.display.writeRGB565(
      bytes,
      { x: 0, y: 0, w: width, h: height },
      { swapBytes: true }
    );
    this.frameSeq = sequence;
    this.hideOverlay();
  }

  async setImage(image, sequence = ++this.frameSeq) {
    const bitmap = await createImageBitmap(image);
    try {
      const context = this.display.getContext2D();
      context.clearRect(0, 0, this.display.width, this.display.height);
      context.drawImage(bitmap, 0, 0, this.display.width, this.display.height);
      this.display.present();
      this.frameSeq = sequence;
      this.hideOverlay();
    } finally {
      bitmap.close();
    }
  }

  setLed(color) {
    if (!color || !this.ledTarget) return;
    this.model.handle({ type: 'led', target: this.ledTarget, color, on: true });
  }

  frameDataUrl() {
    return this.viewer.screenshot();
  }

  dispose() {
    this.viewer.dispose();
  }
}
