# Unit CamS3-5MP — U174-B

Official source checked 2026-10-26. The exact U174-B product is the fixed-focus **PY260 5MP** model, not the earlier OV2640 model. Nominal dimensions are 40×24×11 mm; model axes are +X right, +Y antenna end, +Z camera front, giving [24,40,11] mm. See [official product page](https://docs.m5stack.com/en/unit/Unit-CAMS3%205MP).

The exact official structure supplies three assembled plastic parts: front carrier, rear shell and fixed optical cover. Their native relative pose is retained. Only laterally exploded duplicate copies are excluded. Native lens, rear RF, header, card, Grove and clip reliefs remain open. The RF opening contains an actual metal shield/module substrate; the bottom window contains a card roof, insulating carrier, side rails and eight recessed contacts. The fixed optical stack contains an annular barrel, two physical glass elements, a sensor die/carrier and a 24-contact FPC assembly. A main PCB and microphone package occupy their real subassembly roles. No photo is used as a solid surface.

The exact rear photograph and dimension drawing show two **1×3** 2.54 mm female headers. The left is EN/G0/GND, the right G44/G43/5V. The linked generic schematic/MCP description instead reports Header4/GPIO3/GPIO8. Official feedback `e93f98ee2af2490cb83526f65cb8a56e` requests the correct revision; this visual model follows exact U174-B photographs and dimension drawing. No electrical interpretation is provided.

## Public visual API

`Model` is a standalone device; `GroveModule` supports the existing rendered Grove cable and Unit frame. Components: `status-led` (fixed blue, external on/brightness), `sensor` (noninteractive visual anchor), `grove`, `sd`, `download` and `expansion`. The latter three are physical mating frames only and reject Grove modules. There are no real onboard buttons or movable optics to expose.

```js
import {Model,GroveModule} from './src/units/cams3-5mp/index.js';
const camera = new Model();
camera.get('status-led','led').set({on:true,brightness:.6});
const unit = new GroveModule({cableLength:45});
host.port('grove').attach(unit);
host.handle({type:'pose',target:'grove/unitFrame',position:[0,50,0]});
```

No capture, frames, image recognition, microphone audio, networking, card/filesystem, firmware, USB/UART or electrical commands are implemented. Camera optics are fixed. LED appearance does not respond automatically to attachment or pretend capture state.

## Sticker boundary

Four approved final PNG rasters reproduce the supplied original design: front 5MP label, top wrap, rear brand label and rear pinout. They are rendered at 1024 px width from original outline artwork, not enlarged from the preview and not cropped from a product photograph. Cut/fold guides are excluded, with original glyph outlines preserved using corrected nonzero winding. Front/top/rear prints project onto their actual physical surfaces; the die-cut rear pinout film spans the product's true label recess while the PCB/card assembly remains behind it. `artwork:false` disables all prints without changing component API or nonprinted geometry.

Source table, vector original, source links, mappings, conversion intermediates and generators are private. Only final PNGs and surface registration code are included. Final artwork remains the owner's copyright; code and official structure retain their respective MIT notices.

## Necessary checks and limitations

[smoke.json](./smoke.json) records finite physical geometry, complete source shell selection, physical lens glass/barrel and microphone bore normals, RF/card/Grove backing, six recessed header sockets, fixed-blue API, passive sensor rejection, rendered four-wire attachment/pose/detachment/disposal and artwork opt-out. [sources.json](./sources.json) records official references, hashes and selected-source transform.

Concealed board Z/outline/thickness, optical/FPC, RF package, card contacts and LED/microphone datums are visual reconstructions from exact references. They are not production fit or optical simulation. No browser, exhaustive face acceptance, real hardware or firmware check was run; stage remains **modeled**.
