"""One complete repository matrix round, without retries or service sessions."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / ".work/unit-runtime-source-flashlight-final/qemu"
BINARY = SOURCE / "build/qemu-system-xtensa"
EXPECTED_BINARY_SHA = "7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e"
C6_BINARY = Path(os.environ.get("M5_QEMU_RISCV32", ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32")).resolve()
C6_ROM = Path(os.environ.get("M5_QEMU_RISCV32_ROM_DIR", ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/pc-bios")).resolve()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relative(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def receipt():
    path = SOURCE / ".m5-unit-runtime-source.json"
    declared_bytes = path.read_bytes()
    declared = json.loads(declared_bytes)
    files = {name: sha((SOURCE / name).read_bytes()) for name in declared["files"]}
    patches = {name: sha((ROOT / name).read_bytes()) for name in declared["patches"]}
    binary_sha = sha(BINARY.read_bytes())
    assert binary_sha == EXPECTED_BINARY_SHA
    assert files == declared["files"] and patches == declared["patches"]
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "xtensa_binary": relative(BINARY), "xtensa_binary_size": BINARY.stat().st_size,
            "xtensa_binary_sha256": binary_sha, "binary_matches_parent_provided_sha256": True,
            "source_receipt": relative(path), "source_receipt_sha256": sha(declared_bytes),
            "qemu": declared["qemu"], "source_file_hashes": files, "source_files_match_receipt": True,
            "source_files_manifest_sha256": sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()),
            "patch_hashes": patches, "patches_match_receipt": True,
            "xtensa_rom_dir": relative(SOURCE / "pc-bios"),
            "xtensa_rom_hashes": {p.name: sha(p.read_bytes()) for p in sorted((SOURCE / "pc-bios").glob("esp32*rom*.bin"))},
            "c6_binary": relative(C6_BINARY), "c6_binary_sha256": sha(C6_BINARY.read_bytes()),
            "c6_rom_dir": relative(C6_ROM),
            "c6_rom_hashes": {p.name: sha(p.read_bytes()) for p in sorted(C6_ROM.glob("esp32c6*rom*.bin"))}}


environment = dict(os.environ,
    M5_QEMU_XTENSA=str(BINARY), M5_QEMU_XTENSA_ROM_DIR=str(SOURCE / "pc-bios"),
    M5_QEMU_RISCV32=str(C6_BINARY), M5_QEMU_RISCV32_ROM_DIR=str(C6_ROM),
    M5_PYTHON_DEPS=str(ROOT / ".work/py312"), PYTHONPATH=str(ROOT / ".work/py312"))
listing_command = [sys.executable, "tests/uiflow2/run_peripheral_matrix.py", "--list-json"]
listing = subprocess.run(listing_command, cwd=ROOT, env=environment, capture_output=True, check=True)
(OUT / "full-matrix-list.json").write_bytes(listing.stdout)
cases = json.loads(listing.stdout)
assert len(cases) == 67
target = OUT / "full"
target.mkdir(exist_ok=False)
command = [sys.executable, "tests/uiflow2/run_peripheral_matrix.py", "--out-dir", str(target)]
before = receipt()
save("full-runtime-receipt-before.json", before)
runner_sources = [Path("tests/uiflow2/run_peripheral_matrix.py"), Path("tests/uiflow2/run_profile_ui_test.py"),
                  Path("platform/peripherals/runtime-coverage.json")]
for case in cases:
    if case.get("files_dir"):
        runner_sources.extend(sorted(Path(case["files_dir"]).rglob("*.py")))
save("full-request.json", {"classification": "DIRECT_REPOSITORY_REGRESSION_NOT_DEVICE_SERVICE_FUNCTIONAL_SESSION",
    "selected_cases": cases, "argv": command,
    "environment_overrides": {key: environment[key] for key in ("M5_QEMU_XTENSA", "M5_QEMU_XTENSA_ROM_DIR", "M5_QEMU_RISCV32", "M5_QEMU_RISCV32_ROM_DIR", "M5_PYTHON_DEPS", "PYTHONPATH")},
    "runner_input_sha256": {str(path): sha(path.read_bytes()) for path in sorted(set(runner_sources))},
    "retry_policy": "DISABLED", "rounds_authorized": 1, "targeted_results_inherited": False})
started = time.monotonic()
with (OUT / "full.stdout.log").open("wb") as stdout, (OUT / "full.stderr.log").open("wb") as stderr:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
after = receipt()
save("full-runtime-receipt-after.json", after)
fixed_runtime = {key: value for key, value in before.items() if key != "generated_at"} == {key: value for key, value in after.items() if key != "generated_at"}
matrix_summary = json.loads((target / "summary.json").read_bytes()) if (target / "summary.json").is_file() else None
results = matrix_summary["results"] if matrix_summary else {}
counts = dict(Counter(case["status"] for case in results.values()))
processes = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True).splitlines()
owned = [line.strip() for line in processes if "qemu-system-" in line and str(target.resolve()) in line and "-qmp" in line]
artifacts = {}
for case in cases:
    name = case["id"]
    files = {}
    for artifact in (target / f"{name}.stdout", target / f"{name}.stderr", target / name / "serial.log", target / name / "before.png", target / name / "after.png"):
        if artifact.is_file():
            data = artifact.read_bytes()
            item = {"size": len(data), "sha256": sha(data)}
            if artifact.suffix == ".png":
                item["png_signature_valid"] = data[:8] == b"\x89PNG\r\n\x1a\n"
                item["dimensions"] = list(struct.unpack(">II", data[16:24])) if len(data) >= 24 else None
            files[str(artifact.relative_to(target))] = item
    artifacts[name] = files
save("full-evidence-files.json", artifacts)
no_retries = all(case.get("attempts") == 1 and not case.get("retry_used") for case in results.values())
complete = set(results) == {case["id"] for case in cases}
summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
    "elapsed_seconds": round(time.monotonic() - started, 3), "matrix_counts": counts,
    "case_count": len(results), "all_67_cases_present": complete,
    "status": "PASS" if result.returncode == 0 and complete and fixed_runtime and no_retries and not owned else "FAIL",
    "binary_and_source_receipt_unchanged": fixed_runtime, "one_attempt_each": no_retries,
    "active_owned_qemu_processes": owned, "owned_qemu_stopped": not owned,
    "retry_policy": "DISABLED", "device_service_sessions_started": 0,
    "rounds_run": 1, "targeted_results_inherited": False,
    "stdout_sha256": sha((OUT / "full.stdout.log").read_bytes()),
    "stderr_sha256": sha((OUT / "full.stderr.log").read_bytes()),
    "matrix_summary": "full/summary.json", "case_evidence_hashes": "full-evidence-files.json"}
save("full-result.json", summary)
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(0 if summary["status"] == "PASS" else 1)
