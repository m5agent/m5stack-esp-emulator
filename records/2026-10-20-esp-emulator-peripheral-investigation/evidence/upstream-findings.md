# Upstream findings (checked 2026-10-20)

- Repository: https://github.com/espressif/esp-emulator
- Public repo commit inspected: `017d587c590abee41488abaa43dffeb867694ade`
- Installed release: `esp-emu 0.49.0` (aarch64-apple-darwin)
- Public repo contains release binaries, docs and test applications; the emulator source itself is not published.
- Issue #10 says source publication is still undecided. A LICENSE file exists, but this should not be treated as an available source tree or plugin API.
- Issue #5 requests external SPI/I2C/GPIO device bridges. Maintainer response: tracker stays open and peripheral emulation ideas are being discussed. No implementation/ETA was published as of this check.
- Issue #5 proposes transaction-level bridges for SPI/I2C and an edge bridge for GPIO, plus an I2S stream bridge. Those would be the missing pieces for displays, touch, PMIC, RTC, sensors and audio codecs.
- Issue #20 reports that UART RX timeout (`RXFIFO_TOUT`) and line timing are not modelled and TX/RX complete instantly. UART1 peer scripts work for byte exchange but are not timing-faithful for Modbus/RS485 idle-based framing.
- Issue #28 reports a stock ESP-IDF v5.5.2 P4 image from an M5Stack Tab5 failing in the second-stage bootloader SPI-flash path. Our controlled P4 smoke run with IDF v5.5.5 passed, so this must be treated as a board/image-specific open compatibility risk rather than a blanket P4 pass/fail claim.
- Current built-in peripheral models documented by upstream: UART, USB Serial/JTAG, GPIO, timers, eFuse, SPI flash, GDMA, GP-SPI, RMT, LEDC, PCNT, MCPWM, I2C with one built-in 24Cxx-style EEPROM at address `0x50`, watchdogs.
- The smoke test explicitly expects address `0x50` to ACK and address `0x55` to NACK. There is no documented CLI option to attach arbitrary I2C/SPI/GPIO device models.
