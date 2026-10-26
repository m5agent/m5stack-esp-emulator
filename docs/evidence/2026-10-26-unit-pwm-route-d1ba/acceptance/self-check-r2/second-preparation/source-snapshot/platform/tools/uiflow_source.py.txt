"""Compose source into an admitted UIFlow2 base without executing guest code.

The caller owns firmware-family, chip, security and device admission. A mountable
LittleFS alone does not identify UIFlow2. This helper supports its current
``vfs`` data partition (subtype 0x81) and UIFlow2's run-main boot convention;
it is not a generic MicroPython or encrypted/signed-firmware importer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
import sys
import unicodedata

from firmware_analysis import (
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    parse_partition_table,
)

MAX_SOURCE_FILES = 128
MAX_SOURCE_BYTES = 1024 * 1024
MAX_FILE_BYTES = 256 * 1024
MAX_FLASH_BYTES = 64 * 1024 * 1024
MAX_PATH_BYTES = 512
MAX_PATH_DEPTH = 32
MAX_VFS_ENTRIES = 4096
DEFAULT_BOOT = "_uiflow_run_main = True\n"
FS_CONFIG = {
    "block_size": 4096,
    "read_size": 128,
    "prog_size": 32,
    "lookahead_size": 128,
    "block_cycles": 100,
}


class UIFlowSourceError(ValueError):
    """Stable service-neutral error, translated by the API layer."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _error(code: str, message: str, status: int = 400) -> None:
    raise UIFlowSourceError(code, message, status)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _source_files(files: dict[str, str]) -> tuple[dict[str, bytes], list[dict]]:
    if not isinstance(files, dict) or not files:
        _error("invalid_uiflow_source", "files must be a non-empty object")
    if len(files) > MAX_SOURCE_FILES:
        _error("uiflow_source_too_large", f"at most {MAX_SOURCE_FILES} caller files are allowed", 413)
    encoded, keys, total = {}, set(), 0
    for path, source in files.items():
        if not isinstance(path, str) or not isinstance(source, str):
            _error("invalid_uiflow_source", "file paths and source values must be strings")
        try:
            raw_path = path.encode("utf-8")
            payload = source.encode("utf-8")
        except UnicodeEncodeError:
            _error("invalid_uiflow_source", "file paths and source must be valid UTF-8")
        parts = path.split("/")
        if (
            not path or "\\" in path or ":" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or any(part in {"", ".", ".."} for part in parts)
            or PurePosixPath(path).is_absolute()
            or PurePosixPath(path).as_posix() != path
            or unicodedata.normalize("NFC", path) != path
            or not path.endswith(".py")
            or len(raw_path) > MAX_PATH_BYTES
            or len(parts) > MAX_PATH_DEPTH
            or any(len(part.encode("utf-8")) > 255 for part in parts)
        ):
            _error("invalid_uiflow_source_path", "paths must be canonical relative UTF-8 POSIX .py paths")
        key = _path_key(path)
        if key in keys:
            _error("uiflow_source_path_conflict", "source paths collide after Unicode/case normalization", 409)
        keys.add(key)
        if b"\x00" in payload:
            _error("invalid_uiflow_source", "Python source must not contain NUL bytes")
        if len(payload) > MAX_FILE_BYTES:
            _error("uiflow_source_too_large", f"each source file is limited to {MAX_FILE_BYTES} UTF-8 bytes", 413)
        total += len(payload)
        if total > MAX_SOURCE_BYTES:
            _error("uiflow_source_too_large", f"caller sources are limited to {MAX_SOURCE_BYTES} UTF-8 bytes", 413)
        encoded[path] = payload
    if "main.py" not in encoded:
        _error("invalid_uiflow_source", "a root main.py file is required")
    generated = "boot.py" not in encoded
    if generated:
        if _path_key("boot.py") in keys:
            _error("uiflow_source_path_conflict", "source path collides with generated boot.py", 409)
        encoded["boot.py"] = DEFAULT_BOOT.encode("utf-8")
    normalized = {_path_key(path) for path in encoded}
    for path in encoded:
        if any(_path_key(str(parent)) in normalized for parent in PurePosixPath(path).parents if str(parent) != "."):
            _error("uiflow_source_path_conflict", "a source file is also used as a parent directory", 409)
    rows = [
        {"path": path, "size": len(payload), "sha256": _sha(payload),
         "origin": "generated" if generated and path == "boot.py" else "caller"}
        for path, payload in sorted(encoded.items())
    ]
    return encoded, rows


def _layout(base: bytes, flash_size: int) -> dict:
    table = parse_partition_table(base, image_size=flash_size)
    if not table["valid"] or table["warnings"]:
        _error("invalid_uiflow_base", "base has an invalid or incomplete partition table")
    partitions = table["partitions"]
    named = [part for part in partitions if part["label"] == "vfs"]
    if len(named) != 1 or named[0]["type"] != 1 or named[0]["subtype"] != 0x81:
        _error("unsupported_uiflow_vfs", "base requires exactly one supported vfs data partition (subtype 0x81)", 409)
    intervals = []
    for part in partitions:
        start, size = part["offset"], part["size"]
        if size <= 0 or start < PARTITION_TABLE_OFFSET + PARTITION_TABLE_SIZE or start + size > flash_size:
            _error("invalid_uiflow_base", "base partition range is empty, reserved or outside flash")
        if any(start < end and other_start < start + size for other_start, end in intervals):
            _error("invalid_uiflow_base", "base partitions overlap")
        intervals.append((start, start + size))
    vfs = named[0]
    if vfs["flags"] != 0:
        _error("unsupported_uiflow_vfs", "flagged or encrypted VFS partitions are not supported", 409)
    if vfs["offset"] % 4096 or vfs["size"] % 4096 or vfs["size"] < 8192:
        _error("unsupported_uiflow_vfs", "VFS must contain at least two aligned 4096-byte blocks", 409)
    if vfs["offset"] + vfs["size"] > len(base):
        _error("invalid_uiflow_base", "base does not contain the complete existing VFS")
    return {"label": "vfs", "type": 1, "subtype": 0x81, "flags": 0,
            "offset": vfs["offset"], "size": vfs["size"],
            "partition_table_offset": table["offset"],
            "source": "actual-base-partition-table"}


def _snapshot(fs, vfs_size: int) -> tuple[dict, set[str]]:
    """Hash mounted files without exposing or decoding their contents."""
    files, directories, entries, logical_bytes = {}, set(), 0, 0
    pending = [("", 0)]
    while pending:
        directory, depth = pending.pop()
        if depth > MAX_PATH_DEPTH:
            _error("unsupported_uiflow_vfs", "base filesystem exceeds the supported directory depth", 409)
        for item in fs.scandir("/" + directory):
            entries += 1
            if entries > MAX_VFS_ENTRIES:
                _error("unsupported_uiflow_vfs", "base filesystem contains too many entries", 409)
            if not item.name or "/" in item.name or item.name in {".", ".."}:
                _error("unsupported_uiflow_vfs", "filesystem contains an invalid directory entry", 409)
            path = directory + "/" + item.name if directory else item.name
            if item.type == item.TYPE_DIR:
                directories.add(path)
                pending.append((path, depth + 1))
            elif item.type == item.TYPE_REG:
                logical_bytes += item.size
                if item.size < 0 or logical_bytes > vfs_size:
                    _error("unsupported_uiflow_vfs", "filesystem file sizes exceed the VFS capacity", 409)
                with fs.open("/" + path, "rb") as handle:
                    payload = handle.read(item.size + 1)
                if len(payload) != item.size:
                    _error("uiflow_source_verification_failed", "filesystem file size and readback differ", 500)
                files[path] = {"size": item.size, "sha256": _sha(payload)}
            else:
                _error("unsupported_uiflow_vfs", "filesystem entry type is unsupported", 409)
    return files, directories


def _check_base_paths(files: dict[str, bytes], base_files: dict, base_dirs: set[str]) -> None:
    base_paths = {}
    for path in set(base_files) | base_dirs:
        key = _path_key(path)
        if key in base_paths and base_paths[key] != path:
            _error("uiflow_source_path_conflict", "base paths collide after Unicode/case normalization", 409)
        base_paths[key] = path
    file_keys = {_path_key(path) for path in base_files}
    dir_keys = {_path_key(path) for path in base_dirs}
    for path in files:
        key = _path_key(path)
        if key in dir_keys or (key in base_paths and base_paths[key] != path):
            _error("uiflow_source_path_conflict", "source path conflicts with an existing base path", 409)
        for parent in PurePosixPath(path).parents:
            if str(parent) == ".":
                continue
            parent_key = _path_key(str(parent))
            if parent_key in file_keys or (parent_key in base_paths and base_paths[parent_key] != str(parent)):
                _error("uiflow_source_path_conflict", "source parent conflicts with an existing base path", 409)


def _littlefs():
    try:
        import littlefs
    except (ImportError, OSError) as error:
        raise UIFlowSourceError("uiflow_source_dependency_unavailable", "compatible littlefs-python is required", 503) from error
    return littlefs


def _filesystem(littlefs, payload: bytearray):
    # LittleFS's default constructor formats after a failed mount. Never use it.
    return littlefs.LittleFS(context=littlefs.UserContext(buffer=payload),
        block_count=len(payload) // FS_CONFIG["block_size"], mount=False,
        filename_encoding="utf-8", **FS_CONFIG)


def build_uiflow_source_image(
    base: bytes,
    flash_size: int,
    files: dict[str, str],
    *,
    expected_base_sha256: str | None = None,
) -> tuple[bytes, dict]:
    """Return a derived image and hash-only provenance; never format or execute.

    Source limits apply to caller files; an absent boot.py adds the generated
    UIFlow2 run-main flag. All other existing VFS files/directories survive.
    A successful build is packaging evidence, not firmware or hardware PASS.
    """
    if not isinstance(base, bytes) or not base:
        _error("invalid_uiflow_base", "base must be non-empty immutable bytes")
    if type(flash_size) is not int or not 0 < flash_size <= MAX_FLASH_BYTES or flash_size % 4096:
        _error("invalid_uiflow_base", "flash_size must be a positive aligned size no larger than 64 MiB")
    if len(base) > flash_size:
        _error("invalid_uiflow_base", "base exceeds the declared flash size")
    base_sha = _sha(base)
    if expected_base_sha256 is not None:
        if not isinstance(expected_base_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_base_sha256):
            _error("invalid_uiflow_base", "expected_base_sha256 must be a lowercase SHA256")
        if expected_base_sha256 != base_sha:
            _error("uiflow_base_hash_mismatch", "base SHA256 does not match the requested immutable base", 409)
    encoded, source_rows = _source_files(files)
    layout = _layout(base, flash_size)
    littlefs = _littlefs()
    start, size = layout["offset"], layout["size"]
    vfs = bytearray(base[start:start + size])
    fs = _filesystem(littlefs, vfs)
    try:
        fs.mount()
    except Exception as error:
        raise UIFlowSourceError("uiflow_vfs_unmountable", "existing VFS cannot be mounted with the supported LittleFS layout", 409) from error
    try:
        before_files, before_dirs = _snapshot(fs, size)
        before_disk = fs.fs_stat().disk_version
        _check_base_paths(encoded, before_files, before_dirs)
        for path, payload in sorted(encoded.items()):
            parent = str(PurePosixPath(path).parent)
            if parent != ".":
                fs.makedirs("/" + parent, exist_ok=True)
            with fs.open("/" + path, "wb") as handle:
                if handle.write(payload) != len(payload):
                    _error("uiflow_source_verification_failed", "filesystem did not accept all source bytes", 500)
    except UIFlowSourceError:
        raise
    except Exception as error:
        status = 413 if getattr(error, "code", None) in {-28, -27} else 500
        code = "uiflow_vfs_full" if status == 413 else "uiflow_source_build_failed"
        raise UIFlowSourceError(code, "source files could not be written to the existing VFS", status) from error
    finally:
        already_failed = sys.exc_info()[0] is not None
        try:
            fs.unmount()
        except Exception as error:
            if not already_failed:
                raise UIFlowSourceError("uiflow_source_build_failed", "VFS unmount failed", 500) from error
    # A separate mount verifies persisted bytes, not a cached open handle.
    readback = _filesystem(littlefs, bytearray(vfs))
    mounted = False
    try:
        readback.mount()
        mounted = True
        after_files, after_dirs = _snapshot(readback, size)
        if set(after_files) != set(before_files) | set(encoded) or not before_dirs <= after_dirs:
            _error("uiflow_source_verification_failed", "VFS membership changed outside the submitted source paths", 500)
        for path, expected in before_files.items():
            if path not in encoded and after_files.get(path) != expected:
                _error("uiflow_source_verification_failed", "an original VFS file changed unexpectedly", 500)
        for path, payload in encoded.items():
            with readback.open("/" + path, "rb") as handle:
                if handle.read() != payload:
                    _error("uiflow_source_verification_failed", "persisted source bytes differ from submitted UTF-8", 500)
        after_disk = readback.fs_stat().disk_version
    except UIFlowSourceError:
        raise
    except Exception as error:
        raise UIFlowSourceError("uiflow_source_verification_failed", "derived VFS could not be read back", 500) from error
    finally:
        already_failed = sys.exc_info()[0] is not None
        if mounted:
            try:
                readback.unmount()
            except Exception as error:
                if not already_failed:
                    raise UIFlowSourceError("uiflow_source_verification_failed", "readback VFS unmount failed", 500) from error
    image = bytearray(base)
    image.extend(b"\xff" * (flash_size - len(image)))
    image[start:start + size] = vfs
    result = bytes(image)
    if len(result) != flash_size or result[:start] != base[:start] or result[start + size:len(base)] != base[start + size:]:
        _error("uiflow_source_verification_failed", "image bytes outside VFS changed", 500)
    caller_rows = [row for row in source_rows if row["origin"] == "caller"]
    def bundle(payload):
        return _sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    metadata = {
        "schema_version": 1, "kind": "uiflow2-source-composition", "status": "COMPOSED_NOT_EXECUTED",
        "firmware_family_precondition": "caller-admitted-UIFlow2-base", "entrypoint": "main.py",
        "base_sha256": base_sha, "base_size": len(base), "flash_size": flash_size,
        "source_sha256": bundle({row["path"]: encoded[row["path"]].decode("utf-8") for row in caller_rows}),
        "effective_source_sha256": bundle({path: payload.decode("utf-8") for path, payload in encoded.items()}),
        "source_hash_format": "canonical-json-utf8-path-to-source/v1",
        "files": source_rows, "caller_file_count": len(caller_rows),
        "caller_source_bytes": sum(row["size"] for row in caller_rows),
        "generated_files": [row["path"] for row in source_rows if row["origin"] == "generated"],
        "firmware_sha256": _sha(result), "vfs": {**layout, "filesystem": "LittleFS",
            "base_sha256": _sha(base[start:start + size]), "derived_sha256": _sha(vfs),
            "base_disk_version": before_disk, "derived_disk_version": after_disk},
        "preservation": {"base_file_count": len(before_files),
            "preserved_file_count": len(set(before_files) - set(encoded)),
            "overwritten_files": sorted(set(before_files) & set(encoded)),
            "outside_vfs_unchanged": True, "existing_files_readback_verified": True,
            "source_readback_verified": True},
        "toolchain": {"builder": "uiflow_source/1", "python": sys.version.split()[0],
            "python_abi": sys.implementation.cache_tag,
            "littlefs_python": str(getattr(littlefs, "__version__", "unknown")),
            "littlefs_library": str(littlefs.__LFS_VERSION__),
            "littlefs_disk": str(littlefs.__LFS_DISK_VERSION__), "config": dict(FS_CONFIG)},
    }
    return result, metadata
