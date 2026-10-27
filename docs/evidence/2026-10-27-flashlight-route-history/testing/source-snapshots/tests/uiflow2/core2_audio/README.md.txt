# Core2 v1.1 NS4168 speaker probe

Uses the official `Speaker` API with Core2 v1.1's ESP32 I2S1 controller and
NS4168 amplifier. The host captures PCM from the firmware-populated I2S DMA
descriptors and requires the AXP2101 ALDO3 speaker rail to be enabled.
