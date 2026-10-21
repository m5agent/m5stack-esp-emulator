# Tab5 RS-485 probe

Uses the official `machine.UART` RS-485 half-duplex mode on UART1 with the
Tab5 SIT3088 topology. The Tab5 UIFlow2 build does not currently ship the
separate `hardware.PWR485` wrapper module:

- TX: GPIO20
- RX: GPIO21
- direction/RTS: GPIO34
- mode: `MODE_RS485_HALF_DUPLEX`

The esp-emu `--uart1-tcp` bridge is connected to a host-side peer. The guest
transmits `TAB5_RS485_PING`; the peer replies `TAB5_RS485_PONG`. The test
prints the exact bytes and only emits `TAB5_RS485_DONE PASS` after receiving
the response.

The default runner also captures the real 1280x720 tab5 framebuffer through
native `riscv64-elf-gdb`, injects touch and requires the frame to change.
Docker is only a fallback when the native RISC-V GDB is unavailable.

Run:

```bash
python3 tests/uiflow2/run_tab5_rs485.py
```

Use `--probe-only` for a serial-only run, or `--touch X,Y` to change the
injected touch point.

![Tab5 RS-485 test](../../../docs/images/tab5-rs485-test.png)
