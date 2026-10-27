# Unit MIDI U187

The model retains the entire native rear shell (3452 triangles), front shell (2892), and green power light guide (254) from its own official structure. One common rigid translation is applied at scale 1. The displaced duplicate parts are excluded. Native holes, embossed M5, mounting tongue, seams and cutouts are preserved. Model coordinates are X = 40 mm width, Y = 48 mm length towards the AUDIO jack, and Z = 25 mm thickness towards the front label; the vendor lists 48 × 40 × 25 mm. Original CAD/physical envelope is 39.994690 × 47.989529 × 25 mm. The drawing's two Ø4.85 mm mounting bores have 16 mm pitch.

The two large side apertures contain separate physical DIN five-contact female sockets: squared flanges, insertion barrel, upper key channel, insulating carrier with five actual holes, hollow metal contact sleeves/springs and recessed stops. Both five-hole sets are open to about 8.28 mm behind their face. Each of the three PJ-342 sockets has a true 3.5 mm bore, three spring contacts and a physical stop about 12.825 mm behind the mouth. They are not black disks over empty shells. The Grove socket has an open cavity, four metal contacts and a rear wall. The PCB, SAM2695, TLP2361 optocoupler, regulator, transistor, crystal, passives, upper board and board connectors provide physical internal backing.

Concealed board outlines, Z positions, package placement, interconnect arrangement, socket contact/key geometry and depths are visual reconstruction. They are not production assembly datums. No manufacturing fit or mechanical interchangeability has been verified.

## External components

| ID | Type | Physical meaning |
| --- | --- | --- |
| `grove` | `grove` Port | Four contacts; GND, 5V, UART_RX, UART_TX labels from official Grove table |
| `midi-in-din` | `din-5pin-female` Port | Right side DIN MIDI INPUT |
| `midi-out-din` | `din-5pin-female` Port | Left side DIN MIDI OUTPUT |
| `midi-in-trs` | `audio-3.5mm-trs` Port | Right side 3.5 mm MIDI INPUT |
| `midi-out-trs` | `audio-3.5mm-trs` Port | Left side 3.5 mm MIDI OUTPUT |
| `audio` | `audio-3.5mm-trs` Port | Far end stereo AUDIO OUTPUT, tip left/ring right/sleeve AGND |
| `mode` | Latching Button | Left Bypass = 0; right Separate = 1; retained visual slide |
| `power-led` | Fixed-green Led | Original light guide; independent external brightness, default off |
| `sensor` | Passive Component | Fixed SAM2695 appearance anchor |

TRS ports deliberately share the existing physical connector family, with distinct `meta.signalRole` values. A connector match only permits geometric placement. It does not demonstrate signal/electrical compatibility. DIN and TRS ports reject Grove modules. The official product table groups all five connectors under audio outputs, but its own photos and schematic identify two MIDI inputs, two MIDI outputs and only one stereo audio output; model roles follow that direct evidence.

```js
import { Model, GroveModule } from '../../../src/units/midi/index.js';
const model = new Model();
model.handle({ type:'position', target:'mode', position:1, immediate:true });
model.handle({ type:'led', target:'power-led', on:true, brightness:0.6 });
model.on('input', event => {
  if (event.id === 'mode') {
    // Feed input intent to your framework; decide routing/audio externally.
  }
});

const module = host.port('grove').attach(new GroveModule({ artwork:true, cableLength:100 }));
host.handle({ type:'pose', target:'grove/unitFrame', position:[0,110,0], rotation:[0,0,0.2] });
host.handle({ type:'position', target:'grove/mode', position:0 });
host.handle({ type:'led', target:'grove/power-led', on:false });
host.update(1/60);
host.port('grove').detach();
```

The slide travels 2 mm along X; travel is a visual estimate from the native aperture and own U187 photograph, not a measured specification. External commands produce no input echo. Pointer/key input changes the retained detent and emits normal input intent; release/cancel ends capture while retaining the selected physical position. Fixed package, jacks and light guide do not move. Key M is mapped to `mode`. The green light guide is confirmed by its own product photo and LED1 in its own schematic; its appearance does not turn on automatically when connected or when the slide changes.

The model has no joint, display, speaker, automatic MIDI patching, UART parser, synth, audio playback or signal simulation. The passive `sensor` rejects MIDI, note, route, sound and sensor-value commands. External frameworks own firmware, electrical state, protocol and sound. The four-strand Grove cable and attached Unit poses are mechanical visualization only, including when used under a HUB.

## Source discrepancies and checks

The product table writes 31520 bps, while the official Unit MIDI Arduino tutorial explicitly writes 31250. The model implements no baud rate. The original schematic also repeats R11 for a 22K reset pull-up and a 220R MIDI output resistor. These conflicts and the interface-role table were submitted through M5Stack official feedback; receipt `483f51e99d0646a98323a77676cfd3e2`.

[smoke.json](smoke.json) records the necessary local checks: finite FrontSide geometry, native mounting bores, both DIN five-hole/contact/key depths, three TRS insertion cavities, stable slide/independent green light, rejected nonvisual commands, two decal registrations with physical buffers/index/matrix invariant when artwork is disabled, and nested four-wire Grove pose, detach and resource release. No browser-wide review, physical hardware, audio/MIDI, electrical or production-fit validation was performed; stage remains `modeled`.

See [sources.json](sources.json), [artwork.md](artwork.md) and [artwork.json](artwork.json).
