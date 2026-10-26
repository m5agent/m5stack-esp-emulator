import * as THREE from 'three';
import { Device } from '../../core/Device.js';
import { Button } from '../../core/components/Button.js';
import { Display } from '../../core/components/Display.js';
import { Led } from '../../core/components/Led.js';
import { Speaker } from '../../core/components/Speaker.js';
import { Imu } from '../../core/components/Imu.js';
import { Port } from '../../core/components/Port.js';
import { roundedSlab, roundedRect, capsule, basisQuaternion, decal, paintTexture } from '../../core/geometry.js';
import { materials } from '../../core/materials.js';
import { paintBackLabel, paintSidePrint, paintHeaderFace, paintGroveFace } from './labels.js';

/*
 * M5Stack StickS3 (SKU K150) — dimensions in mm, from the official spec sheet
 * and product photography (see reference/sticks3/ and BUILD.md).
 *
 * Model frame: origin at the body centre, +X = right side (KEY2), +Y = top end
 * (Hat2 header / IR), +Z = front (screen). Overall 24 × 48 × 15.
 */
export const DIM = {
  W: 24, H: 48, D: 15,
  cornerR: 3.8,
  splitZ: -0.8, // front shell / rear shell seam
  frontBevel: 0.6,
  rearBevel: 0.9,
  // 1.14" ST7789P3, 135 × 240 at 0.1101 mm pitch
  lcd: { w: 14.86, h: 26.42, cx: 0, cy: 6.1, z: 6.92 },
  window: { w: 17.4, h: 29.4, cy: 6.1, r: 1.3 }, // opening at the face (bevel rolls 0.6 mm inwards)
  key1: { w: 12.2, h: 4.0, cy: -15.0 },
  key2: { y: 1.5, z: 3.2, len: 7.4, hgt: 5.6 },
  pwr: { y: -17.0, z: 3.2, len: 4.2, hgt: 3.4 },
  header: { w: 20.6, h: 5.4, depth: 3, z: -4.15 },
  grove: { w: 9.9, h: 5.2, depth: 6.25, z: -5.0 },
  usb: { w: 8.9, h: 3.2, z: 1.6 },
};

/** Hat2-Bus pinout (2 × 8, 2.54 mm). */
export const HAT2_PINS = [
  { n: 1, name: 'GND' }, { n: 2, name: 'G5' }, { n: 3, name: 'EXT_5V' }, { n: 4, name: 'G4' },
  { n: 5, name: 'BOOT (G0)' }, { n: 6, name: 'G6' }, { n: 7, name: 'G1' }, { n: 8, name: 'G7' },
  { n: 9, name: 'G8' }, { n: 10, name: 'G43' }, { n: 11, name: 'BAT' }, { n: 12, name: 'G44' },
  { n: 13, name: '3V3_L2' }, { n: 14, name: 'G2' }, { n: 15, name: '5V_IN' }, { n: 16, name: 'G3' },
];

/** USB Type-C receptacle (USB 2.0 signals only). */
export const USB_PINS = [
  { n: 1, name: 'VBUS' }, { n: 2, name: 'D− (G19)' }, { n: 3, name: 'D+ (G20)' }, { n: 4, name: 'CC' }, { n: 5, name: 'GND' },
];

/** HY2.0-4P Grove (PORT.A / PORT.CUSTOM). */
export const GROVE_PINS = [
  { n: 1, name: 'GND', wire: 'black' }, { n: 2, name: '5V', wire: 'red' },
  { n: 3, name: 'G9', wire: 'yellow' }, { n: 4, name: 'G10', wire: 'white' },
];

// Frames for parts mounted on the four side faces (local +Z = outward normal).
const FACE = {
  top: basisQuaternion([1, 0, 0], [0, 0, -1], [0, 1, 0]),
  bottom: basisQuaternion([1, 0, 0], [0, 0, 1], [0, -1, 0]),
  right: basisQuaternion([0, 1, 0], [0, 0, 1], [1, 0, 0]),
  left: basisQuaternion([0, -1, 0], [0, 0, 1], [-1, 0, 0]),
  back: basisQuaternion([-1, 0, 0], [0, 1, 0], [0, 0, -1]),
};

/**
 * M5Stack StickS3.
 *
 * Components (addressable via `device.get(id)`):
 *   lcd      Display 135×240 ST7789P3 (portrait, pixel 0,0 top-left)
 *   btnA     KEY1 — blue front key (G11)
 *   btnB     KEY2 — right side key (G12)
 *   btnPWR   power / reset side key (via M5PM1)
 *   irTx     IR LED (G46), rendered as a camera would see it
 *   speaker  ES8311 + AW8737, 8 Ω 1 W
 *   imu      BMI270 (sensor axes: X → USB end, Y → right side, Z → out of screen)
 *   hat      Port "m5.hat2" — 2×8 header on the top end
 *   grove    Port "grove"   — HY2.0-4P on the bottom end (G9/G10)
 *   usb      Port "usb-c"   — USB-C on the bottom end; plug a cable to signal VBUS
 *
 * Options: { touch=false, pixelEffect=true, caseColor, keyColor, keymap }
 */
export class StickS3 extends Device {
  static meta = {
    id: 'm5stack.sticks3',
    name: 'M5StickS3',
    vendor: 'M5Stack',
    sku: 'K150',
    size: [DIM.W, DIM.H, DIM.D],
    mcu: 'ESP32-S3-PICO-1-N8R8',
    keymap: {
      Space: 'btnA', Enter: 'btnA', KeyA: 'btnA',
      KeyB: 'btnB', ArrowRight: 'btnB',
      KeyP: 'btnPWR',
    },
  };

  build({ touch = false, pixelEffect = true, caseColor = 0x333438, keyColor = 0x1f8dff } = {}) {
    const caseMat = materials.plastic(caseColor, { roughness: 0.78, clearcoat: 0 });
    const rearMat = materials.plastic(new THREE.Color(caseColor).offsetHSL(0, 0, 0.012), { roughness: 0.82, clearcoat: 0 });
    const cavity = materials.cavity();
    this.materials = { case: caseMat, rear: rearMat };

    this.#buildShell(caseMat, rearMat, cavity);
    this.#buildFront(touch, pixelEffect, keyColor, cavity);
    this.#buildSides(caseMat);
    this.#buildTopEnd(cavity);
    this.#buildBottomEnd(cavity);
    this.#buildBack();

    this.add(new Imu({
      id: 'imu', label: 'IMU (BMI270)', axes: { x: '-y', y: '+x', z: '+z' },
      meta: { chip: 'BMI270', i2c: '0x68', scl: 'G48', sda: 'G47' },
    }));
  }

  #buildShell(caseMat, rearMat) {
    const { W, H, D, cornerR, splitZ, frontBevel, rearBevel, window: win, key1 } = DIM;
    const front = new THREE.Mesh(roundedSlab({
      w: W, h: H, depth: D / 2 - splitZ, radius: cornerR, bevel: frontBevel, curveSegments: 16,
      holes: [
        { w: win.w, h: win.h, r: win.r, cy: win.cy },
        { w: key1.w, h: key1.h, cy: key1.cy },
      ],
    }), caseMat);
    front.position.z = splitZ;
    front.name = 'front-shell';

    // The rear shell runs 1.2 mm up into the front shell so its own bevel is
    // hidden there; the visible seam is then only the front shell's small bevel.
    const rear = new THREE.Mesh(roundedSlab({
      w: W - 0.1, h: H - 0.1, depth: splitZ + 1.2 + D / 2, radius: cornerR, bevel: rearBevel, curveSegments: 16,
    }), rearMat);
    rear.position.z = -D / 2;
    rear.name = 'rear-shell';
    this.body.add(front, rear);
  }

  #buildFront(touch, pixelEffect, keyColor, cavity) {
    const { lcd, window: win, key1, D } = DIM;
    // LCD module: black glass border behind the active area.
    const bezel = new THREE.Mesh(new THREE.PlaneGeometry(win.w, win.h),
      new THREE.MeshStandardMaterial({ color: 0x040506, roughness: 0.35 }));
    bezel.position.set(0, win.cy, lcd.z - 0.03);
    this.body.add(bezel);

    this.add(new Display({
      id: 'lcd', label: 'LCD 1.14" 135×240', width: 135, height: 240, size: [lcd.w, lcd.h],
      position: [lcd.cx, lcd.cy, lcd.z], style: 'lcd', touch, pixelEffect,
      glass: { size: [win.w, win.h], offset: 0.04, intensity: 0.3, roughness: 0.12 },
      meta: { driver: 'ST7789P3', panel: 'IPS', mosi: 'G39', sck: 'G40', dc: 'G45', cs: 'G41', rst: 'G21', bl: 'G38' },
    }));

    // KEY1: blue pill key sitting in the front slot.
    const capW = key1.w - 1.6, capH = key1.h - 1.5;
    const capGeo = roundedSlab({ w: capW, h: capH, depth: 1.8, radius: capH / 2, bevel: 0.55 });
    capGeo.translate(0, 0, -1.25);
    const cap = new THREE.Mesh(capGeo, materials.glossy(keyColor, { roughness: 0.4 }));
    const well = new THREE.Mesh(new THREE.ShapeGeometry(capsule(key1.w - 1.2, key1.h - 1.2)), cavity);
    well.position.set(0, key1.cy, D / 2 - 2.0);
    this.body.add(well);
    this.add(new Button({
      id: 'btnA', label: 'KEY1 · BtnA', mesh: cap, position: [0, key1.cy, D / 2], travel: 0.45,
      meta: { gpio: 'G11', note: 'Hold at power-on: download mode' },
    }));
  }

  #buildSides(caseMat) {
    const { W, key2, pwr } = DIM;
    const keyMat = materials.plastic(new THREE.Color(caseMat.color).offsetHSL(0, 0, -0.02), { roughness: 0.6 });

    const k2 = roundedSlab({ w: key2.len, h: key2.hgt, depth: 1.6, radius: 1.2, bevel: 0.45 });
    k2.translate(0, 0, -1.1);
    this.add(new Button({
      id: 'btnB', label: 'KEY2 · BtnB', mesh: new THREE.Mesh(k2, keyMat), travel: 0.4,
      position: [W / 2, key2.y, key2.z], quaternion: FACE.right, meta: { gpio: 'G12' },
    }));

    const kp = roundedSlab({ w: pwr.len, h: pwr.hgt, depth: 1.4, radius: 0.9, bevel: 0.4 });
    kp.translate(0, 0, -1.0);
    this.add(new Button({
      id: 'btnPWR', label: 'Power / Reset', mesh: new THREE.Mesh(kp, keyMat), travel: 0.35, longPressMs: 2000,
      position: [-W / 2, pwr.y, pwr.z], quaternion: FACE.left,
      meta: { via: 'M5PM1', note: 'Press: on · Double: off · Hold: download mode' },
    }));

    const print = decal(26, 3.6, paintSidePrint, { pxPerMm: 28 });
    print.position.set(-W / 2 - 0.02, 1.0, 3.2);
    print.quaternion.copy(FACE.left);
    this.body.add(print);
  }

  #buildTopEnd(cavity) {
    const { H, header } = DIM;
    const top = H / 2;
    const face = (o, x, z) => {
      o.position.set(x, top, z);
      o.quaternion.copy(FACE.top);
      this.body.add(o);
      return o;
    };

    // Speaker grille: three slots.
    for (const x of [3.4, 1.7, 0]) {
      const slot = new THREE.Mesh(new THREE.ShapeGeometry(capsule(0.8, 2.2)), cavity);
      face(slot, x, 1.3).position.y += 0.015;
    }
    // IR receiver window (black, glossy).
    const rx = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.3, 2.1), new THREE.MeshStandardMaterial({ color: 0x08080a, roughness: 0.15 }));
    rx.position.set(-4.6, top + 0.05, 1.3);
    this.body.add(rx);

    this.add(new Led({
      id: 'irTx', label: 'IR transmitter (G46)', color: 0xb46bff, radius: 0.75, glowSize: 5, lensColor: 0xd9d9de,
      position: [8.0, top - 0.15, 1.3], quaternion: FACE.top, meta: { gpio: 'G46', note: 'Shown as a phone camera sees IR' },
    }));
    this.add(new Speaker({
      id: 'speaker', label: 'Speaker 8Ω 1W', position: [1.7, top, 1.3], quaternion: FACE.top,
      meta: { codec: 'ES8311', amp: 'AW8737' },
    }));

    // Hat2 female header — black housing with a painted hole pattern on its face.
    const housing = new THREE.MeshStandardMaterial({ color: 0x141415, roughness: 0.55 });
    const faceMat = new THREE.MeshStandardMaterial({ map: paintTexture(header.w, header.h, paintHeaderFace, { pxPerMm: 30 }), roughness: 0.6 });
    const hdr = new THREE.Mesh(new THREE.BoxGeometry(header.w, header.depth, header.h),
      [housing, housing, faceMat, housing, housing, housing]);
    hdr.position.set(0, top - header.depth / 2 + 0.05, header.z);
    this.body.add(hdr);

    this.add(new Port({
      id: 'hat', label: 'Hat2-Bus (2×8, 2.54 mm)', connector: 'm5.hat2', pins: HAT2_PINS,
      position: [0, top, 0],
      hitSize: [header.w + 0.6, 1.2, header.h + 0.6], hitOffset: [0, 0.3, header.z],
      pinGrid: {
        cols: 8, rows: 2, pitch: 2.54, center: [0, header.z],
        // col 0 = −X; pins 1/2 sit at +X. Row 0 (back) carries the even pins.
        order: (col, row) => (7 - col) * 2 + (row === 0 ? 2 : 1),
      },
      meta: { pitch: '2.54 mm', note: 'Mates with Hat2 modules on the top end' },
    }));
  }

  #buildBottomEnd(cavity) {
    const { H, D, grove, usb } = DIM;
    const bottom = -H / 2;

    // USB-C: metal shell ring with a dark cavity and tongue.
    const usbGroup = new THREE.Group();
    usbGroup.position.set(0, bottom, usb.z);
    usbGroup.quaternion.copy(FACE.bottom);
    const ringShape = capsule(usb.w, usb.h);
    ringShape.holes.push(capsule(usb.w - 0.5, usb.h - 0.5, { path: new THREE.Path(), clockwise: true }));
    const ring = new THREE.Mesh(new THREE.ExtrudeGeometry(ringShape, { depth: 1.2, bevelEnabled: false, curveSegments: 10 }),
      materials.metal(0x8e9298, { roughness: 0.45 }));
    ring.position.z = -1.15;
    const hole = new THREE.Mesh(new THREE.ShapeGeometry(capsule(usb.w - 0.4, usb.h - 0.4)), cavity);
    hole.position.z = -1.1;
    const tongue = new THREE.Mesh(new THREE.BoxGeometry(6.4, 0.7, 0.6), new THREE.MeshStandardMaterial({ color: 0x1a1a1c, roughness: 0.5 }));
    tongue.position.z = -0.75;
    usbGroup.add(ring, hole, tongue);
    this.body.add(usbGroup);

    this.add(new Port({
      id: 'usb', label: 'USB-C (charge / program)', connector: 'usb-c', pins: USB_PINS,
      position: [0, bottom, usb.z],
      quaternion: new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI),
      hitSize: [usb.w + 0.8, 1.2, usb.h + 0.8], hitOffset: [0, 0.3, 0],
      meta: { power: '5 V in · 250 mAh Li-ion', data: 'USB OTG (D− G19, D+ G20)' },
    }));

    // Microphone hole.
    const mic = new THREE.Mesh(new THREE.CircleGeometry(0.45, 16), cavity);
    mic.position.set(6.8, bottom - 0.015, usb.z);
    mic.quaternion.copy(FACE.bottom);
    this.body.add(mic);

    // Grove receptacle: white housing on the back half of the bottom end.
    const white = materials.plastic(0xf1f0eb, { roughness: 0.55 });
    const faceMat = new THREE.MeshStandardMaterial({ map: paintTexture(grove.w, grove.h, paintGroveFace, { pxPerMm: 30 }), roughness: 0.55 });
    const housing = new THREE.Mesh(new THREE.BoxGeometry(grove.w, grove.depth, grove.h), [white, white, white, faceMat, white, white]);
    housing.position.set(0, bottom + grove.depth / 2 - 0.25, grove.z);
    housing.position.z = -D / 2 + grove.h / 2 - 0.1;
    this.body.add(housing);

    this.add(new Port({
      id: 'grove', label: 'Grove PORT.A (HY2.0-4P)', connector: 'grove', pins: GROVE_PINS,
      position: [0, bottom - 0.25, housing.position.z],
      quaternion: new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI),
      hitSize: [grove.w + 0.6, 1.2, grove.h + 0.6], hitOffset: [0, 0.3, 0],
      meta: { pins: 'GND · 5V · G9 · G10', note: '5 V output needs M5.Power.setExtOutput(true)' },
    }));
  }

  #buildBack() {
    const { D } = DIM;
    const back = -D / 2 - 0.02;
    const label = decal(21, 33.5, paintBackLabel, { pxPerMm: 24, roughness: 0.45 });
    label.position.set(0, 6.6, back);
    label.quaternion.copy(FACE.back);
    this.body.add(label);

    const brass = materials.metal(0xc9a24a, { roughness: 0.35 });
    const steel = materials.metal(0xb8bcc4, { roughness: 0.3 });
    const hole = materials.cavity(0x16120a);
    const disc = (r, h, mat, x, y) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 24), mat);
      m.rotation.x = Math.PI / 2;
      m.position.set(x, y, -D / 2 + h / 2 - 0.12);
      this.body.add(m);
      return m;
    };
    for (const sx of [-1, 1]) {
      disc(1.35, 0.3, brass, sx * 7.4, -12.6);
      disc(0.75, 0.32, hole, sx * 7.4, -12.6);
      disc(1.55, 0.36, steel, sx * 8.4, -20.2);
      const hex = new THREE.Mesh(new THREE.CircleGeometry(0.6, 6), hole);
      hex.position.set(sx * 8.4, -20.2, -D / 2 - 0.25);
      hex.rotation.y = Math.PI;
      this.body.add(hex);
    }
  }
}
