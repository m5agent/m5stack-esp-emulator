# Unit Laser RX — U065

The exact U065 dimension drawing specifies **24 × 32 × 8 mm** in model X/Y/Z axes (the product table orders these 32 × 24 × 8). +X is right, +Y the receiving end and +Z the labeled front. Two **5 mm** mounting bores are on **16 mm** pitch at (−8, −4) and (+8, −4). The opposite edge from Grove has the native **3 mm** optical aperture. The black Grove face is **10 × 5.2 mm**.

Official assembled-shell component 0 contains **3556 triangles**. It is retained with one common translation, scale 1. Components 1/2 are displaced half-shell copies (1810 + 1746 triangles), not additional installed parts. Native mounting bores, optical aperture, connector cutout, screw relief, printed-face recesses, seams and molded M5 remain unchanged. No source wall is cut, moved, scaled or filled to conceal gaps.

The interior has a physical PCB with mounting scallops, screw bore, receiver lead bores and four Grove solder bores. The original schematic identifies P1 Header3, R1 10K, R2 20K, C2 100nF and J1 GROVE_IO. The product page identifies the receiving element as ISO103. A fixed dark receiver body, non-emissive domed receiving surface, back seal and three metal leads occupy the real receiving aperture. They are receiving geometry, never an indicator or light source. There is no exposed indicator LED, button or moving joint in the retrieved same-SKU exterior evidence.

The open black HY2.0-4P includes side walls, floor, latch details, four distinct contact pins, solder tails and a recessed physical rear wall. The mouth remains a real insertion cavity. The rear screw includes a head and shank. PCB outline/thickness/plane, hidden ISO103 package profile/depth/tint, lead bends, passive placement, screw shank and Grove insertion depth are reconstructed visual detail; the evidence does not supply a populated production assembly or package installation drawing. No production-fit or electrical/optical performance claim is made.

Two high-resolution code-drawn `reference-redraw` PNGs reproduce the observed front receiving diagram / LASER BEAM / LASER.RX label and rear LASER.RX / frequency / PORT.B.I/O / pin blocks. They contain no cropped photographic pixels. [Artwork](./artwork.md) gives references and registration. `artwork:false` removes only artwork triangles; physical attributes, indices and transforms are identical.

## Integration

```js
import { Model, GroveModule } from './src/units/laser-rx/index.js';
const rx = new Model();
rx.port('grove');               // bottom socket, outward −Y
rx.get('sensor', 'component');  // passive ISO103 anchor at receiving end, +Y

const module = host.port('portB').attach(new GroveModule({ cableLength: 60 }));
host.handle({ type: 'pose', target: 'portB/unitFrame',
  position: [20, 80, 0], rotation: [0.2, 0, 0] });
host.port('portB').detach({ dispose: false });
module.dispose();
```

`GroveModule` exposes `unitFrame`, `cable`, nested `grove` and `sensor`. Four conductors and two plugs follow the Unit pose. The documented black/red/yellow/white order is GND / 5V / NC / DOUT. The rear label faithfully reads **IN** from the receiving Unit's perspective; API pin metadata uses the official table's **DOUT**. Mechanical attachment and namespacing do not prove electrical compatibility or transfer a signal. The sensor is a passive visual anchor and accepts no illumination, laser, reception, communication, waveform, GPIO or digital-output commands. Optical coupling and all internal behavior belong to the external framework.

[Smoke results](./smoke.json) cover finite geometry, envelope, original mounting bores and FrontSide walls, native receiver aperture with real dark backing, PCB bore walls, Grove insertion cavity, passive API, both artwork registrations, unchanged physical geometry with `artwork:false`, four-wire pose, detach and resource disposal. No browser, optical, hardware or production-fit acceptance was performed; stage remains `modeled`.
