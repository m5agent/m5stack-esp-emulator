#!/usr/bin/env python3
"""Portable archive/contract verification; no service, guest or dependency.

Default reads only this directory. Optional --check-originals compares retained
internal files; missing originals never invalidate portable archive integrity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

HERE = Path(__file__).resolve().parent


def need(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def hashes(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "sha512": hashlib.sha512(data).hexdigest()}


def png(path, *, center=False):
    data = path.read_bytes()
    need(data.startswith(b"\x89PNG\r\n\x1a\n"), "not PNG: " + str(path))
    offset, header, compressed, ended = 8, None, bytearray(), False
    while offset < len(data):
        need(offset + 12 <= len(data), "truncated PNG chunk")
        size, = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        need(len(payload) == size and offset + 12 + size <= len(data), "truncated PNG payload")
        crc, = struct.unpack_from(">I", data, offset + 8 + size)
        need(zlib.crc32(kind + payload) & 0xffffffff == crc, "PNG CRC differs")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            ended = True
            need(offset + 12 + size == len(data), "bytes after IEND")
        offset += 12 + size
    need(ended and header and header[0] > 0 and header[1] > 0 and compressed, "empty PNG")
    result = {"size": list(header[:2])}
    if not center:
        return result
    width, height, bits, color, compression, filtering, interlace = header
    need(bits == 8 and color in (2, 6) and compression == 0 and filtering == 0 and interlace == 0, "unsupported center decoder format")
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(compressed)
    need(len(raw) == height * (stride + 1), "PNG inflated size differs")
    previous = bytearray(stride)
    for y in range(height // 2 + 1):
        at = y * (stride + 1)
        mode, row = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        need(0 <= mode <= 4, "invalid PNG filter")
        for x in range(stride):
            left, up = row[x - channels] if x >= channels else 0, previous[x]
            upper_left = previous[x - channels] if x >= channels else 0
            if mode == 1:
                value = left
            elif mode == 2:
                value = up
            elif mode == 3:
                value = (left + up) // 2
            elif mode == 4:
                prediction = left + up - upper_left
                a, b, c = abs(prediction - left), abs(prediction - up), abs(prediction - upper_left)
                value = left if a <= b and a <= c else up if b <= c else upper_left
            else:
                value = 0
            row[x] = (row[x] + value) & 255
        previous = row
    result["center"] = list(previous[(width // 2) * channels:(width // 2) * channels + 3])
    return result


def no_payload(value):
    if isinstance(value, dict):
        need(not (value.get("encoding") == "base64" and isinstance(value.get("data"), str)), "unredacted base64 file payload")
        for child in value.values():
            no_payload(child)
    elif isinstance(value, list):
        for child in value:
            no_payload(child)


def verify(args):
    manifest, index = read("manifest.json"), read("index.json")
    actual = {str(path.relative_to(HERE)) for path in HERE.rglob("*") if path.is_file() and path.name != "manifest.json"}
    need(actual == set(manifest["files"]), "missing or unlisted archive files")
    for name, expected in manifest["files"].items():
        path = HERE / name
        need(path.suffix not in {".zip", ".mpy", ".bin", ".rom"}, "forbidden binary artifact")
        data = path.read_bytes()
        need(not data.startswith(b"PK\x03\x04"), "ZIP bytes must not be archived")
        need(hashes(data) == expected, "archive hash differs: " + name)
        if path.suffix == ".png":
            png(path)
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError):
            continue
        no_payload(value)
    for item in index["originals"]:
        if item["archive"] is None:
            need(item["disposition"].startswith("omitted-"), "omission provenance missing")
            continue
        archived = item["archive"]
        need(manifest["files"][archived["path"]] == {key: archived[key] for key in ("bytes", "sha256", "sha512")}, "original/archive mapping differs")
        if item["disposition"] == "original-byte-identical":
            need(all(item["original"][key] == archived[key] for key in ("bytes", "sha256", "sha512")), "byte-identical provenance differs")
        else:
            need(item["disposition"] == "redacted-json-metadata" and any(item["transformations"].values()), "redaction classification missing")
    report = read("live-gen45-r1/report.json")
    hold = report["handoff"]
    need(report["status"] == "PASS" and hold["worker_generation"] == 45 and report["hardware"] == "NOT RUN", "live category differs")
    need(report["source_sha256"] == report["source_sha256_after"], "source changed during execution")
    need(report["forbidden"] == [] and report["page_errors"] == [], "unexpected browser effects/errors")
    need([phase["label"] for phase in report["phases"]] == ["load-binary", "web-run", "web-repeat", "pir-true", "pir-false", "source-recovery"], "phase sequence differs")
    need([phase["guest"].get("entry", phase["guest"].get("recovery"))["count"] for phase in report["phases"]] == [1, 2, 3, 3, 3, 3], "same-VM import count differs")
    wanted = [[0, 255, 0], [0, 255, 0], [0, 255, 0], [255, 255, 255], [0, 255, 0], [0, 0, 255]]
    for phase, color in zip(report["phases"], wanted):
        need(phase["session"]["pid"] == hold["pid"] and phase["session"]["firmware_sha256"] == hold["firmware_sha256"]
             and phase["session"]["worker"]["generation"] == 45, "phase VM identity differs")
        frame = phase["frame"]
        image = png(HERE / "live-gen45-r1" / frame["path"], center=True)
        need(image == frame["metrics"] and image["center"] == color and phase["mounted"]["frame"]["center"] == color, "frame/mounted center differs")
        need(frame["sha256"] == hashlib.sha256((HERE / "live-gen45-r1" / frame["path"]).read_bytes()).hexdigest(), "frame SHA differs")
        need(phase["mounted"]["module"]["meta_id"] == "m5.unit.pir.grove" and phase["mounted"]["module"]["annotation_owns_actual_anchor"] is True, "PIR mount proof differs")
        record = phase["guest"].get("entry", phase["guest"].get("recovery"))
        need(record["nonce"] == hold["nonce"] and record["owner_id"] == hold["owner_id"], "guest seed/owner differs")
        if "entry" in phase["guest"]:
            need(record["guard"] is True and record["name"] == "__main__" and record["dep_value"] == 29
                 and record["main_id"] == record["sys_main_id"] == record["import_main_id"] != hold["owner_id"], "binary main identity differs")
        else:
            need(record["owner_restored"] is True and record["expected_owner_id"] == hold["owner_id"], "source owner restoration differs")
    need(report["cancelled"]["state"] == "cancelled" and report["cancelled"]["interrupt_ack"] == "confirmed", "cancel was not acknowledged")
    writes = report["mutations"]
    need(len(writes) == 7 and len([row for row in writes if row["path"].endswith("/runs")]) == 3
         and len([row for row in writes if row["path"].endswith("/input")]) == 2
         and len([row for row in writes if row["path"].endswith("/cancel")]) == 1, "Web effect scope differs")
    saved = [row["body"] for row in writes if row["path"] == "/api/v1/program-revisions"]
    need(len(saved) == 1 and saved[0]["entrypoint"] == "main.py" and "main.mpy" not in saved[0]["files"], "source fork differs")
    need(saved[0]["files"]["dep.mpy"]["original_decoded"]["sha256"] == hold["binary_file_sha256"]["dep.mpy"], "original dependency differs")
    need(hashlib.sha256(saved[0]["files"]["main.py"]["data"].encode()).hexdigest() == hold["source_restore_sha256"], "source recovery bytes differ")
    for name, expected in hold["binary_file_sha256"].items():
        need(report["binary_checkpoint"]["files"][name]["original_decoded"]["sha256"] == expected, "binary metadata differs")
    omitted_zip = [item for item in index["originals"] if item["disposition"] == "omitted-zip-byte-payload"]
    need(len(omitted_zip) == 2 and omitted_zip[0]["original"]["sha256"] == omitted_zip[1]["original"]["sha256"], "ZIP omission provenance differs")
    need(all(next(row for row in item["zip_members"] if row["path"] == "frames/current.png")["sha256"] == report["phases"][-1]["frame"]["sha256"] for item in omitted_zip), "ZIP final frame differs")
    need(hashlib.sha256((HERE / "observer/observe.mjs").read_bytes()).hexdigest() == report["source_sha256"][".work/main-mpy-web-acceptance-20261027/observe.mjs"], "executed observer source differs")
    classification = read("browser-capture-classification.json")
    need(classification["optional_browser_body_capture"] == "PARTIAL" and len(classification["zero_png_200"]) == 8, "optional capture scope differs")
    for row in classification["zero_png_200"]:
        need(row["status"] == 200 and row["bytes"] == 0 and row["capture_status"] == "partial", "empty PNG observation was promoted")
        need((HERE / "live-gen45-r1" / row["body"]).read_bytes() == b"", "empty original fingerprint differs")
    normal = [row for row in report["browser_http"] if row["status"] == 304]
    need(len(normal) == 77 == classification["normal_304_count"] and all("body" not in row and row["body_absent"] == "HTTP 304 no response entity" for row in normal), "normal 304 classification differs")
    need(index["counts"] == {"mandatory_phases": 6, "web_mutations": 7, "browser_responses": 364, "optional_zero_png_200": 8,
         "normal_304": 77, "offline_preview_python": 109, "offline_preview_client_groups": 25, "offline_managed_program_groups": 33,
         "offline_ordinary_program_groups": 14, "offline_create_groups": 11}, "index counts differ")
    need(read("offline/preview-client-final.json")["count"] == 25, "client regression receipt differs")
    for folder, count in (("preview-program", 33), ("ordinary-program", 14), ("preview-create", 11)):
        value = read("offline/" + folder + "/report.json")
        need(value["status"] == "PASS" and len(value["checks"]) == count, "browser regression receipt differs")
    need("Ran 109 tests" in (HERE / "offline/preview-host-final.stderr").read_text() and (HERE / "offline/preview-host-final.stderr").read_text().rstrip().endswith("OK"), "Python regression receipt differs")
    for name, expected in report["source_sha256"].items():
        candidate = HERE / "source-snapshot" / name
        if candidate.is_file():
            need(hashlib.sha256(candidate.read_bytes()).hexdigest() == expected, "source snapshot differs")
    originals_checked = 0
    if args.check_originals:
        need(args.workspace is not None, "--check-originals requires --workspace")
        for item in index["originals"]:
            name = item["original"]["path"]
            path = Path(args.external_root) / name.removeprefix("external-offline/") if name.startswith("external-offline/") else Path(args.workspace) / name
            need(path.is_file(), "original unavailable: " + name)
            need(hashes(path.read_bytes()) == {key: item["original"][key] for key in ("bytes", "sha256", "sha512")}, "original hash differs: " + name)
            originals_checked += 1
    return {"status": "PASS", "category": "PORTABLE_ARCHIVE_VERIFICATION_NOT_NEW_GUEST_EXECUTION", "archive_files": len(actual),
            "originals": len(index["originals"]), "originals_checked": originals_checked, "mandatory_phases": 6,
            "optional_browser_capture": "PARTIAL", "zero_png_200": 8, "normal_304": 77, "hardware": "NOT RUN"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-originals", action="store_true")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--external-root", type=Path, default=Path("/tmp"))
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args), ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
