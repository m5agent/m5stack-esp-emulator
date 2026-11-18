# Tab5 ST7123 SDMMC input write fixture

The ESP32-P4 guest mounts FAT16 through the Tab5 SDMMC slot 0 wiring and displays
a target on the native 720 × 1280 DSI panel. Touch the center at panel coordinates
`(360, 640)` and release. The fixture reads the point and release through the
ST7123 interrupt and I²C1, then writes and reads back two files through ESP-IDF
FATFS. The frame changes after successful readback. The UART prints
`TAB5_TAP_SD_READY` while waiting and `TAB5_TAP_SD_PASS` after both files pass.

| Path | Bytes | SHA-256 |
| --- | ---: | --- |
| `/TAP.TXT` | 23 | `e59c5f2a8d8443bca8ecc4485c4c23646b238ae3ba678898aee92ce433266782` |
| `/POINT.TXT` | 12 | `f9e9bceda3918948b1cba9d072dea5aa7f328985fea2d73fa30e7d2c681980bb` |

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
The [Tab5 board support package](https://github.com/m5stack/M5Tab5-UserDemo/blob/fe8aa051beb9385468f7e46b909e764169df3f7a/platforms/tab5/components/m5stack_tab5/m5stack_tab5.c)
supplies the panel timing and slot wiring.

```sh
source "${IDF_PATH}/export.sh"
probe_dir="${PWD}/.work/tab5-sdmmc-action-proof"
mkdir -p "${probe_dir}"
cp -R tests/firmware/tab5_sdmmc_action "${probe_dir}/source"
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" set-target esp32p4
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" build
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" merge-bin --fill-flash-size 16MB
python3 platform/tools/sd_image.py --out "${probe_dir}/blank.img" \
  --format fat16-superfloppy --size-mib 32
```

1. Start an isolated Device Service with the pinned esp-emu 1.1.0 runtime,
   Tab5 ROM, eFuse, C6 companion and native ST7123 Touch ESP Part listed in the
   [validation receipt](summary.json). Upload and import the built merged image
   for Tab5. Admit the resulting normalized SHA on the ST7123 board. Confirm
   the device reports `fixtures.sd.interface=sdmmc` and
   `fixtures.sd.write_stamp=true`.
2. Upload the blank image to the Device Service role used by the isolated
   Reviewer. Run a local saved-snapshot Retry of the fixture with Burner
   submission disabled. In `validation`, set
   `storage.sd_image_artifact_id` to the blank image SHA and set
   `input_assertions.touch_center` to
   `{"type":"sd_write","timeout_seconds":4,"retained_file":"/TAP.TXT"}`.
3. Bind the accepted touch, quiet and post-input stamp, DSI frame change, UART
   point, UART release and `TAB5_TAP_SD_PASS` to the same session. Check the
   Device Service ZIP and inspect the stopped session's FAT inventory for
   both expected file hashes.
4. For a reset control, start a new admitted session with seeded media and
   zero inputs. Use a quiet baseline stamp. Reset through the Device Service
   API. A new P4 process rotates the stamp's media identity. For this control,
   the SD image inode, hash and modification time stay stable. Capture the
   evidence before stop, stop with `purge=0` and check that a stopped session
   rejects a live write stamp.

A timestamp observes any flushed write in the input window, including
background activity. The guest's touch and file markers establish the
relationship to the tap for this fixture. A retained FAT entry establishes
file presence at stop. An assertion that a file was created needs the input
image's file inventory. SD controller read counters, physical hardware,
hot-plug and Burner were outside this run.

[Device Service storage API](../../../docs/device-service-api.md)
