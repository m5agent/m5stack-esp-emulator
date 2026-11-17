# Native ESP32-C6 crash symbols

This benign probe on Nesso N1 prints a readiness marker and calls `abort()`
from a named function. ESP-IDF prints the abort call site and the Core 0
`MEPC` register, then halts. The binary, variant, merged Flash and ELF must
belong to the same build.

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
Use an absolute build path and SDKCONFIG path. From this directory run

```sh
idf.py -B "$BUILD_DIR" -DSDKCONFIG="$BUILD_DIR/sdkconfig" -DIDF_TARGET=esp32c6 build
cd "$BUILD_DIR"
python -m esptool --chip esp32c6 merge_bin --fill-flash-size 16MB -o merged.bin @flash_args
```

Start an isolated Device Service with native C6 QEMU and matching ROM.
Upload `merged.bin`, the exact application ELF, and a different C6 build's
ELF. Register the merged firmware for `nesso-n1` and create a native
`runtime=qemu` session. Confirm `RISCV_C6_CRASH_PROBE_BOOT`,
`RISCV_C6_CRASH_PROBE_ARMED`, and the guest's abort and MEPC lines.

Read `/api/v1/sessions/{id}/crash` with `elf_artifact_id` referencing the
matching ELF. Compare the full app descriptor digest, panic prefix and
uploaded artifact hash. The matching report should identify both the guest
abort site and `MEPC`, with symbol names consistent with
`riscv32-esp-elf-addr2line -f -e m5_riscv_c6_crash.elf <pc>`.
Repeat without an ELF and with the other ELF. Both receipts should contain
no decoded addresses. The Xtensa live PC API remains unsupported for this
C6 session.

Download the same-session ZIP with
`include=serial,logs,crash&elf_artifact_id=<matching-elf-digest>`. Check the
archive integrity and match its crash receipt and bounded serial digest.
Stop with `purge=0&retain_flash=0`. Check the retained crash receipt,
released Flash, and absence of an active process or lease.

[Bounded virtual-device results](summary.json) record the unchanged-
artifact baseline and candidate. The probe qualifies little-endian RISC-V
ELF32 ILP32 soft-float executable symbols on native ESP32-C6. Stack memory
printed by the panic handler is not unwound by the service.
