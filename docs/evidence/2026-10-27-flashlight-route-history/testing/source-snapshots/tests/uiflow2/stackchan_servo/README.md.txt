# StackChan SCS servo probe

Uses the official `driver.scs_servo.Scscl` protocol over UART1 (TX GPIO6,
RX GPIO7) to verify both StackChan servo IDs:

- PING/ACK;
- torque enable;
- position write;
- present-position readback.

The expected UI result is `status=ok` with a green marker.
