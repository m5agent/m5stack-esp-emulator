"""Create a portable redacted Web evidence bundle, never copy MPY/ZIP bytes."""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".work/main-mpy-web-acceptance-20261027"
LIVE = WORK / "gen45-r1"
OUT = ROOT / "docs/evidence/2026-10-27-public-main-mpy/web"
OUT.mkdir(parents=True, exist_ok=False)
entries = []
MAC = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")


def hashes(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "sha512": hashlib.sha512(data).hexdigest()}


def origin(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return "external-offline/" + path.parent.name + "/" + path.name


def clean(value, count):
    if isinstance(value, dict):
        if value.get("encoding") == "base64" and isinstance(value.get("data"), str):
            raw = base64.b64decode(value["data"], validate=True)
            count["byte_payloads"] += 1
            return {"encoding": "redacted-byte-payload", "redaction": "Original base64 file bytes omitted; use api-runtime source/recipe for reproducible compilation.",
                    "original_decoded": hashes(raw), **{key: clean(child, count) for key, child in value.items() if key not in {"encoding", "data"}}}
        return {key: clean(child, count) for key, child in value.items()}
    if isinstance(value, list):
        return [clean(child, count) for child in value]
    if isinstance(value, str):
        text = value.replace(str(ROOT), "<WORKTREE>")
        if text != value:
            count["local_paths"] += 1
        text, changed = MAC.subn("[REDACTED_MAC]", text)
        count["mac_addresses"] += changed
        return text
    return value


def put(path, destination, *, role="evidence"):
    data = path.read_bytes()
    item = {"original": {"path": origin(path), **hashes(data)}, "role": role}
    if path.suffix == ".zip" or data.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            members = [{"path": info.filename, **hashes(archive.read(info.filename))} for info in archive.infolist() if not info.is_dir()]
        item.update(archive=None, disposition="omitted-zip-byte-payload", zip_members=members)
        entries.append(item)
        return
    if path.suffix.lower() in {".mpy", ".bin", ".rom"}:
        item.update(archive=None, disposition="omitted-binary-byte-payload")
        entries.append(item)
        return
    count = {"byte_payloads": 0, "local_paths": 0, "mac_addresses": 0}
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeError):
        parsed = None
    if parsed is not None:
        redacted = clean(parsed, count)
        if any(count.values()):
            data = (json.dumps(redacted, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    destination = Path(destination)
    if destination.suffix == ".md":
        destination = destination.with_suffix(".md.txt")
    target = OUT / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    item.update(archive={"path": str(destination), **hashes(data)},
                disposition="redacted-json-metadata" if any(count.values()) else "original-byte-identical",
                transformations=count)
    entries.append(item)


for path in sorted(LIVE.rglob("*")):
    if path.is_file():
        put(path, Path("live-gen45-r1") / path.relative_to(LIVE))
put(WORK / "plan.json", "observer/plan.json")
put(WORK / "observe.mjs", "observer/observe.mjs", role="observer-source")
put(Path(__file__).resolve(), "observer/archive.py", role="archive-source")
put(WORK / "preview-host-final.stdout", "offline/preview-host-final.stdout")
put(WORK / "preview-host-final.stderr", "offline/preview-host-final.stderr")
put(WORK / "preview-client-final.json", "offline/preview-client-final.json")
for folder, target in [
    (Path("/tmp/m5-main-mpy-preview-program-frozen-20261027"), "preview-program"),
    (Path("/tmp/m5-main-mpy-program-panel-archive-final-20261027"), "ordinary-program"),
    (Path("/tmp/m5-main-mpy-preview-create-20261027"), "preview-create"),
]:
    assert json.loads((folder / "report.json").read_text())["status"] == "PASS"
    for path in sorted(folder.iterdir()):
        if path.is_file():
            put(path, Path("offline") / target / path.name)

report = json.loads((LIVE / "report.json").read_text())
assert report["status"] == "PASS"
assert report["source_sha256"] == report["source_sha256_after"]
sources = [path for path in report["source_sha256"] if path.startswith("platform/web/")]
sources += ["platform/web/sha256.js", "platform/tools/preview_service.py", "platform/tools/preview_store.py",
            "platform/tests/test_preview_service.py", "platform/tests/test_preview_store.py", "platform/tests/test_preview_client.mjs",
            "platform/tests/test_preview_program_panel.mjs", "platform/tests/test_preview_session_create.mjs", "platform/tests/test_program_panel.mjs"]
for name in dict.fromkeys(sources):
    path = ROOT / name
    if name in report["source_sha256"]:
        assert hashes(path.read_bytes())["sha256"] == report["source_sha256"][name]
    put(path, Path("source-snapshot") / name, role="source-snapshot-captured-after-run-matching-recorded-sha-where-listed")

partial = [row for row in report["browser_http"] if row.get("capture_status") != "complete"]
normal304 = [row for row in report["browser_http"] if row["status"] == 304]
assert len(partial) == 8 and all(row["status"] == 200 and row["bytes"] == 0 and row["path"].endswith("/frame.png") for row in partial)
assert all(row.get("body_absent") == "HTTP 304 no response entity" and "body" not in row for row in normal304)
classification = {"mandatory": "PASS", "optional_browser_body_capture": "PARTIAL", "zero_png_200": partial,
                  "normal_304_count": len(normal304), "normal_304_indices": [row["index"] for row in normal304],
                  "rule": "Zero-byte HTTP 200 observations are not PNG/texture-transfer evidence. HTTP 304 has no response entity and is not a capture failure."}
(OUT / "browser-capture-classification.json").write_text(json.dumps(classification, ensure_ascii=False, indent=2) + "\n")

index = {"schema_version": 1, "category": report["category"], "mandatory_status": "PASS", "optional_browser_body_capture": "PARTIAL",
         "hardware": "NOT RUN", "generation": 45, "captured_at": report["captured_at"], "archived_at": datetime.now(timezone.utc).isoformat(),
         "entrypoints": {"report": "live-gen45-r1/report.json", "verifier": "verify.py", "notes": "README.md.txt"},
         "counts": {"mandatory_phases": len(report["phases"]), "web_mutations": len(report["mutations"]),
                    "browser_responses": len(report["browser_http"]), "optional_zero_png_200": 8, "normal_304": len(normal304),
                    "offline_preview_python": 109, "offline_preview_client_groups": 25,
                    "offline_managed_program_groups": 33, "offline_ordinary_program_groups": 14, "offline_create_groups": 11},
         "source_snapshots": "Captured after execution; matching recorded before/after SHA256 for every listed live source. Additional helper/test snapshots are reproduction context, not a claim of extra live fingerprint coverage.",
         "omitted": "No original firmware/ROM/MPY files, ZIP bytes or base64-encoded file payloads are stored here. Original hashes are provenance only; archive hashes describe actual redacted/retained files.",
         "originals": entries}
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": "ARCHIVE_CONTENT_CREATED", "originals": len(entries), "omitted_zip": sum(item["archive"] is None for item in entries),
                  "json_transformations": sum(item.get("transformations", {}).get("byte_payloads", 0) for item in entries), "normal304": len(normal304)}))
