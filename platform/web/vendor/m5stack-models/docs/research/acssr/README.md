# Unit ACSSR U139

Modeled as the complete assembled 80 × 45 × 31 mm kit: the original small controller enclosure plus its bundled solid-state relay. Axes: +X right, +Y AC-output end, +Z front/button face. Only necessary local construction/API checks were run; this remains `modeled`, with no browser or physical-device acceptance.

The official [U139 product page](https://docs.m5stack.com/en/unit/acssr) and [controller drawing](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/786/U139_Model_Size.png) distinguish the kit envelope from the approximately 45 × 18.7 × 11.5 mm controller. The [original structure](https://github.com/m5stack/M5_Hardware/tree/e29c139cbc7c80b5ccc5557e5ab8025a7a19a109/Products/U139_Unit_ACSSR/Structures) supplies only this controller. Component 0 retains all 2,654 triangles, using one rigid transform; components 1 and 2 are displaced shell copies. No stretching, clipping, replacement front cap or artwork closure is used.

The exact U139 gallery identifies the bundled DELIXI CDG1-1DA/10A SSR, four real screw terminals, white screw-access guards, thermal base, two fork contacts and two removable orange four-pole plugs. These SSR parts, the controller PCB/packages and their installed transforms are photo/dimension-constrained appearance reconstructions. They are not production assembly tolerances. The [official schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/598/Sch_UNIT_ACSSR.pdf) confirms the separate D4 red 0603 power LED on page 2 and LED1 SK6812 plus S1 button on page 4.

## External visual API

- `button`: original integral controller tongue; `press` / `release` / `cancel` emits input intent. Its inferred 0.22 mm free-end travel bends the original vertices from the hinge and restores exact neutral positions/normals after release/cancel. The invisible stable pick target does not replace the visible shell.
- `rgb`: SK6812 full-color appearance, independent external `led` command.
- `power-led`: controller D4 fixed red `#ff2820`, independent external on/brightness. Rear guide/optical placement is inferred from the PWR mark; original rear shell is preserved.
- `ssr-led`: SSR independent fixed red `#ff2820`, external on/brightness. No automatic relationship to any button, cable, other LED or SSR terminal.
- `ssr-screw-1` / `ssr-screw-2`: visible upper AC-output screw heads, left/right in front view. `ssr-screw-3` / `ssr-screw-4`: lower DC-input screw heads. External `joint` angle rotates each physical head only. No axial clamp travel, thread pitch, torque or safe tightening range is claimed. RPM is rejected.
- `grove`: red HY2.0-4P, GND / 5V / SDA / SCL. `GroveModule` provides four physical wires, two plugs and `unitFrame` pose.
- `terminal-1` / `terminal-2`: left/right recessed `ht3.96-4p` sockets. Their local contact order is RS485_B / RS485_A / VIN / GND. Both are physical attachment frames, without simulated electrical linkage.
- Exported `TerminalPlug` mates to either terminal and exposes `screw-1`…`screw-4`. `new Model({terminalPlug:true})` or `new GroveModule({terminalPlug:true})` installs two independent supplied plugs; default models show their fixed empty sockets. The screw geometry remains below true access bores.
- `sensor`: passive visual anchor with no operational commands or data.

```js
import {Model, GroveModule, TerminalPlug} from './src/units/acssr/index.js';
const unit = new Model({terminalPlug:true});
unit.handle({type:'press', target:'button', source:'external-pointer'});
unit.update(0.016);
unit.handle({type:'cancel', target:'button', source:'external-pointer'});
unit.handle({type:'led', target:'rgb', color:'#2f73ff', brightness:0.4});
unit.handle({type:'led', target:'ssr-led', on:true});
unit.handle({type:'joint', target:'ssr-screw-1', angleDeg:35});
unit.handle({type:'joint', target:'terminal-2/screw-3', angleDeg:-40});
```

There is no moving armature in this semiconductor SSR. No AC/DC switching, actual load, mains, supply, I2C/Modbus, Wi-Fi, firmware or hardware behavior is implemented. White guards are fixed because a supported cover-removal motion/production attachment contract has not been confirmed.

## Stickers and rights

Two final PNGs were drawn from exact-model official photographs, alongside this model. They are code-drawn clean artwork, without product-photo crops: `reference-redraw-controller-back.png` (2250 × 900) from photos 04/05 and `reference-redraw-ssr.png` (2150 × 1450) from photo 07. No exact ACSSR/U139 row was found in the supplied private sticker table. Small unreadable QR/serial content on the SSR plate is omitted, and logo/certification/bulb outlines are approximate. These appearances do not establish certification or ratings. Position/scale follows the physical shell/plate and remains an appearance estimate.

`artwork:false` removes both printed surfaces and preserves the complete physical geometry and APIs. The final PNGs may be distributed under the user's image authorization; M5Stack/DELIXI names, symbols and marks retain their respective rights. The private table, mapping, originals, redraw code and conversion intermediates are excluded. Official CAD derivatives retain M5_Hardware MIT attribution.

Necessary checks are in [smoke.json](./smoke.json): finite positions/normals, complete controller triangles, actual mounting/screw bores and FrontSide walls, real fork slots, full SSR backing, native tongue cancellation, three independent LEDs, all screw angles, two separate removable plugs, four-wire pose/nested commands/disposal and physical invariance with stickers disabled.

Official populated mechanical assembly, SSR part dimensions and rated button travel remain unavailable in the checked sources. A specific documentation request was saved through M5Stack knowledge feedback: `f18f5b11d40847f78e7e950a583a548e`. This does not block visual-only expansion; refine installed dimensions when those source drawings become available.
