# StopWatch firmware fixtures

Firmware binaries are intentionally not committed to this public repository.

Download the official UIFlow2 firmware into the ignored cache:

```bash
python3 platform/tools/fetch_firmware.py stopwatch
```

The resulting image is written to:

```text
platform/.cache/firmware/stopwatch/uiflow2.bin
```

The browser reference runtime can load it with:

```text
?fw=/platform/.cache/firmware/stopwatch/uiflow2.bin
```

You can also select any local merged ESP32-S3 image from the runtime's file
input. Official UserDemo or other third-party firmware must be obtained under
its own terms; it is not redistributed here.
