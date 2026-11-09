# PaperS3 and PaperDIY native QEMU validation

Validation ran on virtual devices through Device Service and the repository's
UIFlow2 matrix. Firmware, evidence archives and mutable Flash stay outside Git.
The [summary](summary.json) identifies inputs, firmware and runtime hashes,
serial markers, pixel oracles, panel scan counters and cleanup.

The PaperS3 factory case uses the published
[V0.5 release](https://github.com/m5stack/M5PaperS3-UserDemo/releases/tag/V0.5).
The PaperDIY V1.0 binary was built from
[M5PaperDIY-UserDemo at 71748ca](https://github.com/m5stack/M5PaperDIY-UserDemo/tree/71748ca831af4c67b18d63822fda45d1a2a1a739)
with [ESP-IDF v5.5.4](https://github.com/espressif/esp-idf/tree/v5.5.4),
`python fetch_repos.py` and `idf.py build`. The build regenerated dependency
lock metadata. The application source was unchanged. Merge the bootloader at
`0x0`, partition table at `0x8000` and application at `0x10000` with
`esptool.py --chip esp32s3 merge_bin --fill-flash-size 16MB`. The local build
hash records the image tested and includes its build timestamp.

PaperDIY's first start sends the M5PM1 shutdown command after its factory
sequence. To reproduce the next power-on UI, create a 0x6000-byte NVS partition
with the ESP-IDF generator and the following CSV. This overlay is used only by
the factory input case.

```csv
key,type,encoding,value
paperdiy,namespace,,
factory_done,data,u8,1
```

Build native QEMU with the layer list in `scripts/bootstrap-unit-runtime.py`
and start an isolated Device Service as described in [deployment](../../deployment.md).
Use its loopback API, service token file and separate output directories:

```sh
python3 tests/firmware/paper_runtime/run_test.py --api "$API" --token-file "$TOKEN_FILE" \
  --device papers3 --firmware "$PAPERS3_FACTORY" --output-dir .work/papers3-factory
python3 tests/firmware/paper_runtime/run_test.py --api "$API" --token-file "$TOKEN_FILE" \
  --device paperdiy --firmware "$PAPERDIY_FACTORY" --nvs-image "$PAPERDIY_NVS" \
  --output-dir .work/paperdiy-factory
python3 tests/uiflow2/run_device_matrix.py --device papers3 --device paperdiy \
  --flash-transport direct --out-dir .work/paper-uiflow-matrix
```

Factory interactions use GT911 touch on PaperS3 and independent A/B hold and
release on PaperDIY. The two stock UIFlow2 images reach the Code Information
screen. Stock UIFlow2 menu interaction was inconclusive. The same UIFlow2
builds composed with the checked-in probe have separate guest input and
framebuffer assertions.

The ET047TC1 model exposes a digital black-and-white scanout. Optical
waveforms and grayscale, PaperS3 buzzer audio and PMS150G power behavior,
mounted-card I/O, radio, external accessories and physical hardware were
outside this validation.
