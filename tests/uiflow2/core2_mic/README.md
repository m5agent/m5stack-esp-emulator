# Core2 v1.1 SPM1423 microphone probe

Records through the official `Mic` API, ESP32 I2S0 PDM RX and the legacy I2S
linked-list DMA engine. The host injects deterministic PCM into the real DMA
descriptors consumed by the UIFlow2 microphone driver.
