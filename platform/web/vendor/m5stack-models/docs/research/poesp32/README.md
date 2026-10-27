# Unit PoESP32 U138

The visual model retains the complete official shell pair and adds the physical PCB stack, ESP32 module shield, IP101G package/leads, regulator/crystal, PoE converter substrate/transformer/capacitors, cyan UART Grove and magnetic RJ45. The RJ45 has a real stepped air cavity, recessed insertion stop, eight independent gold contact springs, folded shield and two independent yellow/green lenses. Native mounting bores, recesses and connector reliefs stay intact.

Official product dimensions are **72 × 26 × 19.2 mm**; repository axes use `[26,72,19.2]`, +Y towards RJ45, +Z towards the front label. Native CAD mounting bores are Ø3.2 mm through with about Ø4.85 mm rear counterbores at X±8, Y−24. One common source translation `[0,24,9.6]` centers islands 0 and 2. The inferred RJ45 face extends 0.15 mm beyond the shell, making the assembled visual envelope 26 × 72.15 × 19.2 mm.

## External visual API

```js
import {Model,GroveModule} from '../../src/units/poesp32/index.js';
const unit = new Model();
unit.get('link-led','led').set({on:true,brightness:0.6}); // fixed yellow
unit.get('activity-led','led').set({brightness:0.3});    // fixed green
const module = new GroveModule({cableLength:65});
host.port('grove').attach(module);
host.handle({type:'led',target:'grove/activity-led',on:true});
host.handle({type:'pose',target:'grove/unitFrame',position:[0,90,0],rotation:[0,0,0]});
```

Both LEDs accept external `on`/`brightness`; attempts to change the fixed lens color retain yellow/green. No automatic link/activity state is derived. `ethernet` is a visual `Port` with connector `rj45-8p8c`, eight documented contacts and +Y outward frame. `grove` uses UART pins `GND,5V,UART_RX,UART_TX`. `sensor` is an inert appearance anchor with no commands or values. There are no exposed buttons, USB ports or moving joints. The model does not implement networking, PHY, PoE power, serial/AT, WiFi/BLE, web, registers, electrical or firmware behavior.

## Artwork

Three final PNGs are attached by default and disabled by `new Model({artwork:false})` or the same option on `GroveModule`. Front/back are exact supplied flat artwork converted to high-resolution PNG; the certification mark uses its complete supplied flat raster preview at native resolution because the CDR converter omits a mark. These are flat source designs, not product-photo crops or redraws. Raw vectors, input table, private mappings and conversion intermediates are not distributed. M5Stack retains artwork rights; the user's permission covers final raster distribution.

The front artwork follows the original recessed front surface. Official assembled photographs show the continuous rear adhesive film spanning the native RJ45-roof relief; the shield/body remain modeled beneath it. Certification registration on the right side is inferred because available assembled photos do not expose the label location.

## Evidence and limits

[sources.json](sources.json) records immutable STL and public references plus final runtime hashes. [smoke.json](smoke.json) records the necessary local check: finite geometry, 5,294 retained native triangles, mounting/PCB/download-hole FrontSide walls, true RJ45 cavity and contacts, aperture backing, fixed-color LED isolation, passive API, four-wire Grove pose/detach/disposal and artwork disable behavior. It is not a browser, production-fit or physical-device acceptance report.

PCB contours, board spacing, internal component XYZ/envelopes, RJ45 insertion internals, spring bends and certification label placement are estimates. Official sources do not include a complete populated production STEP. Further refinement should use such a source rather than altering the original shell to fit the estimates.
