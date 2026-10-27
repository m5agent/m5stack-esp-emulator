# Unit DAC2 U012-B

Runtime model axes are X = 24 mm, Y = 32 mm, Z = 10.2 mm; the official product table lists the same dimensions in 32 × 24 × 10.2 mm order. The full original assembled shell is 24 × 32 × 8 mm. Its 3,286 triangles are retained at scale 1 with one rigid Y half turn and translation. The two displaced shell copies are excluded. No hole filling, shell scaling, separate half alignment or CAD cuts were used.

The original mounting holes stay faceted and stepped. At the rear straight bore, opposing inner walls span about 5.000 mm in X and 4.8753 mm in Y; the entry recess and centre relief remain the native geometry. The board outline clears the two mounting bosses and the Grove mouth, and has a real central fastening bore. A separate reconstructed PCB carries a physical ten-lead GP8413, TPS61040DBVR, HX6306P332MR, inductor, rectifier, TVS and passives. Concealed package positions and board dimensions are inferred from the actual U012-B envelope and its own schematic. These do not establish production component locations or fit.

Exact U012-B official front, connector and package photographs show a burgundy open-top Grove, an orange fixed four-pole HT3.96 socket and a separate four-screw plug. The socket has a real insertion cavity, floor, side walls, rear wall, four roof inspection holes and four metal contacts. The removable plug has individual contact bores and recessed metal springs, four wire-entry bores, clamp cages and cross-recess screw heads. The plug and concealed contact geometry are product-local appearance estimates, not a universal certified connector asset.

The own schematic has JP1 populated with a 0 Ω A0 strap and JP2/JP3 unpopulated A1/A2 pads. These are small fixed PCB features. They are not external DIP switches. Neither the exact visible product photographs nor the own schematic establishes an exposed LED, so this model has no LED or button component.

## External API

`Model`, `GroveModule`, `TerminalPlug`, and `spec` are exported by `src/units/dac2/index.js`. The chassis has `grove`, `terminal`, and a passive `sensor` appearance anchor. `sensor` accepts no DAC, voltage, current, address, protection or sensor-data commands. Grove is a physical four-pin connector with GND / 5V / SDA / SCL; front label G/V/D/C order is retained. Terminal left-to-right V0/G/V1/G maps to the own schematic's P1 pins 4/3/2/1.

```js
import {Model, GroveModule, TerminalPlug} from './src/units/dac2/index.js';

const unit = new Model({terminalPlug: true});
unit.handle({type: 'joint', target: 'terminal/screw-1', angleDeg: 70, durationMs: 150});
unit.update(0.15);
unit.handle({type: 'joint', target: 'terminal/screw-1', angleDeg: 0});

// The same supplied plug can be attached and detached independently.
const bare = new Model();
const plug = new TerminalPlug();
bare.port('terminal').attach(plug);
bare.port('terminal').detach({dispose: false});
plug.dispose();
```

`terminal/screw-1` through `terminal/screw-4` externally rotate only their own visible heads. They support a finite angle and timed angle transition, and reject nonzero RPM. A ±180° viewer suggestion is not a measured mechanical tightening range. Resetting to 0 restores each original head quaternion exactly. There is no axial travel, clamp displacement, tightening torque, wire insertion state, voltage, current or electrical conversion behavior. External commands do not emit user input intent.

```js
// A host Port with connector:'grove' accepts this module.
const module = new GroveModule({cableLength: 60, terminalPlug: true});
host.port('grove').attach(module);
host.handle({type: 'pose', target: 'grove/unitFrame', position: [12, 65, -4], rotation: [0.2, 0, -0.1]});
host.handle({type: 'joint', target: 'grove/terminal/screw-4', angleDeg: -35});
host.update(0.016);
```

`GroveModule` adds the common `unitFrame` pose controller and `cable`: four distinct black/red/yellow/white wires, two physical plugs, and a moving endpoint. This demonstrates physical attachment and nested addressing; it does not establish pin continuity, I2C communication, bus loading or a DAC firmware implementation. Each model/module needs its own `artwork:false` option if its labels should be hidden.

## Evidence and limits

The own official MCP result, exact official schematic, original CAD and exact product photographs establish product identity, fixed visible components and connector roles. [sources.json](sources.json) records public source URLs and hashes; [artwork.md](artwork.md) describes the two original-source PNGs. No raw CAD, product photographs, private source artwork, original vector names, spreadsheet records, source links or generation scripts are distributed.

[smoke.json](smoke.json) records necessary local checks: complete physical envelope, native faceted bore walls, actual connector backing, independent screw animation and reset, plug detach/reattach, unchanged chassis buffers/indices/transforms for artwork and plug options, passive API rejection, four-wire Grove pose, nested addressing, resource release and raster registration. This is the `modeled` stage. Browser pixel re-review, physical devices, production fit, voltage/current, short-circuit protection, bus communication and firmware behavior have not been verified.
