# Actual C6 GPIO IRQ preimage

These source fixtures are the exact selected postimages of the canonical QEMU
base and ordered patch inputs in `source-provenance.json`. That receipt was
checked against the existing canonical source before copying the files. They
retain upstream copyright/license headers. No ROM, firmware or mutable Flash
is included.

The unchanged board-I2C file allows the host sanitizer oracle to exercise real
PI4IOE/FT source arbitration through the actual GPIO controller. The machine
and C6 subclass files permit patch replay and wiring checks; the host oracle
does not execute QEMU machine realization or the RISC-V CPU. See the
[test workflow and guest boundary](../../../../tests/firmware/esp32c6_gpio_irq/README.md).
