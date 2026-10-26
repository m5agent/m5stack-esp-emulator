#!/usr/bin/env python3
"""Prove WebBurner package selection is deterministic and fail closed."""
from __future__ import annotations

import hashlib
import json
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_manifest import ManifestError, import_package  # noqa: E402
from test_firmware_analysis import build_flash  # noqa: E402

OUTPUT = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-webburner-import-policy.json"
)
TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "firmware_manifest": ROOT / "platform/tools/firmware_manifest.py",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_parts(root: Path, image: bytes) -> tuple[dict[str, bytes], dict[str, int]]:
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
    for name, data in parts.items():
        (root / name).write_bytes(data)
    return parts, offsets


def rejected(call) -> str:
    try:
        call()
    except ManifestError as error:
        return str(error)
    raise RuntimeError("expected ManifestError")


def main() -> int:
    tool_hashes_before = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    image = build_flash()
    with tempfile.TemporaryDirectory(prefix="m5-webburner-policy-") as tmp:
        temp = Path(tmp)
        multi = temp / "multi-build"
        multi.mkdir()
        parts, offsets = write_parts(multi, image)
        build = {
            "parts": [
                {
                    "path": name,
                    "offset": offsets[name],
                    "size": len(parts[name]),
                }
                for name in parts
            ]
        }
        (multi / "manifest.json").write_text(
            json.dumps(
                {
                    "name": "Multi Build",
                    "version": "1.0.0",
                    "builds": [
                        {"chipFamily": "ESP32-S3", **build},
                        {"chipFamily": "ESP32-C3", **build},
                    ],
                }
            )
        )
        selected = import_package(
            multi,
            temp / "out-selected",
            device_id="sticks3",
            flash_size=8 << 20,
        )["manifest"]
        no_device_error = rejected(
            lambda: import_package(multi, temp / "out-no-device")
        )
        wrong_soc_error = rejected(
            lambda: import_package(
                multi,
                temp / "out-wrong-soc",
                device_id="nesso-n1",
                flash_size=8 << 20,
            )
        )

        duplicate_manifest = temp / "duplicate-manifest"
        duplicate_manifest.mkdir()
        manifest_row = json.dumps({"builds": [{"chipFamily": "ESP32-S3", **build}]})
        (duplicate_manifest / "manifest.json").write_text(manifest_row)
        (duplicate_manifest / "web-manifest.json").write_text(manifest_row)
        duplicate_manifest_error = rejected(
            lambda: import_package(
                duplicate_manifest,
                temp / "out-duplicate-manifest",
                device_id="sticks3",
                flash_size=8 << 20,
            )
        )

        duplicate_sdkconfig = temp / "duplicate-sdkconfig"
        duplicate_sdkconfig.mkdir()
        (duplicate_sdkconfig / "firmware.bin").write_bytes(image)
        for name in ("a", "b"):
            directory = duplicate_sdkconfig / name
            directory.mkdir()
            (directory / "sdkconfig").write_text("CONFIG_SECURE_BOOT=n\n")
        duplicate_sdkconfig_error = rejected(
            lambda: import_package(
                duplicate_sdkconfig / "firmware.bin",
                temp / "out-duplicate-sdkconfig",
                device_id="sticks3",
                flash_size=8 << 20,
            )
        )

        duplicate_efuse = temp / "duplicate-efuse"
        duplicate_efuse.mkdir()
        (duplicate_efuse / "firmware.bin").write_bytes(image)
        for name in ("a", "b"):
            directory = duplicate_efuse / name
            directory.mkdir()
            (directory / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": False,
                            "readable": True,
                        },
                        "SPI_BOOT_CRYPT_CNT": {
                            "value": "Disable",
                            "readable": True,
                        },
                    }
                )
            )
        duplicate_efuse_error = rejected(
            lambda: import_package(
                duplicate_efuse / "firmware.bin",
                temp / "out-duplicate-efuse",
                device_id="sticks3",
                flash_size=8 << 20,
            )
        )

        collision_zip = temp / "collision.zip"
        with zipfile.ZipFile(collision_zip, "w") as archive:
            archive.writestr("A.bin", b"a")
            archive.writestr("a.bin", b"b")
        collision_error = rejected(
            lambda: import_package(
                collision_zip,
                temp / "out-collision",
            )
        )

        symlink_zip = temp / "symlink.zip"
        entry = zipfile.ZipInfo("firmware.bin")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(symlink_zip, "w") as archive:
            archive.writestr(entry, "target.bin")
        symlink_error = rejected(
            lambda: import_package(
                symlink_zip,
                temp / "out-symlink",
            )
        )

        dotdot_zip = temp / "dotdot.zip"
        with zipfile.ZipFile(dotdot_zip, "w") as archive:
            archive.writestr("dir/../firmware.bin", b"firmware")
        dotdot_error = rejected(
            lambda: import_package(
                dotdot_zip,
                temp / "out-dotdot",
            )
        )

        reserved_zip = temp / "reserved.zip"
        with zipfile.ZipFile(reserved_zip, "w") as archive:
            archive.writestr("CON.bin", b"firmware")
        reserved_error = rejected(
            lambda: import_package(
                reserved_zip,
                temp / "out-reserved",
            )
        )

        nested_collision_zip = temp / "nested-collision.zip"
        with zipfile.ZipFile(nested_collision_zip, "w") as archive:
            archive.writestr("A/file.bin", b"a")
            archive.writestr("a/other.bin", b"b")
        nested_collision_error = rejected(
            lambda: import_package(
                nested_collision_zip,
                temp / "out-nested-collision",
            )
        )

        duplicate_sbom = temp / "duplicate-sbom"
        duplicate_sbom.mkdir()
        (duplicate_sbom / "firmware.bin").write_bytes(image)
        (duplicate_sbom / "sbom.json").write_text(
            json.dumps({"bomFormat": "CycloneDX"})
        )
        (duplicate_sbom / "bom.json").write_text(
            json.dumps({"bomFormat": "CycloneDX"})
        )
        duplicate_sbom_error = rejected(
            lambda: import_package(
                duplicate_sbom / "firmware.bin",
                temp / "out-duplicate-sbom",
            )
        )

        sdkconfig_precedence = temp / "sdkconfig-precedence"
        sdkconfig_precedence.mkdir()
        (sdkconfig_precedence / "firmware.bin").write_bytes(image)
        (sdkconfig_precedence / "sdkconfig").write_text(
            "CONFIG_SECURE_BOOT=n\n"
        )
        (sdkconfig_precedence / "sdkconfig.defaults").write_text(
            "CONFIG_SECURE_BOOT=y\n"
        )
        selected_sdkconfig = import_package(
            sdkconfig_precedence / "firmware.bin",
            temp / "out-sdkconfig-precedence",
        )["manifest"]["resources"]["sdkconfig"]["file"]

        duplicate_defaults = temp / "duplicate-sdkconfig-defaults"
        duplicate_defaults.mkdir()
        (duplicate_defaults / "firmware.bin").write_bytes(image)
        (duplicate_defaults / "sdkconfig").write_text(
            "CONFIG_SECURE_BOOT=n\n"
        )
        for name in ("a", "b"):
            directory = duplicate_defaults / name
            directory.mkdir()
            (directory / "sdkconfig.defaults").write_text(
                "CONFIG_SECURE_BOOT=n\n"
            )
        duplicate_defaults_error = rejected(
            lambda: import_package(
                duplicate_defaults / "firmware.bin",
                temp / "out-duplicate-sdkconfig-defaults",
            )
        )

        duplicate_flasher = temp / "duplicate-flasher"
        duplicate_flasher.mkdir()
        (duplicate_flasher / "firmware.bin").write_bytes(image)
        for name in ("a", "b"):
            directory = duplicate_flasher / name
            directory.mkdir()
            (directory / "flasher_args.json").write_text(
                json.dumps({"flash_files": {"0x0": "../firmware.bin"}})
            )
        duplicate_flasher_error = rejected(
            lambda: import_package(duplicate_flasher, temp / "out-duplicate-flasher")
        )

        boolean_offset = temp / "boolean-offset"
        boolean_offset.mkdir()
        (boolean_offset / "firmware.bin").write_bytes(image)
        (boolean_offset / "manifest.json").write_text(
            json.dumps(
                {
                    "builds": [
                        {
                            "chipFamily": "ESP32-S3",
                            "parts": [
                                {
                                    "path": "firmware.bin",
                                    "offset": True,
                                }
                            ],
                        }
                    ]
                }
            )
        )
        boolean_offset_error = rejected(
            lambda: import_package(
                boolean_offset,
                temp / "out-boolean-offset",
                device_id="sticks3",
                flash_size=8 << 20,
            )
        )

    checks = {
        "target_build_selected": (
            selected["target"]["soc"] == "esp32s3"
            and selected["provenance"]["source_format"] == "web-manifest"
        ),
        "multi_build_requires_target": (
            "requires a target device" in no_device_error
        ),
        "multi_build_requires_unique_soc": (
            "exactly one build" in wrong_soc_error
        ),
        "multiple_web_manifests_rejected": (
            "multiple WebBurner manifests" in duplicate_manifest_error
        ),
        "multiple_sdkconfig_rejected": (
            "multiple sdkconfig resources" in duplicate_sdkconfig_error
        ),
        "multiple_efuse_rejected": (
            "multiple eFuse summaries" in duplicate_efuse_error
        ),
        "zip_case_collision_rejected": (
            "collide after normalization" in collision_error
        ),
        "zip_symlink_rejected": (
            "symlink entries" in symlink_error
        ),
        "zip_dotdot_rejected": "escapes root" in dotdot_error,
        "zip_reserved_name_rejected": "reserved name" in reserved_error,
        "zip_nested_case_collision_rejected": (
            "directory paths collide" in nested_collision_error
        ),
        "multiple_sbom_rejected": (
            "multiple sbom resources" in duplicate_sbom_error
        ),
        "sdkconfig_precedence_is_explicit": (
            selected_sdkconfig == "sdkconfig"
        ),
        "multiple_sdkconfig_defaults_rejected": (
            "multiple sdkconfig.defaults resources"
            in duplicate_defaults_error
        ),
        "multiple_flasher_args_rejected": (
            "multiple flasher_args.json" in duplicate_flasher_error
        ),
        "boolean_offset_rejected": (
            "has invalid offset" in boolean_offset_error
        ),
    }
    tool_hashes_after = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-webburner-import-policy",
        "date": "2026-10-26",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "static WebBurner import selection and path policy",
        "tool_hashes": tool_hashes_before,
        "input_assets_unchanged": tool_hashes_before == tool_hashes_after,
        "checks": checks,
        "errors": {
            "multi_build_no_device": no_device_error,
            "multi_build_wrong_soc": wrong_soc_error,
            "multiple_web_manifests": duplicate_manifest_error,
            "multiple_sdkconfig": duplicate_sdkconfig_error,
            "multiple_efuse": duplicate_efuse_error,
            "multiple_sbom": duplicate_sbom_error,
            "multiple_sdkconfig_defaults": duplicate_defaults_error,
            "multiple_flasher_args": duplicate_flasher_error,
            "boolean_offset": boolean_offset_error,
            "zip_case_collision": collision_error,
            "zip_symlink": symlink_error,
            "zip_dotdot": dotdot_error,
            "zip_reserved_name": reserved_error,
            "zip_nested_case_collision": nested_collision_error,
        },
        "boundary": {
            "flash": "NOT RUN",
            "boot": "NOT RUN",
            "runtime": "NOT RUN",
            "physical_hardware": "NOT RUN",
        },
    }
    OUTPUT.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
