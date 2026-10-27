#!/usr/bin/env python3
"""Verify archived source/output hashes; optionally compile and run C logic only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="compile standard-C programs and repeat 40 logic cases plus the real old-source negative")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_text())
    for name, item in manifest["files"].items():
        path = Path(name)
        assert not path.is_absolute() and ".." not in path.parts, name
        data = (root / path).read_bytes()
        assert len(data) == item["bytes"] and digest(data) == item["sha256"], name
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    assert actual == set(manifest["files"]) | {"manifest.json"}, "unlisted/missing archive file"

    provenance = json.loads((root / "source-provenance.json").read_text())
    for mode in ("candidate", "old"):
        for name, expected in provenance[mode + "_original_source_sha256"].items():
            assert digest((root / "sources" / mode / name).read_bytes()) == expected, name
        source_manifest = json.loads((root / (mode + "-source-manifest.json")).read_text())
        assert digest((root / "programs" / (mode + ".c")).read_bytes()) == source_manifest["program"]
    for mode in ("", "old-"):
        before = json.loads((root / ("whole-tu-" + mode + "source-before.json")).read_text())
        assert digest((root / ("whole-tu-" + mode + "harness.c")).read_bytes()) == before["harness.c"]
    assert (root / "whole-tu-source-before.json").read_bytes() == (root / "whole-tu-source-after.json").read_bytes()

    rows = json.loads((root / "portable-results.json").read_text())
    for row in rows:
        for stream in ("stdout", "stderr"):
            assert digest(row[stream + "_utf8"].encode()) == row[stream + "_sha256"]
    current = [row for row in rows if row["mode"] == "candidate"]
    old = [row for row in rows if row["mode"] == "old"]
    assert len(current) == 40 and all(row["returncode"] == 0 for row in current)
    assert len(old) == 1 and old[0]["returncode"] != 0
    assert "at-500001ns at=500001 known=0" in old[0]["stdout_utf8"]
    assert json.loads((root / "shared-runtime-regression.json").read_text())["status"] == "FAIL - NOT ACCEPTED"

    if args.run:
        compiler = shutil.which("cc")
        assert compiler, "C compiler unavailable"
        with tempfile.TemporaryDirectory() as temporary:
            for mode, cases in (("candidate", current), ("old", old)):
                binary = Path(temporary) / (mode + ".bin")
                command = [compiler, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                           "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                           "-DOLD_RUNTIME=" + str(int(mode == "old")),
                           str(root / "programs" / (mode + ".c")), "-o", str(binary)]
                compiled = subprocess.run(command, capture_output=True, timeout=30)
                assert compiled.returncode == 0, compiled.stderr.decode(errors="replace")
                for row in cases:
                    result = subprocess.run([str(binary), row["case"]], capture_output=True, timeout=5)
                    if mode == "candidate":
                        assert result.returncode == 0 and ("PASS " + row["case"]).encode() in result.stdout, row["case"]
                    else:
                        assert result.returncode != 0 and b"at-500001ns at=500001 known=0" in result.stdout
    print(json.dumps({"archive_hashes": "PASS", "original_source_hashes": "PASS",
                      "candidate_c_cases": 40, "old_cold_negative": "RETAINED FAIL",
                      "c_logic_repeated": args.run, "shared_runtime_regression": "FAIL - NOT ACCEPTED"}))


if __name__ == "__main__":
    main()
