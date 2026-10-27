# Unit DDS U105

The complete native assembled shell is retained from the exact official U105 structure:6562 triangles, one common translation at scale1. The displaced separated front/rear copies are excluded. No cuts, filling, scaling or per-part realignment changes the original seams, mounting bores or the two small connector-retention windows.

Coordinates use X width24 mm, Y shell length64 mm towards SMA, and Z thickness8 mm towards the front label. Origin is at the shell centre. The official drawing gives overall length71.4 mm including SMA, so catalog/model nominal dimensions are24 ×71.4 ×8 mm; vendor order is71.4 ×24 ×8 mm. The full visual bounds have Y=-32 to39.4 mm and are not centred at the origin. Two native Ø4.85 mm mounting bores sit at[-8,-20] and[8,-20], a16 mm pitch.

## Physical contents

The output is an actual SMA female geometry: continuous external helical thread, annular metal mating barrel, recessed PTFE insulator, hollow recessed female centre-contact sleeve, real0.5 mm centre bore and a blind end4.5 mm behind the face. Its retained internal hex body backs both original gold-coloured windows. Those windows are openings onto the connector body, not LEDs. The rear connector feed-through, short concealed coax and IPEX board receptacle provide physical backing. The Grove mouth is an open red HY2.0-4P cavity with four metal contacts, guide/latch details and a rear wall.

The PCB has scalloped native-mounting clearances, central screw clearance and connector relief. The fixed schematic packages include STM32F031G4x, AD9833, OPA365, SPX3819, X1 marked25M, RP1, passives and SWD pads. Internal PCB/package installation, outlines/depths, short coax arrangement, connector thread pitch/diameters/contact depth and screws are visual reconstruction. They do not claim production assembly, electrical properties or mechanical interchangeability. The bundled SMA-to2.54 mm accessory lead is not included in this model.

## External components

| ID | Type | Scope |
| --- | --- | --- |
| `grove` | Port `grove` | Physical four-wire attachment; GND/5V/SDA/SCL pin labels |
| `sma` | Port `sma-female` | Physical output connector family, centre SMA_OUT and outer AGND labels |
| `sensor` | Passive Component | AD9833 appearance anchor; no commands |

There are no push buttons, rotating controls, LEDs, displays or sound components. No output waveform, frequency, phase, sleep, signal, I2C register or electrical behavior is implemented. The printed curves remain fixed artwork.

```js
import { Model, GroveModule } from './src/units/dds/index.js';
const standalone = new Model();
const connected = host.get('grove').attach(new GroveModule({ cableLength:100 }));
host.handle({ type:'pose', target:'grove/unitFrame', position:[35,80,0], rotation:[0,.2,0] });
// The four-core Grove cable follows the remote body frame.
// `grove/sma` and `grove/sensor` address the attached Unit components.
// Port IDs above belong to the example host; use the actual host's Grove ID.
```

Connector matching describes physical shape only. The `sma` port rejects Grove modules; the `grove` port rejects an SMA family module. Register/firmware/electrical semantics belong to an external framework.

## Source conflict and verification

The exact official product specification says10MHz reference clock. Its original linked schematic labels X1=25M and MCU PA8 RCC_CLK_25MHz routed through R9 to AD9833 MCLK. The exact rear product photograph also prints25MHz. The public sources do not explain whether runtime MCU firmware changes/divides the clock. The model preserves the observed printed label and schematic clock-can appearance without choosing a runtime clock. M5Stack official feedback accepted this clarification request: `618a44e752d24afd8575022fb72781c9`.

[smoke.json](smoke.json) records the necessary local checks: finite FrontSide geometry, complete native shell, open native mounting bores and inner walls, real SMA mouth/centre depth/metal sleeve/dielectric and both window backings, independent connector families, passive anchor rejection, two PNG registrations and physical invariance with artwork disabled, four-wire Grove attachment/pose/detach and complete resource disposal. No browser-wide review, waveform/electrical, hardware or production-fit test was performed. Stage is `modeled`.

See [sources.json](sources.json), [artwork.md](artwork.md) and [artwork.json](artwork.json).
