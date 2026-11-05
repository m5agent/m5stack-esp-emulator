# PaperColor UIFlow2 Local UI and Key Test

```bash
cp platform/.cache/firmware/papercolor/uiflow2.bin /tmp/papercolor-base.bin
truncate -s 16777216 /tmp/papercolor-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/papercolor-base.bin --machine m5papercolor \
  --files-dir tests/uiflow2/papercolor_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 400x600 --input key:a --efuse-pkg-version 0 \
  --wait 10
```

The official image can route Python output to USB CDC. The checked-in `boot.py`
attaches the original guest program to the real UART0 controller with
`machine.UART(0)`, `os.dupterm` and RX notification. This is UART observability,
not USB CDC coverage. Missing UART output alone does not establish a pre-REPL
hang: require the same-run markers, button event and post-input pixel oracle.
