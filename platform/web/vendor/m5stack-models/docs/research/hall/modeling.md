# Unit Hall — U084

The official dimension drawing specifies **24 × 32 × 8 mm** in the model's X/Y/Z axes (product specifications list 32 × 24 × 8), two **5 mm** mounting bores on **16 mm** pitch and a **10 × 5.2 mm** Grove face. Units are millimetres; +X is right, +Y top and +Z the labeled front. Mounting centers are (−8, −4) and (+8, −4).

The complete assembled shell is official CAD component 0, **3252 triangles**. One common translation centers it; scale remains 1. Components 1/2 are displaced individual half copies (1668 + 1584 triangles) and are excluded. Native mounting bores, connector relief, recessed printed faces, screw relief, seams, release detail and molded M5 mark remain unchanged. The original faceted hole walls face the empty bores; no synthetic hole replacement or rear cap closes them.

The assembled visual interior contains a physical PCB with side scallops, a fastening bore and four Grove solder bores, three A3144E packages with three leads each, 74HC08D with fourteen leads, HT7533, four resistors, seven capacitors and the D1 red 0603 package identified by the original schematic. The open black HY2.0-4P has a floor, sides, latch structures, a recessed rear wall and four separate metal contacts, plus solder tails. The connector opening is an insertion cavity rather than a painted hole. The rear fastening screw has a real head and shank.

The exact exterior photographs and source shell do not establish a separate D1 lens, opening or visible optical path. D1 therefore remains a concealed fixed red package; no exterior `Led` API or artificial light aperture is added. There are no user buttons or moving joints. The packaged magnet is visible in official photos, but its measured dimensions are not supplied, so no fabricated magnet accessory is included.

PCB outline, thickness and Z, concealed package envelopes/XYZ, passive placement, contact insertion depth and fastening shank are visual reconstruction. This is not a populated production assembly STEP and makes no manufacturing-fit, electronic, magnetic or optical claim.

Two high-resolution code-drawn `reference-redraw` PNGs ship with the model: front directional magnet illustration / HALL footer, and rear HALL / A3144E / SIGNAL / pin colors. They contain no photographic pixels. [Artwork details](./artwork.md) record the exact U084 references, final PNG hashes and native-shell registration. `artwork:false` removes printed triangles only; physical buffers, indices and transforms remain identical.

## Integration

```js
import { Model, GroveModule } from './src/units/hall/index.js';
const hall = new Model();
hall.port('grove');               // physical bottom socket, outward −Y
hall.get('sensor', 'component');  // passive anchor for the three A3144E packages

const module = host.port('portB').attach(new GroveModule({ cableLength: 60 }));
host.handle({ type: 'pose', target: 'portB/unitFrame',
  position: [20, 80, 0], rotation: [0.2, 0, 0] });
host.port('portB').detach({ dispose: false });
module.dispose();
```

`GroveModule` exposes shared `unitFrame`, `cable`, nested `grove` and `sensor`. Four separate conductors and two plugs render and follow the posed Unit. The documented wire order is GND / 5V / NC / OUT (black / red / yellow / white). Attachment is visual mechanics and addressing only; it does not verify GPIO compatibility or transfer a signal. `sensor` accepts no acquisition, magnetic field, polarity, digital output or LED commands. Those belong to the external framework.

The bounded [smoke record](./smoke.json) checks finite meshes, source/CAD envelope, clear native mounting bores and FrontSide walls, PCB bore walls, Grove backing, passive API, two artwork registrations, physical invariance with `artwork:false`, cable pose, detach and resource disposal. No browser, physical hardware or production-fit acceptance was run; stage remains `modeled`.
