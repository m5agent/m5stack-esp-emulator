#!/usr/bin/env python3
"""Portable, offline archive verification; standard library only, no device I/O."""
import argparse
import hashlib
import json
import struct
import zlib
from collections import Counter
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent
PNG = b"\x89PNG\r\n\x1a\n"


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-originals", action="store_true",
                        help="Also compare local original paths; optional and unavailable on other machines")
    args = parser.parse_args()
    manifest = load(ROOT / "artifact-manifest.json")
    assert manifest["original_file_count"] == len(manifest["original_files"]) == 1341
    expected = {"artifact-manifest.json"}
    counts = Counter()
    for row in manifest["original_files"]:
        name = row["archive_path"]
        assert name not in expected
        expected.add(name)
        path = local(name)
        data = path.read_bytes()
        assert len(data) == row["source_bytes"] == row["archive_bytes"], name
        assert sha(data) == row["source_sha256"] == row["archive_sha256"], name
        if args.check_originals:
            original = Path(row["source_path"])
            assert original.is_file() and not original.is_symlink(), str(original)
            assert original.read_bytes() == data, str(original)
        fmt = row["format"]
        if fmt == "json":
            assert b"\x00" not in data
            json.loads(data.decode("utf8"))
        elif fmt == "png":
            png_info(data)
        elif fmt == "javascript":
            assert b"\x00" not in data
            data.decode("utf8")
        elif fmt == "empty-http-200-browser-body-observation":
            assert not data and name.endswith(".response")
            meta = load(path.with_suffix(".json"))
            assert meta["status"] == 200 and meta["bytes"] == 0 and "/frame.png?" in meta["path"]
        else:
            raise AssertionError((name, "Unadmitted binary/text type", fmt))
        assert path.suffix.lower() not in {".bin", ".rom", ".elf", ".mpy", ".zip", ".pem", ".key"}
        assert path.name != "preview-control-token" and not path.name.endswith(".md")
        counts[fmt] += 1
    for row in manifest["generated_files"]:
        name = row["archive_path"]
        assert name not in expected
        expected.add(name)
        data = local(name).read_bytes()
        assert sha(data) == row["archive_sha256"] and len(data) == row["archive_bytes"]
        data.decode("utf8")
        if name.endswith(".json"):
            json.loads(data)
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    assert actual == expected, {"extra": sorted(actual - expected), "missing": sorted(expected - actual)}
    assert not any(p.is_symlink() for p in ROOT.rglob("*"))

    runs = {name: load(ROOT / "artifacts" / name / "report.json") for name in (
        "live-cores3-torch-r1", "live-cores3-torch-r2", "live-cores3-torch-r3")}
    r1, r2, r3 = runs.values()
    assert r1["status"] == r2["status"] == "FAIL" and r3["status"] == "PASS"
    assert r1["browser_capture"]["errors"] == 185 and len(r1["phases"]) == 5
    assert len(r2["phases"]) == 1 and "not attached to the DOM" in r2["error"]["message"]
    reconstructed = local("artifacts/observer-r1.reconstructed.mjs").read_bytes()
    assert sha(reconstructed) == r1["source_sha256"][".work/flashlight-live-web-20261027/observe.mjs"]
    provenance = load(local("artifacts/observer-r1.reconstructed.provenance.json"))
    assert provenance["original_source_captured_before_execution"] is False
    assert provenance["category"] == "post-run-exact-hash-reconstruction"
    for report, directory in ((r2, "live-cores3-torch-r2"), (r3, "live-cores3-torch-r3")):
        source = report["executed_observer_source"]
        assert source["captured_before_api"] is True
        assert sha(local(f"artifacts/{directory}/" + source["path"]).read_bytes()) == source["sha256"]
    assert r3["source_sha256"] == r3["source_sha256_after"]
    assert len([p for p in (ROOT / "artifacts/live-cores3-torch-r3").rglob("*") if p.is_file()]) == 624

    http_counts, body_classes = {}, {}
    for directory, report in runs.items():
        for kind, rows in (("direct", report["http"]), ("browser", report["browser_http"])):
            counter = Counter()
            for row in rows:
                assert row["method"] == "GET", (directory, kind, row)
                counter[str(row["status"])] += 1
                if "body" in row:
                    data = local(f"artifacts/{directory}/" + row["body"]).read_bytes()
                    assert sha(data) == row["sha256"] and len(data) == row["bytes"]
            http_counts[directory + ":" + kind] = dict(counter)
        assert report["forbidden_mutations"] == []
    assert len(r3["http"]) == 72 and all(row["status"] == 200 and row["bytes"] > 0 for row in r3["http"])
    assert len(r3["browser_http"]) == 318
    for row in r3["browser_http"]:
        assert row["state"] == "complete" and not row.get("metadata_error")
        if row["status"] == 304:
            assert row["body_absent"] == "HTTP 304 has no response entity"
            assert not {"body", "sha256", "bytes"}.intersection(row)
            assert not (ROOT / "artifacts/live-cores3-torch-r3" / f'browser-{row["index"]}.response').exists()
            body_classes["protocol_304_no_entity"] = body_classes.get("protocol_304_no_entity", 0) + 1
        else:
            assert row["status"] == 200
            classification = "http_200_nonempty" if row["bytes"] else "http_200_empty_observed_optional_capture_partial"
            body_classes[classification] = body_classes.get(classification, 0) + 1
    assert body_classes == {"protocol_304_no_entity": 193, "http_200_nonempty": 121,
                            "http_200_empty_observed_optional_capture_partial": 4}
    assessment = load(ROOT / "browser-capture-assessment.json")
    assert assessment["optional_browser_body_capture"] == "PARTIAL"
    assert assessment["mandatory_controller_mounted_frame_status"] == "PASS"
    assert [row["response_index"] for row in assessment["empty_body_rows"]] == [4, 5, 82, 141]
    assert [row["advertised_content_length"] for row in assessment["empty_body_rows"]] == [319, 319, 302, 319]
    assert assessment["http_304_empty_entity_substitutes"] == 0
    for item in assessment["empty_body_rows"]:
        assert not local(item["body_archive"]).read_bytes()
        assert len(item["matching_mandatory_execution_observations"]) == 1
        linked = item["matching_mandatory_execution_observations"][0]
        assert linked["inside_mandatory_capture_browser_window"] is False
        assert linked["advertised_sha_matches_actual_direct_png"] is True

    report_base = ROOT / "artifacts/live-cores3-torch-r3"
    assert len(r3["phases"]) == 5
    assert [s["phase"] for s in r3["phases"]] == ["steady-on", "steady-off", "steady-on", "slow2", "steady-on"]
    expected_known = [True, True, True, False, True]
    expected_brightness = [1, 0, 1, 0, 1]
    execution_ids, images = set(), set()
    for index, stage in enumerate(r3["phases"]):
        execution = stage["execution"]
        execution_ids.add(execution["execution_id"])
        assert execution["pid"] == r3["hold"]["pid"]
        assert execution["firmware_sha256"] == r3["hold"]["firmware_sha256"]
        assert execution["state"] == "completed"
        observed = stage["mounted"]
        led = observed["led"]
        assert observed["bindings"] == {} and observed["physical_events"] == observed["live_controls"] == 0
        assert led["class_name"] == "FixedWhiteLed" and led["attached"] and led["actual_vendor_light"]
        assert led["known"] is expected_known[index] and led["userDataKnown"] is expected_known[index]
        assert led["state"] == {"color": "#fffaf0", "brightness": expected_brightness[index]}
        assert led["glow"] is False
        props = observed["unit"]["properties"]
        assert props["flash-mode"] is False and props["mode-frozen"] is True
        assert props["output-known"] is expected_known[index]
        assert props["en-level"] is (index != 1)
        assert len(stage["raw_qom"]) == 9
        for name, raw in stage["raw_qom"].items():
            assert raw["session_id"] == r3["hold"]["session_id"] and raw["property"] == name
            assert raw["value"] == props[name]
        web = stage["web_qom_response"]
        assert web["status"] == 200 and web["bytes"] > 0
        assert r3["browser_http"][web["index"]] == web
        assert web["unit_payload"]["source"] == "live"
        assert web["unit_payload"]["units"][0]["properties"]["output-known"] is expected_known[index]
        artifacts = [stage["frame"], stage["screenshots"]["renderer"], stage["screenshots"]["panel"],
                     stage["screenshots"]["viewport_image"], stage["screenshots"]["stage"]]
        for item in artifacts:
            assert item["path"] not in images
            images.add(item["path"])
            data = (report_base / item["path"]).read_bytes()
            assert sha(data) == item["sha256"]
            info = png_info(data, center=item is stage["frame"])
            if "metrics" in item:
                assert info["size"] == item["metrics"]["size"]
        frame = stage["frame"]
        expected_pixel = [0, 0, 0] if index == 1 else [255, 255, 255]
        assert png_info((report_base / frame["path"]).read_bytes(), center=True)["center"] == expected_pixel
        assert observed["frame"]["center"] == expected_pixel
        assert frame["headers"]["x-frame-execution-id"] == observed["frame"]["metadata"]["x-frame-execution-id"] == execution["execution_id"]
        assert frame["headers"]["x-frame-revision-id"] == observed["frame"]["metadata"]["x-frame-revision-id"] == execution["revision_id"]
        assert frame["sha256"] == observed["frame"]["metadata"]["x-frame-sha256"]
        bounds = stage["screenshots"]["bounds"]
        assert {b["name"] for b in bounds} == {"host-and-unit", "flashlight"}
        assert all(b["visible"] for b in bounds)
    assert len(images) == 25 and len(execution_ids) == 5
    assert len(r3["screenshot_attempts"]) == 5
    assert all(row["attempt"] == 1 and row["status"] == "PASS" and row["before"]["own_default_order"] == 0
               and row["after"]["allow_three"] is True for row in r3["screenshot_attempts"])
    assert r3["page_errors"] == r3["resource_errors"] == []
    assert not [row for row in r3["console_errors"] if row["type"] == "error"]
    regressions = load(ROOT / "regression-map.json")["rows"]
    assert len(regressions) == 7 and sum(row["archived_report"] is not None for row in regressions) == 5
    for row in regressions:
        if row["archived_report"]:
            data = local(row["archived_report"]).read_bytes()
            assert sha(data) == row["original_report_sha256"] and json.loads(data)["status"] == "PASS"
    return {"archive_integrity": "PASS", "mandatory_controller_mounted_frame_status": "PASS",
            "optional_browser_body_capture": "PARTIAL", "original_files_dual_sha_verified": len(manifest["original_files"]),
            "original_formats": dict(counts), "r3_complete_original_files": 624, "r3_direct_gets": 72,
            "r3_browser_responses": 318, "r3_body_classes": body_classes, "final_png_artifacts_verified": len(images),
            "r1_r2": "Independent original FAIL attempts retained", "archived_regression_reports": 5,
            "regression_stdout_only_no_file_report": 2, "post_or_other_mutation_requests": 0, "hardware": "NOT RUN"}


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
