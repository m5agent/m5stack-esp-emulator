# StickS3 three.js renderer

Date: `2026-10-22`

Status: `INTEGRATED — simulation-only visual shell`

Last reviewed: `2026-10-24`.

The StickS3 device page now has a dedicated three.js shell from the pinned
`MarsTechHAN/sticks3.js` source under `platform/web/vendor/sticks3/`. It replaces
the approximate CSS body only for StickS3; every other device continues to use
`M5DeviceShell`.

The Live sessions page reuses the same shell as a per-session preview. It draws
the session's live or persisted `frame.png` into the modelled LCD and keeps the
3D scene mounted across polling updates. StickS3 also exposes a normalized
runtime-state probe for M5PM1 power values and BMI270 IMU values.

## Boundary

- The model uses the measured 48 × 24 × 15 mm body and the 14.86 × 26.42 mm
  active LCD area.
- The current LCD geometry is 135 × 240, matching the device manifest.
- `StickS3ThreeShell.setFrame()` accepts the existing framebuffer byte stream
  and writes it through the upstream `Display.writeRGB565()` path.
- Physical `BtnA`, `BtnB` and `BtnPWR` hit targets map to the project control
  IDs `a`, `b` and `power`. Known GPIO IDs are forwarded when the model exposes
  them.
- The QEMU execution boundary is unchanged. A rendered 3D shell does not start
  QEMU, prove a firmware frame, or constitute real-hardware validation.

## Dependencies and licensing

- `three` `0.186.1` is vendored with its MIT license.
- The adapter shares `three-device-viewer.js` with the CoreS3 model so display,
  touch, button, screenshot and fallback behavior remain on one code path.
- The `sticks3.js` source is pinned to commit
  `974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb`.
- The upstream project declares MIT in `README.md` and `package.json`, but that
  commit has no standalone `LICENSE` file. See
  `platform/web/vendor/sticks3/UPSTREAM.md`.

## Verification

- Browser UI regression: `cd platform/tests && M5_SIM_BASE=<url> npm test`
- The test checks the three.js renderer is mounted, a red RGB565 pixel reaches
  the LCD buffer, the frame sequence is retained, and `BtnA` emits the expected
  logical input with GPIO 11.
- Desktop, tablet and mobile screenshots are visual QA evidence only.
