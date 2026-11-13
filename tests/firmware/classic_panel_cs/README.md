# Classic SPI panel selection and receive FIFO

Issue [222](https://github.com/m5agent/m5stack-esp-emulator/issues/222) is
**PARTIAL**. The original HamRadio 0.1.5 image was entirely black for 240 seconds
on native runtime `fb90044af572c80c488a7767dcd04195cd531ca8047c753c521398e21dd815f5`.
The original app kept drawing through Basic's CS14/DC27 wiring. A diagnostic
trace showed Core2's actual CS5 high during the wrong-board RDDID probe, yet
the SPI W0 read returned the panel ID unconditionally.

Native layer 0190 wires each classic board's actual panel CS, gates both FIFO
and DMA delivery, and clocks selected panel responses into the real RX FIFO.
Subsequent FIFO reads retain the completed transfer, including after CS rises.
The existing bounded FIFO repetition and full-duplex TX snapshot are retained.
No guest BIN, board identifier, watchdog or scheduling parameter is changed.

On clean 0190 runtime
`b32a4afa8535a514623a4a9199a5aba41782e52b2572b6840791d1255dd508a7`,
the same HamRadio image now rejects the Basic probe, selects Core2 and displays
the application's missing SD configuration message. The independent original
AWS firmware still reaches its homepage. Original UIFlow 1.15.5 remains black
at 120 seconds, so the whole issue remains open. These are **virtual-device
validation** results, not physical or browser-WASM validation. Network/radio
operation and storage-dependent HamRadio functionality are separate checks.

## Reproduce

Build the maintained native recipe through 0190, supply the matching ROMs to an
owned Device Service, and obtain the original image matching a SHA in
[evidence-summary.json](evidence-summary.json). Then run:

```sh
python3 tests/firmware/classic_panel_cs/run_original.py \
  --service "$DEVICE_SERVICE" --token-file "$TOKEN_FILE" \
  --firmware "$ORIGINAL_BIN" --sha256 "$ORIGINAL_SHA256" \
  --out-dir "$EVIDENCE_DIR" --seconds 120
```

Readiness is assessed from the saved application frames and serial output,
not the session's `running` state. The script saves evidence before stopping
with `purge=0`. Earlier observer failures and diagnostic-only traces are kept
outside the source tree and do not grant an application verdict.

The standalone host C regression replays the full native prefix from a pinned
upstream SPI fixture. Eight independent cases cover deselection, split and
turnaround reads, retained FIFO, ignored writes, other commands, high FIFO and
full-duplex preservation. The old model fails seven expected negative cases;
the new model passes all eight under address/undefined-behavior sanitizers.

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_classic_panel_cs_fifo_patch test_core2_spi_dma_patch \
  test_core2_dual_spi_panel_patch test_spi_panel_read_cursor_patch
```

## Core2 SD follow-up

[The SD follow-up](sd-evidence-2026-11-13.json) binds the official UIFlow2
`SDCard` sector read/write to real classic SPI DMA and an independent disk
oracle. It also retains an unchanged HamRadio BIN run with a provided FAT32 SD
image: the actual B/C/B keys open the Ini Loader, select `IC705USB.ini`, load
it and reach the instrument page with `CHECK WIFI`. The application needs
explicit network/transceiver configuration for its remote features; these were
not supplied or claimed by this run.

Prepare a FAT32 SD image using `platform/tools/sd_image.py`, place configuration
files from the pinned [M5HamRadio documentation](https://github.com/armel/M5HamRadio/tree/f10b8924bcfd990f970947dbff9144ce88566799)
in its root, and upload it as a Device Service artifact. Set
`storage.sd_image_artifact_id` when creating the Core2 session. During the blue
Ini Loader gauge, press B to open the menu, C to move down and B to select.
The firmware copies the chosen file into Flash; a file named `.backup.ini` on
SD does not replace this original selection flow. Keep all image bytes, input
receipts, serial and frame evidence with that same session and request its ZIP
before stopping with `purge=0`. Retain raw configuration only in private storage.

The final combined native runtime `33c0ec98…` independently repeats the unchanged
HamRadio/SD selection for 180 seconds: one boot, no panic/watchdog, the actual
ICSMeter gauge page and `CHECK WIFI`. Its Device Service metadata reports `spi`,
with the original storage artifact and isolated writable copy bound to the
same lease. Exact service-timeline inputs and frame/ZIP hashes are in the
`final_combined_runtime` section of the SD evidence; history is retained.
