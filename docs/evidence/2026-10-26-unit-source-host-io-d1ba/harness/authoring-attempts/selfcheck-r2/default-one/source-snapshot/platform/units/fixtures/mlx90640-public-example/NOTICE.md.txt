# MLX90640 public example fixture

Derived from `https://raw.githubusercontent.com/pimoroni/mlx90640-library/55646516aec32c340605f9e9c7bb64d1fed8dde3/MLX90640%20example%20data.xlsx` at commit `55646516aec32c340605f9e9c7bb64d1fed8dde3`.
The source repository distributes this workbook under its Apache-2.0 license;
`LICENSE.Apache-2.0` preserves that license. This is the publicly distributed
Melexis library example workbook mirrored in Pimoroni's library repository,
not a measurement made by this emulator project.

Changes: extracted Input data EEPROM and two raw subframes into JSON;
removed EEPROM serial words 7, 8 and 9; added metadata, hashes and temperatures
computed by the unmodified official M5Stack MLX90640 driver.
The serial redaction leaves all 768 computed temperatures unchanged.
No original spreadsheet, firmware binary or live device identifier is stored.

The fixture's control word is 0x1901; both subframes contain
832 raw words, with subpage IDs 0 and 1 supplied by the sensor status register.
The expected temperatures are algorithm/reference values for this dataset,
not a new physical measurement or certification of sensor accuracy.

`synthetic-plus16.json` adds 16 modulo 65536 to each of the first 768 raw IR
words in both subpages. EEPROM, auxiliary words and control remain unchanged.
Reproduce it with `python3 tests/units/derive_thermal_fixture.py` from the
repository root. Its expected values are computed by the unchanged official
driver's host-side calibration/math functions. They are reference expectations;
they are not guest execution or physical temperature measurements.
