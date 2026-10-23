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
MAX_FAT_DEPTH = 32
MAX_FAT_DIRECTORY_ENTRIES = 65536
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
    r"(?:\.env(?:\..*)?|credentials?(?:\..*)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|"
    r"private[^/]*|secrets?(?:\..*)?|passwd|shadow|"
    r"[^/]+\.(?:key|p12|pfx))",
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


def _is_sensitive_path(path: str) -> bool:
    return any(
        part and SENSITIVE_PATH_RE.fullmatch(part)
        for part in path.split("/")
    )


def _public_path(path: str) -> tuple[str, str | None, bool]:
    if not _is_sensitive_path(path):
        return path, None, False
    return "<redacted-sensitive-path>", _sha256(path.encode()), True


def _file_kind(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if name in LICENSE_NAMES or "license" in name or "notice" in name:
        return "license"
    if _is_sensitive_path(path):
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


class _FatError(ValueError):
    pass


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


class _FatVolume:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 512:
            raise _FatError("FAT boot sector is truncated")
        if data[510:512] != b"\x55\xaa":
            raise _FatError("FAT boot-sector signature is missing")

        self.bytes_per_sector = _u16(data, 11)
        self.sectors_per_cluster = data[13]
        self.reserved_sectors = _u16(data, 14)
        self.fat_count = data[16]
        self.root_entry_count = _u16(data, 17)
        total_sectors_16 = _u16(data, 19)
        total_sectors_32 = _u32(data, 32)
        fat_sectors_16 = _u16(data, 22)
        fat_sectors_32 = _u32(data, 36)

        if (
            self.bytes_per_sector not in {512, 1024, 2048, 4096}
            or not _is_power_of_two(self.bytes_per_sector)
        ):
            raise _FatError("unsupported FAT bytes-per-sector")
        if (
            not _is_power_of_two(self.sectors_per_cluster)
            or self.sectors_per_cluster > 128
        ):
            raise _FatError("unsupported FAT sectors-per-cluster")
        if self.reserved_sectors <= 0:
            raise _FatError("FAT reserved-sector count is zero")
        if not 1 <= self.fat_count <= 4:
            raise _FatError("unsupported FAT copy count")

        self.total_sectors = total_sectors_16 or total_sectors_32
        self.fat_sectors = fat_sectors_16 or fat_sectors_32
        if self.total_sectors <= 0 or self.fat_sectors <= 0:
            raise _FatError("FAT total or table sector count is zero")
        if self.total_sectors * self.bytes_per_sector > len(data):
            raise _FatError("FAT volume is truncated")

        self.root_dir_sectors = (
            self.root_entry_count * 32 + self.bytes_per_sector - 1
        ) // self.bytes_per_sector
        metadata_sectors = (
            self.reserved_sectors
            + self.fat_count * self.fat_sectors
            + self.root_dir_sectors
        )
        data_sectors = self.total_sectors - metadata_sectors
        if data_sectors <= 0:
            raise _FatError("FAT volume has no data region")
        self.cluster_count = data_sectors // self.sectors_per_cluster
        if self.cluster_count <= 0:
            raise _FatError("FAT volume has no clusters")
        self.cluster_size = (
            self.bytes_per_sector * self.sectors_per_cluster
        )
        self.max_cluster = self.cluster_count + 1

        explicit_fat32 = (
            fat_sectors_16 == 0
            and fat_sectors_32 > 0
            and self.root_entry_count == 0
        )
        if explicit_fat32:
            self.fat_type = "fat32"
        elif self.cluster_count < 4085:
            self.fat_type = "fat12"
        elif self.cluster_count < 65525:
            self.fat_type = "fat16"
        else:
            self.fat_type = "fat32"

        if self.fat_type == "fat32":
            if self.root_entry_count != 0 or fat_sectors_16 != 0:
                raise _FatError("inconsistent FAT32 geometry")
            self.root_cluster = _u32(data, 44) & 0x0FFFFFFF
            if not 2 <= self.root_cluster <= self.max_cluster:
                raise _FatError("FAT32 root cluster is out of range")
        else:
            if self.root_entry_count <= 0:
                raise _FatError("FAT12/16 root entry count is zero")
            self.root_cluster = None

        self.fat_offset = self.reserved_sectors * self.bytes_per_sector
        self.fat_size = self.fat_sectors * self.bytes_per_sector
        fat_start = self.fat_offset
        fat_end = fat_start + self.fat_size
        if fat_end > len(data):
            raise _FatError("FAT table is truncated")
        self.fat_data = data[fat_start:fat_end]

        minimum_fat_bytes = {
            "fat12": ((self.cluster_count + 2) * 3 + 1) // 2,
            "fat16": (self.cluster_count + 2) * 2,
            "fat32": (self.cluster_count + 2) * 4,
        }[self.fat_type]
        if self.fat_size < minimum_fat_bytes:
            raise _FatError("FAT table is too small for the data clusters")

        self.root_dir_offset = (
            (self.reserved_sectors + self.fat_count * self.fat_sectors)
            * self.bytes_per_sector
        )
        self.first_data_sector = metadata_sectors
        declared_offset = 54 if self.fat_type != "fat32" else 82
        self.declared_filesystem = (
            data[declared_offset : declared_offset + 8]
            .rstrip(b"\x00 ")
            .decode("ascii", errors="replace")
        )

    def _is_eoc(self, value: int) -> bool:
        if self.fat_type == "fat12":
            return value >= 0xFF8
        if self.fat_type == "fat16":
            return value >= 0xFFF8
        return value >= 0x0FFFFFF8

    def _is_bad(self, value: int) -> bool:
        return {
            "fat12": 0xFF7,
            "fat16": 0xFFF7,
            "fat32": 0x0FFFFFF7,
        }[self.fat_type] == value

    def fat_entry(self, cluster: int) -> int:
        if not 2 <= cluster <= self.max_cluster:
            raise _FatError(f"cluster {cluster} is out of range")
        if self.fat_type == "fat12":
            offset = cluster + cluster // 2
            if offset + 1 >= len(self.fat_data):
                raise _FatError("FAT12 entry is outside the table")
            raw = self.fat_data[offset] | self.fat_data[offset + 1] << 8
            value = raw >> 4 if cluster & 1 else raw & 0x0FFF
        elif self.fat_type == "fat16":
            offset = cluster * 2
            if offset + 2 > len(self.fat_data):
                raise _FatError("FAT16 entry is outside the table")
            value = _u16(self.fat_data, offset)
        else:
            offset = cluster * 4
            if offset + 4 > len(self.fat_data):
                raise _FatError("FAT32 entry is outside the table")
            value = _u32(self.fat_data, offset) & 0x0FFFFFFF
        return value

    def cluster_chain(self, start: int, limit: int | None = None):
        if not 2 <= start <= self.max_cluster:
            raise _FatError(f"cluster chain starts out of range: {start}")
        maximum = limit if limit is not None else self.cluster_count + 1
        seen: set[int] = set()
        current = start
        for _ in range(maximum):
            if current in seen:
                raise _FatError("FAT cluster chain contains a loop")
            if not 2 <= current <= self.max_cluster:
                raise _FatError("FAT cluster chain points out of range")
            seen.add(current)
            yield current
            value = self.fat_entry(current)
            if self._is_eoc(value):
                return
            if self._is_bad(value):
                raise _FatError("FAT cluster chain contains a bad cluster")
            if value == 0:
                raise _FatError("FAT cluster chain reaches a free cluster")
            current = value
        if limit is None:
            raise _FatError("FAT cluster chain exceeds the volume")

    def cluster_bytes(self, cluster: int) -> bytes:
        if not 2 <= cluster <= self.max_cluster:
            raise _FatError(f"cluster {cluster} is out of range")
        sector = (
            self.first_data_sector
            + (cluster - 2) * self.sectors_per_cluster
        )
        offset = sector * self.bytes_per_sector
        end = offset + self.cluster_size
        if end > self.total_sectors * self.bytes_per_sector:
            raise _FatError(f"cluster {cluster} extends past the volume")
        return self.data[offset:end]

    def _short_name(self, raw: bytes, attributes: int) -> str:
        base = bytearray(raw[:8])
        extension = bytearray(raw[8:11])
        if base and base[0] == 0x05:
            base[0] = 0xE5
        base_text = bytes(base).rstrip(b" ").decode(
            "cp437",
            errors="replace",
        )
        extension_text = bytes(extension).rstrip(b" ").decode(
            "cp437",
            errors="replace",
        )
        nt_reserved = raw[12]
        if (attributes & 0x18) == 0:
            if nt_reserved & 0x08:
                base_text = base_text.lower()
            if nt_reserved & 0x10:
                extension_text = extension_text.lower()
        return (
            f"{base_text}.{extension_text}"
            if extension_text
            else base_text
        )

    def _directory_blocks(self, start_cluster: int | None, is_root: bool):
        if is_root and self.fat_type != "fat32":
            start = self.root_dir_offset
            end = start + self.root_dir_sectors * self.bytes_per_sector
            yield self.data[start:end]
            return
        cluster = (
            self.root_cluster if is_root else start_cluster
        )
        if cluster is None:
            raise _FatError("directory has no start cluster")
        for item in self.cluster_chain(cluster):
            yield self.cluster_bytes(item)

    def directory_entries(
        self,
        start_cluster: int | None,
        is_root: bool,
    ) -> list[dict]:
        entries: list[dict] = []
        lfn_slots: dict[int, tuple[bytes, int]] = {}
        raw_entry_count = 0
        saw_dot = False
        saw_dotdot = False
        for block in self._directory_blocks(start_cluster, is_root):
            for offset in range(0, len(block), 32):
                raw = block[offset : offset + 32]
                if len(raw) < 32 or raw[0] == 0x00:
                    if not is_root and not (saw_dot and saw_dotdot):
                        raise _FatError(
                            "subdirectory is missing . and .. entries"
                        )
                    return entries
                raw_entry_count += 1
                if raw_entry_count > MAX_FAT_DIRECTORY_ENTRIES:
                    raise _FatError("FAT directory entry limit reached")
                if raw[0] == 0xE5:
                    lfn_slots.clear()
                    continue

                attributes = raw[11]
                if attributes == 0x0F:
                    sequence = raw[0] & 0x1F
                    if 1 <= sequence <= 20:
                        lfn_slots[sequence] = (raw, raw[13])
                    continue
                if (
                    attributes & 0xC0
                    or raw[18] != 0
                    or raw[19] != 0
                    or b"\x00" in raw[:11]
                ):
                    lfn_slots.clear()
                    continue

                short_name = self._short_name(raw, attributes)
                long_name = short_name
                if lfn_slots:
                    sequences = sorted(lfn_slots)
                    if sequences == list(range(1, sequences[-1] + 1)):
                        checksums = {
                            checksum for _, checksum in lfn_slots.values()
                        }
                        characters: list[str] = []
                        for sequence in sequences:
                            lfn_raw = lfn_slots[sequence][0]
                            encoded = (
                                lfn_raw[1:11]
                                + lfn_raw[14:26]
                                + lfn_raw[28:32]
                            )
                            characters.append(
                                encoded.decode(
                                    "utf-16le",
                                    errors="replace",
                                )
                            )
                        candidate = "".join(characters).split("\x00", 1)[0]
                        if (
                            len(checksums) == 1
                            and next(iter(checksums))
                            == _fat_short_name_checksum(bytes(raw[:11]))
                            and lfn_slots[sequences[-1]][0][0] & 0x40
                            and candidate
                        ):
                            long_name = candidate
                lfn_slots.clear()

                if short_name == ".":
                    saw_dot = True
                    continue
                if short_name == "..":
                    saw_dotdot = True
                    continue
                if attributes & 0x08:
                    continue
                name = _fat_safe_name(long_name)
                cluster = _u16(raw, 26)
                if self.fat_type == "fat32":
                    cluster |= _u16(raw, 20) << 16
                entries.append(
                    {
                        "name": name,
                        "attributes": attributes,
                        "cluster": cluster & 0x0FFFFFFF,
                        "size": _u32(raw, 28),
                        "directory": bool(attributes & 0x10),
                    }
                )
        if not is_root and not (saw_dot and saw_dotdot):
            raise _FatError("subdirectory is missing . and .. entries")
        return entries

    def read_file(self, start_cluster: int, size: int) -> tuple[str, bytes]:
        if size == 0:
            return _sha256(b""), b""
        if start_cluster < 2:
            raise _FatError("non-empty FAT file has no start cluster")
        cluster_total = (size + self.cluster_size - 1) // self.cluster_size
        digest = hashlib.sha256()
        prefix = bytearray()
        remaining = size
        read = 0
        for cluster in self.cluster_chain(start_cluster, limit=cluster_total):
            payload = self.cluster_bytes(cluster)
            take = min(remaining, len(payload))
            chunk = payload[:take]
            digest.update(chunk)
            if len(prefix) < MAX_LICENSE_BYTES:
                prefix.extend(chunk[: MAX_LICENSE_BYTES - len(prefix)])
            remaining -= take
            read += take
            if remaining == 0:
                break
        if read != size:
            raise _FatError(
                f"FAT file is truncated: expected {size} bytes, read {read}"
            )
        return digest.hexdigest(), bytes(prefix)


def _fat_short_name_checksum(name: bytes) -> int:
    value = 0
    for byte in name:
        value = (((value & 1) << 7) + (value >> 1) + byte) & 0xFF
    return value


def _fat_safe_name(name: str) -> str:
    cleaned = (
        name.replace("\x00", "")
        .replace("/", "_")
        .replace("\\", "_")
        .strip()
    )
    return cleaned[:255] or "<unnamed>"


def _list_fat(data: bytes, partition: dict) -> dict:
    try:
        volume = _FatVolume(data)
    except _FatError as error:
        return {
            **partition,
            "type": "fat",
            "status": "INVALID",
            "errors": [str(error)],
        }

    files: list[dict] = []
    directories: list[str] = []
    redacted_directories: list[dict] = []
    sensitive_files: list[dict] = []
    license_files: list[dict] = []
    declared_licenses: set[str] = set()
    listing_errors: list[str] = []
    total_file_bytes = 0
    files_truncated = False
    directories_truncated = False
    visited_directory_clusters: set[int] = (
        {volume.root_cluster} if volume.root_cluster is not None else set()
    )

    stack: list[tuple[int | None, bool, str, int]] = [
        (volume.root_cluster, True, "/", 0)
    ]
    while stack and not (files_truncated or directories_truncated):
        start_cluster, is_root, parent, depth = stack.pop()
        if not is_root and start_cluster is not None:
            if start_cluster in visited_directory_clusters:
                listing_errors.append(
                    "FAT directory cluster is referenced more than once"
                )
                continue
            visited_directory_clusters.add(start_cluster)
        try:
            entries = volume.directory_entries(start_cluster, is_root)
        except _FatError as error:
            listing_errors.append(str(error))
            continue

        child_directories: list[tuple[int, str, int]] = []
        for entry in entries:
            name = entry["name"]
            path = f"{parent}/{name}" if parent != "/" else f"/{name}"
            if entry["directory"]:
                display_path, path_hash, redacted = _public_path(path)
                if len(directories) >= MAX_DIRECTORIES:
                    directories_truncated = True
                    break
                directories.append(display_path)
                if path_hash is not None:
                    redacted_directories.append(
                        {
                            "path": display_path,
                            "path_sha256": path_hash,
                        }
                    )
                if depth + 1 > MAX_FAT_DEPTH:
                    listing_errors.append(
                        f"FAT directory depth exceeds {MAX_FAT_DEPTH}"
                    )
                    continue
                if entry["cluster"] < 2:
                    listing_errors.append(
                        f"FAT directory has invalid cluster: {display_path}"
                    )
                    continue
                child_directories.append(
                    (entry["cluster"], path, depth + 1)
                )
                continue

            display_path, path_hash, redacted = _public_path(path)
            if len(files) >= MAX_FILES:
                files_truncated = True
                break
            try:
                file_hash, prefix = volume.read_file(
                    entry["cluster"],
                    entry["size"],
                )
            except _FatError as error:
                listing_errors.append(f"{display_path}: {error}")
                continue
            kind = _file_kind(path)
            row = {
                "path": display_path,
                "size": entry["size"],
                "sha256": file_hash,
                "kind": kind,
                "permissions": "not-recorded",
                "attributes": f"0x{entry['attributes']:02x}",
            }
            if path_hash is not None:
                row["path_sha256"] = path_hash
                row["redacted"] = redacted
            files.append(row)
            total_file_bytes += entry["size"]
            if kind == "sensitive":
                sensitive_files.append(
                    {
                        "path": display_path,
                        "path_sha256": _sha256(path.encode()),
                        "sha256": file_hash,
                    }
                )
            if kind == "license":
                text = prefix.decode("utf-8", errors="ignore")
                licenses = sorted(
                    {value.strip() for value in SPDX_RE.findall(text)}
                )
                declared_licenses.update(licenses)
                license_files.append(
                    {
                        "path": display_path,
                        "sha256": file_hash,
                        "declared_licenses": licenses,
                    }
                )

        for child_cluster, child_path, child_depth in reversed(
            child_directories
        ):
            stack.append(
                (child_cluster, False, child_path, child_depth)
            )

    return {
        **partition,
        "type": "fat",
        "status": "PARTIAL" if listing_errors else "PASS",
        "errors": listing_errors[:32],
        "fat_type": volume.fat_type,
        "declared_filesystem": volume.declared_filesystem,
        "bytes_per_sector": volume.bytes_per_sector,
        "sectors_per_cluster": volume.sectors_per_cluster,
        "cluster_size": volume.cluster_size,
        "cluster_count": volume.cluster_count,
        "fat_count": volume.fat_count,
        "root_cluster": volume.root_cluster,
        "fat_sha256": _sha256(volume.fat_data),
        "file_count": len(files),
        "directory_count": len(directories),
        "total_file_bytes": total_file_bytes,
        "files": files,
        "directories": directories,
        "redacted_directories": redacted_directories,
        "sensitive_files": sensitive_files,
        "license_files": license_files,
        "declared_licenses": sorted(declared_licenses),
        "limits": {
            "files_truncated": files_truncated,
            "directories_truncated": directories_truncated,
            "max_files": MAX_FILES,
            "max_directories": MAX_DIRECTORIES,
            "max_depth": MAX_FAT_DEPTH,
            "max_directory_entries": MAX_FAT_DIRECTORY_ENTRIES,
        },
        "not_claimed": [
            "deleted file recovery",
            "file slack space",
            "runtime permissions",
            "license compliance",
        ],
    }


def _looks_like_fat_boot_sector(data: bytes) -> bool:
    try:
        _FatVolume(data)
    except _FatError:
        return False
    return True


def _blank_partition_value(data: bytes) -> int | None:
    if not data:
        return None
    first = data[0]
    if first in {0x00, 0xFF} and data.count(first) == len(data):
        return first
    return None


SPIFFS_CONFIGS = (
    (256, 4096, 32, 4),
    (256, 65536, 32, 4),
    (256, 4096, 64, 4),
    (256, 65536, 64, 4),
    (512, 4096, 32, 4),
    (512, 65536, 32, 4),
    (256, 4096, 32, 0),
    (256, 65536, 32, 0),
)


def _valid_spiffs_name(raw: bytes) -> str | None:
    value = raw.split(b"\x00", 1)[0]
    if not value or len(value) > 512:
        return None
    try:
        name = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(char) < 0x20 for char in name):
        return None
    return name


def _spiffs_lut_obj_id(
    data: bytes,
    page_ix: int,
    *,
    block_size: int,
    pages_per_block: int,
    lookup_pages: int,
) -> int:
    block = page_ix // pages_per_block
    block_page = page_ix % pages_per_block
    if block_page < lookup_pages:
        return 0xFFFF
    offset = (
        block * block_size
        + (block_page - lookup_pages) * 2
    )
    if offset + 2 > len(data):
        return 0xFFFF
    return _u16(data, offset)


def _parse_spiffs_config(
    data: bytes,
    *,
    page_size: int,
    block_size: int,
    name_len: int,
    meta_len: int,
) -> dict | None:
    if (
        page_size <= 0
        or block_size <= 0
        or block_size % page_size
        or len(data) < block_size
        or len(data) % block_size
    ):
        return None
    pages_per_block = block_size // page_size
    lookup_pages = (
        pages_per_block * 2 + page_size - 1
    ) // page_size
    if lookup_pages >= pages_per_block:
        return None
    page_count = len(data) // page_size
    index_header_len = 8 + 4 + 1 + name_len + meta_len
    if index_header_len + 2 > page_size:
        return None
    head_entries = (page_size - index_header_len) // 2
    continuation_entries = (page_size - 8) // 2
    if head_entries <= 0 or continuation_entries <= 0:
        return None

    index_pages: dict[tuple[int, int], dict] = {}
    for page_ix in range(page_count):
        block_page = page_ix % pages_per_block
        if block_page < lookup_pages:
            continue
        offset = page_ix * page_size
        page = data[offset : offset + page_size]
        if len(page) < index_header_len:
            continue
        stored_obj_id = _u16(page, 0)
        flags = page[4]
        if not stored_obj_id & 0x8000:
            continue
        if (
            _spiffs_lut_obj_id(
                data,
                page_ix,
                block_size=block_size,
                pages_per_block=pages_per_block,
                lookup_pages=lookup_pages,
            )
            != stored_obj_id
        ):
            continue
        if (
            flags & 0x01
            or flags & 0x02
            or flags & 0x04
            or not flags & 0x40
            or not flags & 0x80
        ):
            continue
        span_ix = _u16(page, 2)
        if span_ix > 0x7FFF:
            continue
        if span_ix == 0:
            size = _u32(page, 8)
            obj_type = page[12]
            if obj_type != 1:
                continue
            name = _valid_spiffs_name(page[13 : 13 + name_len])
            if name is None:
                continue
            entries_start = index_header_len
        else:
            size = None
            name = None
            entries_start = 8
        entries: list[int] = []
        for entry_offset in range(entries_start, page_size - 1, 2):
            data_page_ix = _u16(page, entry_offset)
            if data_page_ix == 0xFFFF:
                break
            if data_page_ix >= page_count:
                return None
            entries.append(data_page_ix)
        key = (stored_obj_id & 0x7FFF, span_ix)
        candidate = {
            "page_ix": page_ix,
            "size": size,
            "name": name,
            "entries": entries,
            "span_ix": span_ix,
        }
        previous = index_pages.get(key)
        if previous is None or page_ix > previous["page_ix"]:
            index_pages[key] = candidate

    object_ids = sorted({obj_id for obj_id, span_ix in index_pages if span_ix == 0})
    if not object_ids:
        return None

    return {
        **{
            "page_size": page_size,
            "block_size": block_size,
            "pages_per_block": pages_per_block,
            "lookup_pages": lookup_pages,
            "obj_name_len": name_len,
            "meta_len": meta_len,
            "head_entries": head_entries,
            "continuation_entries": continuation_entries,
        },
        "object_ids": object_ids,
        "index_pages": index_pages,
        "page_count": page_count,
    }


def _score_spiffs_candidate(data: bytes, parsed: dict) -> tuple[int, int, int, int]:
    page_size = parsed["page_size"]
    data_content_len = page_size - 5
    index_pages = parsed["index_pages"]
    complete_objects = 0
    valid_data_pages = 0
    for obj_id in parsed["object_ids"]:
        header = index_pages.get((obj_id, 0))
        if header is None:
            continue
        expected_data_pages = (
            header["size"] + data_content_len - 1
        ) // data_content_len
        expected_index_pages = (
            1
            if expected_data_pages <= parsed["head_entries"]
            else 1
            + (
                expected_data_pages
                - parsed["head_entries"]
                + parsed["continuation_entries"]
                - 1
            )
            // parsed["continuation_entries"]
        )
        page_indexes: list[int] = []
        for span in range(expected_index_pages):
            page = index_pages.get((obj_id, span))
            if page is None:
                break
            page_indexes.extend(page["entries"])
        else:
            object_valid_pages = 0
            for data_span_ix, data_page_ix in enumerate(page_indexes):
                if data_span_ix >= expected_data_pages:
                    break
                offset = data_page_ix * page_size
                page = data[offset : offset + page_size]
                if (
                    len(page) >= 5
                    and _u16(page, 0) == obj_id
                    and _u16(page, 2) == data_span_ix
                    and page[4] == 0xFC
                    and _spiffs_lut_obj_id(
                        data,
                        data_page_ix,
                        block_size=parsed["block_size"],
                        pages_per_block=parsed["pages_per_block"],
                        lookup_pages=parsed["lookup_pages"],
                    )
                    == obj_id
                ):
                    valid_data_pages += 1
                    object_valid_pages += 1
                else:
                    break
            if object_valid_pages == expected_data_pages:
                complete_objects += 1
    return (
        complete_objects,
        valid_data_pages,
        len(index_pages),
        len(parsed["object_ids"]),
    )


def _list_spiffs(data: bytes, partition: dict) -> dict:
    candidates: list[dict] = []
    attempts: list[dict] = []
    for page_size, block_size, name_len, meta_len in SPIFFS_CONFIGS:
        candidate = _parse_spiffs_config(
            data,
            page_size=page_size,
            block_size=block_size,
            name_len=name_len,
            meta_len=meta_len,
        )
        attempt = {
            "page_size": page_size,
            "block_size": block_size,
            "obj_name_len": name_len,
            "meta_len": meta_len,
            "match": candidate is not None,
        }
        if candidate is not None:
            complete, valid_pages, index_pages, objects = (
                _score_spiffs_candidate(data, candidate)
            )
            candidate["score"] = (
                complete,
                valid_pages,
                index_pages,
                objects,
            )
            attempt["score"] = {
                "complete_objects": complete,
                "valid_data_pages": valid_pages,
                "index_pages": index_pages,
                "objects": objects,
            }
        attempts.append(attempt)
        if candidate is not None:
            candidates.append(candidate)

    parsed = (
        max(
            candidates,
            key=lambda item: item["score"],
        )
        if candidates
        else None
    )

    if parsed is None:
        blank = _blank_partition_value(data)
        if blank is not None:
            return {
                **partition,
                "type": "spiffs",
                "status": "UNFORMATTED",
                "errors": [
                    "SPIFFS partition appears erased or zero-filled"
                ],
                "config_attempts": attempts,
            }
        return {
            **partition,
            "type": "spiffs",
            "status": "INVALID",
            "errors": [
                "no supported SPIFFS object index page was found"
            ],
            "config_attempts": attempts,
        }

    page_size = parsed["page_size"]
    index_pages = parsed["index_pages"]
    files: list[dict] = []
    directories: set[str] = {"/"}
    redacted_directories: list[dict] = []
    sensitive_files: list[dict] = []
    license_files: list[dict] = []
    declared_licenses: set[str] = set()
    listing_errors: list[str] = []
    total_file_bytes = 0
    files_truncated = False
    data_content_len = page_size - 5
    total_index_pages = 0
    total_data_pages = 0

    for obj_id in parsed["object_ids"]:
        header = index_pages.get((obj_id, 0))
        if header is None:
            continue
        name: str = header["name"]
        size: int = header["size"]
        display_path, path_hash, redacted = _public_path(name)
        if len(files) >= MAX_FILES:
            files_truncated = True
            break
        expected_data_pages = (
            size + data_content_len - 1
        ) // data_content_len
        expected_index_pages = (
            1
            if expected_data_pages <= parsed["head_entries"]
            else 1
            + (
                expected_data_pages
                - parsed["head_entries"]
                + parsed["continuation_entries"]
                - 1
            )
            // parsed["continuation_entries"]
        )
        page_indexes: list[int] = []
        for span in range(expected_index_pages):
            index_page = index_pages.get((obj_id, span))
            if index_page is None:
                listing_errors.append(
                    f"{display_path}: missing SPIFFS index span {span}"
                )
                break
            page_indexes.extend(index_page["entries"])
        digest = hashlib.sha256()
        prefix = bytearray()
        remaining = size
        read_bytes = 0
        for data_span_ix, data_page_ix in enumerate(page_indexes):
            if remaining <= 0:
                break
            offset = data_page_ix * page_size
            page = data[offset : offset + page_size]
            if len(page) < 5:
                listing_errors.append(
                    f"{display_path}: truncated SPIFFS data page"
                )
                break
            stored_obj_id = _u16(page, 0)
            stored_span_ix = _u16(page, 2)
            flags = page[4]
            if (
                stored_obj_id != obj_id
                or stored_span_ix != data_span_ix
                or flags & 0x01
                or flags & 0x02
                or not flags & 0x04
                or not flags & 0x40
                or not flags & 0x80
                or _spiffs_lut_obj_id(
                    data,
                    data_page_ix,
                    block_size=parsed["block_size"],
                    pages_per_block=parsed["pages_per_block"],
                    lookup_pages=parsed["lookup_pages"],
                )
                != obj_id
            ):
                listing_errors.append(
                    f"{display_path}: invalid SPIFFS data page"
                )
                break
            take = min(remaining, data_content_len)
            chunk = page[5 : 5 + take]
            digest.update(chunk)
            if len(prefix) < MAX_LICENSE_BYTES:
                prefix.extend(chunk[: MAX_LICENSE_BYTES - len(prefix)])
            remaining -= take
            read_bytes += take
        if read_bytes != size:
            listing_errors.append(
                f"{display_path}: expected {size} bytes, read {read_bytes}"
            )
            continue

        kind = _file_kind(name)
        row = {
            "path": display_path,
            "size": size,
            "sha256": digest.hexdigest(),
            "kind": kind,
            "permissions": "not-recorded",
            "object_id": obj_id,
            "index_page_count": expected_index_pages,
            "data_page_count": read_bytes // data_content_len
            + (1 if read_bytes % data_content_len else 0),
        }
        if path_hash is not None:
            row["path_sha256"] = path_hash
            row["redacted"] = redacted
        files.append(row)
        total_file_bytes += size
        total_index_pages += expected_index_pages
        total_data_pages += row["data_page_count"]

        path_parts = [part for part in name.split("/") if part]
        for count in range(1, len(path_parts)):
            directory = "/" + "/".join(path_parts[:count])
            if len(directories) >= MAX_DIRECTORIES:
                break
            if directory in directories:
                continue
            directories.add(directory)
            shown, directory_hash, _ = _public_path(directory)
            if directory_hash is not None:
                redacted_directories.append(
                    {
                        "path": shown,
                        "path_sha256": directory_hash,
                    }
                )

        if kind == "sensitive":
            sensitive_files.append(
                {
                    "path": display_path,
                    "path_sha256": _sha256(name.encode()),
                    "sha256": digest.hexdigest(),
                }
            )
        if kind == "license":
            text = bytes(prefix).decode("utf-8", errors="ignore")
            licenses = sorted(
                {value.strip() for value in SPDX_RE.findall(text)}
            )
            declared_licenses.update(licenses)
            license_files.append(
                {
                    "path": display_path,
                    "sha256": digest.hexdigest(),
                    "declared_licenses": licenses,
                }
            )

    return {
        **partition,
        "type": "spiffs",
        "status": "PARTIAL" if listing_errors else "PASS",
        "errors": listing_errors[:32],
        "page_size": page_size,
        "block_size": parsed["block_size"],
        "block_count": len(data) // parsed["block_size"],
        "pages_per_block": parsed["pages_per_block"],
        "lookup_pages_per_block": parsed["lookup_pages"],
        "object_name_len": parsed["obj_name_len"],
        "metadata_len": parsed["meta_len"],
        "selected_config": {
            "page_size": parsed["page_size"],
            "block_size": parsed["block_size"],
            "object_name_len": parsed["obj_name_len"],
            "metadata_len": parsed["meta_len"],
        },
        "lut_validated": True,
        "index_page_count": total_index_pages,
        "data_page_count": total_data_pages,
        "file_count": len(files),
        "directory_count": max(0, len(directories) - 1),
        "total_file_bytes": total_file_bytes,
        "files": files,
        "directories": sorted(directories - {"/"}),
        "redacted_directories": redacted_directories,
        "sensitive_files": sensitive_files,
        "license_files": license_files,
        "declared_licenses": sorted(declared_licenses),
        "limits": {
            "files_truncated": files_truncated,
            "max_files": MAX_FILES,
            "max_directories": MAX_DIRECTORIES,
        },
        "config_attempts": attempts,
        "not_claimed": [
            "deleted object recovery",
            "runtime permissions",
            "license compliance",
        ],
    }


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
        redacted_directories: list[dict] = []
        sensitive_files: list[dict] = []
        license_files: list[dict] = []
        declared_licenses: set[str] = set()
        total_file_bytes = 0
        files_truncated = False
        directories_truncated = False
        listing_error: str | None = None
        block_count = filesystem.block_count
        used_block_count = filesystem.used_block_count
        try:
            for root, dir_names, file_names in filesystem.walk("/"):
                root = root.rstrip("/") or "/"
                for name in dir_names:
                    path = f"{root}/{name}" if root != "/" else f"/{name}"
                    if len(directories) >= MAX_DIRECTORIES:
                        directories_truncated = True
                        break
                    display_path, path_hash, _ = _public_path(path)
                    directories.append(display_path)
                    if path_hash is not None:
                        redacted_directories.append(
                            {
                                "path": display_path,
                                "path_sha256": path_hash,
                            }
                        )
                if directories_truncated:
                    break
                for name in file_names:
                    path = f"{root}/{name}" if root != "/" else f"/{name}"
                    if len(files) >= MAX_FILES:
                        files_truncated = True
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
                if files_truncated or directories_truncated:
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
            "redacted_directories": redacted_directories,
            "sensitive_files": sensitive_files,
            "license_files": license_files,
            "declared_licenses": sorted(declared_licenses),
            "limits": {
                "files_truncated": files_truncated,
                "directories_truncated": directories_truncated,
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
        return _list_spiffs(window, header)
    if subtype == FAT_SUBTYPE:
        if _blank_partition_value(window) is not None:
            return {
                **header,
                "type": "fat",
                "status": "UNFORMATTED",
                "errors": ["FAT partition appears erased or zero-filled"],
            }
        return _list_fat(window, header)
    if (
        len(window) >= 512
        and window[510:512] == b"\x55\xaa"
        and _looks_like_fat_boot_sector(window)
    ):
        return _list_fat(window, header)
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
