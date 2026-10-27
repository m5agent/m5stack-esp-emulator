# Arduino Nesso N1 SX1262 LoRa probe

Exercises the board SX1262 through the UIFlow2 `lora.SX1262` driver on the
documented shared SPI pins: SCK `G20`, MOSI `G21`, MISO `G22`, CS `G23`,
BUSY `G19` and IRQ `G15`. The probe uses `machine.SoftSPI` because the
UIFlow2 `hardware.LoRa` wrapper reinitializes the display-owned hardware SPI
bus on this board; the same four physical GPIO lines still carry every
command, register and packet FIFO byte.

The probe also configures the board PI4IOE power/RF-switch rails before
initializing the modem. QEMU models the SX1262 command, register and packet
FIFO protocol and performs a local TX-to-RX loopback; no UIFlow2 API values
are replaced in Python.
