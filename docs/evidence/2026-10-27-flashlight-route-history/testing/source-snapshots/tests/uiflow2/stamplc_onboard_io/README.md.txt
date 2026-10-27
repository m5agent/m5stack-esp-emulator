# StamPLC onboard IO probe

Validates the documented chip split:

- AW9523B `0x59` controls relays P0_0..P0_3 and optocoupler inputs
  P0_4..P0_7/P1_4..P1_7;
- PI4IOE5V6408 `0x43` controls the front-panel keys and RGB LED.

The test writes relay 1 through AW9523, verifies its output readback, enables
the red channel through PI4IOE, and injects AW9523 input bits so all eight
input channels read high.
