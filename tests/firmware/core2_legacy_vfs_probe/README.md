# Core2 legacy VFS probe

This fixture starts from the public UIFlow `v1.15.4` VFS and adds markers to
the original `/flash/boot.py` and `/flash/main.py`; it does not replace their
SD-card or `m5stack` initialization logic. It is used to distinguish a
missing or reformatted VFS from a later application-startup failure.

`boot.py` must be packed with the LittleFS2 implementation from the matching
UIFlow source tree. A generic newer `mklittlefs` image is rejected by the
Core2 legacy guest and replaced by an empty filesystem on first boot.

Keep the application binary, generated filesystem images, serial logs and
frames outside Git. The repository stores only these small source fixtures.

## Pack

Use a base Core2 image with this partition table:

| Partition | Offset | Size |
| --- | ---: | ---: |
| `factory` | `0x10000` | `0x510000` |
| `vfs` | `0x520000` | `0x6de000` |
| `config` | `0xbfe000` | `0x1000` |
| `wifi` | `0xbff000` | `0x1000` |

The UIFlow `v1.15.4` source used by this probe includes:

```bash
tools/littlefs/prebuilt/littlefs2 \
  -c -v -b core2 \
  -i /path/to/flash-assets \
  -o /path/to/vfs.bin \
  -s 0x6de000
```

The VFS payload must be exactly `0x6de000` bytes. Splice it into a copy of
the base image at `0x520000` and record the resulting SHA256.

## Expected markers

With a correctly recognized VFS, the serial log contains:

```text
BOARD NAME: M5STACK-CORE2
APIKEY: <redacted-by-test-runner>
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
```

If startup reaches the application, `CORE2_LEGACY_ORIGINAL_MAIN_START`,
`CORE2_LEGACY_ORIGINAL_MAIN_IMPORT_DONE` and
`CORE2_LEGACY_ORIGINAL_MAIN_DRAW_DONE` identify the import and draw phases.
The `MAIN_IMPORT_DONE` marker is the boundary between Python import/display
initialization and the original `main.py` drawing sequence.

Use the Device Service `runtime=qemu-wifi` path. A plain `runtime=qemu`
session omits `misc.esp32_wifi`; legacy UIFlow can then poll the WiFi DMA
status alias without a backing device and never reach `/flash/boot.py`.
