# PaperMono PDM microphone probe

Records from the built-in PDM microphone through the official `Mic` API. QEMU
injects deterministic PCM into I2S RX/GDMA with `M5SW_I2S_RX_PCM_FILE`.
