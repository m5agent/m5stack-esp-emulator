# UIFlow2 Tab5 emulator patch

These patches add the ESP32-P4 Tab5 virtual-host build used by the emulator
matrix. They are split by repository boundary:

1. `0001-uiflow2-tab5-emulator.patch` applies to the `uiflow_micropython`
   checkout.
2. `0002-m5gfx-tab5-emulator.patch` applies inside
   `m5stack/components/M5Unified/M5GFX`.
3. `0003-lvgl-build-guards.patch` applies inside
   `m5stack/cmodules/lv_binding_micropython`.

Recommended order:

```bash
export UIFLOW_MICROPYTHON_DIR=/path/to/uiflow-micropython
cd "$UIFLOW_MICROPYTHON_DIR"
git apply /path/to/0001-uiflow2-tab5-emulator.patch
git -C m5stack/components/M5Unified/M5GFX apply /path/to/0002-m5gfx-tab5-emulator.patch
git -C m5stack/cmodules/lv_binding_micropython apply /path/to/0003-lvgl-build-guards.patch
```

The emulator target deliberately disables the LVGL Python binding:

- the production Tab5 configuration still enables LVGL;
- the emulator test build uses the native M5GFX/UIFlow2 display path;
- the production partition layout remains unchanged;
- the emulator-only partition layout keeps all populated partitions below
  8 MiB to work around the current `esp-emu` P4 download-mode address limit.

Build artifacts are created with:

```bash
python3 tests/uiflow2/build_tab5_emulator.py \
  --uiflow-repo "$UIFLOW_MICROPYTHON_DIR" \
  --clean
```

This patch set is simulation infrastructure. It does not constitute a
real-hardware Tab5 PASS.
