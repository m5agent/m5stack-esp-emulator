#!/usr/bin/env python3
"""Offline live-evidence verification; stdlib only; never calls an API/guest."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
PNG = b"\x89PNG\r\n\x1a\n"
RUNTIME = "3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf8"))


def local(name):
    p = PurePosixPath(name)
    assert not p.is_absolute() and ".." not in p.parts and p.as_posix() == name
    result = ROOT / name
    assert result.is_file() and not result.is_symlink(), name
    return result


def png_info(data, center=False):
    """Validate chunks/CRC, decompressed scanlines; decode guest center pixels."""
    assert data.startswith(PNG)
    at, chunks, compressed = 8, [], bytearray()
    ihdr, ended = None, False
    while at < len(data):
        assert at + 12 <= len(data)
        size = struct.unpack_from(">I", data, at)[0]
        kind = data[at + 4:at + 8]
        assert at + 12 + size <= len(data)
        body = data[at + 8:at + 8 + size]
        crc = struct.unpack_from(">I", data, at + 8 + size)[0]
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == crc
        chunks.append(kind)
        if kind == b"IHDR":
            assert ihdr is None and size == 13
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            assert size == 0
            ended = True
        at += size + 12
        if ended:
            break
    assert ended and at == len(data) and chunks[0] == b"IHDR" and compressed
    width, height, depth, color, compression, filtering, interlace = ihdr
    assert 0 < width <= 10000 and 0 < height <= 20000
    assert depth == 8 and color in (2, 6) and compression == filtering == interlace == 0
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    assert len(raw) == height * (stride + 1)
    assert all(raw[y * (stride + 1)] <= 4 for y in range(height))
    result = {"size": [width, height]}
    if center:
        previous = bytearray(stride)
        for y in range(height // 2 + 1):
            offset = y * (stride + 1)
            method = raw[offset]
            row = bytearray(raw[offset + 1:offset + stride + 1])
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = previous[i]
                upper_left = previous[i - channels] if i >= channels else 0
                if method == 1:
                    predictor = left
                elif method == 2:
                    predictor = up
                elif method == 3:
                    predictor = (left + up) // 2
                elif method == 4:
                    p = left + up - upper_left
                    distances = (abs(p - left), abs(p - up), abs(p - upper_left))
                    predictor = (left, up, upper_left)[distances.index(min(distances))]
                else:
                    predictor = 0
                row[i] = (row[i] + predictor) & 255
            previous = row
        result["center"] = list(previous[(width // 2) * channels:(width // 2) * channels + 3])
    return result


def no_payload(value):
    if isinstance(value, dict):
        assert not (value.get("encoding") == "base64" and isinstance(value.get("data"), str))
        for child in value.values():
            no_payload(child)
    elif isinstance(value, list):
        for child in value:
            no_payload(child)


def verify_lane(row):
    r = load(local(row["report"]))
    assert r["status"] == "PASS" and r["cleanup"]["status"] == "PASS"
    assert r["device_id"] == row["device"] and r["flash_mode"] is (row["mode"] == "flash")
    assert len(r["runs"]) == len(r["observations"]) == 21
    assert r["worker"]["generation"] == 47 and r["runtime"]["sha256"] == RUNTIME
    stopped = r["cleanup"]["session"]
    assert stopped["state"] == "stopped" and stopped["pid"] == r["pid"]
    assert stopped["flash_retained"] is False and stopped["worker"]["lease_active"] is False
    assert r["cleanup"]["pid_gone"] is True and r["cleanup"]["zip_before_stop"] is True
    assert r["evidence_zip"]["members"] == 117
    for x in r["observations"]:
        assert x["execution"]["pid"] == r["pid"] and x["execution"]["firmware_sha256"] == r["firmware_sha256"]
        assert x["guest"]["nonce"] == r["nonce"]
        assert x["unit"]["source"] == "guest-qom" and x["unit"]["available"] is True and not x["unit"]["errors"]
        for name, qom in x["raw_qom"].items():
            assert qom["session_id"] == r["session_id"] and qom["property"] == name
            assert qom["value"] == x["unit"]["properties"][name]
        if x["phase"] in ("atomic", "stable-unknown"):
            p = x["unit"]["properties"]
            assert p["program-state"] == "unqualified" and p["output-known"] is p["active"] is False
            assert p["waveform-qualified"] is False and p["settle-at-ns"] == p["timeout-at-ns"] == -1
        if x["phase"] == "atomic":
            event = x["guest"]["events"][0]
            assert event["before_raw"] & 1023 == 256 and event["returned_raw"] == event["before_raw"]
            assert event["away_raw"] & 1023 == {"ledc73": 73, "rmt81": 81, "out-inv": 768}[x["route_name"]]
            assert 0 <= event["route_window_us"] <= event["arm_to_return_us"] < 100000
            assert x["unit"]["properties"]["decoded-programs"] == x["before_properties"]["decoded-programs"] + 1
    return r


def verify_web(index):
    w = load(local(index["web"]["report"]))
    owner = load(local(index["web"]["owner_report"]))
    assert w["status"] == owner["status"] == "PASS" and owner["cleanup"]["status"] == "PASS"
    assert len(w["phases"]) == 13 and len(owner["runs"]) == len(owner["observations"]) == 14
    assert owner["runtime"]["sha256"] == RUNTIME and owner["worker"]["generation"] == 47
    assert w["forbidden_mutations"] == w["page_errors"] == w["resource_errors"] == []
    assert w["browser_capture"]["errors"] == w["browser_capture"]["pending"] == 0
    webdir = local(index["web"]["report"]).parent
    for x in w["phases"]:
        name = x["phase"]
        known = name == "initial" or "recover-" in name
        active = name == "initial" or name.endswith("recover-driver")
        en = not name.endswith("recover-reset")
        p = x["units"]["units"][0]["properties"]
        assert p["output-known"] is known and p["en-level"] is en
        assert p["gpio-route-supported"] is (not name.endswith("web-away"))
        assert p["program-state"] == ("torch-active" if active else "ready-low" if known else "unqualified")
        for mount in (x["mounted"], x["mounted_after_render"]):
            assert mount["session"]["pid"] == owner["pid"] and mount["session"]["firmware_sha256"] == owner["firmware_sha256"]
            assert mount["state_source"] == "live" and mount["physical_events"] == 0 and mount["bindings"] == {}
            led = mount["led"]
            assert led["class_name"] == "FixedWhiteLed" and led["attached"] is led["actual_vendor_light"] is True
            assert led["known"] is led["userDataKnown"] is known
            assert led["state"] == {"color": "#fffaf0", "brightness": 1 if active else 0} and led["glow"] is False
            assert mount["frame"]["center"] == ([255] * 3 if en else [0] * 3)
            assert mount["frame"]["metadata"]["x-frame-execution-id"] == x["execution"]["execution_id"]
        frame = (webdir / x["frame"]["path"]).read_bytes()
        assert sha(frame) == x["frame"]["sha256"] == x["frame"]["headers"]["x-frame-sha256"]
        assert png_info(frame, center=True)["center"] == ([255] * 3 if en else [0] * 3)
        for kind in ("panel", "renderer", "viewport_image", "stage"):
            image = x["screenshots"][kind]
            raw = (webdir / image["path"]).read_bytes()
            assert sha(raw) == image["sha256"]
            png_info(raw)
    rows = w["browser_http"]
    assert len(rows) == 1062 and Counter(r["status"] for r in rows) == {200: 386, 304: 676}
    assert sum(r["status"] == 200 and r.get("bytes") == 0 for r in rows) == w["browser_capture"]["partial"] == 7
    for r in rows:
        if r["status"] == 304:
            assert r.get("body_absent") and "body" not in r
        elif r.get("bytes") == 0:
            assert r.get("body_incomplete")
    assert owner["evidence_zip"]["members"] == 78
    c = owner["cleanup"]
    assert c["pid_gone"] is True and c["zip_before_stop"] is True
    assert c["session"]["flash_retained"] is False and c["session"]["worker"]["lease_active"] is False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check-originals", action="store_true")
    p.add_argument("--origin-root", type=Path)
    args = p.parse_args()
    index = load(ROOT / "index.json")
    manifest = load(ROOT / "manifest.json")
    assert index["schema_version"] == manifest["schema_version"] == 1
    files = manifest["files"]
    assert len({r["archive"] for r in files}) == len(files)
    assert {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()} == {r["archive"] for r in files} | {"manifest.json"}
    for row in files:
        raw = local(row["archive"]).read_bytes()
        assert len(raw) == row["archive_bytes"] and sha(raw) == row["archive_sha256"], row["archive"]
        if row["mode"] == "original":
            assert row["original_sha256"] == row["archive_sha256"] and row["original_bytes"] == row["archive_bytes"]
        if row["archive"].endswith((".json", ".response")):
            try:
                no_payload(json.loads(raw))
            except (UnicodeDecodeError, ValueError):
                pass
        if raw.startswith(PNG):
            png_info(raw)
        if args.check_originals and row.get("source"):
            assert args.origin_root is not None, "--origin-root required with --check-originals"
            rel = PurePosixPath(row["source"])
            assert rel.parts[0] == ".work" and ".." not in rel.parts
            assert "control-token" not in rel.name and "control_token" not in rel.name
            original = args.origin_root / rel
            assert original.is_file() and not original.is_symlink()
            data = original.read_bytes()
            assert len(data) == row["original_bytes"] and sha(data) == row["original_sha256"]
    summary = index["summary"]
    assert summary["eight_lane_status"] == "PASS" and summary["lanes"] == 8 and summary["executions"] == 168
    assert summary["runtime_sha256"] == RUNTIME and summary["generation"] == 47
    assert summary["web_mandatory_status"] == "PASS" and summary["web_mandatory_phases"] == 13 and summary["web_owner_executions"] == 14
    assert summary["web_optional_capture_status"] == "PARTIAL" and summary["web_optional_empty_200"] == 7
    expected = {(d, m) for d in ("cores3", "atoms3r", "sticks3", "stopwatch") for m in ("flash", "torch")}
    assert {(r["device"], r["mode"]) for r in index["eight_lanes"]} == expected and len(index["eight_lanes"]) == 8
    for row in index["eight_lanes"]:
        verify_lane(row)
    verify_web(index)
    for fail in index["preserved_failed_runs"]:
        original = load(local(fail["report"]))
        assert original["status"] == "FAIL" and len(original["observations"]) == fail["observations"]
    assert len(index["preserved_failed_runs"]) == 2
    final = load(local(index["separate_first_failure_finalization"]))
    assert final["status"] == "RESOURCE_FINALIZATION_CONFIRMED_SEPARATE_FROM_FUNCTIONAL_FAIL"
    assert final["functional_observations"] == 0 and final["original_pid_gone"] is True and final["history_equals_zip_frame"] is True
    assert summary["cleanup"] == {"owned_sessions": 13, "original_pass": 12, "original_unconfirmed": 1,
                                  "separate_finalization_confirmed": 1, "confirmed_resource_finalizations": 13}
    for window in manifest["serial_windows"]:
        raw = local(window["archive"]).read_bytes()
        raw.decode("ascii")
        assert sha(raw) == window["window_sha256"] and len(raw) == window["end"] - window["start"]
        assert b"__M5_EXEC_" in raw and (b"__:DONE" in raw or b"__:ERROR" in raw)
        if args.check_originals:
            with zipfile.ZipFile(args.origin_root / window["source_zip"]) as z:
                serial = z.read("serial.log")
            assert sha(serial) == window["source_member_sha256"] and serial[window["start"]:window["end"]] == raw
    print(json.dumps({"status": "PASS", "files": len(files), "eight_lanes": 8, "executions": 168, "web_phases": 13,
                      "optional_browser_capture": "PARTIAL", "api_contacted": False, "guest": "NOT RUN", "check_originals": args.check_originals}))


if __name__ == "__main__":
    main()
