# StackChan UIFlow2 Local UI and Touch Test

The test replaces the user LittleFS files in the official StackChan
UIFlow2 v2.5.3 image and verifies a 320x240 frame plus touch input.

```bash
cp platform/.cache/firmware/stackchan/uiflow2.bin /tmp/stackchan-base.bin
truncate -s 16777216 /tmp/stackchan-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/stackchan-base.bin --machine m5stackchan \
  --files-dir tests/uiflow2/stackchan_ui_test \
  --vfs-offset 0xAA0000 --vfs-size 0x4C0000 --flash-size 0x1000000 \
  --expected-size 320x240 --input touch:160,183 --efuse-pkg-version 0
```
