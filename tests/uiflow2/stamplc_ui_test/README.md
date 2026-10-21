# StamPLC UIFlow2 Local UI and Key Test

The test uses the existing local M5Stack UIFlow2 v2.5.3 StamPLC merged
image, renders a 240x135 industrial dashboard, and increments the counter
after the emulated front-panel A key changes PI4IOE register `0x0F`.

```bash
cp /path/to/stamplc-uiflow2-v2.5.3.bin /tmp/stamplc-base.bin
truncate -s 8388608 /tmp/stamplc-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/stamplc-base.bin --machine m5stamplc \
  --files-dir tests/uiflow2/stamplc_ui_test \
  --vfs-offset 0x651000 --vfs-size 0x1AE000 --flash-size 0x800000 \
  --expected-size 240x135 --input key:a --efuse-pkg-version 0
```
