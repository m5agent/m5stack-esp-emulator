# Core2 legacy VFS probe

This fixture adds a visible `/flash/boot.py` marker before the legacy UIFlow
system menu starts. It is used to distinguish a missing or reformatted VFS
from a later system-startup failure.

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
CORE2_LEGACY_VFS_BOOT
```

Reaching `CORE2_LEGACY_VFS_BOOT` proves that the guest mounted the injected
VFS and executed its `/flash/boot.py`. It does not prove that the system menu
or the application framebuffer initialized.

Use the Device Service `runtime=qemu-wifi` path. A plain `runtime=qemu`
session omits `misc.esp32_wifi`; legacy UIFlow can then poll the WiFi DMA
status alias without a backing device and never reach `/flash/boot.py`.
