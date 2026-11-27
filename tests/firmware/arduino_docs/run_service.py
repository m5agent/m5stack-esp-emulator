#!/usr/bin/env python3
"""Replay firmware documentation cases on two isolated Device Service runtimes."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform" / "tools"))
from user_firmware_matrix import HttpError, MatrixError, request_bytes, request_json


RUNTIMES = ("qemu", "esp32sim")
FATAL = re.compile(
    r"Guru Meditation|panic'ed|Interrupt wdt timeout|assert failed|Backtrace:|"
    r"stack smashing|Traceback \(most recent call last\)", re.IGNORECASE,
)


class OracleFailure(ValueError):
    """An observed result contradicted the paired case predicate."""


class Service:
    def __init__(self, url, token):
        self.base = url.rstrip("/") + "/api/v1/"
        self.headers = {"Authorization": f"Bearer {token}"}

    def json(self, path, *, method="GET", payload=None):
        return request_json(self.base + path, method=method, payload=payload, headers=self.headers)

    def download(self, path):
        data, _ = request_bytes(self.base + path, headers=self.headers)
        return data

    def register(self, device, path):
        data = path.read_bytes()
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError("firmware file is a Git LFS pointer")
        digest = sha256(data).hexdigest()
        artifact = request_json(
            self.base + "artifacts", method="POST", body=data, timeout=180,
            headers=self.headers | {"X-Artifact-Name": path.name, "Content-Type": "application/octet-stream"},
        )
        if artifact["sha256"] != digest:
            raise ValueError("uploaded bytes differ from the local image")
        firmware = self.json("firmware", method="POST", payload={
            "device_id": device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        return firmware["firmware_id"], digest


def error_code(error):
    return error.payload.get("error", {}).get("code") if isinstance(error.payload, dict) else None


def read_frame(service, route, path, geometry):
    data = service.download(route + "/frame.png?max_age_ms=0")
    path.write_bytes(data)
    with Image.open(BytesIO(data)) as png:
        image = png.convert("RGB")
    if image.size != geometry:
        raise OracleFailure(f"expected panel geometry {geometry}, observed {image.size}")
    return image


def changed(first, second):
    left, right = first.tobytes(), second.tobytes()
    return sum(left[i:i + 3] != right[i:i + 3] for i in range(0, len(left), 3))


def cores3_shapes(frame):
    colors = frame.getcolors(frame.width * frame.height)
    return len(colors) > 100 and max(count for count, _ in colors) <= 44 * 44


def cores3_bars(frame):
    bottom = {rgb: count for count, rgb in frame.crop((0, 239, 320, 240)).getcolors(320)}
    colors = {rgb: count for count, rgb in frame.getcolors(frame.width * frame.height)}
    return bottom.get((0, 0, 0)) == 64 and len(bottom) > 55 and colors.get((255, 255, 255), 0) > 350


def minimum_colors(count):
    return lambda frame: frame.getcolors(count - 1) is None


def classic_shapes(frame):
    colors = {rgb: count for count, rgb in frame.getcolors(frame.width * frame.height)}
    return len(colors) >= 3 and colors.get((255, 255, 255), 0) > 50_000


def stick_drawing(frame, minimum_palette):
    colors = frame.getcolors(frame.width * frame.height)
    return len(colors) >= minimum_palette and any(count == 400 for count, _ in colors)


def stick_scroll(frame):
    colors = {rgb: count for count, rgb in frame.getcolors(frame.width * frame.height)}
    bounds = frame.getbbox()
    if len(colors) != 9 or bounds is None:
        return False
    left, top, right, bottom = bounds
    lit = frame.width * frame.height - colors.get((0, 0, 0), 0)
    return bottom - top == 240 and right - left > 116 and 1400 <= lit <= 2600


def stick_hello(frame):
    colors = {rgb: count for count, rgb in frame.getcolors(frame.width * frame.height)}
    lit = frame.width * frame.height - colors.get((0, 0, 0), 0)
    return len(colors) == 2 and 98 <= lit <= 135 and frame.getbbox() == (0, 0, 65, 7)


def stick_display_step(frame, step):
    colors = {rgb: count for count, rgb in frame.getcolors(frame.width * frame.height)}
    bounds = frame.getbbox()
    if bounds is None:
        return False
    lit = frame.width * frame.height - colors.get((0, 0, 0), 0)
    if step == 1:
        return len(colors) == 1 and next(iter(colors))[:2] == (0, 0)
    if step == 2:
        return (lit == 1056 and bounds == (0, 0, 132, 8)
                and colors.get((255, 0, 0)) == 238 and colors.get((255, 255, 255)) == 818)
    if step in (3, 4):
        count, expected = {3: (103, (0, 0, 59, 8)), 4: (169, (5, 20, 60, 67))}[step]
        return colors.get((255, 255, 255)) == count and bounds == expected
    left, top, right, bottom = bounds
    size = tuple(sorted((right - left, bottom - top)))
    low, high, expected = {
        5: (1, 1, (1, 1)), 6: (13, 13, (13, 13)),
        7: (100, 220, (48, 77)), 8: (1000, 1200, (48, 77)),
        9: (76, 76, (10, 30)), 10: (200, 200, (10, 20)), 11: (150, 199, (10, 20)),
    }[step]
    return size == expected and low <= lit <= high


# Frame predicates and thresholds from the fork's CoreS3 and S3-B checkers.
# Keep the prerequisites explicit where a service lacks a controller observation.
ANIMATION = {
    ("cores3", "display"): ((320, 240), cores3_shapes, 20_001),
    ("cores3", "quickstart-bargraph"): ((320, 240), cores3_bars, 2_501),
    ("basic-v27", "quickstart-longtextscroll"): ((320, 240), minimum_colors(2), 20),
    ("core2", "quickstart-scrollgraph"): ((320, 240), minimum_colors(2), 20),
    ("stickc-plus-se", "display"): ((135, 240), lambda frame: stick_drawing(frame, 3), 1),
    ("stickc-plus-se", "quickstart-scrollgraph"): ((135, 240), stick_scroll, 1),
    ("stickc-plus2", "display"): ((135, 240), lambda frame: stick_drawing(frame, 21), 1),
    ("stickc-plus2", "quickstart-display"): ((135, 240), lambda frame: stick_drawing(frame, 21), 1),
    **{
        (device, case): (size, minimum_colors(4 if case == "display" else 8), 150)
        for device, size, quickstart in (
            ("cardputer", (240, 135), "quickstart-display"),
            ("dial", (240, 240), "quickstart-display"),
            ("sticks3", (135, 240), "quickstart-scrollgraph"),
            ("stopwatch", (466, 466), "quickstart-bargraph"),
        )
        for case in ("display", quickstart)
    },
}
STATIC = {
    ("basic-v27", "display"): ((320, 240), classic_shapes),
    ("core2", "display"): ((320, 240), classic_shapes),
    ("stackchan", "display"): ((320, 240), minimum_colors(101)),
    ("stamplc", "quickstart-display"): ((240, 135), minimum_colors(3)),
    ("stickc", "quickstart-helloworld"): ((80, 160), stick_hello),
    **{(device, case): ((128, 128), minimum_colors(3)) for device, case in (
        ("atoms3", "display"), ("atoms3", "quickstart-display"),
        ("atoms3r", "display"), ("atoms3r", "quickstart-bargraph"),
    )},
    **{("stickc-plus", f"display-{step}"): (
        (135, 240), lambda frame, step=step: stick_display_step(frame, step),
    ) for step in range(1, 12)},
}
PAPER = {
    ("papercolor", "display"): (400, 600),
    ("paperdiy", "display-1"): (540, 960),
    ("papermono", "display-1"): (480, 800),
}
CLASSIC_ATOMS = {"atom-lite", "atom-matrix", "atom-matrix-v11"}
CLASSIC_ATOM_CASES = {(device, case) for device in CLASSIC_ATOMS
                      for case in ("button", "imu", "rgb", "quickstart-logoutput")}
CASES = ANIMATION.keys() | STATIC.keys() | PAPER.keys() | {
    ("cores3", "button"), ("cores3", "power"), ("cores3", "imu"), ("cores3", "ltr553"),
    ("dial", "encoder"),
} | CLASSIC_ATOM_CASES


def frames(service, route, out, deadline, size, label="frame"):
    samples = 0
    while time.monotonic() < deadline:
        try:
            image = read_frame(service, route, out / f"{label}-{samples:03}.png", size)
        except HttpError as error:
            if error_code(error) != "frame_unavailable":
                raise
        else:
            samples += 1
            yield image
        time.sleep(0.5)


def observe_animation(service, route, out, deadline, oracle):
    size, predicate, minimum = oracle
    reference = None
    best = samples = 0
    for image in frames(service, route, out, deadline, size):
        samples += 1
        if predicate(image):
            if reference is None:
                reference = image
            else:
                best = max(best, changed(reference, image))
                if best >= minimum:
                    break
    return {
        "frame_predicates_pass": best >= minimum,
        "samples": samples,
        "changed_pixels": best,
        "required_changed_pixels": minimum,
        "size": size,
    }


def observe_paper(service, route, out, deadline, case):
    started = time.monotonic()
    white_at = None
    details = {}
    complete = False
    for image in frames(service, route, out, deadline, PAPER[case]):
        colors = image.getcolors(image.width * image.height)
        if len(colors) == 1 and colors[0][1] == (255, 255, 255):
            if white_at is None:
                white_at = time.monotonic() - started
            continue
        device, _ = case
        details = {"colors": len(colors)}
        if device == "papercolor":
            complete = len(colors) == 6
        elif device == "papermono":
            complete = len(colors) == 4 and all(max(rgb) - min(rgb) <= 3 for _, rgb in colors)
        else:
            shades = [image.getpixel((x, 395))[0] for x in (145, 223, 297, 375)]
            details["swatches"] = shades
            complete = shades[0] < shades[1] < shades[2] and shades[3] == shades[0]
        if complete and white_at is not None:
            break
    return {
        **details, "frame_predicates_pass": complete and white_at is not None,
        "white_frame_wall_seconds": white_at,
        "confirmed_refresh_wall_seconds": time.monotonic() - started if complete else None,
    }


def observe_cores3_button(service, route, out, deadline):
    def fingerprint(frame, box):
        return sha256(frame.crop(box).tobytes()).hexdigest()[:24]

    def has_title(frame):
        return fingerprint(frame, (25, 0, 295, 30)) == "c4a38b120d47ced5d52ee13c"

    indicator = (85, 75, 235, 108)
    size = (320, 240)
    before = next((image for image in frames(service, route, out, deadline, size, "idle")
                   if has_title(image) and not image.crop(indicator).getbbox()), None)
    if before is None:
        return {"frame_predicates_pass": False, "idle_screen": False}
    payload = {"kind": "button", "control": "power", "action": "hold", "seconds": 0.25}
    service.json(route + "/input", method="POST", payload=payload)
    observed = any(has_title(image) and fingerprint(image, indicator) == "41f349b8c87d6799dcadc65e"
                   for image in frames(service, route, out, deadline, size, "pressed"))
    return {"frame_predicates_pass": observed, "idle_screen": True, "input": payload}


def observe_dial_encoder(service, route, out, deadline):
    size = (240, 240)
    frame = next((image for image in frames(service, route, out, deadline, size, "idle")
                  if image.getcolors(1) is None), None)
    if frame is None:
        return {"frame_predicates_pass": False, "idle_screen": False}
    observations = []
    for delta in (4, -2):
        payload = {"kind": "encoder", "delta": delta, "edge_period_ms": 20, "settle_seconds": 1}
        receipt = service.json(route + "/input", method="POST", payload=payload)
        controller = receipt.get("controller")
        delivery = None
        if controller:
            target = controller["target_detents"]
            edges = controller["previous_gpio_edges"] + 4 * abs(delta)
            while time.monotonic() < deadline:
                state = service.json(route + "/device-state")["components"]["encoder"]["properties"]
                delivery = state
                if (state["delivered-detents"] == target and state["gpio-edges"] == edges
                        and not state.get("busy")):
                    break
                time.sleep(0.25)
            else:
                observations.append({"input": payload, "controller": controller, "delivery": delivery})
                return {"frame_predicates_pass": False, "idle_screen": True, "steps": observations}
        previous = frame
        frame = next((image for image in frames(service, route, out, deadline, size, f"delta-{delta}")
                      if image.getcolors(1) is None and changed(previous, image) >= 15), None)
        observations.append({
            "input": payload,
            "changed_pixels": changed(previous, frame) if frame is not None else 0,
            "controller": controller,
            "delivery": delivery,
        })
        if frame is None:
            break
    return {"frame_predicates_pass": frame is not None, "idle_screen": True, "steps": observations}


def set_properties(service, route, path, properties):
    for prop, value in properties.items():
        service.json(route + "/qom", method="POST", payload={
            "path": path, "property": prop, "value": value,
        })


def observe_cores3_power(service, route, out, deadline, runtime):
    digests = (
        ("f83e71bb2ade05b54cb74d90", "93d433c5af778794b4162220", "bb3d061653d6a42cb33e8ddc", "ce2226aaf0b274dfd02ccadb"),
        ("d7a1fc59369cf9ece5b018ec", "f7ae615f67944bd91195cf68", "9fa0d54e0c4a58da2ca17251", "4ceee824322d265b87dda6c5"),
    )
    steps = []
    for index, (mv, percent, charging, vbus_mv) in enumerate(((4123, 87, True, 5000), (3678, 42, False, 0))):
        requested = {"mv": mv, "percent": percent, "charging": charging, "vbus_mv": vbus_mv}
        if runtime == "esp32sim":
            service.json(route + "/input", method="POST", payload={
                "kind": "battery", "mv": mv, "percent": percent, "charging": charging, "vbus": bool(vbus_mv),
            })
        else:
            set_properties(service, route, "/machine/axp2101", {
                "vbat-mv": mv, "battery-level": percent, "vin-mv": vbus_mv, "charging": charging,
            })
        observed = ()
        for frame in frames(service, route, out, deadline, (320, 240), f"battery-{index}"):
            observed = tuple(sha256(frame.crop((10, y, 260, y + 20)).tobytes()).hexdigest()[:24]
                             for y in range(30, 110, 20))
            if observed == digests[index]:
                break
        steps.append({"battery": requested, "display_regions": observed, "matched": observed == digests[index]})
        if not steps[-1]["matched"]:
            break
    return {"frame_predicates_pass": len(steps) == 2 and all(step["matched"] for step in steps), "steps": steps}


def observe_cores3_sensor(service, route, out, deadline, case, runtime):
    if case == "imu":
        box = (0, 20, 170, 198)
        variants = (
            ({"accel": [0.5, -0.25, 0.75], "gyro": [125, -250, 62.5], "mag": [20, -10, 30]},
             "99ee1de8968435d2c82d0617"),
            ({"accel": [-0.375, 0.625, -1], "gyro": [-375, 500, -125], "mag": [-12.5, 33, -15]},
             "2d18f7a0bc9baa5f29142146"),
        )
        initialized = any(
            frame.crop((0, 182, 160, 198)).getbbox() is not None
            for frame in frames(service, route, out, deadline, (320, 240), "imu-initialized")
        )
        if not initialized:
            raise OracleFailure("the sketch did not finish its first nine-axis screen")
    else:
        box = (25, 106, 290, 133)
        variants = (
            ({"ch0": 400, "ch1": 120, "proximity": 321}, "d81b684af029a96628ec684a"),
            ({"ch0": 2000, "ch1": 880, "proximity": 1456}, "96a270409805a3f5c5097c32"),
        )
    steps = []
    for index, (sample, expected) in enumerate(variants):
        applied = sample
        if runtime == "esp32sim":
            service.json(route + "/input", method="POST", payload={
                "kind": "imu" if case == "imu" else "als", **sample,
            })
        elif case == "imu":
            props = {f"{group}-{axis}": value for group in ("accel", "gyro")
                     for axis, value in zip("xyz", sample[group])}
            set_properties(service, route, "/machine/bmi270", props)
            set_properties(service, route, "/machine/bmm150", dict(zip(("mag-x", "mag-y", "mag-z"), sample["mag"])))
        else:
            # QEMU returns the same raw sample for both ALS channels.
            applied = {"light-level": (sample["ch0"] + sample["ch1"]) // 2,
                       "proximity-level": sample["proximity"]}
            set_properties(service, route, "/machine/ltr553", applied)
        observed = None
        for frame in frames(service, route, out, min(deadline, time.monotonic() + 22), (320, 240), f"{case}-{index}"):
            observed = sha256(frame.crop(box).tobytes()).hexdigest()[:24]
            if observed == expected:
                break
        steps.append({"sample": sample, "applied": applied, "region_digest": observed,
                      "expected_region_digest": expected, "matched": observed == expected})
    return {"frame_predicates_pass": all(step["matched"] for step in steps), "steps": steps}


def console(service, route):
    return service.json(route + "/serial?channel=console&limit=65536")["data"]


def serial_until(service, route, deadline, predicate):
    while time.monotonic() < deadline:
        data = console(service, route)
        if predicate(data):
            return data
        time.sleep(0.2)
    return console(service, route)


def observe_classic_atom_button(service, route, deadline):
    serial_until(service, route, deadline, lambda text: "entry " in text)
    time.sleep(2.5)
    idle = "BtnA was pressed" not in console(service, route)
    for count, hold in enumerate((0.15, 1.25), start=1):
        service.json(route + "/input", method="POST", payload={
            "kind": "key", "key": "a", "hold_seconds": hold, "settle_seconds": 0.1,
        })
        data = serial_until(service, route, min(deadline, time.monotonic() + 7),
                            lambda data: data.count("BtnA was released") >= count)
    observations = {event: data.count(f"BtnA was {event}") for event in ("pressed", "released", "held")}
    return {"service_predicates_pass": idle and observations == {"pressed": 2, "released": 2, "held": 1},
            "idle_control": idle, "guest_events": observations}


def observe_classic_atom_rgb(service, route, deadline, device):
    leds = 1 if device == "atom-lite" else 25
    expected = {0xff0000, 0x00ff00, 0x0000ff}
    seen = set()
    while time.monotonic() < deadline and seen != expected:
        io = service.json(route + "/device-state")["components"]["onboard-io"]["properties"]
        values = io["led-rgb"] if isinstance(io["led-rgb"], list) else [io["led-rgb"]]
        if len(values) == leds and io["led-frames"] > 0 and len(set(values)) == 1:
            seen.update(expected.intersection(values))
        time.sleep(0.08)
    return {"service_predicates_pass": seen == expected, "uniform_colors": sorted(seen), "leds": leds}


def atom_vectors(text):
    values = [float(value) for value in re.findall(r"(?:Acc|Gyr) [XYZ] =\s+(-?\d+\.\d+)", text)]
    return [values[index:index + 6] for index in range(0, len(values) - 5, 6)]


def observe_classic_atom_imu(service, route, deadline, device, runtime):
    idle_text = serial_until(service, route, deadline, atom_vectors)
    idle = atom_vectors(idle_text)
    if device == "atom-lite":
        return {"service_predicates_pass": bool(idle) and all(not any(vector) for vector in idle),
                "no_imu_control": idle[:3]}
    steps = []
    for vector in ((0.5, -0.25, 1.0, 125, -50, 25), (-0.75, 0.375, 0.25, -100, 80, -30)):
        if runtime == "esp32sim":
            service.json(route + "/input", method="POST", payload={
                "kind": "imu", "accel": vector[:3], "gyro": vector[3:],
            })
        else:
            path = "/machine/mpu6886" if device == "atom-matrix" else "/machine/bmi270"
            properties = dict(zip(("accel-x", "accel-y", "accel-z", "gyro-x", "gyro-y", "gyro-z"), vector))
            set_properties(service, route, path, properties)

        def matches(observed):
            return all(abs(a - b) < 0.25 for a, b in zip(observed, vector))

        text = serial_until(service, route, min(deadline, time.monotonic() + 9),
                            lambda text: any(matches(sample) for sample in atom_vectors(text)))
        samples = atom_vectors(text)
        observed = next((sample for sample in samples if matches(sample)), samples[-1] if samples else [])
        steps.append({"injected": vector, "observed": observed,
                      "matched": bool(observed) and matches(observed),
                      "idle_matches": any(matches(sample) for sample in idle)})
    return {"service_predicates_pass": bool(idle) and all(step["matched"] and not step["idle_matches"] for step in steps),
            "steps": steps}


def observe_case(service, route, out, deadline, case, runtime):
    if case in ANIMATION:
        return observe_animation(service, route, out, deadline, ANIMATION[case])
    if case in STATIC:
        size, predicate = STATIC[case]
        return {"frame_predicates_pass": any(predicate(frame) for frame in frames(service, route, out, deadline, size))}
    if case in PAPER:
        return observe_paper(service, route, out, deadline, case)
    if case == ("dial", "encoder"):
        return observe_dial_encoder(service, route, out, deadline)
    if case == ("cores3", "power"):
        return observe_cores3_power(service, route, out, deadline, runtime)
    if case in {("cores3", "imu"), ("cores3", "ltr553")}:
        return observe_cores3_sensor(service, route, out, deadline, case[1], runtime)
    if case in CLASSIC_ATOM_CASES:
        device, name = case
        if name == "button":
            return observe_classic_atom_button(service, route, deadline)
        if name == "imu":
            return observe_classic_atom_imu(service, route, deadline, device, runtime)
        if name == "rgb":
            return observe_classic_atom_rgb(service, route, deadline, device)
        data = serial_until(service, route, deadline, lambda text: "count:2" in text)
        return {"service_predicates_pass": "count:1" in data and "count:2" in data}
    return observe_cores3_button(service, route, out, deadline)


def collect_serial(service, route, out):
    logs = []
    for channel in ("console", "usb-serial-jtag"):
        path = route + f"/serial?channel={channel}&limit=65536"
        try:
            receipt = service.json(path)
        except HttpError as error:
            if channel == "console" or error.status not in {400, 404, 409}:
                raise
        else:
            logs.append(receipt["data"])
            (out / f"serial-{channel}.json").write_text(json.dumps(receipt) + "\n")
    return not any(FATAL.search(log) for log in logs)


def collect_evidence(service, route, out, result):
    result["session"] = service.json(route)
    data = service.download(route + "/evidence")
    with ZipFile(BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if set(archive.namelist()) != manifest["files"].keys() | {"manifest.json"}:
            raise ValueError("evidence ZIP members differ from the manifest")
        for name, metadata in manifest["files"].items():
            member = archive.read(name)
            if len(member) != metadata["size"] or sha256(member).hexdigest() != metadata["sha256"]:
                raise ValueError(f"invalid evidence member: {name}")
    (out / "evidence.zip").write_bytes(data)
    result["evidence_sha256"] = sha256(data).hexdigest()


def stop(service, route):
    state = service.json(route + "?purge=0", method="DELETE")["state"]
    deadline = time.monotonic() + 15
    while state == "stopping" and time.monotonic() < deadline:
        time.sleep(0.25)
        state = service.json(route)["state"]
    if state != "stopped":
        raise ValueError(f"session stop did not complete: {state}")
    return state


def run_trial(service, out, device, case, firmware_id, digest, runtime, trial, timeout):
    out.mkdir(parents=True)
    result = {
        "device": device, "case": case, "firmware_sha256": digest,
        "runtime": runtime, "trial": trial,
    }
    route = None
    started = time.monotonic()
    try:
        lease = service.json("sessions", method="POST", payload={
            "device_id": device, "firmware_id": firmware_id, "runtime": runtime,
            "ttl_seconds": int(timeout) + 120,
        })
        route = "sessions/" + lease["session_id"]
        if lease["runtime"] != runtime:
            raise ValueError("service selected a different runtime")
        result["normalized_firmware_sha256"] = lease["firmware_sha256"]
        service.json(route + "/wait", method="POST", payload={"timeout_seconds": 60})
        result["observations"] = observe_case(
            service, route, out, time.monotonic() + timeout, (device, case), runtime,
        )
        result["no_fatal_marker"] = collect_serial(service, route, out)
        observations = result["observations"]
        matched = observations.get("service_predicates_pass", observations.get("frame_predicates_pass", False))
        if result["no_fatal_marker"] and matched:
            result["status"] = "PASS"
            result["scope"] = "Service oracle, including recorded observations. Standalone fork checks are separate."
        else:
            result["status"] = "FAIL"
    except OracleFailure as error:
        result.update(status="FAIL", reason=str(error))
    except (MatrixError, OSError, ValueError, KeyError) as error:
        result.update(status="ERROR", error=str(error))
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        if route:
            for label, operation in (
                ("evidence", lambda: collect_evidence(service, route, out, result)),
                ("stop", lambda: result.update(stop_state=stop(service, route))),
            ):
                try:
                    operation()
                except (MatrixError, OSError, ValueError, KeyError, BadZipFile) as error:
                    result.update(status="ERROR", **{label + "_error": str(error)})
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--firmware-root", required=True, type=Path)
    parser.add_argument("--case", action="append", metavar="DEVICE/CASE")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    url = urlsplit(args.service)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
            or url.port in {8787, 8830, 18787, 18853} or url.path not in {"", "/"}
            or url.username or url.password or url.query or url.fragment):
        parser.error("provide the loopback URL of an agent-owned Device Service")
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    cases = [tuple(case.split("/")) for case in args.case] if args.case else sorted(CASES)
    if any(case not in CASES for case in cases):
        parser.error("case has no service oracle")
    if len(cases) != len(set(cases)):
        parser.error("each case may be selected once")
    args.out.mkdir(parents=True)
    token = args.token_file.read_text().strip()
    if not token:
        parser.error("control token file is empty")
    service = Service(args.service, token)
    results = []
    for device, case in cases:
        path = args.firmware_root / device / case / "sketch.merged.bin"
        if not path.is_file():
            row = {"device": device, "case": case, "status": "NOT RUN", "reason": "missing merged image"}
            results.append(row)
            print(device, case, row["status"], row["reason"], flush=True)
            continue
        try:
            firmware, digest = service.register(device, path)
        except (MatrixError, OSError, ValueError) as error:
            results.append({"device": device, "case": case, "status": "ERROR", "error": str(error)})
            print(device, case, "intake ERROR", error, flush=True)
            continue
        for trial in (1, 2):
            for runtime in RUNTIMES:
                out = args.out / device / case / runtime / str(trial)
                result = run_trial(service, out, device, case, firmware, digest, runtime, trial, args.timeout)
                results.append(result)
                print(device, case, runtime, trial, result["status"], flush=True)
    (args.out / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(row["status"] != "PASS" for row in results))


if __name__ == "__main__":
    sys.exit(main())
