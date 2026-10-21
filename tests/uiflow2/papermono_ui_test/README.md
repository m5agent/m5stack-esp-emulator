# PaperMono UIFlow2 Local UI and Touch Test

```bash
cp platform/.cache/firmware/papermono/uiflow2.bin /tmp/papermono-base.bin
truncate -s 16777216 /tmp/papermono-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/papermono-base.bin --machine m5papermono \
  --files-dir tests/uiflow2/papermono_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 480x800 --input touch:240,650 --efuse-pkg-version 0 \
  --wait 10
```
