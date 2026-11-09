import * as THREE from 'three';
import {Button, Device, Led, Port, materials} from '../../core/index.js';
import {isolateActuatorMaterials} from '../../modeling/actuators.js';
import {addCadParts} from '../../modeling/cad.js';
import {microSD, usbC} from '../../modeling/connectors.js';
import {FACE, mesh, portQuaternion, slab} from '../../modeling/parts.js';
import {PaperDisplay} from '../../modeling/PaperDisplay.js';
import geometry from './geometry-data.js';
import {addRearArtwork} from './rear-artwork.js';

const displaySize = [58.32, 103.68];
const displayCenterY = 3.79;
const customPort = {x: 11.85, y: -33.35, z: -3.71};
const statusLight = {x: -29.5, y: -53.45, z: -3.64};
const rearHoles = [
  ...[-28.5, 28.5].map(cx => ({w: 7.2, h: 7.2, cx, cy: -31.55})),
  {w: 5.55, h: 3.55, r: 0.22, cx: customPort.x, cy: customPort.y},
  {w: 1.58, h: 1.58, cx: statusLight.x, cy: statusLight.y},
];

function addRearAssembly(host) {
  const {body} = host;
  const pcb = materials.plastic(0x25382d, {roughness: 0.82});
  const light = materials.plastic(0xe9e7e1, {roughness: 0.76});
  const black = materials.plastic(0x202425, {roughness: 0.82});
  const metal = materials.metal(0xadaca4, {roughness: 0.54});
  const gold = materials.metal(0xb5a273, {roughness: 0.47});

  slab(body, 53, 45, 0.7, 1.6, [0, -36, 0.32], pcb, [], 0.06).name = 'PaperS3 PCB';
  slab(body, 54, 70, 2.7, 2.8, [0, 19.5, -1.82], metal, [], 0.22).name = '1800 mAh battery pouch';

  // The fixed rear label carrier closes the antenna and battery-service
  // openings. Separate screw bores, the exposed expansion port and LED remain.
  slab(body, 63.8, 116.2, 0.22, 3.1, [0, -0.66, -3.83], light,
    rearHoles.map(hole => ({...hole, cy: hole.cy + 0.66})), 0.035).name = 'PaperS3 rear label carrier';
  for (const x of [-28.5, 28.5]) {
    const head = new THREE.CylinderGeometry(2.02, 2.08, 0.54, 28).rotateX(Math.PI / 2);
    mesh(body, head, metal, [x, -31.55, -3.48], 'Recessed rear screw');
    const slot = new THREE.BoxGeometry(1.85, 0.26, 0.035);
    mesh(body, slot, black, [x, -31.55, -3.765], 'Screw drive slot');
    mesh(body, slot, black, [x, -31.55, -3.765], 'Screw drive slot').rotation.z = Math.PI / 2;
  }
  for (const x of [-30.5, 30.5]) {
    slab(body, 2.2, 2.2, 1.5, 1.1, [x, 57.75, -3.73], gold, [{w: 1.45, h: 1.45}], 0.035).name = 'Rear M2 brass insert';
  }
  if (host.options.artwork !== false) addRearArtwork(body, rearHoles);

  const portBody = new THREE.Group();
  portBody.name = 'HC1.25-4PLT expansion receptacle';
  portBody.position.set(customPort.x, customPort.y, customPort.z);
  portBody.quaternion.copy(FACE.back);
  body.add(portBody);
  slab(portBody, 5.7, 3.62, 1.45, 0.25, [0, 0, -1.52], light,
    [{w: 4.95, h: 2.55, r: 0.2}], 0.045).name = 'Expansion receptacle walls';
  mesh(portBody, new THREE.BoxGeometry(5, 2.7, 0.42), black, [0, 0, -1.66], 'Expansion receptacle stop');
  for (let pin = 0; pin < 4; pin++) {
    mesh(portBody, new THREE.BoxGeometry(0.26, 0.28, 1.02), gold, [(pin - 1.5) * 1.25, 0.16, -1.04], 'Expansion pin');
  }
  host.add(new Port({
    id: 'custom', label: 'HC1.25-4PLT', connector: 'hc1.25-4plt',
    position: [customPort.x, customPort.y, customPort.z], quaternion: portQuaternion('back'),
    hitSize: [5.55, 0.26, 3.55],
    pins: ['GND', '3V3', 'G1', 'G2'].map((name, index) => ({n: index + 1, name})),
    pinGrid: {cols: 4, rows: 1, pitch: 1.25, center: [0, 0.16], order: column => column + 1},
    meta: {role: 'visual-connector', face: 'back', pitch: 1.25},
  }));

  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.57, 0.59, 0.27, 24).rotateX(Math.PI / 2),
    materials.plastic(0xb4897b, {roughness: 0.4, clearcoat: 0.17}));
  lens.name = 'Rear status light window';
  host.add(new Led({
    id: 'status', label: 'Rear status light', color: 0xff2525, mesh: lens,
    position: [statusLight.x, statusLight.y, statusLight.z], quaternion: FACE.back,
    radius: 0.4, glowSize: 2.4, meta: {role: 'externally-driven-visual'},
  }));
}

export class PaperS3 extends Device {
  static meta = {
    id: 'm5stack.papers3',
    name: 'PaperS3',
    sku: 'C139',
    vendor: 'M5Stack',
    size: [67.7, 127.5, 7.7],
    keymap: {KeyP: 'power'},
  };

  build() {
    const shell = materials.plastic(0xc4c4bd, {roughness: 0.68, clearcoat: 0.06});
    const parts = addCadParts(this, geometry, {
      shell,
      hook: materials.plastic(0xbabab2, {roughness: 0.71, clearcoat: 0.04}),
      key: materials.plastic(0xc8c8c0, {roughness: 0.64, clearcoat: 0.06}),
    });
    this.add(new Button({
      id: 'power', label: 'Power button', mesh: isolateActuatorMaterials(parts['PaperS3 power cap']),
      travel: 0.25, axis: [-1, 0, 0], meta: {role: 'visual-control', controller: 'PMS150G'},
    }));

    addRearAssembly(this);
    slab(this.body, 63.5, 117.8, 0.83, 2.5, [0, 0, 2.91],
      materials.plastic(0xcac9bf, {roughness: 0.62, clearcoat: 0.12}), [
        {w: displaySize[0], h: displaySize[1], r: 0.04, cy: displayCenterY},
      ], 0.11).name = 'Full-front touch-panel surround';
    slab(this.body, 62.1, 115.2, 0.68, 0.38, [0, 0, 2.91],
      materials.plastic(0xb4b2a8, {roughness: 0.9}), [], 0.06).name = 'ET047TC1 panel substrate';
    this.add(new PaperDisplay({
      id: 'lcd', label: '4.7-inch ET047TC1 touch e-paper', width: 540, height: 960,
      size: displaySize, position: [0, displayCenterY, 3.67], touch: true,
      meta: {role: 'external-framebuffer', surface: 'reflective', monochrome: true, grayscaleLevels: 16, orientation: 'portrait', touchController: 'GT911'},
    }));

    usbC(this, {position: [-22.2, -60.58, 0.07], face: 'bottom', w: 8.7, h: 2.98, depth: 4.7});
    microSD(this, {position: [-33, -44.19, -0.58], face: 'left', w: 11.5, h: 1.45, depth: 6.2});
  }
}

export default PaperS3;
