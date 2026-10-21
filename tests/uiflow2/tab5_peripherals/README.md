# Tab5 peripheral probe

Uses the Tab5 system I2C bus (`G31` SDA, `G32` SCL) through the native
ESP32-P4 emulator controller.

The esp-emu `--i2c-dev` register-file backend is preloaded with the documented
chip identities and sample/time registers for:

- BMI270 `0x68`, CHIP_ID `0x24`;
- INA226 `0x41`, manufacturer ID `0x5449`;
- PI4IOE5V6408 at `0x43/0x44`, chip ID `0xA2`;
- RX8130CE `0x32`, BCD date/time registers.
- PI4IOE2 charger status input `0x0F=0x00` (low = charging) and CHG_EN
  output bit.

This is a controller-level register simulation. Dynamic sensor updates and
GPIO side effects remain partial until esp-emu exposes writable QOM/dynamic
I2C models.

## Verified result

With UIFlow2 running on ESP32-P4:

```text
TAB5_I2C_PORT 1
TAB5_I2C_SCAN [50, 65, 67, 68, 80, 85, 104]
TAB5_BMI270_CHIP_ID=0x00
TAB5_INA226_MANUFACTURER_ID=0x5449
TAB5_INA226_CALIBRATION=0x1234
TAB5_PI4IOE1_CHIP_ID=0xA2
TAB5_PI4IOE1_WRITEBACK=0x55
TAB5_PI4IOE2_CHIP_ID=0xA2
TAB5_PI4IOE2_WRITEBACK=0x55
TAB5_RX8130_TIME=57301203211026
TAB5_SYSTEM_RTC_API (2026, 10, 22, 3, 12, 34, 56)
TAB5_BATTERY 8000 1248 87
TAB5_CHARGE_INPUT=0x00
TAB5_CHARGING True
TAB5_CHARGE_ENABLE 1
TAB5_UI_DRAWN 1280 720
TAB5_DRAW_AFTER_TOUCH 1
```

`BMI270` is visible at address `0x68`. The diagnostic probe confirms that
register zero stores `0x24` when written from `main.py`, but the UIFlow2 boot
board path clears the preloaded identity before the script runs. A real
BMI270 reset/init state machine and dynamic samples remain required.

Run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_tab5_ui_test.py \
  --base .work/uiflow2-tab5/tab5-emulator-merged.bin \
  --elf .work/uiflow2-tab5/micropython.elf \
  --files-dir tests/uiflow2/tab5_peripherals \
  --touch 640,520 --timeout 120 \
  --i2c-dev '1:0x41,fill=0,reg=0xFE=0x54,reg=0xFF=0x49,reg=0x02=0x19,reg=0x03=0x00,reg=0x04=0xB0,reg=0x05=0x00' \
  --i2c-dev '1:0x43,fill=0,reg=0x01=0xA2' \
  --i2c-dev '1:0x44,fill=0,reg=0x01=0xA2,reg=0x0F=0x00' \
  --i2c-dev '1:0x32,fill=0' \
  --i2c-dev '1:0x68,fill=0,reg=0x00=0x24'
```

The PI4IOE2 `CHG_STAT` input and `CHG_EN` output register paths reach the
official `M5.Power` API. `CHG_STAT` is active-low: `0x0F=0x00` makes
`Power.isCharging()` return `True`, while `0x0F=0x40` makes it return `False`.
The deterministic scenarios in `scenarios.json` also verify signed current and
battery-level conversion:

- charging-normal: `8000 mV / 1248 mA / 87%`
- discharging-low: `7200 mV / -501 mA / 37%`

Run both with:

```bash
python3 tests/uiflow2/run_tab5_peripheral_scenarios.py
```

The IP2326 analog charge-current/termination state machine and hot state
injection remain partial on esp-emu 0.50.0; changing states currently requires
a new emulator launch.

INA226 bus-voltage/current register injection reaches the official power API
as `8000 mV / 1248 mA / 87%` while charging and
`7200 mV / -501 mA / 37%` while discharging. Dynamic host injection remains
unavailable.

The Rust I2C probe writes and reads RX8130 time registers directly through
`machine.I2C`, proving the P4 controller and register file path. `machine.RTC()`
only changes the ESP32-P4 system clock and is not counted as external RTC
evidence. RX8130 time progression and dynamic host time injection remain
unavailable on esp-emu 0.50.0.

If `riscv64-elf-gdb` is installed, framebuffer capture runs natively; Docker
is only a fallback.

![Tab5 peripheral probe](../../../docs/images/tab5-peripherals-test.png)
