# StamPLC LM75 probe

Reads the documented LM75BDP at I2C address `0x48` on StamPLC G15/G13.
The probe validates the chip-native 11-bit two's-complement temperature
encoding after QOM injection.
