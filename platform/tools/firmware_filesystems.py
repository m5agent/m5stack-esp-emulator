#!/usr/bin/env python3
"""Inventory firmware data partitions without exposing file contents."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

LITTLEFS_SUBTYPE = 0x83
SPIFFS_SUBTYPE = 0x82
FAT_SUBTYPE = 0x81
MAX_FILES = 512
MAX_DIRECTORIES = 512
MAX_LICENSE_BYTES = 256 * 1024
SPDX_RE = re.compile(
    r"SPDX-License-Identifier:\s*([A-Za-z0-9.+\-() ]+)"
)
LICENSE_NAMES = {
    "copying",
    "copying.txt",
    "license",
    "license.md",
    "license.txt",
    "notice",
    "notice.txt",
    "unlicense",
}
SENSITIVE_PATH_RE = re.compile(
    r"(?:^|/)(?:\.env(?:\..*)?|credentials?(?:\..*)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|"
    r"private[^/]*|secrets?(?:\..*)?|passwd|shadow|"
    r"[^/]+\.(?:key|p12|pfx))$",
    re.IGNORECASE,
)
SCRIPT_SUFFIXES = {".py", ".pyc", ".lua", ".js", ".mjs"}
CONFIG_SUFFIXES = {
    ".conf",
    ".ini",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}
CERTIFICATE_SUFFIXES = {
    ".cer",
    ".crt",
    ".der",
    ".pem",
    ".p12",
    ".pfx",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public_path(path: str) -> tuple[str, str | None, bool]:
    if not SENSITIVE_PATH_RE.search(path):
        return path, None, False
    return "<redacted-sensitive-path>", _sha256(path.encode()), True


def _file_kind(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if name in LICENSE_NAMES or "license" in name or "notice" in name:
        return "license"
    if SENSITIVE_PATH_RE.search(path):
        return "sensitive"
    if suffix in SCRIPT_SUFFIXES:
        return "script"
    if suffix in CERTIFICATE_SUFFIXES:
        return "certificate"
    if suffix in CONFIG_SUFFIXES:
        return "config"
    return "resource"


def _hash_stream(handle: object) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _list_littlefs(data: bytes, partition: dict) -> dict:
    try:
        from littlefs import LittleFS, UserContext
    except ImportError:
        return {
            **partition,
            "type": "littlefs",
            "status": "UNAVAILABLE",
            "errors": ["littlefs-python is not installed"],
        }

    errors: list[str] = []
    for block_size in (4096, 8192, 2048, 1024, 512):
        if len(data) < block_size or len(data) % block_size:
            continue
        context = UserContext(buffer=bytearray(data))
        filesystem = LittleFS(
            context=context,
            block_size=block_size,
            block_count=len(data) // block_size,
            mount=False,
        )
        try:
            filesystem.mount()
        except Exception as error:
            errors.append(f"block {block_size}: {error}")
            continue

        files: list[dict] = []
        directories: list[str] = []
        sensitive_files: list[dict] = []
        license_files: list[dict] = []
        declared_licenses: set[str] = set()
        total_file_bytes = 0
        truncated = False
        listing_error: str | None = None
        block_count = filesystem.block_count
        used_block_count = filesystem.used_block_count
        try:
            for root, dir_names, file_names in filesystem.walk("/"):
                root = root.rstrip("/") or "/"
                for name in dir_names:
                    path = f"{root}/{name}" if root != "/" else f"/{name}"
                    if len(directories) >= MAX_DIRECTORIES:
                        truncated = True
                        break
                    directories.append(path)
                if truncated:
                    break
                for name in file_names:
                    path = f"{root}/{name}" if root != "/" else f"/{name}"
                    if len(files) >= MAX_FILES:
                        truncated = True
                        break
                    stat = filesystem.stat(path)
                    with filesystem.open(path, "rb") as handle:
                        file_hash = _hash_stream(handle)
                    display_path, path_hash, redacted = _public_path(path)
                    kind = _file_kind(path)
                    row = {
                        "path": display_path,
                        "size": stat.size,
                        "sha256": file_hash,
                        "kind": kind,
                        "permissions": "not-recorded",
                    }
                    if path_hash is not None:
                        row["path_sha256"] = path_hash
                        row["redacted"] = redacted
                    files.append(row)
                    total_file_bytes += stat.size
                    if kind == "sensitive":
                        sensitive_files.append(
                            {
                                "path": display_path,
                                "path_sha256": _sha256(path.encode()),
                                "sha256": file_hash,
                            }
                        )
                    if kind == "license":
                        with filesystem.open(path, "rb") as handle:
                            text = handle.read(MAX_LICENSE_BYTES).decode(
                                "utf-8",
                                errors="ignore",
                            )
                        licenses = sorted(
                            {
                                value.strip()
                                for value in SPDX_RE.findall(text)
                            }
                        )
                        declared_licenses.update(licenses)
                        license_files.append(
                            {
                                "path": display_path,
                                "sha256": file_hash,
                                "declared_licenses": licenses,
                            }
                        )
                if truncated:
                    break
        except Exception as error:
            listing_error = str(error)
        finally:
            filesystem.unmount()

        return {
            **partition,
            "type": "littlefs",
            "status": "PARTIAL" if listing_error else "PASS",
            "errors": [listing_error] if listing_error else [],
            "block_size": block_size,
            "block_count": block_count,
            "used_block_count": used_block_count,
            "file_count": len(files),
            "directory_count": len(directories),
            "total_file_bytes": total_file_bytes,
            "files": files,
            "directories": directories,
            "sensitive_files": sensitive_files,
            "license_files": license_files,
            "declared_licenses": sorted(declared_licenses),
            "limits": {
                "files_truncated": truncated,
                "max_files": MAX_FILES,
                "max_directories": MAX_DIRECTORIES,
            },
            "not_claimed": [
                "file contents",
                "runtime permissions",
                "license compliance",
            ],
        }
    return {
        **partition,
        "type": "littlefs",
        "status": "INVALID",
        "errors": errors[:16],
    }


def inventory_data_partition(data: bytes, partition: dict) -> dict | None:
    offset = partition.get("offset")
    size = partition.get("size")
    subtype = partition.get("subtype")
    if (
        not isinstance(offset, int)
        or not isinstance(size, int)
        or offset < 0
        or size <= 0
        or offset >= len(data)
    ):
        return None
    window = data[offset : min(offset + size, len(data))]
    header = {
        "label": partition.get("label"),
        "subtype": subtype,
        "offset": offset,
        "size": size,
        "sha256": _sha256(window),
    }
    if subtype == LITTLEFS_SUBTYPE or b"littlefs" in window[:64]:
        return _list_littlefs(window, header)
    if subtype == SPIFFS_SUBTYPE:
        return {
            **header,
            "type": "spiffs",
            "status": "UNSUPPORTED",
            "errors": ["SPIFFS inventory is not implemented"],
        }
    if (
        subtype == FAT_SUBTYPE
        or (len(window) >= 512 and window[510:512] == b"\x55\xaa")
    ):
        return {
            **header,
            "type": "fat",
            "status": "UNSUPPORTED",
            "errors": ["FAT inventory is not implemented"],
        }
    return None


def inventory_flash_filesystems(
    data: bytes,
    partition_table: dict,
) -> list[dict]:
    results: list[dict] = []
    for partition in partition_table.get("partitions", []):
        if partition.get("type") != 1:
            continue
        row = inventory_data_partition(data, partition)
        if row is not None:
            results.append(row)
    return results
