import * as THREE from 'three';
import {Led, materials} from '../../core/index.js';
import {FACE, grove, mesh, slab} from '../../modeling/parts.js';
import {physicalButton} from '../../modeling/actuators.js';
import {microSD, usbC} from '../../modeling/connectors.js';

export function addAssembly(host) {
  const {body} = host;
  const dark = materials.plastic(0x1d2521, {roughness: 0.91});
  const green = materials.plastic(0x344c3d, {roughness: 0.9});
  const alloy = materials.metal(0xadb3af, {roughness: 0.48});

  // The actual PCB edge is visible between the upper shell and battery base.
  slab(body, 83.1, 53.0, 0.78, 2.2, [0, 0, -1.32], green, [], 0.04).name = 'Visible main PCB seam';
  slab(body, 66, 32, 5.2, 2.2, [0, -5, -5.25],
    materials.plastic(0x838b88), [], 0.22).name = 'Base battery visual envelope';
  slab(body, 20.5, 13.2, 1.9, 1.2, [27.8, 16.4, 2.6],
    materials.plastic(0x838b88), [], 0.12).name = 'Main unit battery visual envelope';
  slab(body, 23.4, 17.4, 0.78, 0.35, [27.8, 16.47, 5.53], green, [], 0.05).name = 'Stamp-S3 PCB';

  const antenna = new THREE.Shape();
  antenna.moveTo(-2.8, -6.85);
  antenna.lineTo(2.8, -6.85);
  antenna.lineTo(2.8, -0.58);
  antenna.lineTo(1.43, -0.58);
  antenna.lineTo(1.43, 0.58);
  antenna.lineTo(2.8, 0.58);
  antenna.lineTo(2.8, 6.85);
  antenna.lineTo(-2.8, 6.85);
  antenna.closePath();
  mesh(body, new THREE.ExtrudeGeometry(antenna, {depth: 0.55, bevelEnabled: false}), alloy,
    [19.8, 16.47, 8.55], 'Stamp-S3 metal antenna');

  for (const [x, y, z, face] of [
    [-29, 9, 9.4, 'front'], [12.5, 9, 9.4, 'front'], [31.3, 20.95, 9.87, 'front'],
    [-29, 9, -8.9, 'back'], [12.5, 9, -8.9, 'back'],
  ]) hexScrew(body, [x, y, z], face, alloy, dark);

  const cover = slab(body, 23.1, 17.1, 0.16, 0.53, [27.8, 16.47, 9.706],
    materials.plastic(0xe0e3db), [
      {w: 3.1, h: 3.1, r: 1.55, cx: 3.5, cy: 4.48},
      {w: 1.78, h: 1.78, r: 0.23, cx: 7.4, cy: -6.02},
    ], 0.012);
  cover.name = 'Stamp-S3 adhesive cover carrier';
  host.parts['stamp-label-carrier'] = cover;

  const ledCap = slab(body, 1.46, 1.46, 0.55, 0.21, [0, 0, 0],
    materials.glossy(0xc7cebc, {roughness: 0.38}), [], 0.035);
  ledCap.name = 'Stamp-S3 RGB emitter package';
  const led = host.add(new Led({
    id: 'stamp-rgb',
    label: 'Stamp-S3 RGB',
    mesh: ledCap,
    position: [35.2, 10.45, 8.82],
    radius: 0,
    glowSize: 2.1,
    meta: {emitter: 'WS2812B-2020', role: 'externally-driven-visual', electricalBehavior: false},
  }));
  led.glow.position.z = 0.56;

  usbC(host, {id: 'usb', position: [41.96, 16.47, 7.85], face: 'right', w: 8.65, h: 3.15, depth: 6.4});
  microSD(host, {id: 'micro-sd', position: [-12.8, 26.75, -0.06], face: 'top', w: 12.6, h: 1.45, depth: 7.1});
  grove(host, {position: [-42.02, 19, 1.55], face: 'left', w: 9.9, h: 4.75, color: 0xd1d3cf});
  addGroveSelector(host, dark);

  const ir = new THREE.Group();
  ir.name = 'IR transmitter package and lens';
  ir.position.set(-32.45, 26.55, 0.36);
  body.add(ir);
  mesh(ir, new THREE.CylinderGeometry(0.79, 0.82, 1.75, 24), dark, [0, -0.82, 0], 'IR diode body');
  mesh(ir, new THREE.SphereGeometry(0.78, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2),
    materials.glossy(0x353a35, {roughness: 0.24}), [0, 0, 0], 'IR domed lens');

  const speaker = slab(body, 8.3, 5.35, 1.5, 1.1, [39.8, 16.5, 2.65], dark, [], 0.08);
  speaker.quaternion.copy(FACE.right);
  speaker.name = 'Speaker enclosure behind side perforations';
}

function addGroveSelector(host, dark) {
  const {body} = host;
  const carrier = slab(body, 4.5, 1.55, 1.6, 0.12, [-40.15, 8.15, 0.03], dark,
    [{w: 3.45, h: 1.07, r: 0.10}], 0.02);
  carrier.quaternion.copy(FACE.left);
  carrier.name = 'Grove voltage direction selector housing';
  mesh(body, new THREE.BoxGeometry(0.3, 3.45, 1.07), dark,
    [-39.25, 8.15, 0.03], 'Selector slot floor');
  const cap = slab(body, 1.25, 0.93, 0.95, 0.1, [-41.53, 7.49, 0.03],
    materials.plastic(0xbdc2be), [], 0.025);
  cap.quaternion.copy(FACE.left);
  cap.name = 'Grove voltage direction slide';
  physicalButton(host, {
    id: 'grove-power', label: 'Grove voltage direction selector', mesh: cap,
    axis: [0, 1, 0], travel: 1.36, latching: true,
    meta: {
      surfaceCenter: [-42, 7.49, 0.03],
      surfaceFace: 'left',
      mechanism: 'slide',
      detents: ['5VOUT', '5VIN'],
      electricalBehavior: false,
    },
  });
}

function hexScrew(body, position, face, alloy, dark) {
  const shape = new THREE.Shape();
  shape.absarc(0, 0, 1.45, 0, Math.PI * 2, false);
  const hex = new THREE.Path();
  for (let i = 0; i < 6; i++) {
    const angle = -i * Math.PI / 3;
    const point = [0.62 * Math.cos(angle), 0.62 * Math.sin(angle)];
    if (i === 0) hex.moveTo(...point);
    else hex.lineTo(...point);
  }
  hex.closePath();
  shape.holes.push(hex);
  const group = new THREE.Group();
  group.name = 'Recessed M2 hex socket head';
  group.position.fromArray(position);
  group.quaternion.copy(FACE[face]);
  body.add(group);
  mesh(group, new THREE.ExtrudeGeometry(shape, {depth: 0.46, bevelEnabled: false, curveSegments: 24}),
    alloy, [0, 0, -0.46], 'Hex socket wall');
  mesh(group, new THREE.CylinderGeometry(1.29, 1.29, 0.35, 24).rotateX(Math.PI / 2),
    dark, [0, 0, -0.6], 'Hex socket recessed floor');
}
