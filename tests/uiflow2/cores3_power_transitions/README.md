# CoreS3 runtime PMIC transitions

Keeps the UIFlow2 application running while the host changes AXP2101 battery
level, battery voltage, VBUS voltage and charging state through QOM. The test
requires the official `Power` API to observe all runtime states without an
emulator restart.
