# CoreS3 MAX3421E USB HID probe

The CoreS3 M-Bus carries a MAX3421E USB host controller on SPI CS0 with
IRQ on GPIO14. This probe uses the official UIFlow2 `module.USBModule` and
enumerates a virtual HID mouse through the MAX3421E register/FIFO path.

The QEMU model must enumerate the USB device, fetch its configuration and
HID report descriptor, configure endpoint 1, and return the injected
`mouse=(5,-3)`, left-button report. A timeout, API-only shortcut, or a fake
Python-side report is a failure.
