#!/usr/bin/env python3
"""Verify and optionally rebuild frozen independent UNIT-HOST-38 C evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-out", type=Path)
    ap.add_argument("--check-sources", action="store_true")
    ap.add_argument("--allow-missing-executables", action="store_true",
                    help="archive may retain only fingerprints of .work Mach-O harnesses")
    args = ap.parse_args()
    if args.rebuild_out:
        args.rebuild_out.mkdir(parents=True, exist_ok=False)
    results = []
    for folder, expected_failures, expected_exit in [("old-r3", 152, 1), ("candidate-r2", 0, 0)]:
        root = ROOT / folder
        receipt = json.loads((root / "receipt.json").read_text())
        assert receipt["compile_exit"] == 0 and receipt["run_exit"] == expected_exit
        assert receipt["api_contacted"] is False and receipt["guest_execution"] == receipt["hardware_execution"] == "NOT RUN"
        for entry in receipt["files"]:
            path = root / entry["path"]
            if args.allow_missing_executables and entry["path"] == "harness" and not path.exists():
                continue
            data = path.read_bytes()
            assert len(data) == entry["bytes"] and sha(data) == entry["sha256"], path
            if path.name != "harness":
                data.decode("utf-8")
        tests = (root / "harness.c").read_text().split("/* Tests are independent of the candidate helper:", 1)[1]
        tests = "/* Tests are independent of the candidate helper:" + tests
        assert sha(tests.encode()) == receipt["tests_sha256"]
        events = [json.loads(line) for line in (root / "stdout.txt").read_text().splitlines()]
        summary = events[-1]
        assert summary["event"] == "SUMMARY" and summary["cases"] == 26 and summary["checks"] == 357
        assert summary["failures"] == expected_failures and summary["result"] == ("FAIL" if expected_failures else "PASS")
        cases = [e for e in events if e["event"] == "CASE_RESULT"]
        assert len(cases) == summary["cases"]
        assert sum(e["checks"] for e in cases) == summary["checks"]
        assert sum(e["failures"] for e in cases) == summary["failures"]
        assert len([e for e in events if e["event"] == "FAIL"]) == expected_failures
        observed = [e for e in events if e["event"] == "ROUNDTRIP_OBSERVED"]
        assert len(observed) == 10
        for event in observed:
            assert event["known_internal"] == event["active_internal"] == event["known_getter"] == (1 if expected_failures else 0)
            assert event["edges_before"] == event["edges_after"]
            assert event["decoded_before"] == event["decoded_after"]
            assert event["original_timeout_ns"] < 0 or event["now_ns"] < event["original_timeout_ns"]
        if args.check_sources:
            for fragment in receipt["fragments"]:
                data = Path(fragment["source_path"]).read_bytes()
                assert sha(data) == fragment["source_sha256"], fragment["source_path"]
                lines = data.decode("utf-8").splitlines(keepends=True)
                snippet = "".join(lines[fragment["start_line"] - 1:fragment["end_line"]])
                archived = (root / fragment["fragment_file"]).read_text()
                assert archived in snippet
                assert sha(archived.encode()) == fragment["fragment_sha256"]
        rerun = None
        if args.rebuild_out:
            out = args.rebuild_out / folder
            out.mkdir()
            argv = ["/usr/bin/clang", "-std=c11", "-O0", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-function", str(root / "harness.c"), "-o", str(out / "harness")]
            build = subprocess.run(argv, capture_output=True)
            (out / "compile.stdout.txt").write_bytes(build.stdout)
            (out / "compile.stderr.txt").write_bytes(build.stderr)
            assert build.returncode == 0
            run = subprocess.run([str(out / "harness")], capture_output=True)
            (out / "stdout.txt").write_bytes(run.stdout)
            (out / "stderr.txt").write_bytes(run.stderr)
            assert run.returncode == expected_exit
            assert run.stdout == (root / "stdout.txt").read_bytes()
            assert run.stderr == (root / "stderr.txt").read_bytes()
            rerun = {"compile_argv": argv, "compile_exit": build.returncode, "run_exit": run.returncode,
                     "stdout_sha256": sha(run.stdout), "stderr_sha256": sha(run.stderr)}
        results.append({"folder": folder, "tests_sha256": receipt["tests_sha256"], "summary": summary, "rebuild": rerun})
    assert results[0]["tests_sha256"] == results[1]["tests_sha256"] == sha((ROOT / "cases.c").read_bytes())
    payload = {"result": "PASS", "category": "independent-controller-C-regression", "api_contacted": False,
               "guest_execution": "NOT RUN", "hardware_execution": "NOT RUN", "comparisons": results}
    if args.rebuild_out:
        (args.rebuild_out / "verification.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
