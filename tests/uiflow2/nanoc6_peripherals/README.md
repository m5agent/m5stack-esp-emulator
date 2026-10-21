# NanoC6 onboard peripheral probe

Uses the official UIFlow2 `hardware.RGB()` board path:

- GPIO19 enables the WS2812 `RGBPWR` rail.
- GPIO20 drives the WS2812 data input.
- GPIO9 is read as an active-low user button with the external pull-up.

The guest sets the LED to red and waits for a host-injected GPIO9 press and
release. The host captures ESP32-C6 RMT symbols and decodes the WS2812 GRB
wire bytes.

```bash
python3 tests/uiflow2/run_nanoc6_peripherals.py
```

Verified result:

```text
NANOC6_PERIPHERALS PASS rgb_grb=00ff00 button=True
GPIO7 blue LED: on -> off
GPIO9 button: idle high -> press -> release -> idle high
GPIO19 RGBPWR: high after hardware.RGB()
RMT: 24 symbols / 192 bytes
```

The C6 machine now selects `nanoc6` through `M5SW_C6_BOARD=nanoc6`, so Nesso
panel, SX1262 and board-I2C models are not attached to NanoC6.
