# Nesso N1 PI4IOE interrupt status and shared GPIO3 pad

The qtest protocol exercises the board’s actual HP I2C0 command engine,
FIFO and two PI4IOE devices. QMP sends real panel A/B and touch events. A
physical-address read of the GPIO input register observes the GPIO3 pad.
The script generates an eight-byte SRAM program with WFI and a backward
jump, starts normal TCG, and verifies the program counter stays in that
fixture. No firmware driver or guest MMIO access runs. The C6 baseline
could not start with the separate qtest accelerator because its CPU setup
expects TCG interrupt operations.

```sh
python3 tests/firmware/esp32c6_nesso_pi4ioe_irq/check_shared_pad.py \
  --qemu "$C6_BEFORE_0023" --rom-dir "$C6_ROM_DIR" --baseline
python3 tests/firmware/esp32c6_nesso_pi4ioe_irq/check_shared_pad.py \
  --qemu "$C6_WITH_0023" --rom-dir "$C6_ROM_DIR"
```

A change from the programmed input default latches the PI4IOE status bit
on an input pin. Reading the live input level leaves the latch alone.
Reading interrupt status clears it. Holding the non-default level after
acknowledgement and returning to the default both leave the latch clear.
The mask gates the active-low output while preserving the status bit.
The probe also exercises the opposite default polarity, output direction,
software reset and independence of the touch and PI4IOE sources.

The board’s GPIO3 net joins the touch controller and the first expander
(`0x43`), along with the schematic’s BMI270 interrupt. The modeled touch
and first-expander outputs drive that pad independently. Register activity
on the second expander (`0x44`) leaves the shared pad alone. This fixture
covers controller state, HP I2C0 traffic and the modeled GPIO pad level.
CPU GPIO interrupt-matrix delivery, BMI270 interrupt generation and
physical electrical timing remain outside this fixture. [Diodes DS40583 Rev 3-5, pp. 9–12](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1219/PI4IOE5V6408ZTAEX.pdf) · [Official Nesso board schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1198/DK001-sche_02.png)

The independent host-C check compiles the selected runtime’s actual slave
callbacks with ASan/UBSan and observes their GPIO3 writes. It also checks that
a pending bit on the second expander cannot drive GPIO3.

```sh
python3 tests/firmware/esp32c6_nesso_pi4ioe_irq/check_controller_actual_c.py   --source "$C6_SOURCE_BEFORE_0023" --baseline
python3 tests/firmware/esp32c6_nesso_pi4ioe_irq/check_controller_actual_c.py   --source "$C6_SOURCE_WITH_0023"
```
