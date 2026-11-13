# Classic ESP32 Bluetooth low-power and modem clock registers

Use the native Xtensa QEMU binary with patches 0195 and 0196 and the matching
classic ESP32 ROM directory. The command also accepts a pre-0195 binary and a
binary with patch 0195 alone.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_mmio.py \
  --rom-dir "$XTENSA_ROM_DIR" \
  --qemu "$PATCHED_XTENSA_QEMU" \
  --bt-clock-only-qemu "$BT_CLOCK_ONLY_XTENSA_QEMU" \
  --unpatched-qemu "$UNPATCHED_XTENSA_QEMU"
```

The test pauses the StickC Plus2 CPUs and exercises 32-bit guest-address-space
access through the QEMU qtest interface. It checks the ESP32 reset values, the
XTAL selector and divider readback, reserved-bit masking, modem clock enable
readback, zero writes, and restoration of the reset values after a QMP system
reset. The optional controls reproduce the original zero reads and show that
0195 alone preserves only the low-power clock settings.

| Address | Register | Reset | Writable mask |
| --- | --- | --- | --- |
| `0x3ff000cc` | `DPORT_WIFI_CLK_EN` | `0xfffce030` | `0xffffffff` |
| `0x3ff000d4` | `DPORT_BT_LPCK_DIV_INT` | `0x000000ff` | `0x00001fff` |
| `0x3ff000d8` | `DPORT_BT_LPCK_DIV_FRAC` | `0x02001001` | `0x0fffffff` |

The register oracle is ESP-IDF v5.5.5 `dport_reg.h` at
`b774170ff46c393eeb5e495ea37936038d3f4f4f`. The raw file SHA-256 is
`b56337324208a6cbb0a014a8cf98e880cb3ba55e4fe9a66475c777cd4efc1acb`.
[Modem clock enable](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1031-L1037)
and [Bluetooth low-power clock](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1088-L1138).

The controller test has no guest execution. Application acceptance uses the
unchanged JIGGLER 1.0 merged BIN in dedicated native Device Service sessions
under both the default and auto icount policies with the watchdog enabled.
PHY clock timing, RF behavior, and BLE HID pairing require separate validation.
See [issue #225](https://github.com/m5agent/m5stack-esp-emulator/issues/225) for
the original image identity and failing UART markers.

## BLE clock sampling

Run the paired qtest with two otherwise equivalent binaries to exercise the
ESP32 BLE time registers before and after patch 0198.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_ble_clock_snapshot.py \
  --rom-dir "$XTENSA_ROM_DIR" \
  --baseline "$PRE_0198_XTENSA_QEMU" \
  --candidate "$XTENSA_QEMU_WITH_0198"
```

A qtest-controlled virtual clock drives guest-address-space reads and writes.
The check covers an atomic coarse/fine sample, both sides of the ESP32 ROM
wake-up predicate, stable reads without a new sample, slot and 27-bit coarse
rollover, read-only latch access, and reset. It also checks that `0x3ff7101c`
continues to use the existing BR/EDR register behavior. The qtest accelerator
executes no guest instructions.

For a candidate that includes 0200, add `--rwbt-clock`. This mode checks the
same BLE clock and confirms that sampling the separate BR/EDR latch leaves
the BLE snapshot unchanged. Its previous-runtime oracle still reproduces the
missing BLE latch before 0198.

The ESP32 register offsets and widths come from the [ESP32 BTDM register map](https://github.com/esp-rs/esp-pacs/blob/e6d898ec67556b8d08b2fc6f6265da930954404f/esp32/svd/patches/btdm.yml#L336-L357).
The [Renesas DA14535 manual, Tables 69 and 70](https://www.renesas.com/en/document/dst/da14535-datasheet#page=166)
describes the same-IP 625 µs coarse clock, microsecond fine count, and
read-only snapshots. The descending fine phase is inferred from the [Dialog SDK reference calculation for a hardware-captured BLE phase](https://github.com/yangchengxcy/da14580/blob/4e1c3006a1cfa4697ed76889b95d754ab0ab54ef/xcy_gump/src/modules/app/src/app_project/prod_test/custom_lld_evt.c#L1961-L1972).
That calculation covers a packet timing capture from the same controller
family. The [ESP32 ROM wake-up check symbol](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_rom/esp32/ld/esp32.rom.ld#L1278)
identifies the separate ESP32 consumer observed polling sample completion and
comparing the fine count with 467. Sample completion is synchronous in the
model. Physical timing of the sample request and the fine counter phase on
ESP32 remain unmeasured.

The [virtual-device evidence summary](ble-clock-evidence-summary.json) records
both qtest binaries and the unchanged original BIN in Device Service. The
final native build ran the original for 65 seconds each with default and auto
icount. Both controls recorded black frames and no watchdog or clock
assertions. The original instructions describe automatic startup with the
display off.

A separate 40-second default-icount session held and released C through
the StickC Plus2 GPIO35 input. The welcome screen did not appear. All 80
sampled frames were black, so the A/B controls were unexercised. The evidence
includes the firmware, runtime, ROM, framebuffer and ZIP hashes and records
that each ZIP was saved before its session stopped. A separate native trace
shows the original ROM crossing the BLE time wait and reaching a BR/EDR sleep
and wake path. Application UI readiness, BLE HID pairing, and physical
hardware remain unverified.
## GPIO display identification and original JIGGLER animation

JIGGLER's original image uses a GPIO-driven `RDDID` probe before selecting
the StickC Plus2 display and power-button path. The firmware's own panel
description selects CS5, SCK13, D/C14, and bidirectional SDA15. It sends
command `0x04`, releases SDA, clocks one turnaround bit, and checks the
returned ID under mask `0xfb`. This matches the [StickC Plus2 board pinout](https://docs.m5stack.com/en/core/StickC-Plus2)
and the [ST7789V2 serial and RDDID specification](https://www.mouser.com/datasheet/2/744/ST7789V2-3314280.pdf).

Before the GPIO attachment, the original application saw GPIO35 go low and
high during its loop but resolved board ID 129, M5AtomPsram. Its branch for
board ID 5, M5StickCPlus2, consumes GPIO35 as the power button. The probe
did not enter the existing SPI2/3 controller, and the LCD received zero
commands or pixels. Both the original image's own board records and actual
guest MMIO confirmed the board mismatch. RTC and IMU reads were separately
observed on the board's I²C bus.

The same GPIO MMIO sequence reads `0xffffffff` on the frozen runtime and
`0x00000085` on the GPIO candidate. CS, D/C, data direction, turnaround,
reselection and GPIO-controller reset controls run through the actual GPIO
data path. The final candidate retains separate SDA drive ownership and
keeps SDA released while the host has an active but unresolved output route.
The [host C ownership control](check_gpio_peer_ownership_actual_c.py) runs the
actual GPIO receiver and verifies that LCD release preserves an independently
driven input level.
The existing VSPI FIFO read returns `0x85` on both runtimes. A Core2 with
the same test-pin sequence does not expose the Plus2 panel. See the
[bounded verification summary](gpio-lcd-evidence-summary.json).

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_gpio_lcd_readback.py \
  --qemu /path/to/qemu-system-xtensa --rom-dir /path/to/pc-bios \
  --expected-id 0x85
```

With the GPIO patch alone, the unchanged original displayed the JIGGLER
animation after C. The default profile stayed on the animation and auto
logged an IDLE0 task-watchdog reset. The short trials did not establish an
A/B response.
The UIFlow2 Plus2 fixture reported board 5, a 135×240 display and an actual
A press. The separate Core2 fixture still reported board 2 and touch-driven
frame output.

## BR/EDR sleep, native clock and timer interrupts

Patch 0200 adds controller timing to the classic ESP32 RWBT register bank at
`0x3ff71000`. Use the GPIO-only runtime as the baseline and the GPIO and RWBT
runtime as the candidate with the same ROMs.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_rwbt_sleep.py \
  --qemu "$GPIO_ONLY_XTENSA_QEMU" --rom-dir "$XTENSA_ROM_DIR" --baseline
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_rwbt_sleep.py \
  --qemu "$XTENSA_QEMU_WITH_0200" --rom-dir "$XTENSA_ROM_DIR"
```

These qtest controls use aligned 32-bit MMIO and advance QEMU virtual time
without running guest instructions. The baseline returns no active sleep
state, elapsed count or IRQ. Its interrupt mask forces bit 9 high. The
candidate tests status, clocks, correction and the actual DPORT source-6
level, including masking a pending interrupt, unmasking it, clearing it
with a write-one-to-clear acknowledgement, and resetting an armed timer.

| RWBT offset | Modeled behavior |
| --- | --- |
| `0x00c`–`0x018` | Mask, masked status, raw status and write-one-to-clear. Slot, wake, fine and gross events drive source 6 through bits 0, 2, 9 and 10. |
| `0x01c`, `0x020` | A SAMP write latches the 28-bit half-slot counter and descending microsecond slot phase together. Both reads retain their values until the next sample. |
| `0x030`–`0x038` | Sleep request, software wake and read-only active status. The elapsed count runs on the integer-divided low-power clock selected at entry. Software wake finishes on the next tick when it precedes the deadline. |
| `0x040`, `0x044` | Clock phase correction resumes the stopped BR/EDR clock and recomputes armed deadlines. |
| `0x0b4`, `0x0b8` | The 23-bit gross comparator advances in 16-slot increments (10 ms). The 27-bit fine comparator advances in 625 µs slots. Both compare modulo their widths. |

The [Bluetooth Core Specification BR/EDR clock section](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/br-edr-controller/baseband-specification.html)
defines the 28-bit clock and 312.5 µs half-slot. The exact ESP32 ROM named in
the evidence programs `0x3ff710b4` from `r_ke_timer_set` through
`0x4001a948`, using the 23-bit clock divided by 16, and its ISR checks and
acknowledges bit 10 at `0x40055621`. The original firmware also programs
`0x0b8` and reads and acknowledges bit 9. The
[pinned Espressif ROM symbol map](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_rom/esp32/ld/esp32.rom.ld)
identifies `r_ke_timer_set`. The observed ROM sleep path programs `0x034`
and `0x030`, polls bit 15, acknowledges bit 2, and computes 213 µs phase
correction from 206 elapsed 2 µs ticks. The corresponding
[Renesas RW-family sleep and correction registers](https://www.renesas.com/en/document/dst/da14535-datasheet#page=167)
and [gross comparator](https://www.renesas.com/en/document/dst/da14535-datasheet#page=177)
are from a separate BLE controller and inform the timer semantics. The
BR/EDR fine phase and synchronous sample behavior are model choices
consistent with these references and the observed driver sequence.

The fixture covers integer division of XTAL and RC8M and samples changes to
clock configuration on the next sleep entry. Fractional division with both
ratio fields nonzero, physical clock-start timing, external early wake and
wake preset pulse behavior remain unverified. The `0x03c` preset retains
register storage. BLE pairing, HID delivery and RF require separate evidence.

With 0199 and 0200 applied, the unchanged original reached its home screen
after a C hold at the default `icount` shift 5. The 85-second capture recorded
no watchdog or reset. The original `shift=auto,sleep=off` argument caused
an IDLE0 task watchdog at 14.844 guest seconds after a C hold and at 14.801
guest seconds without any input. The same original, native binary, ROM and
C hold with `shift=auto,sleep=on` reached the identical home frame after
80.069 seconds and completed the 85-second observation without watchdogs or
resets. The adaptive clock follows host time while idle. Fixed shifts keep
the existing deterministic idle-time behavior.

With the corrected adaptive profile, the first direct Plus2 UIFlow2 fixture
run drew the ready frame but missed its host-timed A pulse. The fixture now
uses `virtual-keytap:a,0.1`, schedules release on the QEMU virtual clock,
and waits for the guest's `STICKCPLUS2_BTN_A 1` marker before checking the
green pixel. The
[bounded evidence summary](rwbt-sleep-evidence-summary.json) binds each
result to its original image, runtime, inputs, frame and retained ZIP.

The integrated Device Service production tap run exercised the same original
with `auto,sleep=on`. C reached home, the 100 ms B tap showed the disconnected
mouse message, and the 100 ms A tap paused. The service queued a 2 s B hold.
The guest then logged an IDLE0 task watchdog at 155.641 guest seconds before
the settings frame appeared. It separately logged a `LoadProhibited` panic
after the first reboot. Both app partitions still matched the original.
This longer failure remains open alongside the shorter C-only result.

The original restart also pulses DPORT core reset `0x3ff000d0` with
`0x7ff` followed by zero before requesting software CPU reset. Patch 0201
connects the documented RWBT MAC and low-power reset domains. The baseline
leaves the old source-6 level and an armed comparator across that pulse. The
candidate clears them and accepts new timer programming afterward. Resetting
only the CPU or the separate BT baseband leaves the RWBT state intact.
The fixture uses aligned 32-bit MMIO. The combined pulse is the reproduced
restart path. The LP-only native clock resume is a model of the surviving
MAC clock reference. [Espressif reset fields](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1008-L1029)
and [restart sequence](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_system/port/soc/esp32/system_internal.c#L28-L41).

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_rwbt_modem_reset.py \
  --qemu "$XTENSA_QEMU_WITH_0200" --rom-dir "$XTENSA_ROM_DIR" --baseline
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_rwbt_modem_reset.py \
  --qemu "$XTENSA_QEMU_WITH_0201" --rom-dir "$XTENSA_ROM_DIR"
```

## Classic adaptive timing and state compatibility

Classic ESP32 Device Service sessions use fixed shift 5 by default. Setting
`M5_CORE2_ICOUNT_SHIFT=auto` selects `shift=auto,align=off,sleep=on,max-shift=5`.
Adaptive adjustment can still select shifts 0 through 5. At the limit,
guest time can fall behind host time rather than allocate more virtual time
per instruction. QEMU auto without the option retains the original 0–10
range. The cap limits emulator pacing and does not alter watchdog registers
or firmware. [QEMU invocation](https://www.qemu.org/docs/master/system/invocation.html)

Patch 0202 rejects the cap with a fixed shift, host clock alignment, instant
idle jumps or record/replay. The record/replay combination is rejected before
opening a file. The migration stream retains the signed 16-bit shift field
in the existing v2 subsection. A capped destination validates the field
before assignment. A failed snapshot load can leave other state partially
loaded, so the test checks the shift field specifically after resuming and
saving the destination.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_icount_admission.py   --qemu "$XTENSA_QEMU_WITH_0202" --uncapped-qemu "$XTENSA_QEMU_WITH_0200"
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_icount_shift_migration.py   --qemu "$XTENSA_QEMU_WITH_0202" --baseline "$XTENSA_QEMU_WITH_0200"
```

The [native peripheral matrix](rwbt-native-matrix-summary.json) passed all 69
cases once under ambient host load using the new Xtensa runtime and the
existing C6 runtime. Its execution source predates the adaptive argument and
Plus2 fixture changes. The seven explicit icount cases all used the same
fixed Core2 arguments before and after that change, and the other 62 cases
had no explicit icount arguments. The Plus2 fixture ran separately with the
corrected adaptive clock and virtual tap.
