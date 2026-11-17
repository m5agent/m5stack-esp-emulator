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
Read only the stopped session's owned SD media. Parse the FAT partition
independently, verify that both files match their exact payloads, and verify
that the original uploaded image still matches its artifact digest. Upload
the stopped session's SD image as a new artifact and repeat the Cardputer case
with the same firmware. Require `STORAGE_PROBE_MOUNT seed=1 prior=1` as the
pre-write marker. Omitting SD media must produce `STORAGE_PROBE_MOUNT_ERROR
ESP_ERR_TIMEOUT` on the tested Cardputer. Require guest exit for each case.

[Observed virtual-device results](../../../docs/evidence/2026-11-17-spi-sd-admission/summary.json).
Physical hardware, browser WASM, PaperDIY G48 detect and community applications
were outside this test.
