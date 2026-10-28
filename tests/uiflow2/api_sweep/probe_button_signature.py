"""Inspect the actual frozen M5 button callback callable in this firmware."""
import json

import M5


def inspect_button(name):
    M5.begin()
    button = getattr(M5, name)
    method = button.setCallback
    row = {
        "button": name,
        "type": str(type(button)),
        "callable_type": str(type(method)),
        "doc": getattr(method, "__doc__", None),
        "dir": [item for item in dir(button) if not item.startswith("_")],
    }
    print("BUTTON_SIGNATURE " + json.dumps(row))
    print("BUTTON_SIGNATURE_DONE")
