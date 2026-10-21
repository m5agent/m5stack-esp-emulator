# StopWatch UIFlow2 local UI test

This test runs a normal UIFlow2 `main.py` from the StopWatch `vfs` LittleFS
partition in the QEMU `m5stopwatch` machine.  It proves the path:

```
ROM -> UIFlow2 runtime -> /flash/main.py -> M5.Display -> touch input
```

The script draws a button and counts a touch press.  A successful run produces
`touches: 0` before the tap and `touches: 1` / `BUTTON OK count=1` after it.
The QEMU console applies the StopWatch round-panel mask, so the screenshots
show a circular visible area; the CO5300 framebuffer itself remains 466x466.

## Run

```bash
python3 -m pip install littlefs-python
python3 tests/uiflow2/stopwatch_ui_test/run_test.py \
  --base /path/to/UIFlow2-StopWatch-v2.5.3-16MiB.bin
```

The base image must be the official merged image padded to exactly 16 MiB.
The test only replaces `boot.py` and `main.py` inside the `vfs` LittleFS
partition at `0x820000` (size `0x7DF000`); the bootloader, application and
system partition remain unchanged.

Outputs:

- `uiflow2-ui-test.bin`
- `before.ppm`
- `after.ppm`
- `serial.log`

## Expected result

`run_test.py` returns `PASS` and prints the generated image and screenshot
paths.  The before/after screenshots differ because the tap increments the
counter and draws a green dot at the touch position.

## Boundary

This is a local user-filesystem test, not a Wi-Fi/cloud or M5Burner flash
test.  It does not validate UIFlow2 networking, M5Things binding, or REPL
input.
