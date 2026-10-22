# High-fidelity device visual modeling backlog

Date: `2026-10-22`

Status: `DEFERRED — specialist visual-modeling work`

Owner: future stronger visual/3D modeling agent

This is a tracked high-difficulty backlog item. The current simulator is
functionally useful, but the visual device shells are not yet a faithful
representation of most M5Stack products.

## Current state

- StopWatch has a dedicated SVG shell, a 466×466 circular screen opening,
  physical side-key geometry, screen glare and a real firmware framebuffer
  mapping. It is the reference-quality implementation.
- Other devices use the generic `M5DeviceShell` renderer with pixel-based
  layouts, simplified CSS decorations and official cutout images.
- The generic shells are useful for layout and interaction, but their body
  proportions, bezel thickness, screen opening, material, color, ports,
  buttons, speaker/mic holes, keyboard, stand and mechanical details are not
  high-fidelity product models.
- Current dimensions in `device-shell.js` are display pixels, not physical
  millimeters. They are not a substitute for a measured device manifest.

## Goal

Build an independently maintainable visual model for every supported device so
that a user can recognize the actual product, understand its screen and
controls, and interact with the emulator through the same physical layout.

The visual model must be driven by the real emulator framebuffer. It must not
fake firmware status, invent a screen image or replace the runtime data plane.

## Required per-device asset pack

Recommended future structure:

```text
platform/web/assets/device-models/<device-id>/
├── visual-model.json
├── references/
│   ├── front.webp
│   ├── back.webp
│   ├── left.webp
│   ├── right.webp
│   └── top-bottom.webp
├── shell.svg
├── layers/
│   ├── back.svg
│   ├── body.svg
│   ├── bezel.svg
│   ├── controls.svg
│   └── ports.svg
└── textures/
```

`visual-model.json` should contain:

- physical body width, height and depth in millimeters;
- body shape, corner radii and shell thickness;
- official body color/material swatches;
- display diagonal, physical active area, visible opening and active-area offset;
- display shape, corner radius and bezel thickness;
- screen coordinate transform and safe drawing area;
- exact button, key, wheel, switch and keyboard positions;
- control hitboxes and their mapping to logical input IDs;
- USB, Grove, SD, HDMI, speaker, microphone, camera, LED and ventilation positions;
- front/back/side reference image hashes;
- device-specific branding and label placement;
- responsive scale rules and minimum interaction size.

## Rendering approach

Use a hybrid layered renderer:

1. SVG or Canvas for the front shell and precise cutouts.
2. A mapped framebuffer layer clipped to the real visible screen area.
3. CSS transforms or SVG masks for bezel/glass reflections and perspective.
4. DOM/SVG hitboxes for controls, with physical-to-logical coordinate mapping.
5. Optional glTF/WebGL only where side thickness or 3D rotation materially
   improves recognition.

Do not replace precise 2D geometry with a single stretched official photo. The
photo is a calibration reference, not the interactive model.

## Acceptance levels

| Level | Requirement |
| --- | --- |
| V0 | Official reference photos and measured body/display dimensions recorded |
| V1 | Silhouette, body proportions, screen opening, bezel and control positions match the measured manifest |
| V2 | Material, color, labels, ports, holes, buttons and mechanical details are represented in layers |
| V3 | Framebuffer mapping, touch/keyboard hitboxes and input feedback work at all supported scales |
| V4 | Visual regression screenshots compare favorably with official references at desktop/tablet/mobile sizes and receive human review |

A device is not “high-fidelity modeled” until V3 is functional and V4 evidence
is archived.

## Device priorities

### Hardest and highest visual value

- Tab5: large tablet body, thin bezel, camera/sensor area, ports and stand.
- CoreS3: square body, camera, bezel, side controls and rear details.
- Cardputer-ADV: keyboard, trackball, speaker, hinge-like body and thickness.
- CardputerZero: keyboard, proportion differences and body finish.
- StackChan: servos, arms, head, camera, mechanical motion and stand.
- StamPLC: industrial terminals, DIN rail, LEDs, labels and rugged shell.
- PaperColor/PaperMono: paper display texture, visible area and refresh states.

### Medium complexity

- Core2
- Arduino Nesso N1
- StickS3
- AtomS3R
- NanoC6

### Reference implementation

- StopWatch: keep the existing shell as the baseline quality target and migrate
  it to the new manifest/layer format without visual regression.

## Visual QA requirements

- Capture front, back and side views at a fixed logical size.
- Compare against official product photos with the same orientation and crop.
- Record body aspect ratio, screen-opening ratio, bezel width and control
  centers as numeric checks, not only eyeballing.
- Verify screen pixels are not stretched, rotated or cropped.
- Verify touch coordinates at the four screen corners and center.
- Test keyboard/buttons with pointer and keyboard input.
- Test at desktop, tablet and mobile viewport sizes.
- Keep screenshots and comparison metrics with the work record.

## Non-goals

- Do not fake device telemetry or runtime status in the visual layer.
- Do not replace the emulator with a static product image.
- Do not use one generic rounded rectangle for all products.
- Do not claim physical/mechanical fidelity without real-device or official
  dimensional evidence.

## Estimated effort

With official references and a repeatable layered renderer:

- simple flat device: 2–4 working days;
- complex device with keyboard, ports or moving parts: 5–10 working days;
- StopWatch migration and common renderer/QA: 3–5 working days;
- all remaining devices plus visual regression: roughly 8–12 working weeks
  serially, or 4–6 weeks with parallel visual workstreams.

This estimate assumes a specialist can obtain the official mechanical
references. It does not include real-device industrial-design verification.

## Handoff checklist

1. Read `platform/web/device-shell.js` and the StopWatch reference page.
2. Create `visual-model.json` for one device before changing the renderer.
3. Build one hard device and one medium device as proof.
4. Add numeric visual regression checks and official-reference comparison.
5. Migrate StopWatch without regression.
6. Roll out per device and update the device manifest only after V4 evidence.
