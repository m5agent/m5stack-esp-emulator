# Core2 8 MiB PSRAM bank-switch probe

This ESP-IDF probe exercises the upper half of the Core2 8 MiB PSRAM through
the real ESP32 `esp_himem` API and DRAM1 MMU bank switching.

The default 4 MiB PSRAM heap window is not enough to prove the board's 8 MiB
capacity. The probe:

1. queries `esp_himem_get_phys_size()` and the reserved MMU window;
2. allocates two 32 KiB physical blocks above the normal heap window;
3. maps each block, one at a time, into the same virtual window,
   writes a deterministic pattern, and unmaps it;
4. remaps the blocks in reverse order and verifies the data;
5. emits `CORE2_HIMEM_BANK_PASS` only when all map/write/unmap/remap/read
   steps succeed.

Build with ESP-IDF for `esp32`, then merge the bootloader, partition table and
application into a 16 MiB flash image. The committed sdkconfig defaults enable
Quad PSRAM, 80 MHz timing and an eight-block bank-switch reserve.

Run three independent Device Service leases:

```bash
python3 tests/firmware/core2_psram_himem/run_test.py \
  --base-url http://127.0.0.1:8787 \
  --image /tmp/core2-himem-16m.bin \
  --attempts 3 \
  --out-dir /tmp/m5-core2-himem
```

This is virtual-device data-plane validation. It does not prove physical PSRAM
capacity, cache timing or hardware behavior.
