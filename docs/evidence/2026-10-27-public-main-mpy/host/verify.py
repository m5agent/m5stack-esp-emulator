#!/usr/bin/env python3
"""Verify this host archive without a checkout, API, guest or probe execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
DIGEST = re.compile(r"[0-9a-f]{64}")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def result_log(relative, tests, *, success):
    value = text(relative)
    found = re.findall(r"(?m)^Ran (\d+) tests in ([0-9.]+)s\s*$", value)
    require(len(found) == 1 and int(found[0][0]) == tests, relative + ": test count")
    if success:
        require(re.search(r"\nOK\s*\Z", value) is not None, relative + ": terminal OK")
    else:
        require(re.search(r"\nFAILED \([^\n]+\)\s*\Z", value) is not None, relative + ": preserved terminal failure")
    return float(found[0][1])


def validate_source_receipt(relative, snapshots):
    receipt = document(relative)
    mapping = receipt.get("sources_sha256", receipt.get("source_sha256", {}))
    for source, digest in mapping.items():
        path = snapshots + source + ".txt"
        require((ROOT / path).is_file(), relative + ": missing original snapshot " + source)
        require(sha((ROOT / path).read_bytes()) == digest, relative + ": snapshot hash " + source)
    return receipt


def main():
    index = document("index.json")
    summary = document("summary.json")
    require(index.get("schema_version") == 1 and index.get("status") == "PASS", "index schema/status")
    require(index.get("inventory_controls") == ["index.json"], "only index is an unindexed control")
    seen, by_path, by_source, by_fingerprint, counts = set(), {}, {}, {}, {}
    for row in index["files"]:
        relative = row.get("archive_path")
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute()
                and ".." not in Path(relative).parts and relative not in seen, "unsafe/duplicate archive path")
        seen.add(relative)
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink(), "missing/symlink archive file: " + relative)
        raw = path.read_bytes()
        raw.decode("utf-8", errors="strict")
        require(type(row.get("bytes")) is int and row["bytes"] == len(raw), relative + ": bytes")
        require(isinstance(row.get("archive_sha256"), str) and DIGEST.fullmatch(row["archive_sha256"])
                and sha(raw) == row["archive_sha256"], relative + ": archive SHA")
        kind = row.get("classification")
        require(kind in {"original", "generated", "redacted-json", "redacted-text"}, relative + ": classification")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "original":
            require(row.get("original_sha256") == row["archive_sha256"] and isinstance(row.get("source"), str),
                    relative + ": original identity")
            by_source.setdefault(row["source"], []).append(row)
        if kind.startswith("redacted"):
            require(DIGEST.fullmatch(row.get("original_sha256", "")) and row["original_sha256"] != row["archive_sha256"],
                    relative + ": distinct redacted fingerprint")
        require(not relative.endswith((".bin", ".rom", ".elf", ".zip", ".mpy", ".md")), relative + ": unsupported artifact")
        if relative.endswith(".py"):
            require(relative == "verify.py", "captured Python must retain .py.txt suffix")
        by_path[relative] = row
        by_fingerprint.setdefault((len(raw), sha(raw)), []).append(relative)
    actual = set()
    for path in ROOT.rglob("*"):
        require(not path.is_symlink(), "archive symlink")
        if path.is_file():
            actual.add(str(path.relative_to(ROOT)))
    require(actual == seen | {"index.json"}, "exact inventory coverage: " + str(sorted(actual ^ (seen | {"index.json"}))))
    require(by_path["verify.py"]["classification"] == "generated"
            and index.get("verifier_sha256") == by_path["verify.py"]["archive_sha256"] == sha(Path(__file__).read_bytes()),
            "verifier self SHA")

    # Each historical failure remains a failure; a later PASS cannot relabel it.
    result_log("tests/platform-r1.log", 1213, success=False)
    require("platform/tools/uiflow_main_loader.py is missing from docs/code-map.md" in text("tests/platform-r1.log"),
            "first platform failure reason")
    seconds = result_log("tests/platform-r2.log", 1213, success=True)
    require(summary["full_platform"]["r1"]["status"] == "FAIL"
            and summary["full_platform"]["r2"]["status"] == "PASS"
            and summary["full_platform"]["r2"]["tests"] == 1213
            and summary["full_platform"]["r2"]["seconds"] == seconds, "platform result summary")
    require("FAILED (" in text("tests/device-r1.log"), "earlier device failure retained")
    for lane, status, exit_code in (("r1", "FAIL", 1), ("r2", "PASS", 0)):
        receipt = validate_source_receipt(f"independent/{lane}/index.json", f"independent/{lane}/sources/")
        require(receipt["status"] == status and receipt["exit_code"] == exit_code,
                "independent " + lane + " result")
        require(receipt["log_sha256"] == sha((ROOT / f"independent/{lane}/tests.log").read_bytes()),
                "independent " + lane + " log SHA")
    old_probe = validate_source_receipt("independent/preview-preflight-review-r1/index.json",
                                        "independent/preview-preflight-review-r1/sources/")
    require(old_probe["exit_code"] == 1 and "FAILED (" in text("independent/preview-preflight-review-r1/probe.log"),
            "historical Preview negative failure retained")

    # Compare only the archived generation-45 snapshots to its launch receipt.
    # Later repository/spec changes are outside this portable archive's scope.
    launch = document("service/gen45/start.json")
    sources = launch["source_sha256"]
    require(len(sources) == 83 and launch["source_stable_across_start"] is True, "gen45 source receipt")
    require(launch["health"]["capacity"]["worker"]["generation"] == 45
            and launch["health"]["capacity"]["worker"]["pid"] == launch["pid"], "gen45 worker identity")
    prefix = "source-snapshots/gen45/"
    snapshot_rows = {path[len(prefix):-4]: row for path, row in by_path.items() if path.startswith(prefix) and path.endswith(".txt")}
    exclusions = {row["source"]: row for row in index["excluded"]}
    require(len(snapshot_rows) == 81 and len(exclusions) == 2 and not (set(snapshot_rows) & set(exclusions))
            and set(snapshot_rows) | set(exclusions) == set(sources), "gen45 exact 81 plus 2 source partition")
    for source, row in snapshot_rows.items():
        require(row["classification"] == "original" and row["source"] == source
                and row["original_sha256"] == sources[source], "gen45 original source SHA: " + source)
    for source, row in exclusions.items():
        require(row["sha256"] == sources[source] and type(row["bytes"]) is int and row["bytes"] > 0
                and row.get("reason"), "gen45 excluded fingerprint: " + source)
    require(summary["captured_source_files"] == 81 and summary["source_receipt_files"] == 83
            and summary["excluded_source_fingerprints"] == index["excluded"], "source summary partition")

    folder = "independent/final-offline-audit-r1/"
    audit = document(folder + "index.json")
    require(audit["status"] == "PASS" and audit["api_contacted"] is False
            and audit["guest"] == audit["hardware"] == "NOT RUN" and audit["compiler_rebuild"] == "NOT RUN",
            "offline audit scope")
    require(all(audit[key] is True for key in ("source_unchanged", "original_r1_unchanged", "archive_unchanged", "portable_copies_exact_and_unchanged")),
            "offline audit preserved inputs")
    for command, row in audit["commands"].items():
        require(row["exit_code"] == 0 and Path(row["log"]).name == row["log"], "offline audit command result")
        raw = (ROOT / folder / row["log"]).read_bytes()
        require(sha(raw) == row["log_sha256"] and raw.decode("utf-8") == row["output"], "offline audit original log: " + command)
    for source, row in audit["sources_sha256"].items():
        require((row["bytes"], row["sha256"]) in by_fingerprint, "offline source receipt absent from host snapshots: " + source)
    for source, row in audit["original_r1_sha256"].items():
        matches = by_source.get(source, [])
        require(any(item["bytes"] == row["bytes"] and item["original_sha256"] == row["sha256"] for item in matches),
                "offline retained original failure SHA: " + source)
    for name in ("original-preview-negative", "old-run-preservation"):
        result_log(folder + name + ".log", 2, success=True)
    require(sha((ROOT / folder / "original-preview-negative.py.txt").read_bytes())
            == sha((ROOT / "independent/preview-preflight-review-r1/probe.py.txt").read_bytes()), "reused negative probe original bytes")
    preservation = text(folder + "old-run-preservation.log")
    for case, error in (("bits32", "program_mpy_incompatible"), ("revoke", "program_mpy_entrypoint_unsupported")):
        found = re.search(r'\{"case": "' + case + r'"[^\n]*\}', preservation)
        require(found is not None, "missing preservation case")
        row = json.loads(found.group())
        require(row["status"] == 409 and row["code"] == error and row["old_run_unchanged"] is True
                and row["session_program_unchanged"] is True and row["cancel_event_set"] is False
                and row["generation_unchanged"] is True, "negative rejection old-state proof")
    api = json.loads(text(folder + "api-runtime-portable.log"))
    web = json.loads(text(folder + "web-portable.log"))
    require(api["status"] == web["status"] == "PASS" and api["api_contacted"] is False
            and api["guests_started"] == 0 and web["hardware"] == "NOT RUN", "portable-copy verifier outputs")
    require(summary["independent_final_offline_audit"]["fresh_negative_tests"] == 4
            and summary["original_failures_preserved"] is True and summary["hardware"] == "NOT RUN", "host summary scope")
    print(json.dumps({"status": "PASS", "category": "PORTABLE_HOST_ARCHIVE_VERIFICATION",
                      "archive_files": len(seen), "classifications": counts, "utf8_files": len(seen),
                      "platform_tests": 1213, "platform_r1": "FAIL PRESERVED", "platform_r2": "PASS",
                      "gen45_source_snapshots": 81, "gen45_excluded_fingerprints": 2,
                      "fresh_negative_tests": 4, "api_contacted": False,
                      "guest": "NOT RUN", "hardware": "NOT RUN"}, sort_keys=True))


if __name__ == "__main__":
    main()
