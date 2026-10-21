# Cardputer-ADV UIFlow2 Local UI and Keyboard Test

The test loads the official UIFlow2 v2.5.3 Cardputer-ADV image, replaces
the user LittleFS files, renders a 240x135 dashboard, and increments the
counter after an injected TCA8418 keyboard event.

```bash
cp platform/.cache/firmware/cardputer-adv/uiflow2.bin /tmp/cardputer-adv-base.bin
truncate -s 8388608 /tmp/cardputer-adv-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/cardputer-adv-base.bin --machine m5cardputeradv \
  --files-dir tests/uiflow2/cardputer_adv_ui_test \
  --vfs-offset 0x641000 --vfs-size 0x1BE000 --flash-size 0x800000 \
  --expected-size 240x135 --input key:a --efuse-pkg-version 0
```
