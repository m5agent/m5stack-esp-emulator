# Unit Laser TX U066

`src/units/laser-tx/index.js` exports `Model`, `GroveModule` and `spec`. Units are millimetres: +X right, +Y toward the emission opening, +Z toward the LASER BEAM front label. Nominal and visual envelope is 24 × 32 × 8 mm; the vendor lists 32 × 24 × 8 mm.

## Structure and visible function

The complete native assembled shell is preserved as component 0 from official M5_Hardware U066 STL: 3556 triangles, one rigid translation, unit scale. Components 1/2 are displaced copies of the two halves and are excluded. No shell cuts, filled holes, independent realignment or modified mounting bores. The source shares its Git blob with U065 RX, but TX electronics are derived only from U066's own schematic and photographs.

The original top emission opening contains an actual hollow brass barrel, diode can, nose, shoulder, solid collimator lens and two internal insulated leads. A notched physical PCB carries the schematic's Q1 AO3400A, R1/R2, C1/C2, Grove solder annuli and four continuous metal tails. The black Grove socket has a real cavity, four contacts and solder tails. Both native mounting holes remain open, with FrontSide-visible bore walls. The fixing screw and shank are physical.

Concealed PCB outline/thickness/XYZ, diode/head dimensions, shoulder/lens profiles, component placement, internal wiring, solder and connector interior depth are photo/CAD-constrained visual reconstruction. The official STL is an enclosure, not a populated production assembly; manufacturing fit and exact internal installation are not claimed.

There are no buttons, moving joints or additional visible indicator LEDs.

## External appearance API

```js
import { Model, GroveModule } from './src/units/laser-tx/index.js';

const unit = new Model();
unit.handle({ type: 'led', target: 'emitter', brightness: 0.7 });
unit.handle({ type: 'led', target: 'emitter', on: false });

// On an existing host Grove Port:
const module = new GroveModule({ cableLength: 50 });
host.port('grove').attach(module);
host.handle({ type: 'led', target: 'grove/emitter', brightness: 0.4 });
host.handle({ type: 'pose', target: 'grove/unitFrame', position: [35, 60, 0] });
host.update(1 / 60);
```

`emitter` is one fixed red `Led`, default off, facing +Y through the native opening. It changes only the local lens material brightness. Colour commands cannot turn it into an RGB indicator. No billboard, beam cone, projected spot, optical propagation, modulation, communication, DIN conversion or receiver coupling is produced. External frameworks own these behaviours and electrical state.

`grove` is a visual HY2.0-4P attachment: GND / 5V / DIN / NC in black / red / yellow / white order. This follows the official U066 interface table. Its own rear sticker literally prints yellow `OUT`; this text is reproduced without changing the host-to-emitter control direction shown by Q1's gate circuit.

`sensor` is a passive fixed physical anchor. It does not accept laser, modulation, communication, receiver, GPIO or sensor-reading commands. A `GroveModule` additionally exposes `unitFrame` and a `cable` with four separate wires and two plugs. Those represent physical placement/attachment only.

To hide artwork, pass `{ artwork: false }` to each model/module separately. This leaves physical position/normal/index buffers and transforms unchanged.

## Artwork and optical evidence

Two high-resolution, code-drawn PNGs reproduce the exact U066 official photographed front and back labels. Both are marked `reference-redraw`; no photograph is cut or projected onto the case. Final PNGs and public source/registration notes are included, while generators and intermediate reference media stay outside the public tree. See [artwork.json](./artwork.json) for each file, size, placement and official photograph hash.

The exact U066 hero and rear sticker print `WL:650NM PWR:5mW`; this supports a visible red emitter appearance. These are printed product claims, not measured output, laser classification or a simulation of optical performance. The schematic identifies D1 only as `Laser` and independently confirms none of those optical quantities.

M5Stack knowledge feedback `b27af2e5d7b74fbbb1fc919b44cc8ac1` was accepted for the schematic-derived search summary omitting the same page's photographic 650 nm / 5 mW claims and for the OUT/DIN naming discrepancy. The model retains the distinction between photo print, schematic topology and electrical behaviour.

## Necessary checks

[smoke.json](./smoke.json) records finite geometry and envelopes; original installation bores and FrontSide walls; PCB fastening/solder bores; actual emission-aperture backing; Grove cavity/contacts; independent fixed-red brightness with no input echo; passive-anchor rejection; four-wire pose/attach/detach/disposal; and both artwork registrations with the physical-geometry invariant.

Stage remains `modeled`. No exhaustive browser, hardware, manufacturing fit, electrical, communication or optical-performance verification was performed.
