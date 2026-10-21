# StickS3 microphone PCM probe

Uses the official `Mic` API with ES8311 and I2S RX/GDMA. The host injects a
deterministic PCM stream through `M5SW_I2S_RX_PCM_FILE`; the probe checks that
the recorded buffer contains non-silent audio.
