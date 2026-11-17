"""Decode supported ESP-IDF ELF32 UART core-dump containers."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from xtensa_elf_symbols import EM_RISCV, EM_XTENSA

ESP32_CHIP_ID = 0
ESP32C6_CHIP_ID = 0x000D
ESP32_ELF_CRC32 = 0x0102
ESP32C6_ELF_CRC32 = (ESP32C6_CHIP_ID << 16) | ESP32_ELF_CRC32
ESP32C6_ELF_SHA256 = (ESP32C6_CHIP_ID << 16) | 0x0103
ESP_APP_NOTE = (b"ESP_CORE_DUMP_INFO\0", 8266)
ESP_EXTRA_NOTE = (b"ESP_EXTRA_INFO\0", 677)
PRSTATUS = (b"CORE\0", 1)
CRASHED_TASK_SKIPPED = 0xDEADBEEF
MAX_TASK_CONTEXTS = 64
FAKE_STACK_START = 0x20000000
FAKE_STACK_END = 0x30000000


@dataclass(frozen=True)
class TaskLayout:
    machine: int
    prstatus_bytes: int
    sp_offset: int
    extra_bytes: int


# ESP-IDF 5.5.4 components/espcoredump/src/port/{xtensa,riscv}/core_dump_port.c.
# Each port uses the TCB address as PRSTATUS PID and PC as the first register.
TASK_LAYOUTS = {
    ESP32_CHIP_ID: TaskLayout(EM_XTENSA, 588, 72 + 65 * 4, 152),
    ESP32C6_CHIP_ID: TaskLayout(EM_RISCV, 204, 72 + 2 * 4, 8),
}
CRC32_VERSIONS = {
    ESP32_CHIP_ID: ESP32_ELF_CRC32,
    ESP32C6_CHIP_ID: ESP32C6_ELF_CRC32,
}


def _payload(dump: bytes, version: int, trailer_size: int) -> memoryview:
    if len(dump) < 24 + 52 + trailer_size or struct.unpack_from("<II", dump) != (len(dump), version):
        raise ValueError("unsupported ESP32 ELF dump version or declared length")
    return memoryview(dump)[:-trailer_size]


def verify_container(dump: bytes, *, version: int = ESP32_ELF_CRC32) -> tuple[int, bytes]:
    """Verify the CRC32 format. The offline Core2 CLI uses the default version."""
    payload = _payload(dump, version, 4)
    checksum, = struct.unpack_from("<I", dump, len(dump) - 4)
    if zlib.crc32(payload) != checksum:
        raise ValueError("UART dump CRC32 mismatch")
    return checksum, bytes(payload[24:])


def _verify_riscv_sha256(dump: bytes) -> tuple[str, bytes]:
    payload = _payload(dump, ESP32C6_ELF_SHA256, 32)
    checksum = hashlib.sha256(payload).digest()
    if checksum != dump[-32:]:
        raise ValueError("UART dump SHA-256 mismatch")
    return checksum.hex(), bytes(payload[24:])


def _core_segments(elf: bytes, machine: int) -> list[tuple[int, int, int, int, int]]:
    if (len(elf) < 52 or elf[:7] != b"\x7fELF\x01\x01\x01"
            or struct.unpack_from("<HH", elf, 16) != (4, machine)):
        raise ValueError("dump does not contain a matching ELF32 core file")
    table_offset, = struct.unpack_from("<I", elf, 28)
    entry_size, count = struct.unpack_from("<HH", elf, 42)
    table_end = table_offset + count * entry_size
    if entry_size != 32 or not 1 <= count <= 256 or table_offset < 52 or table_end > len(elf):
        raise ValueError("invalid ELF program header table")
    segments = []
    for index in range(count):
        kind, offset, addr, _, size, memory_size = struct.unpack_from("<6I", elf, table_offset + index * entry_size)
        if offset + size > len(elf) or (size and offset < table_end):
            raise ValueError("invalid ELF segment extent")
        if size:
            segments.append((offset, offset + size, kind, addr, memory_size))
    previous_end = table_end
    for offset, stop, _, _, _ in sorted(segments):
        if offset < previous_end:
            raise ValueError("overlapping ELF segments")
        previous_end = stop

    return segments


def core_loads(elf: bytes, *, machine: int) -> Iterator[tuple[int, int, memoryview]]:
    """Read only file-backed PT_LOAD program segments from the checked core."""
    for offset, stop, kind, address, size in _core_segments(elf, machine):
        if kind == 1:  # PT_LOAD
            if not address or size < stop - offset or address + size > 1 << 32:
                raise ValueError("invalid ELF load address range")
            yield address, size, memoryview(elf)[offset:stop]


def core_notes(elf: bytes, *, machine: int = EM_XTENSA) -> Iterator[tuple[tuple[bytes, int], bytes]]:
    for offset, stop, kind, _, _ in sorted(_core_segments(elf, machine)):
        if kind != 4:  # PT_NOTE
            continue
        while offset < stop:
            if stop - offset < 12:
                raise ValueError("incomplete ELF note header")
            name_size, desc_size, note_type = struct.unpack_from("<3I", elf, offset)
            name = offset + 12
            desc = name + ((name_size + 3) & ~3)
            offset = desc + ((desc_size + 3) & ~3)
            if offset > stop:
                raise ValueError("invalid ELF note extent")
            yield (elf[name:name + name_size], note_type), elf[desc:desc + desc_size]


def app_note_digest(
    notes: list[tuple[tuple[bytes, int], bytes]], *, version: int = ESP32_ELF_CRC32,
) -> str:
    app_notes = [payload for kind, payload in notes if kind == ESP_APP_NOTE]
    if (len(app_notes) != 1 or len(app_notes[0]) < 68
            or struct.unpack_from("<I", app_notes[0])[0] != version):
        raise ValueError("missing, ambiguous or unsupported dump application ELF note")
    digest = app_notes[0][4:68].rstrip(b"\0")
    if not re.fullmatch(rb"[0-9a-f]{8,64}", digest):
        raise ValueError("invalid ELF note digest")
    return digest.decode("ascii")


def task_contexts(
    notes: list[tuple[tuple[bytes, int], bytes]], layout: TaskLayout,
) -> tuple[int | None, list[dict]]:
    extra = [payload for kind, payload in notes if kind == ESP_EXTRA_NOTE]
    if len(extra) != 1 or len(extra[0]) != layout.extra_bytes:
        raise ValueError("missing, ambiguous or unsupported architecture extra-info note")
    crashed_tcb, = struct.unpack_from("<I", extra[0])
    tasks = []
    seen = set()
    for kind, payload in notes:
        if kind != PRSTATUS:
            continue
        if len(payload) != layout.prstatus_bytes or len(tasks) >= MAX_TASK_CONTEXTS:
            raise ValueError("unsupported or oversized task register notes")
        tcb, = struct.unpack_from("<I", payload, 24)
        pc, = struct.unpack_from("<I", payload, 72)
        sp, = struct.unpack_from("<I", payload, layout.sp_offset)
        if not tcb or tcb in seen:
            raise ValueError("invalid or repeated task handle")
        seen.add(tcb)
        synthetic = FAKE_STACK_START <= sp < FAKE_STACK_END
        tasks.append({
            "tcb": f"0x{tcb:08x}", "crashed": tcb == crashed_tcb,
            "context_status": "sdk_placeholder" if synthetic else "captured",
            "pc": None if synthetic else f"0x{pc:08x}",
            "sp": None if synthetic else f"0x{sp:08x}",
        })
    if not tasks or (crashed_tcb != CRASHED_TASK_SKIPPED and crashed_tcb not in seen):
        raise ValueError("missing saved task context")
    return None if crashed_tcb == CRASHED_TASK_SKIPPED else crashed_tcb, tasks


def decode_task_contexts(
    dump: bytes, panic_prefix: str, *, chip_id: int = ESP32_CHIP_ID,
    capture_core: Callable[[bytes], None] | None = None,
) -> dict:
    if chip_id not in TASK_LAYOUTS or len(dump) < 8:
        raise ValueError("unsupported or incomplete core dump")
    layout = TASK_LAYOUTS[chip_id]
    version, = struct.unpack_from("<I", dump, 4)
    if chip_id == ESP32C6_CHIP_ID and version == ESP32C6_ELF_SHA256:
        sha256, elf = _verify_riscv_sha256(dump)
        checksum_fields = {"format": "esp32c6_riscv_elf32_sha256", "dump_embedded_sha256": sha256}
    else:
        crc32, elf = verify_container(dump, version=CRC32_VERSIONS[chip_id])
        target = "esp32c6_riscv" if chip_id == ESP32C6_CHIP_ID else "esp32_xtensa"
        checksum_fields = {"format": f"{target}_elf32_crc32", "dump_crc32": f"{crc32:08x}"}
    notes = list(core_notes(elf, machine=layout.machine))
    digest = app_note_digest(notes, version=version)
    if not (digest.startswith(panic_prefix) or panic_prefix.startswith(digest)):
        raise ValueError("UART dump ELF note differs from the panic ELF prefix")
    crashed_tcb, tasks = task_contexts(notes, layout)
    if capture_core is not None:
        capture_core(elf)
    return {
        "status": "decoded",
        **checksum_fields,
        "source": "console_tail",
        "dump_sha256": hashlib.sha256(dump).hexdigest(),
        "dump_bytes": len(dump),
        "dump_elf_sha256_prefix": digest,
        "crashed_tcb": f"0x{crashed_tcb:08x}" if crashed_tcb is not None else None,
        "tasks": tasks,
    }
