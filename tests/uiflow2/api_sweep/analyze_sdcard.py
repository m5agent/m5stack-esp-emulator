#!/usr/bin/env python3
"""Observe the real owned SPI disk and immutable source after a visible session.

The retained guest transcript proves block writes and remounted FAT readback.
An independent host check locates the exact unique file payload in the actual
session disk, hashes its changed bytes and verifies source-artifact immutability.
Raw copies remain in the ignored run directory, never source Git.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--service-state", type=Path, required=True)
    parser.add_argument("--file-pattern-bytes", type=int, default=256)
    args = parser.parse_args()
    report = json.loads((args.run / "report.json").read_text())
    stopped = json.loads((args.run / "stopped.json").read_text())
    sid = report["session_id"]
    artifact = stopped["storage"]["artifact_id"]
    if not re.fullmatch("[a-f0-9]{32}", sid) or not re.fullmatch("[a-f0-9]{64}", artifact):
        raise ValueError("invalid session or artifact identity")
    session_disk = args.service_state / "sessions" / sid / "sd-card.img"
    source = args.service_state / "artifacts" / (artifact + ".bin")
    raw, original = session_disk.read_bytes(), source.read_bytes()
    if not 1 <= args.file_pattern_bytes <= 65536:
        raise ValueError("file pattern must be 1..65536 bytes")
    payload = b"M5EMU_SD_FILE_ORACLE_20261027\n" + bytes((i * 7 + 0x31) & 255 for i in range(args.file_pattern_bytes))
    transcript = (args.run / "serial.txt").read_text()
    assertions = [json.loads(line.split("HARDWARE_API ", 1)[1]) for line in transcript.splitlines() if "HARDWARE_API " in line]
    guest_pass = any(row.get("api") == "hardware.SDCard" and row.get("status") == "API_ASSERTION_PASS" for row in assertions)
    from pyfatfs.PyFatFS import PyFatFS
    with PyFatFS(str(session_disk), read_only=True) as filesystem:
        host_file = filesystem.readbytes("/api-sweep.bin")
    checks = {
        "guest_block_and_remount_assertions": guest_pass,
        "source_hash_still_matches_artifact": sha(original) == artifact,
        "owned_disk_changed": sha(raw) != artifact,
        "distinct_payload_present_once_in_owned_disk": raw.count(payload) == 1,
        "payload_absent_from_source_artifact": payload not in original,
        "independent_host_fat_file_matches": host_file == payload,
        "isolated_disk_has_same_capacity": len(raw) == len(original),
        "runtime_stopped": report.get("cleanup", {}).get("runtime_pid_gone") is True,
    }
    output = {
        "schema_version": 1, "device": report["device_id"],
        "status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL",
        "oracle": "Same-session SPI block roundtrip, FAT file write/sync and exact remount readback; independent retained session disk contains the unique complete payload, changed hash and same capacity while immutable source artifact hash stays unchanged.",
        "checks": checks, "source_artifact_sha256": artifact,
        "owned_disk_sha256": sha(raw), "payload_sha256": sha(payload),
        "payload_bytes": len(payload), "payload_offset": raw.find(payload),
        "evidence": {key: report.get(key) for key in ("session_id", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")},
    }
    output["evidence"]["report"] = str(args.run / "report.json")
    output["evidence"]["serial"] = str(args.run / "serial.txt")
    shutil.copyfile(session_disk, args.run / "sd-card-final.img")
    (args.run / "storage-oracle.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"device": output["device"], "status": output["status"], "checks": checks, "payload_offset": output["payload_offset"]}))
    return 0 if output["status"] == "DATA_PLANE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
