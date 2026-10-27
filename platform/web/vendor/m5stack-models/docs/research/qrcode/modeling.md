# Unit QRCode U173

U173 uses the complete original assembled shell, separate original TRIG cap and removable fixed refractor frame from the official M5_Hardware STL. A common translation `[0, -12, -8]` establishes +X right, +Y toward the scanner, +Z toward the TRIG/front label. Source islands 0/3/5 retain all 4740/1054/280 triangles. Displaced duplicates 1/2/4/6 are excluded. No scaling, shell slicing or fixed duplicate button face is used.

The nominal assembled size in model-axis order is 27.2 × 65.8 × 18.4 mm; vendor length-first order is 65.8 × 27.2 × 18.4 mm. The native assembled CAD envelope is 27.6000004 × 65.8207893 × 18.6119833 mm. The direct-view base is 24.0000057 × 48.0000038 × 16 mm. CAD remains unchanged despite the nominal-width difference. The original two Ø5 mounting bores at X=±8, Y=-12 stay open with FrontSide inner walls.

The optical head contains a physical M14 enclosure, internal board, central hollow camera barrel, fixed convex glass, CMOS package/window and two real LED packages. Exact U173 photographs show one white illumination package and one red aiming package; they are distinct external visual LEDs. The carrier PCB includes STM32F030F4P6, HX6306P332MR, FPC-12P socket/ribbon, fixed buzzer, passives and pink four-contact Grove socket. Concealed PCB/component installation, engine/optical-stack dimensions, mirror sheet and mechanical travel are inferred envelopes; no production assembled STEP or manufacturing fit is established.

`refractor:true` is the default installed configuration. `refractor:false` removes the native frame and its reflective sheet together to expose the straight scanner. The accessory is a removable fixed-angle part; there is no invented swivel, hinge, joint, scan beam or optical simulation.

| Address | Surface or object | External behavior |
| --- | --- | --- |
| `button` | Entire original independent TRIG cap | Momentary press/release/cancel; 0.3 mm visual travel estimate; cancel restores the exact neutral transform |
| `mode` | White side slide | Retained position 0 UART / 1 I2C, estimated 2 mm detent travel; `setPosition`/`position` drives shape without input echo |
| `illumination` | One M14 white LED lens | Fixed warm white, independently external on/brightness, default off |
| `aiming` | One M14 aiming LED lens | Fixed red, independently external on/brightness, default off |
| `grove` | Pink HY2.0-4P, four real contacts | Attachment and four-wire cable pose; GND, 5V, UART_RX/SDA, UART_TX/SCL labels |
| `sensor` | Fixed M14 visual anchor | Passive anchor; rejects scan/capture/decode/recognition/audio/register commands |

```js
import {Model, GroveModule} from './src/units/qrcode/index.js';
const device = new Model({refractor: true});
device.on('input', event => externalFramework.receiveInput(event));
device.handle({type: 'press', target: 'button', source: 'external'});
device.update(0.1);
device.handle({type: 'cancel', target: 'button', source: 'external'});
device.update(0.2);
device.handle({type: 'position', target: 'mode', position: 1, immediate: true});
device.handle({type: 'led', target: 'illumination', on: true, brightness: 0.7});
device.handle({type: 'led', target: 'aiming', on: true, brightness: 0.25});
const unit = new GroveModule({refractor: false, artwork: false});
// Compatible hostPort.attach(unit) creates actual four-core Grove cable geometry.
// When attached at host port `unit`, nested targets are unit/button,
// unit/mode, unit/illumination, unit/aiming and unit/unitFrame.
```

The model does not turn button presses, the retained slide or LED commands into decoding, camera capture, firmware, bus mode, registers, sounds or electrical state. A separate framework owns those behaviors. The fixed buzzer has no synthetic audio API.

Three corresponding body labels use final high-resolution rasterized original artwork, documented in [artwork.json](artwork.json). `artwork:false` removes the artwork while preserving all physical buffers, indices and transforms. Product photos are references only; no photograph crop becomes a sticker. Private originals, table, mappings, source URLs and generators are excluded.

[Local smoke](smoke.json) checks finite geometry/world transforms, both assembled envelopes, mounting-hole voids/walls, three actual optical first-hit surfaces, camera barrel bore, Grove cavity/contact count, cap press/cancel reset, retained slide, independent fixed-colour LEDs, artwork physical invariance and nested Grove pose/detach/disposal. Browser, full historical, optical, electrical, firmware, hardware and production-fit acceptance remain outside this local check. Stage is `modeled`.

Official feedback `7b38fe984a6c44da8681786c3336e7b5` was accepted for drawing/STL dimension revision applicability and missing assembled installation/actuation datums.
