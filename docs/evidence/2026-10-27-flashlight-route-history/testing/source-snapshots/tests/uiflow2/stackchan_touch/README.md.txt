# StackChan Si12T body-touch probe

Uses the official UIFlow2 `driver.si12t.Si12T` driver over the StackChan body
I2C bus. QEMU injects `touch-bits` through QOM; the app must report the three
decoded touch points and draw a green success marker.
