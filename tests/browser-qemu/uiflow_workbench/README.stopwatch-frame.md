# StopWatch display observer

The workbench editor runner has a StopWatch-specific display observation. It
uses the original public `M5.Display` API: `setRotation(0)`, `setBrightness(255)`,
`width()`, `height()`, `getBrightness()` and `fillScreen(0xFF0000)`. The SDK's
logical dimensions are **468x468**. The QEMU physical console frame is
**466x466**; these are separate contracts, already documented in this profile.
No C runtime, profile, Flash packaging or display-transport change is required.

The original M5GFX source pinned by UIFlow commit
`50e440780492aa847378c7d3477ab912f7063bac` uses M5GFX commit
`9bcedf4e19d4cab7a0793de0598ae5390b4689fe`.
`M5GFX.cpp:2030-2033` configures a 468x468 logical panel at offset (6,0).
`LGFXBase.hpp:1460-1461` exposes the brightness setter/getter and defaults to
127 at line 1519. `Panel_AMOLED.cpp:171-180` sends the selected brightness as
CO5300 command 0x51. The public MicroPython bindings are in
`m5stack/cmodules/m5unified/m5unified_gfx.c` and
`m5stack/components/M5Unified/mpy_m5gfx.cpp:349-367`.

The compiled runtime75 source `hw/m5stopwatch/co5300.c`, SHA256
`c97309ceb1a2f96f6667c1161f82bdaa6003d8417c2c103cb38396ff780155cd`,
keeps pixels where `(x-233)^2 + (y-233)^2 <= 233^2` and forces all other
console pixels black. Coordinates range from 0 to 465, giving exactly
**170499 inside pixels** and **46657 outside pixels**. It scales each visible
8-bit channel by `brightness / 255` before the real RGB565 frame transport.
At the default brightness 127, a full-red memory image therefore produces
`0x7800`; at explicit brightness 255 it produces `0xf800`.

`public_qemu_stopwatch_frame_oracle.mjs` checks every observed physical pixel:
each of the 170499 circle pixels must be `0xf800` and each of the 46657 outside
pixels must be `0x0000`. It uses fixed reviewed geometry, not geometry inferred
from the output. It neither changes pixels nor accepts a lower whole-frame
red percentage. Other boards retain their existing observations.

The first runtime75 V2 run failed after its 41 completed editor/source checks
passed: its display source omitted a brightness selection, and the generic
oracle required more than 95% of the rectangular frame to be bright red. The
retained frame matched the half-brightness circle exactly, with no mismatching
inside or outside pixels. Even full brightness can only cover 78.5145% of the
rectangle. The first raw report SHA is
`ffd4ede8cf0d8dc2b631f88da18d6a4cf3ea64a3ee7d525894616f61179dc187`.
Its original normal-QMP-exit receipt was **NOT CAPTURED**; six actual CDP Workers
were observed closed before context closure. A later run cannot replace that
failure or supply its missing receipt. Future failures now retain actual
post-stop cleanup metadata separately, without duplicating raw pixel arrays.

Host controls (no guest execution):

```sh
node platform/tests/test_public_qemu_stopwatch_frame_oracle.mjs
node --check platform/tests/test_public_uiflow_guest.mjs
```

The host test constructs a circle independently by scanlines, and rejects a
fully red rectangle, half-brightness circle, one wrong inside pixel, one
leaking corner pixel, exact-boundary mistakes, wrong dimensions, short buffers,
missing frames and wrong colors. These checks establish the observer contract;
the modified source still requires its own full StopWatch guest run with exact
default Flash/runtime identities, editor behavior and normal Worker cleanup.
Use the existing opt-in editor command with `M5_QEMU_DEVICE=stopwatch` and a
new ignored output directory. Run the separate button case as well; display
observation does not establish button behavior or physical display properties.
