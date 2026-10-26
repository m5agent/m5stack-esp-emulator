"""One repository regression run; no Device Service session and no retries."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / ".work/unit-runtime-source-flashlight-final/qemu"
BINARY = SOURCE / "build/qemu-system-xtensa"
EXPECTED_BINARY_SHA = "7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e"


def sha(data):
    return hashlib.sha256(data).hexdigest()


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
            "binary": str(BINARY.relative_to(ROOT)), "binary_size": BINARY.stat().st_size,
            "binary_sha256": binary_sha, "binary_matches_parent_provided_sha256": True,
            "source_receipt": str(path.relative_to(ROOT)), "source_receipt_sha256": sha(declared_bytes),
            "qemu": declared["qemu"], "source_file_hashes": files, "source_files_match_receipt": True,
            "source_files_manifest_sha256": sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()),
            "patch_hashes": patches, "patches_match_receipt": True,
            "rom": "pc-bios/esp32s3_rev0_rom.bin",
            "rom_sha256": sha((SOURCE / "pc-bios/esp32s3_rev0_rom.bin").read_bytes())}


environment = dict(os.environ,
    M5_QEMU_XTENSA=str(BINARY), M5_QEMU_XTENSA_ROM_DIR=str(SOURCE / "pc-bios"),
    M5_PYTHON_DEPS=str(ROOT / ".work/py312"), PYTHONPATH=str(ROOT / ".work/py312"))
listing_command = [sys.executable, "tests/uiflow2/run_peripheral_matrix.py", "--list-json"]
listing = subprocess.run(listing_command, cwd=ROOT, env=environment, capture_output=True, check=True)
(OUT / "matrix-list.json").write_bytes(listing.stdout)
cases = json.loads(listing.stdout)
selected = [case for case in cases if case["id"] == "cores3-peripherals"]
assert len(selected) == 1
target = OUT / "targeted"
target.mkdir(exist_ok=False)
command = [sys.executable, "tests/uiflow2/run_peripheral_matrix.py", "--case", "cores3-peripherals", "--out-dir", str(target)]
before = receipt()
save("runtime-receipt-before.json", before)
runner_sources = [Path("tests/uiflow2/run_peripheral_matrix.py"), Path("tests/uiflow2/run_profile_ui_test.py"),
                  *sorted(Path("tests/uiflow2/cores3_peripherals").rglob("*.py"))]
save("request.json", {"classification": "DIRECT_REPOSITORY_REGRESSION_NOT_DEVICE_SERVICE_FUNCTIONAL_SESSION",
    "selected": selected, "matrix_cases_listed": len(cases), "argv": command,
    "environment_overrides": {key: environment[key] for key in ("M5_QEMU_XTENSA", "M5_QEMU_XTENSA_ROM_DIR", "M5_PYTHON_DEPS", "PYTHONPATH")},
    "runner_input_sha256": {str(path): sha(path.read_bytes()) for path in runner_sources},
    "retry_policy": "DISABLED", "full_matrix": "NOT STARTED; requires explicit parent START"})
started = time.monotonic()
with (OUT / "targeted.stdout.log").open("wb") as stdout, (OUT / "targeted.stderr.log").open("wb") as stderr:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
after = receipt()
save("runtime-receipt-after.json", after)
assert {key: value for key, value in before.items() if key != "generated_at"} == {key: value for key, value in after.items() if key != "generated_at"}
matrix_summary = json.loads((target / "summary.json").read_bytes()) if (target / "summary.json").is_file() else None
summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
    "elapsed_seconds": round(time.monotonic() - started, 3), "matrix_summary": matrix_summary,
    "binary_and_source_receipt_unchanged": True, "retry_policy": "DISABLED",
    "device_service_sessions_started": 0, "full_matrix": "NOT STARTED",
    "stdout_sha256": sha((OUT / "targeted.stdout.log").read_bytes()),
    "stderr_sha256": sha((OUT / "targeted.stderr.log").read_bytes())}
save("targeted-result.json", summary)
print(json.dumps({"exit_code": result.returncode, "elapsed_seconds": summary["elapsed_seconds"],
    "results": matrix_summary["results"] if matrix_summary else None, "evidence": str(OUT.relative_to(ROOT))}, ensure_ascii=False))
raise SystemExit(result.returncode)
