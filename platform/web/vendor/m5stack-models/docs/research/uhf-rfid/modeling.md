# Unit UHF-RFID — U107

Modeled, visual-only. `src/units/uhf-rfid/index.js` exports `Model`, `GroveModule` and `spec`.

## Sources and enclosure

- [Official product documentation](https://docs.m5stack.com/en/unit/uhf_rfid), retrieved 2026-10-26; official MCP product query confirms JRD-4035, integrated ceramic antenna, UART Grove and 56 × 48 × 11.5 mm vendor dimensions.
- Original M5_Hardware U107 assembled STL component 0 is retained in full: 6,104 triangles. Components 1 and 2 are the displaced individual copies, whose triangle counts sum to the assembly. The one common rigid transform turns the original Grove edge down, with no scale, shell cuts, fills or independent alignment. Source and transform are in `cad-map.json`.
- Model axes are +X right, +Y top and +Z the front RFID mark: `[48,56,11.5]` mm. Vendor length/width order `[56,48,11.5]` is separately recorded. The original faceted shell has a measured Y envelope of 55.989 mm.
- Four native through bores at `[±16,±24]` retain their faceted walls, together with the open top strap slot, rear snap windows, front snap tabs, shell seams and recessed back-label bed. The tabs are enclosure fasteners, not invented buttons.

## Physical assembly

The blue HY2.0-4P socket has a real insertion cavity, walls, guides, rear stop, four metal pins and solder tails. Its exposed six-millimetre height follows the native opening; insertion depth is reconstructed. A fixed carrier PCB backs the rear snap windows without closing the strap slot or mounting bores. The module PCB, five-pin P1 spacer and contacts, solid ceramic antenna dielectric, ground electrode, top metallization and feedthrough have physical depth. A concealed unmarked shield and the three interface passives complete the visual stack.

Only the product text confirms the JRD-4035/integrated ceramic assembly. The [public schematic](https://static-cdn.m5stack.com/resource/docs/products/unit/uhf_rfid/uhf_rfid_sch_01.webp) stops at P1 Header5 and J1 HY2.0 UART; it shows R1 10K and C1/C2 100nF/22uF. It does not establish RF ICs, module board size, shielding, antenna dimensions, PCB profiles, stack heights or installed part datums. Those concealed shapes and placements are explicitly inferred visual reconstructions. No production-fit or RF-topology claim is made.

The older MCP schematic summary incorrectly invents an LDO, UART series resistors and RF internals absent from that diagram. The original diagram was checked and feedback was accepted as `6ce62148ba3442c3b9bf6a3aa103c70e`. None of those unsupported circuit components is added.

## External integration

```js
import {Model,GroveModule} from './src/units/uhf-rfid/index.js';
const device = new Model({artwork:true});
const antennaAnchor = device.get('sensor'); // passive Component, getState() === {}

const unit = new GroveModule({cableLength:70});
controller.port('grove').attach(unit); // use the actual controller Port id
controller.handle({type:'pose',target:'grove/unitFrame',position:[0,75,0],rotation:[0,.2,0]});
controller.update(1/60);
controller.port('grove').detach();
unit.dispose();
```

`grove` is the only exposed port. Pin legends in cable order are GND / 5V / RXD / TXD. `sensor` is a passive visual anchor at the antenna/module and accepts no scan/read/write/tag/RSSI/UART command. There are no exterior buttons, LEDs, displays, joints, USB or external antenna connector in the documented product. GroveModule additionally exposes the shared `unitFrame` and four-wire `cable` visual components. External software owns all RF, tag data, UART and firmware behavior.

## Artwork and validation

Two final PNGs accompany the model from its first checkpoint. The back uses the supplied latest exact-product production contours rendered directly to 2,400 × 2,400 PNG, with the original 30 mm square label, full text, pin colours, M5Stack mark and `UP TO 1M` revision. The front antenna/tag mark is a transparent 3,300 × 2,200 reference redraw from the exact-model official front photo. Both project only onto the original shell. Source vectors, table, private links and conversion intermediates are not distributed. See `artwork.json`.

`artwork:false` removes both printed surfaces while retaining identical physical geometry. Necessary smoke checks cover finite geometry, the full native shell, axial mounting/strap clearances, FrontSide native and PCB bore walls, recessed latch/socket backing, solid antenna/module parts, passive API, Grove pose/attach/detach/disposal and both artwork registrations. No browser, full historical, hardware, RF or production-fit verification was performed; stage remains `modeled`.
