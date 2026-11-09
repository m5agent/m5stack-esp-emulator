export const spec = {
  name: 'CoreMatrix',
  sku: 'C158',
  size: [54, 54, 11.6],
  soc: 'ESP32-C61HR8',
  flashMb: 16,
  psramMb: 8,
  display: {
    width: 16,
    height: 16,
    size: [48, 46.8],
    position: [0, -.1, 5.704],
    controller: 'TM1680',
    i2cAddress: 0x72,
    sda: 0,
    scl: 1,
    enable: {controller: 'M5IOE1', i2cAddress: 0x4f, line: 4, signal: 'PYB_LEDS_EN'},
  },
};

// Right-handed millimetre frame: LED face +Z, button edge +Y.
export const cadTranslation = [-27, -27.8713, 5.8];

const pm1 = {controller: 'M5PM1', i2cAddress: 0x6e};
export const keys = [
  ...[-13, 0, 13].map((x, line) => ({
    id: ['btnA', 'btnB', 'btnC'][line],
    label: ['Button A', 'Button B', 'Button C'][line],
    position: [x, 27, -.1],
    face: 'top',
    inward: [0, -1, 0],
    tangent: 2,
    hinge: -3.85,
    tip: 2.4,
    nativeRegion: ([px, y, z]) => Math.abs(px - x) < 3.79 && y > 24.1 && z < 2.4,
    controller: {...pm1, line, signal: 'KEY' + (line + 1)},
  })),
  {
    id: 'power',
    label: 'Power button',
    position: [-27, 13.5, -.65],
    face: 'left',
    inward: [1, 0, 0],
    tangent: 1,
    hinge: 18.1658,
    tip: 9.49,
    nativeRegion: ([x, y, z]) => x < -24.1 && y > 9.49 && z > -3.33 && z < 1.93,
    controller: {...pm1, signal: 'PWR_BTN'},
  },
];

export const ports = {
  usb: {position: [-27, 0, -.82], w: 8.95, h: 3.45},
  grove: {position: [-27, -14, -1.72], w: 10.25, h: 5.32},
  microSD: {position: [7, -27, -.61], w: 12.45, h: 1.55},
  rearUSB: {position: [-22.05, 6.65, -5.59], w: 5.45, h: 8.35},
  battery: {position: [-22.05, -6.65, -5.59], w: 5.45, h: 4.5},
};
