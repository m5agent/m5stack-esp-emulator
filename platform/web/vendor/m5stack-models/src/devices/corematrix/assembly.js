import * as THREE from 'three';
import {Port, materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {FACE, grove, header, mesh, portQuaternion, slab} from '../../modeling/parts.js';
import {microSD, usbC} from '../../modeling/connectors.js';
import {printedFilm} from '../../modeling/artwork.js';
import {ports, spec} from './dimensions.js';
import {MatrixDisplay} from './MatrixDisplay.js';

const charcoal = () => materials.plastic(0x222527, {roughness: .82});
const copper = () => materials.metal(0xbda05c, {roughness: .46});
const box = (parent, size, position, material, name) =>
  mesh(parent, new THREE.BoxGeometry(...size), material, position, name);

function fastener(host, x, y) {
  const frame = new THREE.Group();
  frame.name = 'M3 rear screw and retained insert';
  frame.position.set(x, y, -5.77);
  frame.quaternion.copy(FACE.back);
  host.body.add(frame);
  const shape = new THREE.Shape().absarc(0, 0, 2.12, 0, Math.PI * 2, false);
  const socket = new THREE.Path();
  for (let i = 0; i <= 6; i++) {
    const a = -i * Math.PI / 3;
    socket[i ? 'lineTo' : 'moveTo'](.87 * Math.cos(a), .87 * Math.sin(a));
  }
  shape.holes.push(socket);
  const steel = materials.metal(0x9fa2a0, {roughness: .42});
  mesh(frame, new THREE.ExtrudeGeometry(shape, {depth: .58, bevelEnabled: false, curveSegments: 24}),
    steel, [0, 0, -.58], 'Steel head with real hex recess');
  mesh(frame, new THREE.CylinderGeometry(1.95, 1.95, .24, 32).rotateX(Math.PI / 2),
    steel, [0, 0, -.69], 'Recess floor and underside of screw head');
  mesh(frame, new THREE.CylinderGeometry(1.45, 1.45, 2.1, 32).rotateX(Math.PI / 2),
    copper(), [0, 0, -1.8], 'Inferred brass threaded insert');
}

function rearSocket(host, spec, id, label, signals) {
  const {position, w, h} = spec;
  const frame = new THREE.Group();
  frame.name = label;
  frame.position.fromArray(position);
  frame.quaternion.copy(FACE.back);
  host.body.add(frame);
  const housing = materials.plastic(0xcdcebf, {roughness: .64});
  const shape = roundedRect(w, h, .26);
  shape.holes.push(roundedRect(w - .9, h - .85, .16, {path: new THREE.Path(), clockwise: true}));
  const depth = 2.8;
  mesh(frame, new THREE.ExtrudeGeometry(shape, {depth, bevelEnabled: false}),
    housing, [0, 0, -depth], 'Keyed connector housing');
  box(frame, [w - .8, h - .75, .36], [0, 0, -depth + .15], housing, 'Connector deep dielectric stop');
  for (let i = 0; i < signals.length; i++) {
    const y = (i - (signals.length - 1) / 2) * 1.25;
    box(frame, [.5, .3, 1.95], [-.45, y, -1.67], copper(), 'Connector metal contact');
    box(frame, [.65, .3, .6], [-.45, y, -depth - .25], copper(), 'Connector solder tail');
  }
  for (const y of [-h / 2 + .45, h / 2 - .45]) {
    box(frame, [.6, .35, 1.4], [w / 2 - .58, y, -.7], housing, 'Connector retention lip');
  }
  host.add(new Port({
    id, label, connector: id === 'battery' ? 'mx1.25-2p-battery' : 'mx1.25-4p-usb',
    position, quaternion: portQuaternion('back'), hitSize: [w, 1, h],
    meta: {role: 'visual-connector', face: 'back', signals},
  }));
}

function enclosure(host) {
  const panel = slab(host.body, 51.23, 51.23, .83, 3.62, [0, 0, 4.87],
    new THREE.MeshBasicMaterial({color: 0x1e1f22, toneMapped: false}), [], .2);
  panel.name = 'Smoked LED optical cover';
  const holes = [
    ...[-22, 22].flatMap(x => [-22, 22].map(y => ({w: 4.55, h: 4.55, r: 2.275, cx: x, cy: y}))),
    {w: 4.1, h: 10.5, r: .3, cx: -23.25, cy: -14},
    ...[ports.rearUSB, ports.battery].map(p => ({
      w: p.w + .2, h: p.h + .2, r: .29, cx: p.position[0], cy: p.position[1],
    })),
  ];
  const cover = slab(host.body, 51.2, 51.2, .65, 3.7, [0, 0, -5.64], charcoal(), holes, .11);
  cover.name = 'Rear carrier with M3 and connector cutouts';
  for (const x of [-22, 22]) for (const y of [-22, 22]) fastener(host, x, y);
  // The original graphic is a rear reference only. The film has an original
  // schematic-style redraw and the physical carrier remains without ink.
  const rearInk = printedFilm(host, {
    url: new URL('./artwork/rear-reference-redraw.png', import.meta.url).href,
    size: [48.15, 48.15], position: [0, 0, -5.651], face: 'back',
    name: 'CoreMatrix rear reference redraw', artworkKind: 'reference-redraw',
  });
  if (rearInk) rearInk.raycast = () => {};
  printedFilm(host, {
    url: new URL('./artwork/side-reference-redraw.png', import.meta.url).href,
    size: [30.45, 8.55], position: [27.01, 6.45, .19], face: 'right',
    name: 'CoreMatrix side name reference redraw', artworkKind: 'reference-redraw',
  });
}

function electronics(host) {
  const pcb = materials.plastic(0x1c3a58, {roughness: .85});
  const mountClearance = [-22, 22].flatMap(x => [-22, 22]
    .map(y => ({w: 3.95, h: 3.95, r: 1.975, cx: x, cy: y})));
  slab(host.body, 50.1, 49.95, 1.05, 3.35, [0, 0, .24],
    pcb, mountClearance, .05).name = 'Blue main circuit board';
  slab(host.body, 47.4, 46.8, .65, 2.25, [0, 0, 3.3], pcb, [], .04).name = 'LED daughterboard';
  for (const x of [-20.4, 20.4]) for (const y of [-18, 18]) {
    box(host.body, [1.7, 1.7, 2.9], [x, y, 1.79], charcoal(), 'Inferred daughterboard standoff');
  }
  for (const [name, position, size] of [
    ['ESP32-C61 module body', [0, 2.4, -.29], [14, 16, 1.05]],
    ['BMI270 IMU package', [-5.2, -13.8, -.19], [3.1, 2.6, .85]],
    ['Stamp Timer Power2', [10.5, 3, -.34], [6.5, 7.2, 1.15]],
    ['MLT-8530 buzzer', [6.9, 17.2, -.74], [8.2, 8.2, 1.95]],
  ]) box(host.body, size, position, charcoal(), name);
  header(host.body, {position: [19.8, 0, -1.52], face: 'back', cols: 2, rows: 15});
  for (const x of [-13, 0, 13]) {
    box(host.body, [8.4, .8, 5.4], [x, 24.35, -.55], charcoal(), 'Side key switch support and gap backing');
    box(host.body, [3.5, 1.3, 2.2], [x, 24, .02], charcoal(), 'Side key switch housing');
    box(host.body, [1.1, .9, 1.2], [x, 24.9, .1], copper(), 'Side key switch plunger support');
  }
  box(host.body, [.8, 9.1, 5.4], [-24.35, 13.55, -.55], charcoal(), 'Power key switch support and gap backing');
  box(host.body, [1.4, 3.35, 2.2], [-24.15, 11.85, -.1], charcoal(), 'Power key switch housing');
}

export function addCoreMatrixAssembly(host) {
  electronics(host);
  enclosure(host);
  usbC(host, {...ports.usb, face: 'left', depth: 4.5});
  grove(host, {...ports.grove, face: 'left', color: 0xb02422});
  const grovePort = host.port('grove');
  grovePort.pins = ['GND', '5V', 'G0', 'G1'].map((name, i) => ({n: i + 1, name}));
  grovePort.pinGrid = {cols: 4, rows: 1, pitch: 2, center: [0, -.15], order: col => col + 1};
  microSD(host, {...ports.microSD, face: 'bottom', depth: 5.8});
  rearSocket(host, ports.rearUSB, 'usb-port', 'Rear USB expansion', ['GND', '5V', 'G12', 'G13']);
  rearSocket(host, ports.battery, 'battery', 'Rear battery connector', ['BAT', 'GND']);
  const {width, height, size, position, ...controller} = spec.display;
  host.add(new MatrixDisplay({
    id: 'display', label: '16 × 16 white LED matrix', width, height, size, position,
    meta: {
      role: 'external-framebuffer', surface: 'led-matrix', monochrome: true,
      coordinates: 'front-view row-major, top-left origin', ...controller,
    },
  }));
}
