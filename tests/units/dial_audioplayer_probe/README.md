# Dial Unit AudioPlayer

The native Device Service mounts AudioPlayer U197 on Dial PORT.B
(white RX G1, yellow TX G2) or PORT.A (white RX G15, yellow TX G13).
Mount one indexed virtual directory with `media-track-count` at session
creation. Zero tracks gives a silent UART media path. The field is immutable
for the life of the session.

The guest's hardware UART drives the GPIO matrix output. The N9301 model
validates the complemented command, length and checksum, updates state, and
replies via the mapped controller receive FIFO. It covers the documented
media/track query, indexed track selection, playback state, and volume and
mode commands. Unsupported commands, names and playback time are outside
this model. Unit microSD FAT/physical behavior and actual MP3/WAV decoding,
audio output and electrical signaling remain unmodeled.

## Reproduction

Build the native Xtensa Unit runtime through patch 0218. Start a dedicated
loopback Device Service using that QEMU, matching ROMs, a private state
directory and a control token, as in the [Unit test guide](../README.md).
Set `M5_UNIT_EXPECT_RUNTIME_SHA256` to the expected binary SHA-256.

Pass the unmodified [official UIFlow2 AudioPlayer driver](https://github.com/m5stack/uiflow-micropython/blob/7ec5c5ead5d3e210bda907e5470490f98f028a4b/m5stack/libs/unit/audioplayer.py)
and the matching Dial UIFlow2 base firmware:

```sh
PYTHONPATH=platform/tools:.work/py python3.13 tests/units/run_dial_audioplayer.py \
  --api-url http://127.0.0.1:8941 --token-file <private-token-file> \
  --base-firmware <dial-uiflow2-merged-bin> --driver <official-audioplayer.py> \
  --out-dir .work/dial-audioplayer
```

Use separate output directories for `--port port-a` and `--tracks 0`.
The driver evidence covers framed commands through both sets of physical
board pins. The zero-media control requires two validated commands and
zero replies. Invalid checksum, oversized length and fragment timeout each
leave playback stopped. An invalid track index returns the documented file
error. Play, pause, resume, stop, selection and settings use actual guest
requests and replies.

For the immutable vinylM5Dial 1.0 original, replace `--base-firmware … --driver …`
with `--original-bin <saved-original-bin>`. The runner verifies the original
SHA and waits for track 1 to play. It requires the original indexed UART
play commands after the default 35 ms rotation in both directions,
including full 16-detent turns. It then checks center pause and
resume, upper and lower volume controls, dial press to stop and play, and
a nonblank application frame. The same session retains the Unit data plane,
runtime provenance and an evidence ZIP before stop. The indexed media fixture
does not provide physical audio or a multi-folder filesystem.

The [fast 5 ms follow-up](../../../docs/evidence/2026-11-17-dial-gc9a01-gpio-probe/README.md) retains an original-guest missed selection with all 64 GPIO edges delivered.
