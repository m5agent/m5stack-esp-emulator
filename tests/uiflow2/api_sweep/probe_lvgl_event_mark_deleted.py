"""Match only owned targets in the real nested native LVGL event stack."""
import json
import lvgl as lv


def emit(method, ok, **details):
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl", method=method,
          status="STATE_PASS" if ok else "FAIL", **details)))


target, unrelated = bytearray(b"OWNED"), bytearray(b"OTHER")
matched = lv.event_t({"original_target": target})
other = lv.event_t({"original_target": unrelated})
matched.push()
other.push()
try:
    lv.event_mark_deleted(target)
    emit("event_mark_deleted", bool(matched.deleted) and not other.deleted,
         oracle="native stack traversal marks the matching older event and preserves the unrelated stack head",
         matched_deleted=bool(matched.deleted), unrelated_deleted=bool(other.deleted))
finally:
    other.pop()
    matched.pop()
print("M5EMU_UI_READY")
