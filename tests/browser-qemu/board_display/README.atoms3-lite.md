# AtomS3 Lite C124: no-display browser candidate

`atoms3_lite_main.py` uses the original AtomS3 Lite UIFlow2 firmware's
`hardware.RGB()` and `M5.BtnA` APIs. It never initializes, draws or substitutes a
display. The RGB word starts at `0x204060`, changes to `0x40A020` after a real
guest-observed button press, and returns to `0x204060` after release.

Composition uses the minimal `core2_boot.py` run-main flag, this main source and
the profile's `browser_probe_config.py`. The official v2.5.3 base is firmware
`2099000000000000004`, SHA256
`338baf7f16703b26fff78619d32e593d8ca4f1934bdad63e3c95eef862f3133c`.
The VFS is taken from its actual partition table, `0x641000 / 0x1be000`.
Composition is packaging evidence; it is not guest execution.

The browser engine accepts one fixed read-only output contract:
`/machine/onboard_io` `led-rgb`, `led-frames`, `pressed`. It brackets RGB reads
with the real RMT frame counter and drops a snapshot spanning an LED update.
Only a validated snapshot from the session's engine Worker may drive the
existing model's `rgb` LED and `button` output state. Neither serial text nor
input acknowledgements set an observed LED/pressed value. No RMT frame means
the LED remains visually unknown. A successful read proves a digital output
word, not physical brightness or optics.

Runtime acceptance must retain the exact WASM/firmware hashes, board identity,
serial ready/count/release, QMP A down/up, QOM RGB/frame-count/pressed changes,
3D LED readback and clean engine/pthread/iframe disposal in one browser run.
The candidate remains excluded from ordinary public exports until that run.
