"""Validate semantic controls and send them through the native input data plane."""

import json
import math
from functools import lru_cache
from pathlib import Path

from device_service_encoder import (
    supports_rotary_encoder,
    validate_encoder_delta,
    validate_encoder_edge_period_ms,
)
from device_service_errors import ServiceError

INPUT_PROFILES = Path(__file__).resolve().parents[1] / "web/qemu-browser-profiles.json"
SEMANTIC_FIELDS = {
    "button": {"control", "action", "seconds"},
    "keyboard": {"key", "action", "seconds"},
    "chord": {"keys", "target", "seconds"},
    "encoder": {"delta", "edge_period_ms"},
    "touch": {"x", "y", "action", "seconds"},
}
SEMANTIC_INPUT_KINDS = SEMANTIC_FIELDS.keys() - {"touch"}
CLICK_SECONDS = 0.12
KEYBOARD_BOARDS = {"cardputer", "cardputer-adv"}
VIRTUAL_BUTTONS = {"a", "b", "c"}
NAVIGATION_KEYS = {
    "left": "comma", "down": "dot", "right": "slash", "up": "semicolon",
    "esc": "grave_accent", "delete": "backspace",
}


@lru_cache(maxsize=1)
def input_profiles():
    return {p["deviceId"]: p for p in json.loads(INPUT_PROFILES.read_text())["profiles"]}


def action_seconds(payload, name, default, minimum=0.001, maximum=5):
    value = payload.get(name, default)
    if (
        type(value) not in (int, float)
        or not minimum <= value <= maximum
    ):
        raise ServiceError("invalid_input", f"{name} must be between {minimum} and {maximum} seconds", 400)
    return float(value)


def unavailable(message):
    return ServiceError("unsupported_input", message, 409)


def control_name(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ServiceError("invalid_input", f"{field} must be a nonempty string", 400)
    return value.strip().lower()


def board_controls(spec):
    profile = input_profiles().get(spec.id)
    # Both AtomS3 LCD variants expose the same GPIO41 A button.
    if profile and (
        profile["board"] == spec.machine
        or (spec.id, spec.machine, profile["board"]) == ("atoms3", "m5atoms3-st7735", "m5atoms3")
    ):
        controls = profile["inputs"]
        if spec.id == "cardputer-adv":
            # The published browser build has a GPIO0 mapping absent from the
            # native ADV panel. Do not acknowledge an unwired control.
            return {**controls, "buttons": {}}
        return controls
    if spec.id == "nanoc6":
        return {"buttons": {"a": "gpio9", "button": "gpio9"}, "touch": False}
    return {}


def keyboard_code(spec, controls, key, *, in_chord=False):
    fn = "compose" if spec.id == "cardputer-adv" else "menu"
    aliases = {"fn": fn, "enter": "ret", "return": "ret", "space": "spc", "escape": "esc"}
    if spec.id == "cardputer-adv":
        aliases.update(shift_r="shift", ctrl_r="ctrl", meta_r="meta_l", alt_r="alt")
    key = aliases.get(key, key)
    if key in NAVIGATION_KEYS and spec.id in KEYBOARD_BOARDS:
        if in_chord:
            raise ServiceError("invalid_input", "chords require physical keys; use Fn with the physical key", 400)
        return [fn, NAVIGATION_KEYS[key]]
    if key not in controls.get("keyboard", ()):
        raise unavailable(f"keyboard key {key} has no model input on this board")
    return [key]


def normalize_semantic_input(session, payload, *, native):
    kind = payload["kind"]
    if not native or getattr(session, "management_binding", None):
        raise unavailable("semantic actions require an independent native QMP session")
    unknown = payload.keys() - SEMANTIC_FIELDS[kind] - {"kind", "settle_seconds"}
    if unknown:
        raise ServiceError("invalid_input", f"unexpected {kind} fields: {', '.join(sorted(unknown))}", 400)
    requested_action = payload.get("action", "click")
    settle = action_seconds(payload, "settle_seconds", 0.3, minimum=0)
    command = {"kind": kind, "action": requested_action, "settle_seconds": settle}
    if kind == "encoder":
        if not supports_rotary_encoder(session.spec, session.runtime):
            raise unavailable("encoder requires a native Dial session")
        command.update(action="rotate", delta=validate_encoder_delta(payload.get("delta")))
        if "edge_period_ms" in payload:
            command["edge_period_ms"] = validate_encoder_edge_period_ms(payload["edge_period_ms"])
        return command

    controls = board_controls(session.spec)
    if kind == "chord":
        keys = payload.get("keys")
        if not isinstance(keys, list) or not 2 <= len(keys) <= 4:
            raise ServiceError("invalid_input", "chord keys must be an array of 2 to 4 names", 400)
        target = payload.get("target", "keyboard" if session.spec.id in KEYBOARD_BOARDS else "button")
        if target not in ("button", "keyboard"):
            raise ServiceError("invalid_input", "chord target must be button or keyboard", 400)
        names = [control_name(key, "key") for key in keys]
        command["action"] = "hold"
        command["seconds"] = action_seconds(payload, "seconds", 0.45)
    else:
        target = kind
        field = "control" if kind == "button" else "key"
        names = [control_name(payload.get(field), field)] if kind != "touch" else []
        if requested_action not in ("click", "hold", "double_click"):
            raise ServiceError("invalid_input", "action must be click, hold or double_click", 400)
        if requested_action != "hold" and "seconds" in payload:
            raise ServiceError("invalid_input", "seconds requires action hold", 400)
        command["seconds"] = (
            action_seconds(payload, "seconds", 1, maximum=10 if kind == "button" else 5)
            if requested_action == "hold" else CLICK_SECONDS
        )

    if kind == "touch":
        if not controls.get("touch") or not session.spec.expected_size:
            raise unavailable("semantic touch requires a modeled touch panel")
        if not {"x", "y"} <= payload.keys():
            raise ServiceError("invalid_input", "touch requires x and y", 400)
        return command

    qcodes = []
    for name in names:
        if target == "keyboard":
            qcodes.extend(keyboard_code(session.spec, controls, name, in_chord=kind == "chord"))
        else:
            qcode = controls.get("buttons", {}).get(name)
            if qcode is None:
                raise unavailable(f"button {name} has no model input on this board")
            qcodes.append(qcode)
    if len(qcodes) != len(set(qcodes)):
        raise ServiceError("invalid_input", "chord keys must resolve to distinct physical controls", 400)
    if session.spec.id == "core2" and len(VIRTUAL_BUTTONS.intersection(qcodes)) > 1:
        raise unavailable("Core2 touch buttons share a single touch contact")
    return {**command, "target": target, "names": names, "qcodes": qcodes}


def key_events(keys, down):
    return [
        {"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": key}}}
        for key in keys
    ]


def require_full_adv_keyboard(session):
    properties = session._qmp_call("qom-list", path="/machine").get("return", [])
    if not any(row.get("name") == "keyboard-full-map" for row in properties):
        raise unavailable("Cardputer-ADV native runtime has no full keyboard map")
    enabled = session._qmp_call("qom-get", path="/machine", property="keyboard-full-map")
    if enabled.get("return") is not True:
        raise unavailable("Cardputer-ADV native runtime has no full keyboard map")


def send_semantic_input(session, command, pointer_events):
    """Dispatch validated controls; the session owns locking and audit events."""
    kind, action, seconds = command["kind"], command["action"], command["seconds"]
    qcodes = command.get("qcodes", ())
    if session.spec.id == "cardputer-adv" and command.get("target") == "keyboard":
        require_full_adv_keyboard(session)
    repetitions = 2 if action == "double_click" else 1
    qmp = session._qmp_call

    queue_single_key = kind != "touch" and len(qcodes) == 1 and qcodes[0] != "gpio9"
    if queue_single_key and kind == "button" and session.spec.id == "sticks3":
        # The virtual key queue cannot drain while the guest is suspended.
        status = (qmp("query-status").get("return") or {}).get("status")
        queue_single_key = status != "suspended"
    if queue_single_key:
        hold_ms = math.ceil(seconds * 1000)
        for _ in range(repetitions):
            qmp("send-key", keys=[{"type": "qcode", "data": qcodes[0]}],
                **{"hold-time": hold_ms})
        return {"clock": "virtual", "hold_seconds": seconds, "hold_time_ms": hold_ms,
                "presses": repetitions, "completion": "queued"}

    def send_edge(down):
        if kind == "touch":
            events = pointer_events(command["x"], command["y"], session.spec.expected_size, down)
        elif qcodes == ["gpio9"]:
            qmp("qom-set", path="/machine", property="button-gpio9", value=down)
            return
        else:
            events = key_events(qcodes if down else reversed(qcodes), down)
        qmp("input-send-event", events=events)

    for index in range(repetitions):
        if index:
            session._stop_event.wait(CLICK_SECONDS)
        session._check_cancelled()
        try:
            send_edge(True)
            session._stop_event.wait(seconds)
        except BaseException:
            # A timed-out write may have reached the controller. Attempt the
            # corresponding release even when we did not receive its reply.
            try:
                send_edge(False)
            except ServiceError:
                pass
            raise
        else:
            send_edge(False)
        session._check_cancelled()
    return {"clock": "host", "hold_seconds": seconds, "presses": repetitions,
            "completion": "events_sent"}
