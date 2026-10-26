# Unit Step16 U198

Modeled visual shell and external kinematics. Official product: <https://docs.m5stack.com/en/unit/Unit_Step16>. Local geometry/API smoke only; browser inspection is deferred at the user's request.

## Sources and assembly

Official MCP product documentation and schematic identify **GSMR-16 rotary DIP switch**, **STM32G031G8U6**, **FPC1 seven-segment A–G/DP display**, **WS2812C-2020 RGB**, ME6206A33XG, I2C Grove and internal J4 SWD_5P. This product is a 16-position BCD rotary control, with no documented pressing action. It is not a stepper motor or motor driver.

Official envelope is 32 × 24 × 16.9 mm. Our axes are +X right, +Y top and +Z toward the knob: normalized envelope 24 × 32 × 16.9 mm, from Z −4 to +12.9. The rear label adds 0.008 mm. Four native components use the same rigid translation: complete rear 2670 triangles, front 2334, actual moving cap 1436 and actual RGB light guide 256. Four displaced duplicates are excluded. No shell hole filling, cuts, scaling, independent assembly alignment or guessed replacement cap.

Mounting bores remain real through-holes. The native rear straight bore is approximately 4.85 mm across X; the front is approximately 4.8 mm. Faceted cardinal wall distances are approximately 2.34–2.43 mm; the source is kept unchanged. These are source mesh measurements, not an independently validated drill specification.

A scalloped PCB, MCU/regulator/passive bodies, fixed GSMR-16 body/retaining plate/contacts, rotating shaft, physical seven-segment body/lenses/flex, RGB package, rear screw and real four-contact open Grove housing fill the visible openings appropriately. Concealed electronic layout, sizes, installed Z, segment positions and light spread remain appearance reconstructions. No production assembly STEP, manufacturing fit or electrical behavior is claimed.

## External appearance API

Exports: `Model`, `GroveModule`, `spec`. Components:

| ID | Kind | External command |
| --- | --- | --- |
| `rotation` | joint | `angleDeg`, optional `durationMs` |
| `segment-a` … `segment-g`, `segment-dp` | led | `on`, `brightness`; fixed warm yellow |
| `rgb` | led | `on`, `brightness`, `color` |
| `grove` | port | Standard Grove attach/detach |
| `sensor` | component | Passive visual anchor, no value commands |

```js
import {Model, GroveModule} from './src/units/step16/index.js';
const unit = new Model();
unit.handle({type:'joint', target:'rotation', angleDeg:22.5});
unit.handle({type:'joint', target:'rotation', angleDeg:11.25, durationMs:120});
unit.handle({type:'led', target:'segment-a', on:true, brightness:0.7});
unit.handle({type:'led', target:'segment-dp', on:true});
unit.handle({type:'led', target:'rgb', color:'#00bfff', brightness:0.5});
unit.update(0.12); // Viewer already calls update() while animating.

// Existing host with a Grove Port. The module renders both plugs and four wires.
const branch = new GroveModule({cableLength:60});
host.port('unit').attach(branch);
host.handle({type:'joint', target:'unit/rotation', angleDeg:45});
host.handle({type:'led', target:'unit/segment-g', on:true});
host.handle({type:'pose', target:'unit/unitFrame', position:[14,72,-4], rotation:[0.2,0,0]});
host.port('unit').detach();
```

The rotary joint rotates only the actual native cap and shaft. Its fixed body, front, PCB, segments and RGB remain stationary. The joint metadata records 16 positions and 22.5° spacing; it accepts intermediate visual angles and does not snap. The native CAD rest is visual rest, without claiming firmware zero, mechanical code order or direction. No automatic rotation or nonzero RPM is exposed for this positional control. There is no press/button component.

All nine indicators default off. The eight display segments have independent fixed warm yellow/amber appearance, reconstructed from the exact U198 lit photo, rather than a measured spectrum or confirmed display part number. Each physical segment is independently emissive; a matching local shader patch makes the light visible through the unchanged solid white front membrane. RGB drives the original exposed light guide. This is an appearance approximation, not an optical simulation. There is no LCD framebuffer, hex glyph conversion, automatic angle-to-BCD-to-display link, electrical supply link, I2C, register, firmware, sensor-value or input echo behavior. A simulator controls all of those externally.

## Sticker

One 2292 × 1704 PNG redraws the complete rear STEP16 circuit-diagram label from the same-model official straight rear photo `Unit_Step16_05.webp`. The top blue name band, switch/STM32/G031/segment/RGB diagram and bottom red PORT.A.I2C and four pin cells follow that source. The front and knob are plain white in the exact photographs, so no extra print is invented. Typography, colours and dimensions are reconstructed; this is marked `reference-redraw` rather than an official original. No product-photo crop is used. Source table, vector/redraw inputs, generator and intermediates are private and undistributed.

The raster is projected onto the actual rear mesh at 19.1 × 14.2 mm, [0, 7.1, −3.97], back facing, 0.22 mm projection depth. `new Model({artwork:false})` suppresses the print and leaves all physical parts unchanged.

## Necessary checks

[smoke.json](./smoke.json) records finite meshes; complete native parts/envelope; open native and PCB bores with FrontSide walls; cap/shaft movement and fixed-part invariance; independent segments/RGB and off/rest behavior; external command/no echo boundary; four real Grove wires with nested pose/attach/detach; and artwork/physical invariance. This is not browser acceptance or hardware/electrical verification. [sources.json](./sources.json) and [artwork.json](./artwork.json) preserve source, licensing and raster placement.
