"""Decode the ESP32 Xtensa ELF32/CRC32 UART core-dump container."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Iterator

ESP32_ELF_CRC32 = 0x0102
ESP_APP_NOTE = (b"ESP_CORE_DUMP_INFO\0", 8266)
ESP_EXTRA_NOTE = (b"ESP_EXTRA_INFO\0", 677)
XTENSA_PRSTATUS = (b"CORE\0", 1)
CRASHED_TASK_SKIPPED = 0xDEADBEEF
MAX_TASK_CONTEXTS = 64

# esp-idf v5.5.4 components/espcoredump/src/port/xtensa/core_dump_port.c
XTENSA_STATUS_BYTES = 588
XTENSA_TCB_OFFSET = 24
XTENSA_PC_OFFSET = 72
XTENSA_SP_OFFSET = 72 + 65 * 4
XTENSA_EXTRA_BYTES = 152
XTENSA_FAKE_STACK_START = 0x20000000
XTENSA_FAKE_STACK_END = 0x30000000


def verify_container(dump: bytes) -> tuple[int, bytes]:
    if len(dump) < 80 or struct.unpack_from("<II", dump) != (len(dump), ESP32_ELF_CRC32):
        raise ValueError("unsupported ESP32 ELF CRC32 dump version or declared length")
    checksum, = struct.unpack_from("<I", dump, len(dump) - 4)
    elf = dump[24:-4]
    if zlib.crc32(memoryview(dump)[:-4]) != checksum:
        raise ValueError("UART dump CRC32 mismatch")
    return checksum, elf


def core_notes(elf: bytes) -> Iterator[tuple[tuple[bytes, int], bytes]]:
    if len(elf) < 52 or elf[:7] != b"\x7fELF\x01\x01\x01" or elf[16:20] != b"\x04\x00\x5e\x00":
        raise ValueError("dump does not contain an Xtensa ELF32 core file")
    table_offset, = struct.unpack_from("<I", elf, 28)
    entry_size, count = struct.unpack_from("<HH", elf, 42)
    table_end = table_offset + count * entry_size
    if entry_size != 32 or not 1 <= count <= 256 or table_offset < 52 or table_end > len(elf):
        raise ValueError("invalid ELF program header table")
    segments = []
    for index in range(count):
        kind, offset, _, _, size = struct.unpack_from("<5I", elf, table_offset + index * entry_size)
        if offset + size > len(elf) or (size and offset < table_end):
            raise ValueError("invalid ELF segment extent")
        if size:
            segments.append((offset, offset + size, kind))
    previous_end = table_end
    for offset, stop, kind in sorted(segments):
        if offset < previous_end:
            raise ValueError("overlapping ELF segments")
        previous_end = stop
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


def app_note_digest(notes: list[tuple[tuple[bytes, int], bytes]]) -> str:
    app_notes = [payload for kind, payload in notes if kind == ESP_APP_NOTE]
    if (len(app_notes) != 1 or len(app_notes[0]) < 68
            or struct.unpack_from("<I", app_notes[0])[0] != ESP32_ELF_CRC32):
        raise ValueError("missing, ambiguous or unsupported dump application ELF note")
    digest = app_notes[0][4:68].rstrip(b"\0")
    if not re.fullmatch(rb"[0-9a-f]{8,64}", digest):
        raise ValueError("invalid ELF note digest")
    return digest.decode("ascii")


def task_contexts(notes: list[tuple[tuple[bytes, int], bytes]]) -> tuple[int | None, list[dict]]:
    extra = [payload for kind, payload in notes if kind == ESP_EXTRA_NOTE]
    if len(extra) != 1 or len(extra[0]) != XTENSA_EXTRA_BYTES:
        raise ValueError("missing, ambiguous or unsupported Xtensa extra-info note")
    crashed_tcb, = struct.unpack_from("<I", extra[0])
    tasks = []
    seen = set()
    for kind, payload in notes:
        if kind != XTENSA_PRSTATUS:
            continue
        if len(payload) != XTENSA_STATUS_BYTES or len(tasks) >= MAX_TASK_CONTEXTS:
            raise ValueError("unsupported or oversized Xtensa task register notes")
        tcb, = struct.unpack_from("<I", payload, XTENSA_TCB_OFFSET)
        pc, = struct.unpack_from("<I", payload, XTENSA_PC_OFFSET)
        sp, = struct.unpack_from("<I", payload, XTENSA_SP_OFFSET)
        if not tcb or tcb in seen:
            raise ValueError("invalid or repeated task handle")
        seen.add(tcb)
        synthetic = XTENSA_FAKE_STACK_START <= sp < XTENSA_FAKE_STACK_END
        tasks.append({
            "tcb": f"0x{tcb:08x}", "crashed": tcb == crashed_tcb,
            "context_status": "sdk_placeholder" if synthetic else "captured",
            "pc": None if synthetic else f"0x{pc:08x}",
            "sp": None if synthetic else f"0x{sp:08x}",
        })
    if not tasks or (crashed_tcb != CRASHED_TASK_SKIPPED and crashed_tcb not in seen):
        raise ValueError("missing saved task context")
    return None if crashed_tcb == CRASHED_TASK_SKIPPED else crashed_tcb, tasks


def decode_task_contexts(dump: bytes, panic_prefix: str) -> dict:
    checksum, elf = verify_container(dump)
    notes = list(core_notes(elf))
    digest = app_note_digest(notes)
    if not (digest.startswith(panic_prefix) or panic_prefix.startswith(digest)):
        raise ValueError("UART dump ELF note differs from the panic ELF prefix")
    crashed_tcb, tasks = task_contexts(notes)
    return {
        "status": "decoded",
        "format": "esp32_xtensa_elf32_crc32",
        "source": "console_tail",
        "dump_sha256": hashlib.sha256(dump).hexdigest(),
        "dump_bytes": len(dump),
        "dump_crc32": f"{checksum:08x}",
        "dump_elf_sha256_prefix": digest,
        "crashed_tcb": f"0x{crashed_tcb:08x}" if crashed_tcb is not None else None,
        "tasks": tasks,
    }
