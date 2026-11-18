# StickS3 RTC main comparator while awake

The ESP32-S3 firmware programs and reads back the RTC main comparator while
the digital domain remains running. The main RTC interrupt is masked during
the probe so the raw bit can be observed without a driver clearing it. The
probe does not begin light sleep or test CPU interrupt delivery.

Use ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
Use a separate ignored build directory and the 8 MiB merged flash format.

```sh
source "${IDF_PATH}/export.sh"
mkdir -p .work/sticks3-awake-compare-build
idf.py -C tests/firmware/sticks3_rtc_awake_compare \
  -B "${PWD}/.work/sticks3-awake-compare-build" \
  -D "SDKCONFIG=${PWD}/.work/sticks3-awake-compare-build/sdkconfig" build
idf.py -C tests/firmware/sticks3_rtc_awake_compare \
  -B "${PWD}/.work/sticks3-awake-compare-build" merge-bin --fill-flash-size 8MB
```

Upload the merged image to an isolated Device Service, admit it as `sticks3`
and use native `qemu` with networking disabled. Capture serial and a
same-session evidence ZIP. Stop with `purge=0`, release mutable flash, and
confirm the guest exited and the service has no active leases.

The guest must emit one boot marker and, in order, the programmed low/high
readback, a crossed deadline from an unstrobbed write, the armed deadline
and raw interrupt values, the replaced deadline receipt, and
`RTC_AWAKE_PASS`. A stage after arming changes register readback while the
already armed deadline still fires. Replacing a deadline with a new strobe
keeps raw bit 10 clear across the canceled deadline and sets it at the new
deadline. Clearing the sleep wake and reject bits leaves main raw bit 10
set. Clearing bit 10 then removes it from raw status.

The [observed controls](awake-compare.summary.json) retain the same binary
on the earlier runtime and the timer candidate. The earlier runtime
reached the guest but failed compare-register readback. The candidate
completed the register and timing assertions. The tests used the ESP-IDF
[RTC register definitions](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/soc/esp32s3/register/soc/rtc_cntl_reg.h).
