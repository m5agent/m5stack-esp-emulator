#!/usr/bin/env python3
"""Prove that an unknown required firmware capability fails closed."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "platform/tools/firmware_manifest.py"
DEFAULT_IMAGE = (
    ROOT
    / "platform/.cache/firmware/community/2108939572843147265.bin"
)
DEFAULT_EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-unknown-required-capability-fail-closed.json"
)
FIRMWARE_ID = "2108939572843147265"
DEVICE_ID = "sticks3"
FLASH_SIZE = 8 << 20
EXPECTED_SOURCE_SHA256 = (
    "8b7b47c8d601e1821817f8d0e6b55568829913e50333dbcc15de6ffdbad1997c"
)
EXPECTED_NORMALIZED_SHA256 = (
    "d291e77f782399e37fd5b464f9b206a00654b2c10556d730d1c45667156c603f"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_import(
    input_path: Path,
    *,
    required: list[str],
    optional: list[str] | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="m5-capability-case-") as tmp:
        process = subprocess.run(
            [
                sys.executable,
                str(CLI),
                str(input_path),
                "--out-dir",
                tmp,
                "--device-id",
                DEVICE_ID,
                "--flash-size",
                hex(FLASH_SIZE),
                *[
                    argument
                    for capability in required
                    for argument in ("--require-capability", capability)
                ],
                *[
                    argument
                    for capability in optional or []
                    for argument in ("--optional-capability", capability)
                ],
                "--print",
                "summary",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    try:
        summary = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"manifest CLI returned non-JSON output: {process.stdout!r}"
        ) from error
    return {
        "exit_code": process.returncode,
        "status": summary["status"],
        "manifest_id": summary["manifest_id"],
        "artifact_sha256": summary["artifact_sha256"],
        "flash_size": summary["flash_size"],
        "soc": summary["soc"],
        "source_format": summary["source_format"],
        "errors": summary["errors"],
        "warnings": summary["warnings"],
    }


def build_webburner_package(image: bytes, root: Path) -> Path:
    root.mkdir(parents=True)
    parts = {
        "bootloader.bin": image[:0x8000],
        "partition-table.bin": image[0x8000:0x10000],
        "application.bin": image[0x10000:],
    }
    offsets = {
        "bootloader.bin": 0,
        "partition-table.bin": 0x8000,
        "application.bin": 0x10000,
    }
    rows = []
    for name, data in parts.items():
        (root / name).write_bytes(data)
        rows.append(
            {
                "path": name,
                "offset": offsets[name],
                "size": len(data),
                "sha256": sha256_bytes(data),
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": "Capability Fail-Closed Probe",
                "version": "1.0.0",
                "builds": [
                    {
                        "chipFamily": "ESP32-S3",
                        "parts": rows,
                    }
                ],
            }
        )
    )
    return root


def issue_codes(row: dict, field: str) -> list[str]:
    return [str(issue.get("code")) for issue in row[field]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--out", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()

    source = args.image.resolve()
    if not source.is_file():
        parser.error(f"firmware image is missing: {source}")
    source_sha256 = sha256_file(source)
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        parser.error(
            f"firmware SHA256 mismatch: {source_sha256}; "
            f"expected {EXPECTED_SOURCE_SHA256}"
        )

    merged_pass = run_import(
        source,
        required=["wifi"],
        optional=["camera"],
    )
    merged_unknown_required = run_import(
        source,
        required=["vendor-private-sensor"],
    )
    merged_unknown_optional = run_import(
        source,
        required=["wifi"],
        optional=["vendor-private-sensor"],
    )

    with tempfile.TemporaryDirectory(
        prefix="m5-capability-webburner-"
    ) as tmp:
        root = Path(tmp)
        package = build_webburner_package(
            source.read_bytes(),
            root / "package-a",
        )
        package_repeat = build_webburner_package(
            source.read_bytes(),
            root / "package-b",
        )
        webburner_pass = run_import(
            package,
            required=["wifi"],
            optional=["camera"],
        )
        webburner_repeat = run_import(
            package_repeat,
            required=["wifi"],
            optional=["camera"],
        )
        webburner_unknown_required = run_import(
            package,
            required=["vendor-private-sensor"],
        )

    checks = {
        "public_firmware_hash_bound": source_sha256
        == EXPECTED_SOURCE_SHA256,
        "merged_baseline_pass": merged_pass["status"] == "PASS"
        and merged_pass["exit_code"] == 0,
        "merged_unknown_required_rejected": (
            merged_unknown_required["status"] == "REJECTED"
            and merged_unknown_required["exit_code"] == 1
            and issue_codes(
                merged_unknown_required,
                "errors",
            )
            == ["unknown_required_capability"]
        ),
        "unknown_optional_remains_candidate": (
            merged_unknown_optional["status"] == "PASS"
            and merged_unknown_optional["exit_code"] == 0
            and "unknown_optional_capability"
            in issue_codes(merged_unknown_optional, "warnings")
        ),
        "webburner_baseline_pass": webburner_pass["status"] == "PASS"
        and webburner_pass["exit_code"] == 0
        and webburner_pass["source_format"] == "web-manifest",
        "webburner_unknown_required_rejected": (
            webburner_unknown_required["status"] == "REJECTED"
            and webburner_unknown_required["exit_code"] == 1
            and issue_codes(
                webburner_unknown_required,
                "errors",
            )
            == ["unknown_required_capability"]
        ),
        "merged_webburner_artifact_match": (
            merged_pass["artifact_sha256"]
            == webburner_pass["artifact_sha256"]
            == EXPECTED_NORMALIZED_SHA256
        ),
        "webburner_manifest_id_stable": (
            webburner_pass["manifest_id"]
            == webburner_repeat["manifest_id"]
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-capability-fail-closed",
        "date": "2026-10-26",
        "generated_from_artifact_mtime": datetime.fromtimestamp(
            source.stat().st_mtime,
            timezone.utc,
        ).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": (
            "static-manifest-capability-check-"
            "not-runtime-capability-proof"
        ),
        "sample": {
            "firmware_id": FIRMWARE_ID,
            "device_id": DEVICE_ID,
            "source_bytes": source.stat().st_size,
            "source_sha256": source_sha256,
            "normalized_flash_sha256": EXPECTED_NORMALIZED_SHA256,
        },
        "runs": {
            "merged_baseline": merged_pass,
            "merged_unknown_required": merged_unknown_required,
            "merged_unknown_optional": merged_unknown_optional,
            "webburner_baseline": webburner_pass,
            "webburner_repeat": webburner_repeat,
            "webburner_unknown_required": webburner_unknown_required,
        },
        "checks": checks,
        "boundary": {
            "boot": "NOT RUN",
            "network": "NOT RUN",
            "runtime_capability_call_path": "NOT RUN",
            "secure_boot_runtime": "NOT RUN",
            "physical_hardware": "NOT RUN",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
