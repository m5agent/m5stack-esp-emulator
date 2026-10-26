"""Bounded, non-executing inspection of MicroPython v6 bytecode containers.

Format pinned to micropython/micropython@78ff170de9e32c79db6e64d3e33d2bd60002bdcd:
  docs/reference/mpyfiles.rst; tools/mpy-tool.py;
  py/{persistentcode.c,persistentcode.h,bc.h,bc0.h,smallint.h,runtime0.h,vm.c}.
https://github.com/micropython/micropython/tree/78ff170de9e32c79db6e64d3e33d2bd60002bdcd

This checks container structure, bytecode operand boundaries and references.
It is not a VM stack/type verifier or an untrusted-code sandbox. The caller
must separately compare the version/small-int requirement to the actual guest.

Prelude/opcode decoding is adapted from the above MIT-licensed sources.
Copyright (c) 2013, 2014, 2016-2019 Damien P. George

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
from __future__ import annotations

import re


MAX_MPY_BYTES = 256 * 1024
MAX_TABLE_ITEMS = 4096
MAX_CONSTANT_NODES = 8192
MAX_RAW_CODES = 4096
MAX_DEPTH = 32
MAX_STATE_ITEMS = 4096
MAX_UINT_BYTES = 5  # The admitted ESP32 loader uses 32-bit size_t.
MAX_PRELUDE_BYTES = 16  # Interleaved fields consume as little as one bit/byte.
MAX_NUMBER_BYTES = 4096
STATIC_QSTR_COUNT = 165  # py/makeqstrdata.py, same pinned commit, IDs 1..165.
_INTEGER = re.compile(rb"[+-]?[0-9]+\Z")


class MPYBytecodeError(ValueError):
    """Invalid, unsupported or over-limit bytecode container."""


class _Reader:
    def __init__(self, data: memoryview):
        self.data, self.position = data, 0

    def fail(self, message: str):
        raise MPYBytecodeError(f"{message} at byte {self.position}")

    def take(self, size: int) -> memoryview:
        if size < 0 or size > len(self.data) - self.position:
            self.fail("truncated .mpy data")
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def byte(self) -> int:
        return self.take(1)[0]

    def uint(self) -> int:
        value = 0
        for index in range(MAX_UINT_BYTES):
            byte = self.byte()
            if index == 0 and byte == 0x80:
                self.fail("noncanonical unsigned integer")
            value = (value << 7) | (byte & 0x7f)
            if value > 0xffffffff:
                self.fail("unsigned integer exceeds 32-bit format limit")
            if not byte & 0x80:
                return value
        self.fail("overlong unsigned integer")

    def terminated(self, size: int) -> bytes:
        value = bytes(self.take(size))
        if self.byte() != 0:
            self.fail("missing null terminator")
        return value


class _Inspector:
    def __init__(self, data: bytes):
        self.reader = _Reader(memoryview(data))
        self.qstr_count = self.object_count = self.constant_nodes = 0
        self.raw_codes = self.max_depth = self.bytecode_bytes = self.instructions = 0
        self.small_int_bits = 0

    @staticmethod
    def bounded(value: int, maximum: int, label: str, minimum: int = 0) -> int:
        if not minimum <= value <= maximum:
            raise MPYBytecodeError(f"{label} outside [{minimum}, {maximum}]")
        return value

    def qstr(self):
        reader = self.reader
        encoded = reader.uint()
        if encoded & 1:
            self.bounded(encoded >> 1, STATIC_QSTR_COUNT, "static qstr ID", 1)
        else:
            value = reader.terminated(encoded >> 1)
            try:
                value.decode("utf-8", errors="surrogatepass")
            except UnicodeDecodeError as error:
                raise MPYBytecodeError("invalid UTF-8 qstr") from error

    def constant(self, depth: int = 1):
        self.bounded(depth, MAX_DEPTH, "constant nesting depth", 1)
        self.constant_nodes += 1
        self.bounded(self.constant_nodes, MAX_CONSTANT_NODES, "constant node count")
        reader = self.reader
        kind = reader.byte()
        if kind == 0:
            reader.fail("native function-table constant is unsupported")
        if 1 <= kind <= 4:  # None, False, True, Ellipsis.
            return
        if not 5 <= kind <= 10:
            reader.fail("unknown persistent object kind")
        size = reader.uint()
        if kind == 10:
            self.bounded(size, MAX_CONSTANT_NODES - self.constant_nodes, "tuple item count")
            for _ in range(size):
                self.constant(depth + 1)
            return
        value = reader.terminated(size) if kind in (5, 6) else bytes(reader.take(size))
        if kind == 6:
            return
        try:
            # The official compiler permits escaped, isolated surrogates.
            text = value.decode("utf-8", errors="surrogatepass") if kind == 5 else value.decode("ascii")
        except UnicodeDecodeError as error:
            raise MPYBytecodeError("invalid persistent object text") from error
        if kind == 5:
            return
        self.bounded(size, MAX_NUMBER_BYTES, "numeric constant text size", 1)
        if kind == 7:
            if not _INTEGER.fullmatch(value):
                reader.fail("invalid decimal integer constant")
        else:
            try:
                # Built-in number parsers do not evaluate Python source.
                (float if kind == 8 else complex)(text)
            except ValueError as error:
                raise MPYBytecodeError("invalid floating-point constant") from error

    def prelude(self, reader: _Reader) -> tuple[int, int]:
        # py/bc.h: xSSSSEAA, followed by xFSSKAED extension bytes.
        byte = reader.byte()
        state, exceptions, positional = (byte >> 3) & 15, (byte >> 2) & 1, byte & 3
        keyword = defaults = flags = 0
        index = 0
        while byte & 0x80:
            if index >= MAX_PRELUDE_BYTES - 1:
                reader.fail("overlong prelude signature")
            byte = reader.byte()
            state |= (byte & 0x30) << (2 * index)
            exceptions |= (byte & 2) << index
            flags |= ((byte & 0x40) >> 6) << index
            positional |= (byte & 4) << index
            keyword |= ((byte & 8) >> 3) << index
            defaults |= (byte & 1) << index
            index += 1
        state += 1
        self.bounded(state, MAX_STATE_ITEMS, "VM state size", 1)
        self.bounded(exceptions, MAX_STATE_ITEMS, "exception stack size")
        self.bounded(positional + keyword, MAX_STATE_ITEMS, "argument count")
        self.bounded(flags, 0x0f, "bytecode scope flags")
        argument_locals = positional + keyword + bool(flags & 2) + bool(flags & 4)
        if argument_locals > state:
            reader.fail("argument locals exceed VM state size")
        if defaults > positional:
            reader.fail("default argument count exceeds positional count")

        # py/bc.h: xIIIIIIC, I = source info bytes, C = closure cells.
        info = cells = 0
        for index in range(MAX_PRELUDE_BYTES):
            byte = reader.byte()
            info |= ((byte & 0x7e) >> 1) << (6 * index)
            cells |= (byte & 1) << index
            if not byte & 0x80:
                break
        else:
            reader.fail("overlong prelude size")
        self.bounded(info, len(reader.data) - reader.position, "source info length", 1)
        self.bounded(cells, state, "closure cell count")
        info_reader = _Reader(reader.take(info))
        for _ in range(1 + positional + keyword):
            self.bounded(info_reader.uint(), self.qstr_count - 1, "source-info qstr reference")
        # Line-info entries are one byte or a high-bit byte plus one more byte.
        # Do not let a malformed traceback entry consume closure/opcode bytes.
        while info_reader.position < len(info_reader.data):
            if info_reader.byte() & 0x80:
                info_reader.byte()
        for cell in reader.take(cells):
            self.bounded(cell, state - 1, "closure local index")
        if reader.position == len(reader.data):
            reader.fail("missing bytecode instructions")
        return state, flags

    def bytecode(self, body: memoryview) -> list[int]:
        reader = _Reader(body)
        state, _flags = self.prelude(reader)
        starts, targets, children = set(), [], []
        while reader.position < len(body):
            starts.add(reader.position)
            opcode = reader.byte()
            if not (0x10 <= opcode <= 0x1c or 0x20 <= opcode <= 0x37
                    or opcode == 0x40 or 0x42 <= opcode <= 0x4b
                    or 0x50 <= opcode <= 0x5f or 0x62 <= opcode <= 0x69
                    or 0x70 <= opcode <= 0xd3 or 0xd7 <= opcode <= 0xf9):
                reader.fail("unknown bytecode opcode")
            self.instructions += 1
            fmt = (0x000003a4 >> (2 * (opcode >> 4))) & 3
            argument = None
            if opcode == 0x22:  # Signed small integer, including sign extension.
                byte = reader.byte()
                argument = byte & 0x7f
                if argument & 0x40:
                    argument -= 0x80
                for _ in range(9):
                    if not byte & 0x80:
                        break
                    byte = reader.byte()
                    argument = (argument << 7) | (byte & 0x7f)
                if byte & 0x80:
                    reader.fail("overlong signed integer")
                limit = 1 << (self.small_int_bits - 1)
                if not -limit <= argument < limit:
                    reader.fail("small integer exceeds header requirement")
            elif fmt in (1, 2):
                argument = reader.uint()
            elif fmt == 3:
                first = reader.byte()
                argument = (first & 0x7f) | (reader.byte() << 7) if first & 0x80 else first
                if opcode in (0x40, 0x42, 0x43, 0x44):
                    argument -= 0x4000 if first & 0x80 else 0x40
                # UNWIND_JUMP destination is relative to the extra-byte address
                # (py/vm.c), while other jumps are relative to the next opcode.
                targets.append(reader.position + argument)
            if opcode & 0x9e == 0:
                reader.byte()  # Closure count or unwind depth.
            if fmt == 1:
                self.bounded(argument, self.qstr_count - 1, "opcode qstr reference")
            elif opcode == 0x23:
                self.bounded(argument, self.object_count - 1, "opcode object reference")
            elif opcode in (0x20, 0x21, 0x32, 0x33):
                children.append(argument)
            elif opcode in (0x24, 0x25, 0x26, 0x27, 0x28, 0x29):
                self.bounded(argument, state - 1, "opcode local reference")
            elif opcode == 0x2e and argument not in (2, 3):
                # Unlike other format-2 opcodes the VM reads one byte here.
                # Canonical uint values 2/3 are necessarily one byte long.
                reader.fail("BUILD_SLICE requires a single-byte operand 2 or 3")
            elif 0xb0 <= opcode <= 0xcf:
                self.bounded(opcode & 15, state - 1, "multi-opcode local reference")
            elif 0x70 <= opcode <= 0xaf:
                limit = 1 << (self.small_int_bits - 1)
                if not -limit <= opcode - 0x80 < limit:
                    reader.fail("small integer exceeds header requirement")
        if any(target not in starts for target in targets):
            reader.fail("jump target is outside instruction boundaries")
        return children

    def raw_code(self, depth: int = 1):
        self.bounded(depth, MAX_DEPTH, "raw-code nesting depth", 1)
        self.raw_codes += 1
        self.bounded(self.raw_codes, MAX_RAW_CODES, "raw-code count")
        self.max_depth = max(self.max_depth, depth)
        reader = self.reader
        kind_len = reader.uint()
        if kind_len & 3:
            reader.fail("native raw-code kind is unsupported")
        size = kind_len >> 3
        body = reader.take(size)
        self.bytecode_bytes += size
        references = self.bytecode(body)
        count = reader.uint() if kind_len & 4 else 0
        self.bounded(count, MAX_RAW_CODES - self.raw_codes, "raw-code children count")
        for reference in references:
            self.bounded(reference, count - 1, "opcode child reference")
        for _ in range(count):
            self.raw_code(depth + 1)

    def inspect(self) -> dict:
        reader = self.reader
        header = reader.take(4)
        if header[0] != 0x4d or header[1] != 6:
            reader.fail("only MicroPython .mpy major version 6 is supported")
        if header[2] & 0xfc:
            reader.fail("native architecture, architecture flags or reserved header bit is unsupported")
        self.small_int_bits = self.bounded(header[3], 64, "small-int bits", 1)
        self.qstr_count = self.bounded(reader.uint(), MAX_TABLE_ITEMS, "qstr table count", 1)
        self.object_count = self.bounded(reader.uint(), MAX_TABLE_ITEMS, "object table count")
        for _ in range(self.qstr_count):
            self.qstr()
        for _ in range(self.object_count):
            self.constant()
        self.raw_code()
        if reader.position != len(reader.data):
            reader.fail("trailing .mpy data")
        return {
            "mpy_version": header[1], "small_int_bits": self.small_int_bits,
            "feature_byte": header[2], "native_arch": 0,
            "raw_code_count": self.raw_codes, "qstr_count": self.qstr_count,
            "object_count": self.object_count, "constant_node_count": self.constant_nodes,
            "max_raw_code_depth": self.max_depth, "bytecode_bytes": self.bytecode_bytes,
            "instruction_count": self.instructions,
        }


def validate_bytecode(data: bytes) -> dict:
    """Inspect a bounded v6 bytecode-only container without importing its code.

    Pure bytecode ignores the two sub-version bits, matching the pinned loader.
    Limits define this service's supported subset and are not format maxima.
    """
    if not isinstance(data, bytes):
        raise MPYBytecodeError(".mpy data must be bytes")
    if not 4 <= len(data) <= MAX_MPY_BYTES:
        raise MPYBytecodeError(f".mpy size must be between 4 and {MAX_MPY_BYTES} bytes")
    return _Inspector(data).inspect()
