# Core2 v1.1 INA3221 probe

Reads the INA3221 manufacturer/die ID, channel 1 bus voltage and shunt voltage
through the ESP32 internal I2C0 controller. QOM properties inject physical
voltage/current values; the probe validates the chip-native 8 mV bus and 40 uV
shunt register encodings.
