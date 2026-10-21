# Core2 v1.1 SPM1423 microphone probe

Records through the official `Mic` API, ESP32 I2S0 PDM RX and the legacy I2S
linked-list DMA engine. The host injects deterministic PCM into the real DMA
descriptors consumed by the UIFlow2 microphone driver.

The matrix does not inject touch after this probe. In the current QEMU Core2
backend that combination intermittently raises a cache error after Mic.end();
the microphone test has no input dependency and instead keeps the verified
frame static.
