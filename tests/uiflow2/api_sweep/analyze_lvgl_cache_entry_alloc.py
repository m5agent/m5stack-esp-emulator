#!/usr/bin/env python3
"""Check unchanged guest source against matching SDK allocator preimage/candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]
METADATA = ROOT / "patches/uiflow2-api/0018-lvgl-cache-entry-allocation.json"
PROBE = Path(__file__).with_name("probe_lvgl_cache_entry_alloc.py")
SIZES = (0, 4, 8, 16, 64)
METHODS = (
    "cache_entry_alloc", "cache_entry_get_entry", "cache_entry_alloc_zero_payload",
    "cache_entry_alloc_payload_write", "cache_entry_alloc_reference_lifecycle",
    "cache_entry_alloc_delete",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained(folder):
    report = json.loads((folder / "report.json").read_text())
    serial = (folder / "serial.txt").read_text()
    rows = [json.loads(line.split("M5EMU_UI_RESULT ", 1)[1]) for line in serial.splitlines()
            if line.startswith("M5EMU_UI_RESULT ")]
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        zip_valid = archive.testzip() is None
    return report, serial, rows, zip_valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preimage", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(METADATA.read_text())
    build = json.loads(args.build_receipt.read_text())
    old, old_serial, before, old_zip = retained(args.preimage)
    new, new_serial, after, new_zip = retained(args.candidate)
    correction = [row for row in build.get("corrections", []) if row.get("path") == metadata["path"]]
    old_alloc = [row for row in before if row.get("method") == "cache_entry_alloc"]
    expected = {(size, method) for size in SIZES for method in METHODS}
    seen = [(row.get("payload_size"), row.get("method")) for row in after]
    checks = {
        "build_success": build.get("status") == "BUILT_NOT_EXECUTED" and all(row.get("exit_code") == 0 for row in build.get("stages", [])),
        "exact_patch_provenance": len(correction) == 1 and all(correction[0].get(key) == metadata[key] for key in ("path", "preimage_sha256", "candidate_sha256"))
            and correction[0].get("patch_sha256") == digest(METADATA.with_suffix(".patch")),
        "candidate_source_hash": digest(args.build_receipt.parent / "source" / metadata["path"]) == metadata["candidate_sha256"],
        "original_build_inputs_preserved": all(build.get(key) is True for key in ("original_sources_unchanged", "original_library_unchanged", "original_binding_unchanged", "outside_application_unchanged")),
        "matching_sdk_preimage_base": old.get("base_sha256") == build.get("base_sha256"),
        "matching_sdk_candidate_base": new.get("base_sha256") == build.get("candidate_full_flash_sha256"),
        "separate_sdk_firmware_lanes": all(row.get("firmware_lane") != "stock-frozen" for row in (old, new)),
        "same_probe_bytes": old.get("source_sha256") == new.get("source_sha256") == digest(PROBE),
        "same_fixture_bytes": old.get("fixture_sha256") == new.get("fixture_sha256") == {},
        "same_runtime": old.get("runtime_binary_sha256") == new.get("runtime_binary_sha256") and bool(new.get("runtime_binary_sha256")),
        "both_guests_completed": all(row.get("status") == "EXECUTED" for row in (old, new)) and all("CACHE_ENTRY_ALLOC_DONE" in text for text in (old_serial, new_serial)),
        "old_raw_nonzero_allocations_fail": len(old_alloc) == len(SIZES) and all(row.get("status") == ("STATE_PASS" if row.get("payload_size") == 0 else "FAIL") for row in old_alloc)
            and {row.get("payload_size") for row in old_alloc} == set(SIZES),
        "old_zero_payload_compatibility": len(before) == 10 and all(row.get("status") == "STATE_PASS" for row in before if row.get("payload_size") == 0),
        "old_repair_only_after_failure": [int(line.split()[-1]) for line in old_serial.splitlines() if line.startswith("CACHE_ENTRY_ALLOC_CLEANUP_REPAIR ")] == list(SIZES[1:]),
        "candidate_no_manual_repair": "CACHE_ENTRY_ALLOC_CLEANUP_REPAIR" not in new_serial,
        "candidate_all_thirty_native_contracts": len(seen) == len(expected) and set(seen) == expected and all(row.get("status") == "STATE_PASS" for row in after),
        "candidate_exact_original_metadata": all(row.get("value") == [row["payload_size"], 0, True, False] for row in after if row.get("method") == "cache_entry_alloc"),
        "no_native_crash": not any(marker in text for text in (old_serial, new_serial) for marker in ("Guru Meditation", "stack overflow", "abort() was called", "A fatal error occurred")),
        "both_archives_valid": bool(old_zip and new_zip),
        "both_archive_hashes": all(digest(folder / "evidence.zip") == row.get("evidence_sha256") for folder, row in ((args.preimage, old), (args.candidate, new))),
        "both_firmware_hashes": all(digest(folder / "uiflow2-ui-test.bin") == row.get("firmware_sha256") for folder, row in ((args.preimage, old), (args.candidate, new))),
        "both_stopped_history_preserved": all(row.get("stopped") is True and row.get("cleanup", {}).get("history_preserved") is True for row in (old, new)),
        "both_runtime_pids_gone": all(row.get("cleanup", {}).get("runtime_pid_gone") is True for row in (old, new)),
    }
    result = {
        "schema_version": 1, "validation": "virtual-device validation", "hardware_validation": "NOT RUN",
        "status": "CANDIDATE_PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "scope": "Original native allocation metadata, zeroed full payload, independent metadata-preserving payload write, pointer roundtrip, reference lifecycle and delete on the ESP32 ABI. Stock results remain separate; candidate includes the explicitly recorded SDK patch stack.",
        "provenance": metadata,
        "build_receipt_sha256": digest(args.build_receipt),
        "evidence": {label: {"report": str(folder / "report.json"), **{key: row.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "base_sha256", "runtime_binary_sha256", "evidence_sha256", "cleanup")}}
                     for label, folder, row in (("preimage", args.preimage, old), ("candidate", args.candidate, new))},
    }
    (args.candidate / "cache-entry-alloc-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": checks}))
    return 0 if result["status"] == "CANDIDATE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
