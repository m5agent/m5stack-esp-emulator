# Unit ASR U194

The model uses the exact U194 official product page, schematic and native assembled STL. Model axes are millimetres: +X right, +Y speaker end, +Z front grille. Vendor 48 × 24 × 16 mm becomes [24, 48, 16] in model axes. This is the CI-03T Unit ASR U194, distinct from CI1302 Module ASR M147; no Module ASR USB, switches, M5-Bus or square shell were used.

## Physical assembly

Source island 0 retains all 13362 original assembled-shell triangles with one rigid translation recorded in `cad-map.json`. Islands 1 and 2 are displaced duplicate individual halves. There is no scaling, shell cutting, filling or independent half alignment. The native grille, Grove mouth, two 5 mm mounting bores, fastening relief, embossed mark and seams remain intact.

Added physical components include a carrier PCB with open boss/Grove reliefs, CI-03T module PCB and processor envelope, its 22 fixed edge pads, D1 diode, capacitors/resistor bodies, hidden red D4 package, fastening screw/shank and complete Grove socket cavity/contacts. Hidden geometry placement is inferred, not production CAD. The loudspeaker has a real rectangular chassis with oval opening, suspension, recessed cone, dust cap, basket ribs, magnet can, rear plate, solder terminals, concealed two-pin P1 socket and fixed pair of internal leads. Every sampled native grille path meets physical speaker geometry even with artwork disabled.

The small front shoulder MIC inlet is backed by a physical microphone can, true acoustic bore, insulating rear disc, inferred fitted gasket and duct with real bores, recessed fixed diaphragm, fine protective mesh wires and two fixed PCB leads. Its installation follows the exact exterior photo and existing native shoulder seam, without modifying the original source shell. Microphone package dimensions, gasket/duct geometry and installed datums are visual reconstructions. They do not claim a production acoustic design.

D4 is a red LED in the exact Unit schematic. Exterior photos do not prove an exposed lens/window/light path. A fixed hidden red package is modeled, with no invented exterior Led component. The blue bulb shown on the rear sticker is printed artwork. No actual button or USB is documented or visible. P1 is an internal fixed speaker connection, not an externally exposed mating Port.

The product body calls the speaker 8Ω@0.8W, while the exact official rear label prints 8Ω@1W. Both facts are recorded; the faithful rear PNG retains the printed 1W. The model does not determine electrical speaker rating. Official feedback `6bd4721d4c394947a8bf872de266f1cd` was accepted for this discrepancy and missing production assembly/D4 optical-path data.

## Agent integration

```js
import {Model, GroveModule} from './src/units/asr/index.js';
const standalone = new Model();
const unit = new GroveModule({cableLength: 60});
host.port('grove').attach(unit);
host.handle({type: 'pose', target: 'grove/unitFrame',
  position: [20, 80, 0], rotation: [0.2, 0, -0.15]});
host.update(1 / 60);
```

`grove` is the sole exposed Port, faces −Y and records `GND`, `5V`, `RXD`, `TXD` in black/red/yellow/white order. `GroveModule` supplies two physical plugs and four rendered conductors. Its additional `unitFrame` and `cable` accept the existing pose/cable interfaces. `sensor` is a passive CI-03T visual anchor with empty state and no commands. There are no Button, Led, Joint, Slider, speaker displacement or microphone capture components. UART, recognition, wake words, voiceprint, playback, audio capture, signal processing, firmware, values and electrical behavior belong to the external framework. Fixed cone and microphone geometry do not move autonomously or emit simulated data.

## Evidence and limits

`sources.json` records exact official URLs, CAD commit/blob/source hashes, selected island and all runtime hashes. `smoke.json` records finite geometry/envelope, ten open mounting rays and eight FrontSide bore walls, actual PCB screw-bore walls, 47 native grille paths backed by physical speaker, two contacts/two fixed internal speaker leads, microphone can/gasket real bores with FrontSide walls, protection mesh backing, Grove cavity/four-wire pose, nested identity, detach and resource disposal. Two PNG label registrations and `artwork:false` physical-buffer/transform invariance pass. The rendered ordinary PNGs were decoded and opened locally.

PCB/module/package outlines/XYZ, speaker assembly dimensions/datums, P1 geometry/pitch/location, lead routing and microphone acoustic installation are inferred without a complete production assembled STEP. Necessary checks do not prove browser pixel acceptance, acoustic design, manufacturing fit or real hardware behavior. Exhaustive browser review is deferred under the user's current instruction; catalog stage remains `modeled`. Raw official photos/STL/MCP and generators stay outside the public repository. Both actual label faces are included now; see `artwork.md` and `artwork.json`.
