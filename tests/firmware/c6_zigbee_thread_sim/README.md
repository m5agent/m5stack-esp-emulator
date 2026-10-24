# ESP32-C6 Zigbee / 802.15.4 feasibility

This diagnostic launches a source-built ESP-IDF `HA_on_off_switch` and
`HA_on_off_light` pair in two `esp-emu` C6 instances. A local UDP relay
forwards raw 802.15.4 frames while preserving both serial logs and directional
frame summaries.

It answers a narrow question: can the current `esp-emu --thread-sim` data plane
complete Zigbee commissioning and an On/Off command? A `PARTIAL` result means
radio frames were observed but the application lifecycle did not complete; it
must remain a `runtime_model_gap`, not a firmware FAIL.

The runner accepts built artifacts and does not use host-side fake radio
values:

```bash
python3 tests/firmware/c6_zigbee_thread_sim/run_feasibility.py \
  --emulator /path/to/esp-emu \
  --switch-image /path/to/switch/merged.bin \
  --switch-elf /path/to/switch/light_switch.elf \
  --light-image /path/to/light/merged.bin \
  --light-elf /path/to/light/light_bulb.elf \
  --timeout 45 \
  --out-dir /tmp/m5-c6-zigbee-thread-sim
```
