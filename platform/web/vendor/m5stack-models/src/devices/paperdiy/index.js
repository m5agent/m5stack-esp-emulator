import * as THREE from 'three';
import {Button, Device, Led, materials} from '../../core/index.js';
import {isolateActuatorMaterials} from '../../modeling/actuators.js';
import {addCadParts} from '../../modeling/cad.js';
import {microSD, usbC} from '../../modeling/connectors.js';
import {FACE, mesh, slab} from '../../modeling/parts.js';
import {PaperDisplay} from '../../modeling/PaperDisplay.js';
import geometry from './geometry-data.js';

const displaySize = [58.32, 103.68];
const displayCenterY = 4.18;

function addInternalAssembly(body) {
  const pcb = materials.plastic(0x25372d, {roughness: 0.85});
  const silver = materials.metal(0xa7aaa2, {roughness: 0.65});
  const plastic = materials.plastic(0x24292a, {roughness: 0.78});
  const brass = materials.metal(0xb08b40, {roughness: 0.45});

  // The metal module and test connector can be seen through the official
  // rear-cover cutouts. The concealed board and support stack are inferred.
  slab(body, 58, 47, 0.65, 1, [0, -35, 0.96], pcb, [], 0.06).name = 'PaperDIY main PCB';
  slab(body, 17.65, 16, 1.95, 0.55, [15.6, -21, -2.96], silver, [], 0.1).name = 'ESP32-S3 module shield';
  slab(body, 4.8, 6.75, 1.85, 0.35, [-9.7, -12.3, -2.88], plastic, [], 0.06).name = 'Rear service socket housing';
  for (const y of [-14.15, -10.45]) {
    mesh(body, new THREE.BoxGeometry(3.8, 0.65, 0.22), silver, [-9.7, y, -2.98], 'Service socket retaining contact');
  }
  slab(body, 4.14, 4.14, 1.9, 2.07, [0, -20, -3.04], brass, [{w: 1.9, h: 1.9}], 0.06).name = 'M2 brass threaded insert';
  mesh(body, new THREE.CylinderGeometry(0.91, 0.91, 0.4, 28).rotateX(Math.PI / 2), plastic, [0, -20, -1.34], 'M2 blind-hole stop');

  slab(body, 32, 31, 1.3, 2, [0, 28, -1.78], silver, [], 0.17).name = '140 mAh pouch battery';
  slab(body, 29, 4, 1.2, 0.35, [0, 55.1, -1.9], plastic, [], 0.08).name = 'Rear latch support';
}

export class PaperDIY extends Device {
  static meta = {
    id: 'm5stack.paperdiy',
    name: 'PaperDIY Complete Kit',
    sku: 'K159-B',
    vendor: 'M5Stack',
    size: [68.2, 121.27, 6.3],
    keymap: {KeyA: 'key1', KeyB: 'key2', KeyP: 'power'},
  };

  build() {
    const pla = materials.plastic(0xdddcd6, {roughness: 0.91, clearcoat: 0});
    const parts = addCadParts(this, geometry, {
      shell: pla,
      back: materials.plastic(0xd4d3ce, {roughness: 0.94, clearcoat: 0}),
      key: materials.plastic(0xdcdad1, {roughness: 0.85, clearcoat: 0}),
    });

    for (const [part, id, label, axis, input] of [
      ['PaperDIY Button A cap', 'key1', 'Button A', [1, 0, 0], {gpio: 4}],
      ['PaperDIY Button B cap', 'key2', 'Button B', [1, 0, 0], {gpio: 3}],
      ['PaperDIY power cap', 'power', 'Power button', [0, 1, 0], {controller: 'M5PM1', signal: 'PY_BTN'}],
    ]) {
      this.add(new Button({
        id, label, mesh: isolateActuatorMaterials(parts[part]), travel: 0.24, axis,
        meta: {role: 'visual-control', ...input},
      }));
    }

    addInternalAssembly(this.body);
    const substrate = materials.plastic(0xb6b5ab, {roughness: 0.87});
    const pressurePlate = materials.plastic(0xd0cdc2, {roughness: 0.55, clearcoat: 0.16});
    slab(this.body, 62.1, 115.2, 0.68, 0.26, [0, 0.2, 1.75], substrate, [], 0.045).name = 'ET047TC1 panel substrate';
    slab(this.body, 60.05, 105.7, 0.36, 0.35, [0, displayCenterY, 2.44], pressurePlate, [
      {w: displaySize[0], h: displaySize[1], r: 0.04},
    ], 0.035).name = 'Acrylic pressure-plate margin';
    this.add(new PaperDisplay({
      id: 'lcd', label: '4.7-inch ET047TC1 e-paper', width: 540, height: 960,
      size: displaySize, position: [0, displayCenterY, 2.77], touch: false,
      meta: {role: 'external-framebuffer', surface: 'reflective', monochrome: true, grayscaleLevels: 16, orientation: 'portrait'},
    }));

    usbC(this, {position: [-24, -59.6, -0.54], face: 'bottom', w: 8.75, h: 3.0, depth: 5.1});
    microSD(this, {position: [33, -39.08, -1.55], face: 'right', w: 11.5, h: 1.4, depth: 6.3});

    const lens = mesh(this.body, new THREE.BoxGeometry(0.88, 0.8, 0.22),
      materials.plastic(0xa5a09a, {roughness: 0.44, clearcoat: 0.2}), [-1.5, -59.45, -0.38], 'Second indicator opening insert');
    lens.quaternion.copy(FACE.bottom);
    const powerLens = new THREE.Mesh(new THREE.BoxGeometry(0.87, 0.81, 0.25),
      materials.plastic(0xb49186, {roughness: 0.42, clearcoat: 0.18}));
    powerLens.name = 'Power light window';
    this.add(new Led({
      id: 'status', label: 'Power status light', color: 0xff2525, mesh: powerLens,
      position: [1.5, -59.5, -0.38], quaternion: FACE.bottom, radius: 0.4, glowSize: 2.3,
      meta: {role: 'externally-driven-visual', controller: 'M5PM1', signal: 'PY_LED'},
    }));
  }
}

export default PaperDIY;
