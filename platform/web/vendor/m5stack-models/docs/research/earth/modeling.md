# Unit Earth U019

Stage: **modeled**. The original complete official shell, a solid two-tine probe, its real drillings and electrode faces, the exposed 10K threshold-adjustment head, internal physical circuit parts and a four-contact Grove socket are present. The module renders four separate cable wires and both plugs through the shared Grove wrapper. This is an appearance model; host ADC, comparator interpretation, moisture calibration, electronics and firmware belong to the external runtime.

Coordinates are millimetres: X is the 24 mm width, +Y points toward the probe tips, +Z points toward the blue adjustment head, and Grove exits toward -Y. The complete model is 24 × 64.3 × 8 mm. The official STL contains only the 24 × 32 × 8 mm enclosure. Its assembled component 0 is retained in full, 8,436 triangles, under one common rigid transform; displaced individual shell copies are omitted. The original mounting bores, embossed maker mark, seams and square access aperture remain source geometry. No shell cut, hole fill, scaling or separately aligned shell pieces were introduced.

The official dimension drawing gives a 1 mm probe, 32.3 mm exposed length, 3.95 mm tines and a 4.1 mm central slot. The same-model photographs constrain the tip taper, black base, gold-colored faces and 19 drillings on each tine. The holes pass through the actual PCB and both electrode faces. Electrode color is a visual reconstruction; no conductive alloy, corrosion resistance or environmental rating is claimed. The lower internal circuit PCB includes boss clearances and real fastening/Grove solder holes. Concealed circuit package placements and the connection tabs are appearance reconstructions from the schematic and available photos.

The square front aperture has a fixed blue R3 10K trimmer body, a genuine rotor bore, and a metallic head with a recessed cross slot. `trim` turns only the real head/shaft. The blue housing, shell, fork and circuit stay fixed. This is a positional visual joint: the documentation does not establish mechanical end stops, electrical zero, direction or conversion to threshold. The `visualRangeDeg: [-135, 135]` metadata is a suggested viewing range. Nonzero RPM is rejected. There is no press action. Both the official schematic and same-model images provide no external LED, so none is registered.

```js
import { Model, GroveModule } from './src/units/earth/index.js';

const earth = new Model();
earth.handle({ type: 'joint', target: 'trim', angleDeg: 45 });
earth.handle({ type: 'joint', target: 'trim', angleDeg: -30, durationMs: 180 });
// The viewer or external animation loop calls earth.update(dtSeconds).

const unit = new GroveModule({ cableLength: 55 });
host.port('grove').attach(unit);
host.handle({ type: 'joint', target: 'grove/trim', angleDeg: 20 });
host.handle({
  type: 'pose', target: 'grove/unitFrame',
  position: [20, 82, -9], rotation: [0.2, -0.15, 0.1]
});
host.port('grove').detach({ dispose: false });
unit.dispose();
```

`grove` is a physical port with pins GND, 5V, D.OUT, A.OUT in black/red/yellow/white wire order. `sensor` is a passive physical probe anchor and accepts no moisture, ADC, threshold or digital-output commands. External joint commands emit no synthetic user input and never calculate readings. A four-wire mechanical connection does not prove port electrical or protocol compatibility.

The standard English rear sticker and optional Chinese education variant use the supplied artwork's original vector glyph contours, rendered to 2400 × 1800 PNGs. The conversion library dropped fill styles and layer visibility, which were restored using the matching official standard photo and supplied Chinese preview. `new Model({ stickerVariant: 'education-cn' })` selects the Chinese label. The default is standard English. The vector originals, table, mappings and conversion intermediates are not distributed. Source glyphs were not recreated from a product-photo crop. The native blue head and fork have no additional label in the references.

`new Model({ artwork: false })` disables all print. Pass that option separately to each model/module as needed. All physical vertex/normal/index buffers and world matrices are identical across the standard, Chinese and disabled artwork options at the same pose.

The local smoke report checks finite geometry, the complete original shell, clear mounting holes and FrontSide bore walls, all 38 electrode through holes, the actual access-opening backing, isolated head motion and exact reset, absence of false controls/LEDs, passive API boundaries, nested Grove pose/attachment/detachment/resource release and physical artwork invariance. Browser/pixel acceptance, full historical validation, manufacturing fit and real hardware/electrical execution have not been performed.
