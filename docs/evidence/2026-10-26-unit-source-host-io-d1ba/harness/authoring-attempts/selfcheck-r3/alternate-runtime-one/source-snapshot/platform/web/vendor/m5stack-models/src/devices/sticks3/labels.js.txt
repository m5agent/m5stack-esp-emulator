// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
/**
 * 2D-canvas painters for the StickS3 printed artwork (back pinout sticker,
 * side print, connector faces). Each painter has the signature used by
 * `paintTexture(wMm, hMm, draw)`: (ctx, W, H, s) where `s` = px per mm.
 */

const FONT = '"Arial Narrow", "Helvetica Neue", Arial, sans-serif';

function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function tag(ctx, s, x, y, w, h, bg, fg, text, size = 1.5, weight = 700) {
  ctx.fillStyle = bg;
  rr(ctx, x * s, y * s, w * s, h * s, 0.3 * s);
  ctx.fill();
  ctx.fillStyle = fg;
  ctx.font = `${weight} ${size * s}px ${FONT}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, (x + w / 2) * s, (y + h / 2) * s + 0.05 * s, w * s * 0.94);
}

function text(ctx, s, x, y, str, { size = 1.2, color = '#222', weight = 700, align = 'left' } = {}) {
  ctx.fillStyle = color;
  ctx.font = `${weight} ${size * s}px ${FONT}`;
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  ctx.fillText(str, x * s, y * s);
}

/** Back pinout sticker, 21 × 33.5 mm. Columns line up with the Hat2 header (2.54 mm pitch). */
export function paintBackLabel(ctx, W, H, s) {
  ctx.save();
  rr(ctx, 0, 0, W, H, 1.6 * s);
  ctx.clip();
  ctx.fillStyle = '#f3f3f0';
  ctx.fillRect(0, 0, W, H);

  // Header pin rows (seen from the back: left = device right side = pins 1/2).
  const pitch = 2.54, x0 = 21 / 2 - 4 * pitch;
  const top = ['G5', 'G4', 'G6', 'G7', 'G43', 'G44', 'G2', 'G3'];
  const bottom = [
    ['GND', '#1b1b1b', '#fff'], ['EXT\n5V', '#e0301e', '#fff'], ['G0', '#d9d9d9', '#111'], ['G1', '#d9d9d9', '#111'],
    ['G8', '#d9d9d9', '#111'], ['BAT', '#f5c400', '#111'], ['3V3\nL2', '#e0301e', '#fff'], ['5VIN', '#e0301e', '#fff'],
  ];
  for (let i = 0; i < 8; i++) {
    const x = x0 + i * pitch;
    ctx.fillStyle = i % 2 ? '#cfcfcf' : '#bdbdbd';
    ctx.fillRect(x * s, 0, pitch * s, 2.6 * s);
    text(ctx, s, x + pitch / 2, 1.35, top[i], { size: 1.05, align: 'center', color: '#111' });
    const [label, bg, fg] = bottom[i];
    ctx.fillStyle = bg;
    ctx.fillRect(x * s, 2.6 * s, pitch * s, 2.8 * s);
    const lines = label.split('\n');
    lines.forEach((l, k) => text(ctx, s, x + pitch / 2, 4.0 + (k - (lines.length - 1) / 2) * 1.05, l,
      { size: lines.length > 1 ? 0.9 : 1.0, align: 'center', color: fg }));
  }

  tag(ctx, s, 1.0, 6.2, 2.4, 1.6, '#e0301e', '#fff', 'IRTX', 0.9);
  tag(ctx, s, 1.0, 7.9, 2.4, 1.4, '#e0301e', '#fff', 'G46', 0.9);
  tag(ctx, s, 4.0, 6.1, 8.0, 2.2, '#2f8fe0', '#fff', 'M5STICK·S3', 1.5);
  tag(ctx, s, 17.4, 6.2, 2.6, 1.6, '#24a148', '#fff', 'IRRX', 0.9);
  tag(ctx, s, 17.4, 7.9, 2.6, 1.4, '#24a148', '#fff', 'G42', 0.9);

  // Audio / LCD block
  tag(ctx, s, 1.0, 10.0, 2.6, 2.2, '#2a2a2a', '#fff', 'AW', 1.1);
  tag(ctx, s, 3.8, 10.6, 2.4, 2.2, '#2a2a2a', '#fff', 'ES', 1.1);
  ['MCLK:G18', 'DOUT:G14', 'BCLK:G17', 'LRCK:G15', 'DIN:G16'].forEach((l, i) =>
    text(ctx, s, 6.5, 9.7 + i * 0.85, l, { size: 0.75, color: '#333' }));
  ctx.strokeStyle = '#2f5fe0';
  ctx.lineWidth = 0.15 * s;
  rr(ctx, 11.4 * s, 9.2 * s, 8.8 * s, 5.2 * s, 0.3 * s);
  ctx.stroke();
  text(ctx, s, 15.8, 10.0, '1.14" IPS-LCD', { size: 0.95, align: 'center', color: '#111' });
  tag(ctx, s, 11.8, 10.8, 8.0, 1.4, '#5b6be8', '#fff', 'ST7789P3', 1.0);
  text(ctx, s, 11.9, 12.8, 'MOSI:G39 RST:G21', { size: 0.62, color: '#333' });
  text(ctx, s, 11.9, 13.6, 'SCK:G40  CS:G41', { size: 0.62, color: '#333' });

  // Pseudo circuit traces
  ctx.strokeStyle = '#d2452c';
  ctx.lineWidth = 0.12 * s;
  ctx.beginPath();
  for (const [a, b, c, d] of [[3, 15, 3, 24], [3, 24, 9, 24], [6, 16, 10, 18], [10, 18, 10, 27], [4, 27, 13, 27], [13, 22, 13, 29]]) {
    ctx.moveTo(a * s, b * s); ctx.lineTo(c * s, d * s);
  }
  ctx.stroke();
  tag(ctx, s, 1.0, 15.0, 2.6, 1.8, '#3d8fd1', '#fff', 'BMI', 0.9);
  text(ctx, s, 3.9, 15.5, 'SCL:G48', { size: 0.7, color: '#333' });
  text(ctx, s, 3.9, 16.3, 'SDA:G47', { size: 0.7, color: '#333' });
  tag(ctx, s, 6.2, 17.6, 3.4, 1.2, '#b3261e', '#fff', 'LDO', 0.8);
  tag(ctx, s, 1.0, 19.6, 2.4, 1.6, '#2fbf5a', '#fff', 'PM', 1.0);
  tag(ctx, s, 6.2, 20.8, 3.4, 1.4, '#222', '#fff', 'SW', 0.8);
  tag(ctx, s, 1.0, 22.6, 1.6, 6.0, '#f0a0e0', '#222', '', 0.8);
  ctx.save();
  ctx.translate(1.8 * s, 25.6 * s);
  ctx.rotate(-Math.PI / 2);
  text(ctx, s, 0, 0, 'KEY2:G12', { size: 0.85, align: 'center', color: '#222' });
  ctx.restore();
  tag(ctx, s, 8.6, 23.4, 3.4, 1.4, '#e3542c', '#fff', 'DC/DC', 0.8);
  tag(ctx, s, 3.0, 28.4, 4.2, 1.4, '#e3542c', '#fff', 'CHG-IC', 0.8);

  // Espressif-ish chip mark + certification marks
  ctx.fillStyle = '#e8432e';
  rr(ctx, 12.8 * s, 15.6 * s, 3.4 * s, 3.4 * s, 0.6 * s);
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 0.28 * s;
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(13.6 * s, 18.2 * s, (0.8 + i * 0.75) * s, -Math.PI / 2, 0);
    ctx.stroke();
  }
  text(ctx, s, 17.0, 16.5, 'FC', { size: 1.9, color: '#111', weight: 800 });
  text(ctx, s, 17.0, 18.6, 'CE', { size: 1.9, color: '#111', weight: 800 });
  text(ctx, s, 9.0, 19.8, 'ESP32S3-N8R8', { size: 0.7, color: '#222' });
  text(ctx, s, 9.0, 20.6, 'Model: M5STICKS3', { size: 0.62, color: '#222' });

  // M5 STACK logo, KEY1 tag
  text(ctx, s, 14.4, 24.0, 'M5', { size: 3.6, color: '#2f8fe0', weight: 400 });
  text(ctx, s, 14.6, 26.4, 'STACK', { size: 1.3, color: '#111', weight: 800 });
  tag(ctx, s, 13.6, 27.3, 6.6, 1.7, '#2f6fb8', '#fff', 'KEY1:G11', 1.2);
  text(ctx, s, 20.2, 29.7, 'HOLD:BOOT', { size: 0.7, align: 'right' });
  text(ctx, s, 20.2, 30.5, 'Double:OFF', { size: 0.7, align: 'right' });
  text(ctx, s, 20.2, 31.3, 'Press:ON', { size: 0.7, align: 'right' });

  // Port A legend
  text(ctx, s, 10.4, 30.4, 'PORT.A', { size: 1.0, align: 'center', color: '#222', weight: 400 });
  tag(ctx, s, 7.4, 31.4, 1.6, 1.3, '#1b1b1b', '#fff', 'GND', 0.55);
  tag(ctx, s, 9.1, 31.4, 1.6, 1.3, '#e0301e', '#fff', '5V', 0.7);
  tag(ctx, s, 10.8, 31.4, 1.6, 1.3, '#f5c400', '#111', 'G9', 0.75);
  tag(ctx, s, 12.5, 31.4, 1.8, 1.3, '#f3f3f0', '#111', 'G10', 0.75);
  text(ctx, s, 3.0, 31.6, 'USB · MIC', { size: 0.7, color: '#333' });
  ctx.restore();
}

/** "STICK S3" print running down the left side, 26 × 3.6 mm. */
export function paintSidePrint(ctx, W, H, s) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(205,207,212,0.85)';
  ctx.font = `500 ${2.1 * s}px ${FONT}`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${0.55 * s}px`;
  ctx.fillText('STICK', 4.5 * s, H / 2 + 0.1 * s);
  if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
  ctx.fillStyle = '#1e88e5';
  rr(ctx, 18.6 * s, 0.2 * s, 5.0 * s, H - 0.4 * s, 0.25 * s);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.font = `800 ${2.4 * s}px ${FONT}`;
  ctx.textAlign = 'center';
  ctx.fillText('S3', 21.1 * s, H / 2 + 0.1 * s);
}

/** 2×8 female header face, 20.6 × 5.4 mm. Row 0 (canvas top) is the back row. */
export function paintHeaderFace(ctx, W, H, s) {
  ctx.fillStyle = '#151516';
  ctx.fillRect(0, 0, W, H);
  const pitch = 2.54, hole = 1.05;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 8; c++) {
      const cx = (W / s) / 2 + (c - 3.5) * pitch, cy = (H / s) / 2 + (r - 0.5) * pitch;
      const x = (cx - hole / 2) * s, y = (cy - hole / 2) * s, w = hole * s;
      // funnel chamfer
      ctx.fillStyle = '#2a2a2c';
      ctx.fillRect(x - 0.35 * s, y - 0.35 * s, w + 0.7 * s, w + 0.7 * s);
      ctx.fillStyle = '#000';
      ctx.fillRect(x, y, w, w);
      ctx.fillStyle = 'rgba(190,150,70,0.55)';
      ctx.fillRect(x + w * 0.3, y + w * 0.25, w * 0.4, w * 0.12);
    }
  }
}

/** HY2.0-4P (Grove) receptacle face, 9.9 × 5.2 mm. */
export function paintGroveFace(ctx, W, H, s) {
  ctx.fillStyle = '#f2f1ec';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#101010';
  rr(ctx, 0.9 * s, 0.9 * s, W - 1.8 * s, H - 1.9 * s, 0.25 * s);
  ctx.fill();
  ctx.fillStyle = '#d8d8d8';
  for (let i = 0; i < 4; i++) ctx.fillRect((2.35 + i * 2.0 - 0.25) * s, 1.8 * s, 0.5 * s, 1.8 * s);
  ctx.fillStyle = '#f2f1ec';
  ctx.fillRect(W / 2 - 1.6 * s, H - 1.05 * s, 3.2 * s, 0.3 * s);
}
