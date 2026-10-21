# StamPLC buzzer probe

The documented StamPLC buzzer is driven from `G44` by M5Unified's 1-bit
delta-sigma I2S output. The probe captures firmware-generated I2S TX data and
checks that the output is non-silent.
