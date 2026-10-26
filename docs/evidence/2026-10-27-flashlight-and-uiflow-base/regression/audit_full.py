"""Inspect completed evidence; never invokes a guest or alters the matrix result."""
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
result = json.loads((OUT / "full-result.json").read_bytes())
summary = json.loads((OUT / "full/summary.json").read_bytes())
request = json.loads((OUT / "full-request.json").read_bytes())
evidence = json.loads((OUT / "full-evidence-files.json").read_bytes())
for name, digest in request["runner_input_sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
os.environ.update(request["environment_overrides"])
spec = importlib.util.spec_from_file_location("regression_matrix_evidence_only", ROOT / "tests/uiflow2/run_peripheral_matrix.py")
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)
case_specs = {case["id"]: case for case in matrix.CASES}
missing, bad_png, command_gaps = [], [], []
runtime_counts = Counter()
serial_count = frame_count = raw_count = 0
for name, case in summary["results"].items():
    command = case["command"]
    if "--qemu" not in command:
        rebuilt = matrix.command_for(case_specs[name], Path(case["output"]), reference=case["reference_layout"])
        command_gaps.append({"case": name, "reported_command": command, "reconstructed_runner_command": rebuilt,
            "classification": "RECONSTRUCTED_FROM_MATCHING_RUNNER_SOURCE_AND_FIXED_ENV_NOT_CAPTURED_ARGV",
            "reason": "matrix validation command variable replaces the stored runner command for WS2812 checker"})
        command = rebuilt
    runtime = command[command.index("--qemu") + 1]
    rom = command[command.index("--rom-dir") + 1]
    is_c6 = name.startswith("nesso-")
    expected = request["environment_overrides"]["M5_QEMU_RISCV32" if is_c6 else "M5_QEMU_XTENSA"]
    expected_rom = request["environment_overrides"]["M5_QEMU_RISCV32_ROM_DIR" if is_c6 else "M5_QEMU_XTENSA_ROM_DIR"]
    assert runtime == expected and rom == expected_rom
    runtime_counts["c6" if is_c6 else "new-xtensa"] += 1
    assert case["status"] == "PASS" and case["attempts"] == 1 and not case["retry_used"]
    for artifact in (f"{name}.stdout", f"{name}.stderr", f"{name}/serial.log", f"{name}/before.png", f"{name}/after.png"):
        row = evidence[name].get(artifact)
        if row is None:
            missing.append(artifact)
            continue
        data = (OUT / "full" / artifact).read_bytes()
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
        if artifact.endswith(".png"):
            frame_count += 1
            if not row["png_signature_valid"]:
                bad_png.append(artifact)
        elif artifact.endswith("/serial.log"):
            serial_count += 1
        else:
            raw_count += 1
receipt = json.loads((OUT / "full-runtime-receipt-after.json").read_bytes())
audit = {"status": "PASS" if not missing and not bad_png else "FAIL", "matrix_pass_count": len(summary["results"]),
    "runtime_case_counts": dict(runtime_counts), "summary_runtime_commands_checked": len(summary["results"]) - len(command_gaps),
    "summary_command_provenance_gaps": command_gaps,
    "serial_log_count": serial_count, "frame_png_count": frame_count, "raw_stdout_stderr_count": raw_count,
    "missing_files": missing, "bad_png_signatures": bad_png, "all_recorded_file_hashes_match": True,
    "runner_inputs_unchanged": True, "xtensa_binary_sha256": receipt["xtensa_binary_sha256"],
    "c6_binary_sha256": receipt["c6_binary_sha256"], "source_files_manifest_sha256": receipt["source_files_manifest_sha256"],
    "full_result_sha256": hashlib.sha256((OUT / "full-result.json").read_bytes()).hexdigest(),
    "matrix_summary_sha256": hashlib.sha256((OUT / "full/summary.json").read_bytes()).hexdigest(),
    "targeted_results_inherited": False, "no_owned_qemu_remains": result["owned_qemu_stopped"]}
assert audit["status"] == "PASS" and serial_count == 67 and frame_count == 134 and raw_count == 134
(OUT / "full-evidence-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: value for key, value in audit.items() if key != "summary_command_provenance_gaps"}, ensure_ascii=False))
