# ESP32-S3 shared cache IOMMU / atomic regression

This ESP-IDF fixture programs an unused S3 cache MMU slot on CPU0 while CPU1
reads flash and executes atomic increments in internal RAM. It exercises the
same shared cache IOMMU notifier and TCG atomic lookup as the PaperColor host
crash in issue #217. It does not access the remapped window or change any
application firmware. PSRAM, radio, USB, display and physical timing are outside
this regression.

Build with unmodified ESP-IDF v5.5.4 (commit
`735507283d5b2f9fb363a1901172dbd9e847945d`), target `esp32s3`, using the supplied
`sdkconfig.defaults`. Merge the resulting bootloader at `0x0`, partition table
at `0x8000` and application at `0x10000` with `esptool --chip esp32s3 merge_bin`.
Use DIO, 80 MHz and 16 MiB flash settings.

Start an owned Device Service with the candidate QEMU/ROM paths, separate state,
port and token file. Run:

```sh
python3 tests/firmware/s3_cache_atomic/run_test.py \
  --api "$OWNED_SERVICE_API" --token-file "$OWNED_TOKEN_FILE" \
  --image "$MERGED_PROBE_BIN" --out-dir "$RAW_EVIDENCE_DIR"
```

A PASS requires both guest completion markers, a nonfailed session and no
watchdog/panic/host-error signatures. The runner collects evidence before stop
and retains session history. The ZIP and JSON contain local operational data;
keep them in ignored storage and redact summaries before publication.

For a negative control run the identical merged image against the runtime
before patch `0182-tcg-iommu-vcpu-flush.patch`. Repetition may be necessary:
the old cross-thread TLB race can produce `atomic_mmu_lookup`, `Bad ram pointer`
or a host signal, and a single noncrashing run does not disprove the race.
