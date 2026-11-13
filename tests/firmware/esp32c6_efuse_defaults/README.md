# C6 unprovisioned eFuse defaults

Patch 0019 exposed the actual C6 eFuse controller above an overlapping LP
fallback. An attached NanoC6 identity backing was correct, but an unbacked
Nesso N1 inherited C3-only revision and block-version defaults. In the C6
layout, the C3 block-version bits select package 3. That is a separate path
from the previously validated NanoC6 backing.

The same original Bruce BIN on the TSF-only runtime produced nonblack frames
within two seconds. Adding the eFuse mapping correction produced six black
frames over 30 seconds, with the same service source and no input. Both runs
precede USB patch 0020, preserve application bytes, and export the session ZIP
before stopping and releasing Flash, lease and process. The precise hashes and
passive register/PC observations are in [evidence-summary.json](evidence-summary.json).
The original instructions reached a bitmap drawing loop and later the idle
WFI return; no panic or repeated reboot was observed.

Patch 0021 gives C6 its own realization hook and a distinct parent callback
slot. It calls the existing C3/base chain once, then clears only the two
C3-injected words when there is no supplied backing and updates the mirror.
C3 behavior and all explicitly supplied backing bytes stay unchanged. The
empty C6 mirror is unprovisioned; it does not claim factory calibration or a
measured silicon revision. Field interpretation follows the fixed
[C6 eFuse table](https://github.com/espressif/esp-idf/blob/38628f98b9/components/efuse/esp32c6/esp_efuse_table.c).

Run the extracted actual realization/class-chain tests:

```sh
PYTHONPATH=platform/tests python3 -m unittest test_c6_efuse_defaults_patch
```

Six cases run before and after the patch under ASan/UBSan. Two old C6 default
and mirror-reload expectations fail; four C3/backing/preservation controls
remain valid. All six pass with the correction. The fixture contains exact
canonical preimages for the affected C6 files and the unchanged C3 parent.

**Candidate guest validation is NOT RUN yet.** The next combined native build
must replay the ordered bootstrap patches, record fresh build provenance,
and repeat the same original Bruce BIN through Device Service, including
visible UI, input, requested reset and filesystem remount. A host test or the
older TSF-only runtime does not grant the corrected runtime a PASS. Physical
hardware and browser-WASM are NOT RUN.
