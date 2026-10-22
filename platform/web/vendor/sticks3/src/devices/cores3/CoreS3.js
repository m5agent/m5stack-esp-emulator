import * as THREE from 'three';
import { Device } from '../../core/Device.js';
import { Button } from '../../core/components/Button.js';
import { Display } from '../../core/components/Display.js';
import { Imu } from '../../core/components/Imu.js';
import {
  roundedSlab,
  roundedRect,
  capsule,
  basisQuaternion,
  decal
} from '../../core/geometry.js';
import { materials } from '../../core/materials.js';

/*
 * M5Stack CoreS3 (K128).
 *
 * The core module is 54 × 54 × 15.5 mm. The official hero configuration also
 * includes a DinBase: it brings the mounting ears to 62 mm overall height and
 * the total depth to 31.5 mm. Core geometry remains in millimetres.
 */
export const DIM = {
  W: 54,
  H: 54,
  D: 15.5,
  overallH: 62,
  overallD: 31.5,
  cornerR: 6.4,
  frontDepth: 8.1,
  baseDepth: 16.0,
  glass: { w: 48.6, h: 42.0, cy: 4.5, r: 6.8, z: 8.04 },
  lcd: { w: 40.64, h: 30.48, cy: 6.0, z: 8.10 },
  camera: { x: 0, y: -14.3 },
  sensor: { x: -16.5, y: -13.1 },
  led: { x: 8.8, y: -13.2 },
  power: { y: 6.2, z: 3.4 },
  usb: { x: 27.05, y: 1.2, z: 1.4 },
  mb: { x: 27.05, y: -8.2, z: 2.3 },
  groove: { y: -15.0, z: -1.0 }
};

const FACE = {
  top: basisQuaternion([1, 0, 0], [0, 0, -1], [0, 1, 0]),
  bottom: basisQuaternion([1, 0, 0], [0, 0, 1], [0, -1, 0]),
  right: basisQuaternion([0, 1, 0], [0, 0, 1], [1, 0, 0]),
  left: basisQuaternion([0, -1, 0], [0, 0, 1], [-1, 0, 0]),
  back: basisQuaternion([-1, 0, 0], [0, 1, 0], [0, 0, -1])
};

function panel(w, h, radius, material, { x = 0, y = 0, z = 0 } = {}) {
  const mesh = new THREE.Mesh(
    new THREE.ShapeGeometry(roundedRect(w, h, radius), 12),
    material
  );
  mesh.position.set(x, y, z);
  return mesh;
}

function disc(radius, material, { x = 0, y = 0, z = 0 } = {}) {
  const mesh = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 40),
    material
  );
  mesh.position.set(x, y, z);
  return mesh;
}

function cylinderZ(radius, depth, material, { x = 0, y = 0, z = 0 } = {}) {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, depth, 32),
    material
  );
  mesh.rotation.x = Math.PI / 2;
  mesh.position.set(x, y, z);
  return mesh;
}

function paintRearMark(ctx, W, H, scale) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(225,228,230,.76)';
  ctx.font = `800 ${Math.round(scale * 5.2)}px Arial`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('M5', W / 2, H * .38);
  ctx.font = `700 ${Math.round(scale * 2.0)}px Arial`;
  ctx.letterSpacing = `${Math.round(scale * 0.5)}px`;
  ctx.fillText('CORE S3', W / 2, H * .69);
}

function paintSideMark(ctx, W, H, scale) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(235,237,238,.72)';
  ctx.font = `800 ${Math.round(scale * 2.6)}px Arial`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('CORE', W / 2, H * .34);
  ctx.fillStyle = 'rgba(52,171,238,.9)';
  ctx.fillText('S3', W / 2, H * .7);
}

export class CoreS3 extends Device {
  static meta = {
    id: 'm5stack.cores3',
    name: 'M5Stack CoreS3',
    vendor: 'M5Stack',
    sku: 'K128',
    size: [DIM.W, DIM.overallH, DIM.overallD],
    mcu: 'ESP32-S3',
    keymap: { KeyP: 'power' }
  };

  build({ touch = true, pixelEffect = true, caseColor = 0x3f4143 } = {}) {
    const caseMat = materials.plastic(caseColor, { roughness: .76, clearcoat: .03 });
    const rearMat = materials.plastic(new THREE.Color(caseColor).offsetHSL(0, 0, .015), {
      roughness: .82,
      clearcoat: .02
    });
    const baseMat = materials.plastic(new THREE.Color(caseColor).offsetHSL(0, 0, -.02), {
      roughness: .86,
      clearcoat: .015
    });
    const rubber = materials.plastic(0x27292b, { roughness: .94, clearcoat: 0 });
    const cavity = materials.cavity();
    const blackGlass = new THREE.MeshPhysicalMaterial({
      color: 0x060708,
      roughness: .2,
      metalness: 0,
      clearcoat: .65,
      clearcoatRoughness: .2
    });
    this.materials = { caseMat, rearMat, baseMat, rubber, cavity, blackGlass };

    this.#buildModule(caseMat, rearMat, cavity, blackGlass, touch, pixelEffect);
    this.#buildBase(baseMat, rubber);
    this.#buildFrontDetails(cavity);
    this.#buildSideDetails(caseMat, cavity);
    this.#buildRearDetails();
    this.#buildPowerButton();

    this.add(new Imu({
      id: 'imu',
      label: 'IMU BMI270 / BMM150',
      axes: { x: '+x', y: '+y', z: '+z' },
      meta: { chip: 'BMI270 + BMM150', address: '0x69 + 0x10' }
    }));
  }

  #buildModule(caseMat, rearMat, cavity, blackGlass, touch, pixelEffect) {
    const { W, H, D, frontDepth, cornerR, glass, lcd } = DIM;
    const front = new THREE.Mesh(roundedSlab({
      w: W,
      h: H,
      depth: frontDepth,
      radius: cornerR,
      bevel: .65,
      curveSegments: 18
    }), caseMat);
    front.position.z = D / 2 - frontDepth;
    front.name = 'cores3-front-shell';

    const rear = new THREE.Mesh(roundedSlab({
      w: W - .25,
      h: H - .25,
      depth: D - frontDepth + .8,
      radius: cornerR - .1,
      bevel: .75,
      curveSegments: 18
    }), rearMat);
    rear.position.z = -D / 2;
    rear.name = 'cores3-rear-shell';
    this.body.add(front, rear);

    const glassPanel = panel(glass.w, glass.h, glass.r, blackGlass, {
      y: glass.cy,
      z: glass.z
    });
    this.body.add(glassPanel);

    this.add(new Display({
      id: 'lcd',
      label: 'LCD 2.0" 320×240 touch',
      width: 320,
      height: 240,
      size: [lcd.w, lcd.h],
      position: [0, lcd.cy, lcd.z],
      style: 'lcd',
      touch,
      pixelEffect,
      glass: {
        size: [glass.w, glass.h],
        offset: .035,
        intensity: .18,
        roughness: .1
      },
      meta: {
        driver: 'ILI9342C / ILI9342E',
        panel: 'IPS',
        touch: 'FT6336U',
        cs: 'G3',
        dc: 'G35',
        rst: 'AW9523 P1_1'
      }
    }));

    const rim = new THREE.Mesh(
      new THREE.RingGeometry(2.05, 2.55, 40),
      materials.metal(0x777a7d, { roughness: .42 })
    );
    rim.position.set(DIM.camera.x, DIM.camera.y, glass.z + .055);
    this.body.add(rim);
    this.body.add(cylinderZ(1.75, .34, cavity, {
      x: DIM.camera.x,
      y: DIM.camera.y,
      z: glass.z + .12
    }));
    this.body.add(disc(1.12, new THREE.MeshPhysicalMaterial({
      color: 0x07101a,
      roughness: .1,
      metalness: .05,
      clearcoat: 1
    }), {
      x: DIM.camera.x,
      y: DIM.camera.y,
      z: glass.z + .31
    }));

    for (const [x, color] of [[7.7, 0x38d46a], [10.4, 0x45a4ff], [13.1, 0xd8f3ff]]) {
      const glow = new THREE.Mesh(
        new THREE.SphereGeometry(.46, 16, 10),
        new THREE.MeshBasicMaterial({ color, toneMapped: false })
      );
      glow.scale.z = .35;
      glow.position.set(x, DIM.led.y, glass.z + .1);
      this.body.add(glow);
    }

    this.body.add(cylinderZ(1.25, .3, new THREE.MeshStandardMaterial({
      color: 0x111315,
      roughness: .25
    }), {
      x: DIM.sensor.x,
      y: DIM.sensor.y,
      z: glass.z + .09
    }));

    for (const x of [-6.8, -4.6]) {
      this.body.add(cylinderZ(.38, .26, cavity, {
        x,
        y: -15.0,
        z: glass.z + .08
      }));
    }
  }

  #buildBase(baseMat, rubber) {
    const { W, H, D, baseDepth, overallH } = DIM;
    const baseFrontZ = -D / 2 + .8;
    const base = new THREE.Mesh(roundedSlab({
      w: W,
      h: H,
      depth: baseDepth,
      radius: 5.2,
      bevel: .65,
      curveSegments: 16
    }), baseMat);
    base.position.z = baseFrontZ - baseDepth;
    base.name = 'cores3-din-base';
    this.body.add(base);

    const earDepth = 3.0;
    const earZ = baseFrontZ - earDepth;
    for (const x of [-17.2, 17.2]) {
      for (const y of [-(overallH - 8) / 2, (overallH - 8) / 2]) {
        const ear = new THREE.Mesh(roundedSlab({
          w: 6.2,
          h: 8.0,
          depth: earDepth,
          radius: 2.7,
          bevel: .35,
          holes: [{ w: 3.0, h: 3.0, r: 1.5, cx: 0, cy: y > 0 ? 1.4 : -1.4 }]
        }), baseMat);
        ear.position.set(x, y, earZ);
        this.body.add(ear);
      }
    }

    const topClip = new THREE.Mesh(roundedSlab({
      w: 17,
      h: 5.2,
      depth: 2.4,
      radius: 2.0,
      bevel: .35,
      holes: [{ w: 9.2, h: 1.8, r: .9, cx: 0, cy: .7 }]
    }), rubber);
    topClip.position.set(0, 27.2, -6.3);
    this.body.add(topClip);
  }

  #buildFrontDetails(cavity) {
    for (const x of [-20.0, 20.0]) {
      this.body.add(cylinderZ(.38, .25, cavity, {
        x,
        y: 23.4,
        z: DIM.glass.z + .05
      }));
    }
  }

  #buildSideDetails(caseMat, cavity) {
    const { W, usb, mb } = DIM;
    const metal = materials.metal(0x9ea3a7, { roughness: .34 });

    const usbRingShape = capsule(8.7, 3.1);
    usbRingShape.holes.push(capsule(8.1, 2.65, {
      path: new THREE.Path(),
      clockwise: true
    }));
    const usbRing = new THREE.Mesh(new THREE.ExtrudeGeometry(usbRingShape, {
      depth: .8,
      bevelEnabled: false,
      curveSegments: 10
    }), metal);
    usbRing.quaternion.copy(FACE.right);
    usbRing.position.set(W / 2 + .02, usb.y, usb.z);
    this.body.add(usbRing);
    const usbHole = new THREE.Mesh(new THREE.ShapeGeometry(capsule(8.15, 2.7)), cavity);
    usbHole.quaternion.copy(FACE.right);
    usbHole.position.set(W / 2 + .1, usb.y, usb.z);
    this.body.add(usbHole);

    const mbHousing = new THREE.Mesh(
      new THREE.BoxGeometry(10.2, 4.4, 2.1),
      materials.plastic(0x7d1624, { roughness: .58 })
    );
    mbHousing.quaternion.copy(FACE.right);
    mbHousing.position.set(W / 2 + .8, mb.y, mb.z);
    this.body.add(mbHousing);
    const mbFace = new THREE.Mesh(new THREE.PlaneGeometry(8.2, 2.7), cavity);
    mbFace.quaternion.copy(FACE.right);
    mbFace.position.set(W / 2 + 1.87, mb.y, mb.z);
    this.body.add(mbFace);

    const groove = new THREE.Mesh(
      new THREE.BoxGeometry(.6, 21, 4.8),
      materials.cavity(0x18191a)
    );
    groove.position.set(-W / 2 - .18, DIM.groove.y, DIM.groove.z);
    this.body.add(groove);

    const sideMark = decal(10, 7, paintSideMark, {
      transparent: true,
      roughness: .8,
      pxPerMm: 32
    });
    sideMark.quaternion.copy(FACE.left);
    sideMark.position.set(-W / 2 - .03, 11.5, 2.4);
    this.body.add(sideMark);

    for (const [x, color] of [[-12.5, 0x174c76], [12.5, 0x202224]]) {
      const housing = new THREE.Mesh(
        new THREE.BoxGeometry(11.2, 2.2, 5.4),
        materials.plastic(color, { roughness: .68 })
      );
      housing.position.set(x, -27.9, -2.0);
      this.body.add(housing);
      const face = new THREE.Mesh(new THREE.PlaneGeometry(8.4, 1.5), cavity);
      face.quaternion.copy(FACE.bottom);
      face.position.set(x, -29.02, -2.0);
      this.body.add(face);
    }
  }

  #buildRearDetails() {
    const backZ = -DIM.D / 2 + .8 - DIM.baseDepth - .05;
    const dark = materials.cavity(0x111214);
    const metal = materials.metal(0xa5a8aa, { roughness: .35 });
    const ring = new THREE.Mesh(new THREE.RingGeometry(6.2, 7.4, 48), dark);
    ring.rotation.y = Math.PI;
    ring.position.set(0, 0, backZ);
    this.body.add(ring);
    const center = cylinderZ(3.8, .8, new THREE.MeshStandardMaterial({
      color: 0x282a2c,
      roughness: .55
    }), { z: backZ - .3 });
    center.rotation.y = Math.PI;
    this.body.add(center);

    for (const x of [-21, 21]) {
      for (const y of [-20, 20]) {
        const screw = cylinderZ(2.0, .65, metal, { x, y, z: backZ - .15 });
        this.body.add(screw);
      }
    }

    const label = decal(18, 8.5, paintRearMark, {
      transparent: true,
      roughness: .82,
      pxPerMm: 30
    });
    label.rotation.y = Math.PI;
    label.position.set(0, -20.5, backZ - .08);
    this.body.add(label);
  }

  #buildPowerButton() {
    const cap = roundedSlab({
      w: 3.2,
      h: 7.2,
      depth: 1.7,
      radius: 1.6,
      bevel: .38,
      curveSegments: 12
    });
    cap.translate(0, 0, -1.15);
    const key = new THREE.Mesh(cap, materials.plastic(0x303234, {
      roughness: .62,
      clearcoat: .02
    }));
    this.add(new Button({
      id: 'power',
      label: 'Power',
      mesh: key,
      position: [-DIM.W / 2, DIM.power.y, DIM.power.z],
      quaternion: FACE.left,
      travel: .35,
      longPressMs: 2000,
      meta: { via: 'AXP2101', note: 'Long press to power off' }
    }));
  }
}
