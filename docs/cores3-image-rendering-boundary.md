# CoreS3 UIFlow2 image rendering boundary

Status: `OPEN`

Date: `2026-10-22`

Last reviewed: `2026-10-26`; the boundary remains `OPEN`. This page is a
core-image rendering investigation and does not inherit the later S3/C6/
Core2 network or BLE results.

## Symptom

CoreS3 UIFlow2 startup menus can show horizontal/diagonal stripe artifacts in
the top title bar and several icon tiles. The rest of the UI (text, QR code,
layout and touch regions) remains usable.

## Evidence

The attached user screenshot, the uploaded 2.5.1 firmware frame and the
CoreS3 reference-firmware frame are the same 320x240 image. The artifact is
also stable across repeated captures, so it is not a single mid-refresh frame.

The panel model's raw PPM dump is byte-for-byte identical to the QMP
`screendump` frame. This rules out:

- QMP/PPM row-padding or screenshot conversion;
- a transient framebuffer refresh race;
- a firmware-specific defect in the uploaded image.

## Narrowed cause

The UIFlow startup code draws title and icon assets through
`M5.Lcd.drawImage(...)`; the bundled resource files include palette PNGs with
`tRNS` transparency. A minimal CoreS3 test was used to isolate the path:

- an ordinary RGB PNG (`color type 2`) renders correctly;
- an RGBA PNG (`color type 6`, even with all alpha bytes set to 255) produces
  the same striped corruption;
- text, rectangles and the non-image pelican animation render correctly.

The fault therefore occurs in the image decode/conversion path before the
ILI9342 memory sink writes pixels into the panel framebuffer. The panel model
is faithfully storing the bytes it receives; it is not adding the stripes.

The alpha/readback implementation was checked, but adding a provisional
panel-read path did not change the RGBA reproduction, so that experimental
change was reverted and is not claimed as a fix.

## Next investigation

Compare M5GFX PNG/alpha conversion and `pixelcopy_t` source stride handling
between real hardware and QEMU. The first trace points to inspect are:

- `png_draw_alpha_callback()` and `pushImage()` in M5GFX;
- the source depth/stride passed by the UIFlow LVGL image path;
- PSRAM/cache behavior when decoded image rows are copied into the SPI
  transfer buffer.

Do not work around this by substituting a host-generated screen image; that
would break the requirement that previews come from the firmware data plane.

## Boundary

This is a simulation-only visual defect. It does not prove a defect in the
uploaded firmware and does not replace real-hardware validation.
