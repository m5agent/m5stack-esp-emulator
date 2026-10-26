#!/usr/bin/env python3
"""Read-only input verification and explicit-whitelist local evidence archive."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "tests/units/run_io_cases.py").is_file())
sys.path.insert(0, str(ROOT / "tests/units"))
sys.path.insert(0, str(ROOT / "platform/tools"))
from PIL import Image
from check_batch_evidence import Checker
from annotation_contract import annotation_checks
from run_io_cases import buzzer_timer_window

TARGET = ROOT / "docs/evidence/2026-10-26-unit-buzzer-once-a8fe"
WORK = ROOT / ".work/unit-buzzer-once-archive-20261026"
RUNTIME = "a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047"
FIRMWARE = {
    "original": "d06e243cb5575daacd43cdfe02fe0c45d5ccdd1aa25988b17566696370f8b911",
    "custom": "1be665305135da208b078dd079c6837558cce5ddc4eefbde4eff902080d2b880",
    "natural": "f679d481358af9209847a851d4178986479e2012df7a95f7964f27a567fc2e6e",
    "trace": "68bfd5801f6497440c0164a3c606e0c1cd9a798ffaabfaf752b4f3fc96e3ab09",
}
ZIP_ALLOWED = {"units/contract.json", "units/runtime.json", "units/state.json", "serial.log", "serial1.log",
               "qemu.stdout", "qemu.stderr", "frames/current.png", "qom/snapshot.json", "manifest.json"}
PRIVATE_PATH = re.compile(r"/(?:Users|home)/[^\s\"'<>]+|/opt/" + r"miniconda[^\s\"'<>]*")
MAC = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|-----BEGIN [^-]*PRIVATE KEY|Authorization:\s*(?:Bearer|Basic)\s+\S+", re.I)
PRIVATE_IP = re.compile(r"(?<![0-9.])(?:10\.(?:\d+\.){2}\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![0-9.])")
records = []
retention = {}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def safe_text(raw, label):
    text = raw.decode("utf-8")
    for pattern, reason in ((PRIVATE_PATH, "private absolute path"), (MAC, "MAC address"),
                            (SECRET, "credential pattern"), (PRIVATE_IP, "private network endpoint")):
        if pattern.search(text):
            raise AssertionError(f"{reason} in {label}")


def png(raw):
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        assert image.format == "PNG" and image.width > 0 and image.height > 0


def inspect_zip(raw, label):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert set(archive.namelist()) == ZIP_ALLOWED
        manifest = json.loads(archive.read("manifest.json"))
        for name in archive.namelist():
            content = archive.read(name)
            if name.endswith(".png"):
                png(content)
            else:
                safe_text(content, label + ":" + name)
            if name != "manifest.json":
                assert len(content) == manifest["files"][name]["size"]
                assert digest(content) == manifest["files"][name]["sha256"]
        return manifest


def copy(source, relative, *, sanitize_runtime_paths=False):
    assert source.is_file() and not source.is_symlink()
    name = PurePosixPath(relative)
    assert not name.is_absolute() and ".." not in name.parts
    assert source.suffix.lower() not in {".bin", ".elf", ".rom", ".pyc", ".so", ".dylib"}
    raw = source.read_bytes()
    archived = raw
    changed = 0
    if source.suffix == ".zip":
        inspect_zip(raw, str(source.relative_to(ROOT)))
    elif source.suffix == ".png":
        png(raw)
    else:
        if sanitize_runtime_paths:
            text = raw.decode("utf-8")
            text, changed = PRIVATE_PATH.subn("<local-runtime-path-redacted>", text)
            archived = text.encode("utf-8")
        safe_text(archived, str(source.relative_to(ROOT)))
    destination = TARGET / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert "--resume-owned-partial" in sys.argv
        if relative == "tools/archive.py" and "--update-owned-archiver" in sys.argv:
            previous = read_json(TARGET / "archive-manifest.json")
            owner = next(row for row in previous["files"] if row["archive"] == relative)
            assert digest(destination.read_bytes()) == owner["archived_sha256"]
            destination.write_bytes(archived)
        else:
            assert destination.read_bytes() == archived
    else:
        destination.write_bytes(archived)
    records.append({"source": source.relative_to(ROOT).as_posix(), "archive": relative,
                    "input_sha256": digest(raw), "archived_sha256": digest(archived),
                    "bytes": len(archived), "runtime_path_replacements": changed,
                    "verbatim": raw == archived})


def verify_pair(mode):
    folder = ROOT / f".work/unit-readout-buzzer-{mode}-20261026-r2/buzzer"
    report_path = folder / "report.json"
    report = read_json(report_path)
    controller = read_json(folder / report["controller_result"])
    detail_path = folder / report["browser_report"]
    detail = read_json(detail_path)
    checker = Checker(folder, strict_direct=True)
    manifest, count = checker.zip_manifest(folder / "controller/buzzer/evidence.zip", report, "buzzer")
    verified = set()
    for relative, expected in report["artifact_sha256"].items():
        path = checker.path(relative, relative_to=folder)
        assert digest(checker.read(path)) == expected
        verified.add(checker.label(path))
    direct = checker.direct_record(report["runtime_provenance"], manifest["session"], "buzzer", RUNTIME)
    assert report["firmware_sha256"] == controller["firmware_sha256"] == FIRMWARE[mode]
    assert detail["firmware_sha256"] == FIRMWARE[mode]
    assert detail["session_id"] == report["session_id"] == manifest["session"]["session_id"]
    assert detail["posts"] == [] and detail["annotation_mutation_requests"] == []
    helper = annotation_checks("buzzer", detail, [])
    for snapshot in detail["annotation_snapshots"]:
        event = detail["readbacks"][snapshot["http_event_index"]]
        body = detail["annotation_http_bodies"][snapshot["http_body_event_index"]]
        assert snapshot["http_event_index"] >= snapshot["phase_entry"]["readbacks_index"]
        assert snapshot["http_body_event_index"] >= snapshot["phase_entry"]["http_bodies_index"]
        assert snapshot["phase_entry"]["at"] <= event["at"] <= snapshot["at"]
        # Raw-body task completion can be timestamped after the DOM capture;
        # bind the complete payload to that pre-snapshot GET and verification.
        assert snapshot["phase_entry"]["at"] <= body["at"] <= snapshot["phase_verified_at"]
        assert event["method"] == body["method"] == "GET" and event["status"] == body["status"] == 200
        raw = (detail_path.parent / body["body_file"]).read_bytes()
        assert len(raw) == body["body_bytes"] and digest(raw) == body["body_sha256"]
        parsed = json.loads(raw)
        assert parsed == body["response"] == event["response"]
        properties = snapshot["readback"]["properties"]
        assert next(x for x in event["response"]["units"] if x["id"] == "external1")["properties"] == properties
        assert next(x for x in parsed["units"] if x["id"] == "external1")["properties"] == properties
        actual_text = {row["field"]: row["text"] for row in snapshot["note"]["fields"]}
        assert actual_text == {row["field"]: row["text"] for row in snapshot["expected_scalar_rows"]}
        assert all(row["value"] == properties[row["field"]] for row in snapshot["expected_scalar_rows"])
        assert snapshot["exact_http_controller_dom_alignment"] is True
    serial = (folder / "controller/buzzer/serial.txt").read_bytes().decode("utf-8")
    if mode == "custom":
        assert report["status"] == controller["status"] == "PASS" and all(value is True for value in report["checks"].values())
        assert all(helper.values())
        checker.controller_detail(report, report_path, verified)
        checker.browser_detail(report, report_path, verified, manifest)
        proof = controller["buzzer_timer_zero_observation"]
        matches = [serial[:end] for end in range(len(serial) + 1)
                   if digest(serial[:end].encode()) == proof["before_serial_sha256"]]
        assert len(matches) == 1 and proof["before_serial_sha256"] == proof["after_serial_sha256"]
        assert buzzer_timer_window(proof["qom"], matches[0], matches[0], proof["serial_offset"])
        assert "IO_BUZZER_TIMER_DONE" in serial[len(matches[0]):]
        assert controller["buzzer_callback_patch"]["original_driver_unchanged"] is True
        assert controller["buzzer_callback_patch"]["frozen_modules_modified"] is False
    else:
        assert report["status"] == controller["status"] == "FAIL"
        assert "before TIMER_DONE/manual output" in controller["error"]
        assert helper["annotation_phase_coverage"] is False
        assert [s["phase"] for s in detail["annotation_snapshots"]] == ["buzzer-0", "buzzer-1", "buzzer-2", "buzzer-once"]
        assert "buzzer_timer_zero_observation" not in controller and "buzzer_callback_patch" not in controller
    history = read_json(folder / "history.json")
    assert history["state"] == "stopped" and history["flash_retained"] is False
    return {"mode": mode, "status": report["status"], "firmware_sha256": FIRMWARE[mode],
            "phases": [s["phase"] for s in detail["annotation_snapshots"]],
            "artifacts_verified": len(verified), "zip_members": count, "direct_runtime": direct,
            "fresh_get_and_raw_body_alignment_replayed": True, "history_retained_flash_released": True}


def archive_pair(mode):
    folder = ROOT / f".work/unit-readout-buzzer-{mode}-20261026-r2/buzzer"
    report = read_json(folder / "report.json")
    copy(folder / "report.json", f"{mode}/report.json")
    for relative in sorted(report["artifact_sha256"]):
        copy(folder / relative, f"{mode}/{relative}")
    controller = read_json(folder / "controller/buzzer/result.json")
    for relative, expected in controller["probe_sha256"].items():
        source = folder / "controller/buzzer/files" / relative
        assert digest(source.read_bytes()) == expected
        target = f"{mode}/controller/buzzer/files/{relative}"
        if not any(row["archive"] == target for row in records):
            copy(source, target)
    copy(folder.parent / "source-freeze.json", f"{mode}/source-freeze.json")


def archive_diagnostic(mode):
    folder = ROOT / f".work/buzzer-once-live-20261026-{mode}-r1"
    result = read_json(folder / "result.json")
    assert result["firmware_sha256"] == FIRMWARE[mode] and result["runtime_sha256"] == RUNTIME
    assert result["status"] == "DIAGNOSTIC_COMPLETED" and result["functional_pass_inherited"] is False
    assert all(value is True for value in result["checks"].values())
    manifest = inspect_zip((folder / "evidence.zip").read_bytes(), mode)
    assert digest((folder / "evidence.zip").read_bytes()) == result["evidence_sha256"]
    assert manifest["session"]["firmware_sha256"] == FIRMWARE[mode]
    assert result["session_id"] == manifest["session"]["session_id"]
    # The diagnostic proof is embedded in this result and has no inner SID;
    # bind its enclosing result SID explicitly without rewriting raw evidence.
    Checker(folder, strict_direct=True).direct_record(
        {**result["runtime_provenance"], "session_id": result["session_id"]}, manifest["session"], "buzzer", RUNTIME)
    serial = (folder / "serial.txt").read_bytes().decode("utf-8")
    assert "BUZZER_DIAG_DONE" in serial
    if mode == "trace":
        assert "BUZZER_DIAG_EXCEPTION scheduler-thread TypeError" in serial
    for name in ("created-session.json", "evidence.zip", "final-frame.png", "health-after.json", "history-frame.png",
                 "http-index.json", "natural-frame.png", "prepared-input.json", "result.json", "serial.txt",
                 "source-sha256.json", "stopped-history.json", "zip-serial.txt"):
        copy(folder / name, f"diagnostic-{mode}/{name}")
    index = read_json(folder / "http-index.json")
    by_index = {row["index"]: row for row in index}
    selected = set()
    for observation in result["observations"]:
        for key in ("units_http_index", "serial_http_index"):
            number = observation.get(key)
            if number is not None:
                selected.add(number)
        if observation.get("serial_http_index") is None:
            # Resolve its actual serial body by the committed data-string hash.
            candidates = [row for row in index if row["index"] < observation["units_http_index"]
                          and row["method"] == "GET" and "/serial?" in row["path"]]
            for row in reversed(candidates):
                body = read_json(folder / row["response_file"])
                if digest(body.get("data", "").encode()) == observation["serial_sha256"]:
                    selected.add(row["index"])
                    break
            else:
                raise AssertionError("cannot bind diagnostic observation to archived serial body")
    for number in sorted(selected):
        row = by_index[number]
        assert row["method"] == "GET" and row["status"] == 200
        assert "/units" in row["path"] or "/serial?" in row["path"]
        source = folder / row["response_file"]
        assert digest(source.read_bytes()) == row["response_sha256"]
        copy(source, f"diagnostic-{mode}/{row['response_file']}")
    omitted = [row["response_file"] for row in index if row["index"] not in selected]
    retention[mode] = {"full_http_index_retained": True, "original_http_records": len(index),
                       "selected_observation_http_bodies": len(selected), "omitted_http_bodies": len(omitted),
                       "omission_scope": "Only actual result.observations units and same-data serial GET response bodies are copied; other HTTP bodies remain in private raw .work.",
                       "selected_indices": sorted(selected), "omitted_response_files": omitted}
    prepared = ROOT / f".work/buzzer-once-diagnostic-20261026/prepared-r1/{mode}/prepared.json"
    metadata = read_json(prepared)
    assert metadata["firmware_sha256"] == FIRMWARE[mode]
    copy(prepared, f"diagnostic-{mode}/prepared.json")
    for relative, expected in metadata["probe_sha256"].items():
        source = prepared.parent / "files" / relative
        assert digest(source.read_bytes()) == expected
        copy(source, f"diagnostic-{mode}/probe/{relative}")


assert not TARGET.exists() or "--resume-owned-partial" in sys.argv, "archive must be a new directory or an explicitly owned partial"
pair_review = [verify_pair(mode) for mode in ("original", "custom")]
TARGET.mkdir(parents=True, exist_ok="--resume-owned-partial" in sys.argv)
for mode in ("original", "custom"):
    archive_pair(mode)
for mode in ("natural", "trace"):
    archive_diagnostic(mode)

support = {
    ".work/buzzer-once-source-review-20261026": ["exact-source-receipt.json", "exact-source-demo-result.json",
        "exact_source_demo.py", "haptic-50e4407-verified.py", "soft_timer-50e4407-verified.py",
        "haptic-50e4407-http.json", "soft_timer-50e4407-http.json"],
    ".work/buzzer-ledc-readback-review-20261026": ["investigation.md", "investigation-receipt.json",
        "observed-phase-summary.json", "validated-base-app-desc.json", "machine_pwm-78ff170.c",
        "idf-ledc.c", "idf-ledc_hal.c", "idf-ledc_hal.h", "idf-ledc_hal_iram.c", "idf-s3-ledc_ll.h",
        "idf-s3-ledc_reg.h", "idf-s3-ledc_struct.h", "idf-s3-soc.h", "idf-s3-reg_base.h",
        "uiflow-50e4407-root-tree.json", "uiflow-github-tree.json", "idf-v5.5.5-ref.json", "idf-v5.5.5-tag.json",
        "uiflow-50e4407-README.md", "uiflow-build-release-50e4407.yml", "uiflow-build-firmware-50e4407.yml",
        *[f"fetch-batch{i}.json" for i in range(1, 7)]],
    ".work/buzzer-callback-adapter-independent-review-20261026": ["tests-r1.json"],
    ".work/buzzer-once-natural-independent-review-20261026": ["natural-be5fa5-independent-r1.json"],
    ".work/unit-buzzer-once-archive-20261026/metadata-history": [
        "SHA256SUMS-before-source-snapshot-suffix.txt",
        "archive-manifest-before-source-snapshot-suffix.json", "source-snapshot-format-amendment.json"],
}
for source_folder, names in support.items():
    category = ("metadata-history" if source_folder.endswith("/metadata-history") else
                "official-source" if "source-review" in source_folder else
                "getter-investigation" if "ledc-readback" in source_folder else "offline-review")
    for name in names:
        target_name = name + ".txt" if category == "getter-investigation" and name == "uiflow-50e4407-README.md" else name
        copy(ROOT / source_folder / name, f"{category}/{target_name}", sanitize_runtime_paths=True)
for name in ("tests/units/run_io_cases.py", "tests/units/run_annotation_cases.py", "tests/units/annotation_contract.py",
             "tests/units/test_buzzer_callback_adapter.py", "tests/units/test_annotation_cases.py",
             "tests/units/io_probe/io_drivers/buzzer.py", "tests/units/io_probe/io_drivers/source-manifest.json",
             "patches/uiflow2-unit-buzzer/0001-accept-soft-timer-callback.patch"):
    copy(ROOT / name, "source/" + name)
copy(Path(__file__).resolve(), "tools/archive.py")

README = """# Buzzer once：原版负控与显式 custom guest

2026-10-26，CoreS3 / QEMU 虚拟设备证据。runtime SHA256：`{runtime}`。硬件、声压、频谱和物理波形均 NOT RUN。

| 固件路径 | 最终 firmware SHA256 | 结果 |
| --- | --- | --- |
| 原版 reference app + 原官方 Unit wrapper | `{original}` | **FAIL**：TIMER_DONE/manual 前未观察到自动零；0/1/2/once 四阶段 |
| 显式 callback arity adapter custom guest | `{custom}` | **PASS（该 custom SHA）**：六阶段，timer-zero 在 TIMER_DONE/manual 前由实际 QOM 观察 |
| natural diagnostic custom guest | `{natural}` | DIAGNOSTIC_COMPLETED；原始 once 先观察3500ms，随后独立手动诊断 |
| trace diagnostic custom guest | `{trace}` | DIAGNOSTIC_COMPLETED；后台 scheduler-loop TypeError 被直接转到同 UART 并 re-raise |

builder 先打印 flat LittleFS 阶段 SHA，再打印含 package 的最终 SHA；本表、report、ZIP 和 prepared 使用最终 SHA。归档不含 BIN/ELF/ROM。

原版与 custom 共用同一 reference base（SHA `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`）及 runtime。默认未传 flag 和显式 False 的离线 prepare 都逐字节保持原版 d06e image。显式 `--buzzer-callback-arity-patch --case buzzer` 仅改 generated BuzzerUnit wrapper，接受可选 timer 参数后调用原 frozen `Haptic._cb()`；原 vendor wrapper SHA `a64cd1e918c92b97f3b0cd8c2e451416d0abfda7cd83aaef18883869f2e5c0c3` 不变，frozen Haptic/SoftTimer 和 QEMU 未改。上传固件默认语义未被替换。

原 IO 曾在 TIMER_DONE 后等待零，可能把随后 turn_off 的零当作 timer 证据。当前严格门禁在实际 QOM 两侧抓 serial，要求同 once anchor、完整前缀、真实数值零及2000±40Hz，且两侧均未出现 TIMER_DONE/后续 Buzzer 事件。原版在该门禁明确失败；旧 controller PASS 不能证明自动定时归零，也不能升级为本次 PASS。

natural：timer.dead 在到期前后 False→True，QOM仍约50%；后续 async sentinel不执行，实际 bound callback(timer_arg) 和 detached scheduler.update(original callback) 都 TypeError，no-arg callback能经真实写路径使 QOM为零。这是同固件路径的关联证据。trace 另一个 SHA 直接捕获后台同一签名 TypeError；其入口日志会改变线程时序，因此与 natural 独立列示。`scheduler._run=True` 只是属性，不能视为线程存活。

**Getter 差异仍 OPEN。** 实际 diagnostic guest PWM.duty_u16 getter 全程0，而同 session QOM 按50/25/0变化。固定 QEMU 源码写 shadow/observer 有实现，DUTY/DUTY_R read缺失；官方 MicroPython→IDF→S3 LL getter读取 DUTY_R bits18:0再右移4，与该症状相符。尚未采集实际 BIN getter 的动态 MMIO 地址，不能由源码推断直接结案。实际 app_desc 是 IDF v5.5.5-dirty，50e README/CI却写v5.5.4；归档官方clean v5.5.5参照不等于该dirty构建的完整源码绑定。见 getter-investigation。

`original/` 和 `custom/` 保留 report、其 artifact_sha256 白名单、原 evidence ZIP 和 probe source。`diagnostic-natural/`、`diagnostic-trace/` 保留 result、serial、ZIP、frames、history/health、prepared/source hashes 和实际 observation 对应的 units/serial原HTTP bodies。两者完整 http-index 保留；**其他原HTTP body未归档**，具体保留索引与省略文件见 http-retention.json，不宣称HTTP全量归档。

四份 ZIP 均通过白名单成员、内部manifest大小/SHA、CRC、PNG解码和隐私扫描，逐字节复制，原ZIP SHA未改。所有 raw .work 输入只读。少量 supporting review JSON 的本机runtime路径被替换为占位符，其 input/archived SHA及变更计数在 archive-manifest.json；运行report/ZIP/HTTP bodies保持原字节。未归档凭据、私网端点、MAC、私有绝对路径、二进制固件或缓存。SHA256SUMS覆盖目录内除自身外的全部文件。

上游 README 以 `getter-investigation/uiflow-50e4407-README.md.txt` 保存源码快照；其中相对链接按上游仓库目录解释，原文字节和SHA不变。此次后缀格式修正前的 SHA256SUMS 原字节（SHA `d80c56b255cceaa85c10f59c1dd0959c5f5ced8a43e82a6c7a978410610db4cf`）、原 archive-manifest 及修正记录保留在 metadata-history，均标为历史元数据。

独立复核重放 custom 的6阶段 fresh GET/body/DOM值、原始 serial前缀hash与timer窗口、direct PID/runtime/firmware/worker绑定；原版负控仍为FAIL。Python adapter16+annotation35共51/51离线PASS，真实LittleFS默认image连续性已测。截图和 guest/HTTP观察不是原子 LCD/DOM 采样；此记录不授其他 firmware SHA、board、controller、RF或硬件结论。
""".format(runtime=RUNTIME, **FIRMWARE)
(TARGET / "README.md").write_text(README, encoding="utf-8")
(TARGET / "http-retention.json").write_text(json.dumps(retention, indent=2) + "\n")
manifest = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "category": "safe-local-explicit-whitelist-evidence-archive", "raw_inputs_modified": False,
            "firmware_sha256": FIRMWARE, "runtime_sha256": RUNTIME, "files": records,
            "supporting_runtime_path_replacements": sum(row["runtime_path_replacements"] for row in records),
            "zip_bytes_preserved": True, "binary_firmware_included": False}
(TARGET / "archive-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
verification = {"status": "PASS", "scope": "Independent offline replay and archive checks; no API/session/QEMU execution",
                "pair_review": pair_review, "raw_inputs_modified": False,
                "source_files_modified_by_archiver": False, "runtime_sha256": RUNTIME,
                "hardware_execution": "NOT RUN", "getter_gap": "OPEN", "http_archive": "explicit observation subset"}
(TARGET / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
for path in TARGET.rglob("*"):
    if path.is_file():
        if path.suffix == ".zip":
            inspect_zip(path.read_bytes(), path.relative_to(TARGET).as_posix())
        elif path.suffix == ".png":
            png(path.read_bytes())
        else:
            safe_text(path.read_bytes(), path.relative_to(TARGET).as_posix())
checksum_files = sorted(path for path in TARGET.rglob("*") if path.is_file())
expected_files = {row["archive"] for row in records} | {"README.md", "http-retention.json", "archive-manifest.json", "verification.json"}
assert {path.relative_to(TARGET).as_posix() for path in checksum_files} - {"SHA256SUMS"} == expected_files
checksum_files = [path for path in checksum_files if path.name != "SHA256SUMS"]
(TARGET / "SHA256SUMS").write_text("".join(digest(path.read_bytes()) + "  " + path.relative_to(TARGET).as_posix() + "\n"
                                            for path in checksum_files), encoding="utf-8")
receipt = {"status": "PASS", "archive": TARGET.relative_to(ROOT).as_posix(),
           "files_including_checksums": len(checksum_files) + 1,
           "archive_manifest_sha256": digest((TARGET / "archive-manifest.json").read_bytes()),
           "sha256sums_sha256": digest((TARGET / "SHA256SUMS").read_bytes()),
           "bytes": sum(path.stat().st_size for path in TARGET.rglob("*") if path.is_file()),
           "pair_review": pair_review, "private_paths_credentials_macs_firmware_binaries": "none",
           "http_retention": {mode: {k: row[k] for k in ("original_http_records", "selected_observation_http_bodies", "omitted_http_bodies")}
                              for mode, row in retention.items()}}
(WORK / "archive-result.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
