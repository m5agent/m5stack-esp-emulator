# ESP32-S3 I2C receive-buffer lifetime diagnostic

This reproduces the guest-driver path found while investigating
[issue 223](https://github.com/m5agent/m5stack-esp-emulator/issues/223).
It is **not a simulator fix**. The original StackChan-UserDemo and StackChan-GPT
BINs still fail their stability acceptance.

## Observation

Original UserDemo reports ESP-IDF v5.5.4. An instrumented native run captured
CPU0 at `0x4038c043` reading the I2C DATA register and writing bytes into
`0x3c3d0410..0x3c3d0427`, overlapping CPU1's saved task frame. The task later
executes `retw.n` at `0x4038ffcf` with an invalid return address. BREAK at
`0x403783c0` is the DoubleExceptionVector, a secondary failure. Per-CPU ring
counters do not establish one total ordering across CPUs.

The instruction sequence matches the `read_len_static` branch in
[ESP-IDF v5.5.4 i2c_master.c](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/esp_driver_i2c/i2c_master.c).
The ISR posts completion before copying the receive FIFO into the caller
buffer. The caller can run on the other core and return first.

This small guest allocates the I2C driver/IRQ on CPU0 and reads 25 bytes from
the modeled FT6336 on CPU1 through `i2c_master_transmit_receive`. It keeps the
buffer alive, snapshots it immediately after the synchronous function returns,
and checks it one tick later. No host injection, private ISR invocation,
direct FIFO polling or PSRAM access is used.

On clean native runtime 0182, the original SDK returned `ESP_OK` and then
changed the buffer after return (iterations 10 and 75 in two runs). Moving
only the SDK completion notification after the FIFO copy produced 30,000
completed reads with no later buffer mutation and zero API errors. This
establishes the notification-order failure in the virtual-device path; it
does not establish its probability on hardware or fix all timeout paths.

## Reproduce

Use a clean ESP-IDF v5.5.4 checkout at
`735507283d5b2f9fb363a1901172dbd9e847945d`, its submodules and
`xtensa-esp-elf` GCC 14.2.0 20260121. With the IDF environment active:

```sh
idf.py -C tests/firmware/s3_i2c_lifetime -B "$BUILD_DIR" build
cd "$BUILD_DIR"
python -m esptool --chip esp32s3 merge_bin -o "$IMAGE" \
  --flash_mode dio --flash_size 16MB --flash_freq 80m \
  0 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin \
  0x10000 s3_i2c_lifetime.bin
```

Use an owned Device Service with native `m5stackchan`. From the repository:

```sh
python3 tests/firmware/s3_i2c_lifetime/run_test.py \
  --api "$DEVICE_API" --token-file "$TOKEN_FILE" --image "$IMAGE" \
  --out-dir "$EVIDENCE_DIR" --expect changed --timeout 120
```

Here `PASS` means the requested **diagnostic observation** was reproduced;
`--expect changed` explicitly expects the defect. Evidence is collected before
stopping the session with `purge=0`.

For the positive control, apply `notification-after-read.patch` to a separate
clean IDF checkout, rebuild the same guest, and use `--expect stable`. This
requires `I2C_LIFETIME_NO_CHANGE errors=0` after all 30,000 reads. The SDK patch
is outside all runtime bootstrap lists and is not a complete firmware repair.

## Original-firmware boundary

UserDemo SHA:
`245bc9af0a5dff0388017073d7f571fdd03268a0df71bc62c8de7567f8e32866`;
GPT SHA: `e680215dd1858dfcff5daff312ef13d1467ee72b77d9cb4a0caba2fd23e7cdc0`.

- Clean 0182: both images still panic in a six-session batch. Failing guests
  were stopped early; the planned 330 seconds is not uptime.
- Experimental delayed I2C completion: all six sessions panic within 330
  seconds. This candidate was rejected.
- Single TCG with `icount shift=5,align=off,sleep=on`: UserDemo 3/3 and GPT 2/3
  remain free of observed panic for 330 wall seconds, but GPT 1/3 panics.
  This is a mechanism comparison, not a fix or new default scheduling policy.
- Nonblack frames can survive a guest panic and do not prove animation.
  Native process `running` is not an application PASS.

[evidence-summary.json](evidence-summary.json) binds original-image runs,
minimal controls, runtime hashes and cleanup. Physical hardware and
browser-WASM were **NOT RUN**. Keep issue 223 open: no complete original-BIN
stability fix or physical-firmware attribution has been established.
