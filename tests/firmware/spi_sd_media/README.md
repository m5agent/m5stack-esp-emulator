# Cardputer and PaperS3 SPI SD media probe

The guest uses the ESP-IDF SDSPI and FAT VFS drivers on GPIO12/40/14/39
(CS/SCK/MOSI/MISO) for Cardputer and Cardputer-ADV, and GPIO47/39/38/40 for
PaperS3. It lists `/sd/FIXTURE`, reads seeded `ROM.BIN`, writes
`/sd/PROOF.BIN`, unmounts, mounts again and verifies the complete write.
The guest checks for an existing proof before opening the file for writing.
The test payloads are synthetic strings.

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
For Cardputer and ADV run `idf.py build` in this directory. For PaperS3 copy
the defaults, set `CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y` in place of the 8 MiB
line, and configure `-DPROBE_PAPER=ON` with the corresponding build, defaults
and sdkconfig paths. Use the resulting `flash_args` flash layout to merge the
bootloader, partition table and app with the matching esptool. Pad the merged
image to the selected board's flash size.

Use an owned native Device Service on its own port, state directory and token.
Create a 64 MiB FAT32+MBR image with `python3 platform/tools/sd_image.py
--format fat32-mbr --out <fixture.img>`. Use `pyfatfs==1.1.0` at the generated partition
offset, in bytes, to write `FIXTURE/ROM.BIN` containing
`M5EMU_SEEDED_FAT32_PAYLOAD` with no newline. Python environments without
`pkg_resources` need a compatible setuptools version for this test dependency.

Upload the merged probe and populated SD image via `POST /api/v1/artifacts`.
Register the probe with `POST /api/v1/firmware` as a merged image for the device.
Start a session with `storage.sd_image_artifact_id` set to the SD artifact ID.
Wait for `STORAGE_PROBE_DONE` in serial and require these markers:

```text
STORAGE_PROBE_MOUNT seed=1 prior=0
STORAGE_PROBE_REMOUNT write=1 restored=1
```

Request the evidence ZIP before stopping the same session with `purge=0`.
Setting `M5SW_SPI_SD_TRACE=1` on the owned service process records SPI command
counts in QEMU stderr.
Inventory the stopped session with `GET /sessions/{id}/storage/sd`.
Verify both file hashes and independently parse the retained FAT partition.
Confirm that the original uploaded artifact still matches its digest.
Export with `POST /sessions/{id}/storage/sd/export` and repeat the Cardputer
case with its returned artifact ID and the same firmware. Require
`STORAGE_PROBE_MOUNT seed=1 prior=1` as the pre-write marker. Omitting SD media must produce `STORAGE_PROBE_MOUNT_ERROR
ESP_ERR_TIMEOUT` on the tested Cardputer. Require guest exit for each case.

[Observed virtual-device results](../../../docs/evidence/2026-11-17-spi-sd-admission/summary.json).
Physical hardware, browser WASM, PaperDIY G48 detect and community applications
were outside that first run.

## PaperDIY CARD_DET

PaperDIY uses the PaperS3 SPI pins and a GPIO48 card-detect input. The
`PROBE_PAPERDIY=ON` build samples the detect input with the normal ESP-IDF
driver and mounts the card only when it reads low. Use the same 16 MiB build
procedure as for PaperS3, substituting this CMake option for `PROBE_PAPER`.
[PaperDIY pin map](https://docs.m5stack.com/en/core/PaperDIY_Complete_Kit#microsd)

Run the same exact merged image first with an empty socket and then with
the FAT32 fixture. Require `PAPERDIY_CARD_DET gpio=48 level=1` and
`STORAGE_PROBE_NO_CARD` without media. With media, require level 0,
the same mount readback and remount markers as above, and real CMD17 and
CMD24 transactions. A control build that omits native patch 0208 reports
level 1 even with the same image attached and never reaches the mount.
The [native model A/B](paperdiy-sd-detect-summary.json) identifies the
admission override used to reproduce that old native behavior. For [normal
API validation](paperdiy-sd-detect-api-summary.json), check
`GET /api/v1/devices/paperdiy` before creating sessions. A binary with the
model advertises `features.storage: true`. Its running session returns
`true` for the `sd-card-detect-model` property of `/machine`. Repeat both
requests against a binary built without patch 0208. Expect
`features.storage: false` and `409 storage_not_supported` for the valid
SD attachment request. Still boot the same merged firmware with an empty
slot. The mounting scope is media supplied at session creation. Physical
hardware and hot-plug were outside these tests.

## SPI attachment and larger FAT32 fixtures

The 96 MiB SPI mount proof uses two 512-byte sectors per cluster.
Generate that geometry with
`python3 platform/tools/sd_image.py --format fat32-mbr --size-mib 96 --sectors-per-cluster 2 --out "$TEST_MEDIA"`.
Populate the card and run the same GPIO48 and SPI probe described above.
Require the mounted guest to read and write the fixture, reset the same
session, then confirm the persisted file hash from the stopped session's
SD inventory and the original artifact hash.

The earlier service also attached SPI media to the QEMU SDMMC backend,
which rejected the exact 96 MiB image before the original NC1020 guest ran.
The fixed service attaches that media to the board-wired SPI endpoint.
The original guest mounts the card and begins reading the synthetic ROM.
That observation covers SD ROM import progress. The
[observations](spi-capacity-summary.json) bind exact seed, firmware and runtime
hashes and include the PaperDIY reset and no-ROM/no-media controls.

## NC1020 original save and reload

Use the exact merged original and a writable FAT32 card without replacement
ROM/NOR. Wait for `romdata pre-filled`, `NOR in flash ready`, and a guest
heartbeat. Hold the modeled G0 button, wait for
`state save /sd/nc1020.state: ok`, collect the evidence ZIP, and stop with
`purge=0`. Verify the file with the stopped-session SD inventory, export
the writable card, and attach the exported artifact to a new session using
the same firmware. The second session prints `fixed state values` and resumes
its heartbeat. The source card stays unchanged.

The [run receipt](nc1020-save-summary.json) records the incomplete initial
frame, black frame after reload, and the separate saved-snapshot review.
It also records the partial import of separately authored SD payloads.
The 64 MiB FAT16 comparison card uses
`--format fat16-superfloppy --size-mib 64 --sectors-per-cluster 32`.
The exact original mounts that card and reaches bank 96 before a CPU1
interrupt watchdog reset.

## PaperDIY SD hot-plug

Use the same PaperDIY 16 MiB defaults with `-DPROBE_PAPERDIY_HOTPLUG=ON` and
merge the resulting `flash_args`. Generate the 64 MiB seeded FAT32+MBR image
from the first section. Start a dedicated native Device Service with patch
0215 and `M5SW_SPI_SD_TRACE=1`. Run:

```sh
python3 tests/firmware/spi_sd_media/run_hotplug.py \
  --base-url "$DEVICE_API" --token-file "$CONTROL_TOKEN_FILE" \
  --firmware "$MERGED_PROBE" --media "$FAT32_FIXTURE" --output "$EVIDENCE_DIR"
```

The guest initially attempts a real SPI mount with empty media, observes
four GPIO48 IRQs during insertion and removal, writes once and reopens the
file after reinsertion. The runner ties each state transition to the same
QEMU process. It checks SPI command deltas, the retained evidence ZIP and
the stopped FAT inventory and export receipt. The source image is immutable.
The [virtual-device result](paperdiy-hotplug-summary.json) retains old-backend,
missing-media and normal attached-at-boot controls. Runtime image replacement,
physical/electrical and browser behavior are outside this scope.
