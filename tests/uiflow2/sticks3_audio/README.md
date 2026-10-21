# StickS3 speaker PCM probe

Uses the official `Speaker` API to start ES8311 playback, emits a deterministic
PCM tone through I2S/GDMA, and records whether the UIFlow2 speaker remains
running.

The host-side PCM capture is enabled with:

```bash
M5SW_I2S_PCM_FILE=/tmp/sticks3-speaker.pcm
```
