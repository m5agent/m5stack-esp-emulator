"""CoreS3 native PMIC hold callbacks and FT6336 touch transition recipe.

The host must react to the READY markers through Device Service input APIs.
CoreS3 PMIC button events do not expose a continuous GPIO press level; generic
Button methods that need that level are not inferred from this event test.
"""

import json
import time
import M5


def input_emit(api, status, value=None, detail=None):
    row = {"api": api, "status": status, "value": value}
    if detail:
        row["detail"] = detail
    print("HARDWARE_API " + json.dumps(row))


def poll_button(milliseconds):
    seen = {}
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    names = ("isHolding", "isPressed", "isReleased", "wasClicked",
             "wasDoubleClicked", "wasHold", "wasPressed", "wasReleased",
             "wasSingleClicked", "wasChangePressed", "wasDeciedClickCount")
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        for name in names:
            value = getattr(M5.BtnPWR, name)()
            if value:
                seen[name] = value
        for name in ("lastChange", "getClickCount"):
            value = getattr(M5.BtnPWR, name)()
            if value:
                seen[name] = value
        time.sleep_ms(10)
    return seen


def run_inputs(include_touch=True):
    M5.begin()
    events = []
    button = M5.BtnPWR
    callback_type = button.CB_TYPE.WAS_HOLD
    button.setCallback(type=callback_type, cb=lambda state: events.append(state))
    try:
        print("HARDWARE_PWR_CALLBACK_READY")
        seen = poll_button(4500)
        input_emit("M5.BtnPWR.setCallback", "API_ASSERTION_PASS" if events else "FAIL", events,
                   "CoreS3 native PMIC hold-event callback observed after real same-session key:p input; key:p does not promise short-click semantics")
        for name, value in seen.items():
            input_emit("M5.BtnPWR." + name, "OBSERVED", value)
        input_emit("M5.BtnPWR.wasHold", "API_ASSERTION_PASS" if seen.get("wasHold") else "FAIL", seen.get("wasHold"))
        button.removeCallback(type=callback_type)
        previous = len(events)
        print("HARDWARE_PWR_REMOVED_READY")
        seen = poll_button(4500)
        input_emit("M5.BtnPWR.removeCallback", "API_ASSERTION_PASS" if seen.get("wasHold") and len(events) == previous else "FAIL", {"events_before": previous, "events_after": len(events), "new_hold_observed": bool(seen.get("wasHold"))})
    finally:
        button.removeCallback(type=callback_type)

    if not include_touch:
        print("HARDWARE_INPUT_DATAPLANE_DONE")
        return

    print("HARDWARE_TOUCH_ACTIVE_READY")
    deadline = time.ticks_add(time.ticks_ms(), 4500)
    recorded = False
    counts = []
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        count = M5.Touch.getCount()
        if not counts or counts[-1] != count:
            counts.append(count)
        if count and not recorded:
            x, y = M5.Touch.getX(), M5.Touch.getY()
            detail, raw = M5.Touch.getDetail(), M5.Touch.getTouchPointRaw()
            if len(detail) == 11 and detail[4]:
                input_emit("M5.Touch.getX", "API_ASSERTION_PASS" if x == 61 else "FAIL", x)
                input_emit("M5.Touch.getY", "API_ASSERTION_PASS" if y == 73 else "FAIL", y)
                input_emit("M5.Touch.getDetail", "API_ASSERTION_PASS", detail)
                input_emit("M5.Touch.getTouchPointRaw", "API_ASSERTION_PASS" if tuple(raw[:2]) == (61, 73) else "FAIL", raw)
                recorded = True
        time.sleep_ms(10)
    input_emit("M5.Touch.getCount", "API_ASSERTION_PASS" if recorded and 1 in counts and counts[-1] == 0 else "FAIL", counts,
               "Released -> active single touch -> released through FT6336 interrupt and I2C data plane")
    print("HARDWARE_INPUT_DATAPLANE_DONE")
