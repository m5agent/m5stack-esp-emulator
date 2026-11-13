# Pinned classic DPORT replay seed

These two files are replay inputs from
[`espressif/qemu` commit `40edccac415693c5130f91c01d84176ae6008566`](https://github.com/espressif/qemu/tree/40edccac415693c5130f91c01d84176ae6008566):

- `hw/misc/esp32_dport.c`: SHA-256 `f0a0c8cfc88d01eb86319132c6636474155c66b547a9a2a2f374c78074e9eeeb`
- `include/hw/misc/esp32_dport.h`: SHA-256 `c48562e38470c4455cacd0b387048928449e8cd9b8831798c2de02f1e591b01d`

The C source is byte-identical. The header removes the upstream final blank
line to satisfy the repository whitespace check; its fixture SHA-256 is
`74997ff8cad53481d69ffb0fb59454037ee89a20b9587b0a2074b66d93844ecd`. The header hash above identifies the original upstream bytes.

The C source retains its Espressif copyright and GNU GPL version 2 or later
notice. The header belongs to the same QEMU source distribution.

`test_classic_cache_dirty_sync_patch.py` checks these hashes and replays the
complete native bootstrap prefix through the candidate patch. It compiles the
actual cache synchronization, MMU remapping, PSRAM alias mapping, cache-control
register case and readiness code with observable memory/block/IRQ shims.
The shim does not claim QEMU execution, hardware timing or physical cache
coherence. Original-firmware Device Service validation is separate.
