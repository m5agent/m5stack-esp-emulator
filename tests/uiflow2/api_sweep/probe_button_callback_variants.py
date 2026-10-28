"""Separate argument parsing failures from real button event delivery."""
import json

import M5


def emit(payload):
    print("BUTTON_VARIANT " + json.dumps(payload))


M5.begin()
for owner in ("BtnA", "BtnB", "BtnPWR"):
    button = getattr(M5, owner, None)
    if button is None:
        continue
    callback_type = button.CB_TYPE.WAS_HOLD
    callback = lambda state: None
    variants = (
        ("positional", lambda: button.setCallback(callback_type, callback), lambda: button.removeCallback(callback_type)),
        ("keyword-both", lambda: button.setCallback(type=callback_type, cb=callback), lambda: button.removeCallback(type=callback_type)),
        ("keyword-cb", lambda: button.setCallback(callback_type, cb=callback), lambda: button.removeCallback(callback_type)),
        ("star-positional", lambda: button.setCallback(*[callback_type, callback]), lambda: button.removeCallback(*[callback_type])),
        ("none-positional", lambda: button.setCallback(callback_type, None), lambda: button.removeCallback(callback_type)),
    )
    for name, attach, remove in variants:
        row = {"button": owner, "variant": name, "status": "PASS"}
        try:
            attach()
        except Exception as error:
            row["status"] = "FAIL"
            row["attach_error"] = repr(error)
        else:
            try:
                remove()
            except Exception as error:
                row["status"] = "FAIL"
                row["remove_error"] = repr(error)
        emit(row)
print("BUTTON_VARIANTS_DONE")
