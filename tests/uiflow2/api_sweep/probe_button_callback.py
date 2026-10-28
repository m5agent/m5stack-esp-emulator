"""Observe one board-native M5 button callback after a real host input."""
import json
import time

import M5


def run_button_callback(button_name, event_name="WAS_HOLD", milliseconds=4000):
    M5.begin()
    button = getattr(M5, button_name)
    callback_type = getattr(button.CB_TYPE, event_name)
    events = []
    result = {
        "api": "M5." + button_name + ".setCallback." + event_name,
        "status": "FAIL",
        "events": events,
    }
    try:
        button.setCallback(callback_type, lambda state: events.append(state))
        print("BUTTON_CALLBACK_READY")
        deadline = time.ticks_add(time.ticks_ms(), milliseconds)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            M5.update()
            time.sleep_ms(10)
        result["status"] = "API_ASSERTION_PASS" if events else "FAIL"
        button.removeCallback(callback_type)
        previous = len(events)
        print("BUTTON_CALLBACK_REMOVED_READY")
        deadline = time.ticks_add(time.ticks_ms(), milliseconds)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            M5.update()
            time.sleep_ms(10)
        result["remove"] = {
            "status": "API_ASSERTION_PASS"
            if len(events) == previous and not events[previous:]
            else "FAIL",
            "events_before": previous,
            "events_after": len(events),
        }
    except Exception as error:
        result["error"] = repr(error)
    print("HARDWARE_API " + json.dumps(result))
    print("BUTTON_CALLBACK_DONE")
