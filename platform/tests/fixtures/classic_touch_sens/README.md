# Classic ESP32 touch SENS contract fixture

`esp32s3_sens.c` is the complete preimage of
`0103-classic-touch-measurement.patch`, taken from the QEMU model immediately
before that patch. Its GPL-2.0-or-later notice is retained. The fixture is source
code for a deterministic patch regression; it contains no firmware, ROM, local
execution evidence or device identifiers.

The Python test pins its SHA-256, copies it into a temporary tree, applies the
repository patch, checks reverse applicability, and inserts every definition and
function after the include block verbatim into `contract.c.in`. The real
factory, QOM input registration, SENS writes/reads, timer callback and reset run
inside that translation unit. The timer, RTC MMIO transport, memory mapping,
QOM registration and ADC sample provider are controlled test doubles. No QEMU
checkout, local runtime cache, network access or Device Service is required.

The twelve C cases check:

- All ten factory inputs start at the same nominal 1 MHz; QOM pointers reach
  the actual controller and remain external inputs across a reset.
- Software START uses the model's consumed-command convention. Guest clearing
  START does not cancel an in-flight conversion; a fresh START clears old DONE.
- Shared measurement and XPD timing use the nominal 8 MHz clock, with no early
  completion. Channels 4 and 7 reach their high/low 16-bit result slots.
- DONE, touched status and output counters reject guest forgery; CLEAR removes
  touched status while preserving DONE. Nominal counters support thresholds,
  zero input and saturation without overflowing.
- Timer polling honors RTC's gate, repeats through a separate sleep phase, and
  uses the selected nominal 150 kHz, 32.768 kHz or 8 MHz/256 slow clock.
- Switching from timer sleep to software mode requires a new START; switching
  during conversion allows completion. FSM disable and reset cancel timers.
- The mask and measurement window latch at START. Existing classic/S3 ADC and
  temperature paths retain their original offsets, arguments and output.

Four mutants independently remove sleep-transition cancellation, retain stale
DONE, permit output writes or ignore the QOM input. Each must compile and then
fail its behavioral assertion. The default test requires a C compiler and Git,
and explicitly skips this native contract if either is unavailable. Sanitizers
are not enabled by default, so the test does not depend on host sanitizer
support.

Run from the repository root:

```sh
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_classic_touch_measurement_patch.py' -v
```

The register contract follows Espressif ESP-IDF's ESP32
`soc/sens_reg.h`, `soc/rtc_cntl_reg.h` and `hal/touch_sensor_ll.h`: CTRL1 at
SENS+`0x58`, CTRL2 at `0x84`, result slots at `0x70`–`0x80`, and work mask at
`0x8c`. DONE is read-only bit 10, FORCE is bit 13, START is bit 12 and RTC STATE0
bit 23 gates timer mode. Official LL software triggering writes START=1 then 0;
it does not document START as a hardware self-clearing bit.

This remains a partial nominal controller model. RTC changes are observed when
SENS is accessed or its timer runs; this patch adds no asynchronous RTC hook or
RTC interrupt/wakeup implementation. The tests do not establish calibrated
capacitance, board identification thresholds, physical touch behavior, interrupt
delivery or hardware clock accuracy. Native C contract PASS and visible guest
virtual-device PASS are separate evidence layers.
