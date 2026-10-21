# CoreS3 audio fidelity probe

Feeds a deterministic signed 16-bit mono square wave to the official
`Speaker.playRaw()` API:

- sample rate: 48 kHz;
- frequency: 1 kHz;
- duration: 200 ms;
- amplitude: 8192.

The host can compare the captured I2S PCM against the original square-wave
pattern. A non-silent PCM check alone is insufficient because it cannot detect
duplicated chunks, wrong sample rate, byte order or corrupted waveform.

Run:

```bash
M5SW_I2S_DMA_IRQ=1 \
M5SW_I2S_PCM_FILE=/tmp/m5-cores3-audio-fidelity/live.pcm \
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/cores3/uiflow2.bin \
  --machine m5cores3 \
  --files-dir tests/uiflow2/cores3_audio_fidelity \
  --vfs-offset 0xAA0000 --vfs-size 0x4C0000 --flash-size 0x1000000 \
  --expected-size 320x240 --input key:a --wait 8 \
  --post-input-wait 1 --allow-static-frame \
  --out-dir /tmp/m5-cores3-audio-fidelity

python3 tests/uiflow2/check_pcm_square.py \
  /tmp/m5-cores3-audio-fidelity/live.pcm \
  --sample-rate 48000 --frequency 1000 --duration-ms 200
```

The expected result is approximately 400 sign transitions.
