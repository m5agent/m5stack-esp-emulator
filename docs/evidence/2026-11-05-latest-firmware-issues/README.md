# Latest UIFlow2 regression repairs

Date: 2026-11-05. This campaign separates image/observer defects from actual
controller behavior. Native results are **virtual-device validation**; physical
hardware and browser-WASM validation are NOT RUN.

The source changes retain the original failing controls. They derive VFS layout
from the exact firmware, preserve stock files and all bytes outside VFS, observe
real UART/controller output, and bind expected differences to exact firmware
hashes. Synthetic ADC calibration remains an explicit, application-byte-bound
virtual fixture; unknown application images do not inherit admission.

## Native controller changes

- AXP2101 PMU status2 now reports both charger-state and current-direction fields.
- ED2208 accepts inclusive partial windows (0x83) and the AUTO refresh sequence
  (0x17 with A5/A7); the legacy full-frame refresh protocol is preserved.
- AtomS3 has an explicit `m5atoms3-st7735` LCD variant using the official M5GFX
  ST7735S RAM geometry, mounting and inversion. The original `m5atoms3` GC9107
  machine remains available. This is a declared native profile selection,
  not an automatic firmware-dependent crop or a framebuffer substitution.

## Integration gate

Final integrated platform/native/CI results are not yet recorded in this commit.
See [summary.json](summary.json); result details are appended after execution.
Tab5's corrected latest official image has reached its application address, but
Python/UI/touch readiness remains PARTIAL and must not inherit an old-image PASS.
