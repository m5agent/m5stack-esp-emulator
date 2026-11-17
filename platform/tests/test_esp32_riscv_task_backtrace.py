"""Test the deliberately small RV32 saved task unwinder independently of SDK assets."""

import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from esp32_freertos_task_details import annotate_task_metadata
from esp32_riscv_task_backtrace import MAX_FRAMES, _captured_stack, _saved_backtrace
from xtensa_elf_symbols import EM_RISCV, EM_XTENSA


def cfi(offset=0, *, register=2, expression=None, ra=None):
    rule = {"cfa": SimpleNamespace(reg=register, offset=offset, expr=expression)}
    if ra is not None:
        rule[1] = SimpleNamespace(type=ra[0], arg=ra[1])
    return rule


class SavedRiscVTaskBacktraceTests(unittest.TestCase):
    def test_leaf_ra_then_saved_stack_returns_and_explicit_terminal(self):
        memory = bytearray(32)
        struct.pack_into("<I", memory, 12, 0x3000)
        rules = {
            0x1000: cfi(),
            0x1fff: cfi(16, ra=("OFFSET", -4)),
            0x2fff: cfi(4, ra=("UNDEFINED", None)),
        }
        result = _saved_backtrace(0x1000, 0x8000, 0x2000, 0x8000, memoryview(memory), rules.get)
        self.assertEqual(result, {
            "status": "complete",
            "source": "matched_rv32_debug_frame",
            "stop_reason": "return_address_undefined",
            "frames": [
                {"pc": "0x00001000", "sp": "0x00008000"},
                {"pc": "0x00002000", "sp": "0x00008000"},
                {"pc": "0x00003000", "sp": "0x00008010"},
            ],
        })

    def test_no_unavailable_unaligned_or_unknown_caller_is_emitted(self):
        for row, saved_ra, reason in (
            (cfi(16, register=8, ra=("OFFSET", -4)), 0x2000, "unsupported_cfi"),
            (cfi(16, expression=[0x12], ra=("OFFSET", -4)), 0x2000, "unsupported_cfi"),
            (cfi(64, ra=("OFFSET", -4)), 0x2000, "stack_not_captured"),
            (cfi(16, ra=("OFFSET", -18)), 0x2000, "stack_not_captured"),
            (cfi(16, ra=("OFFSET", -2)), 0x2000, "stack_not_captured"),
            (cfi(), 0x2001, "invalid_return_address"),
            (cfi(), 0x2000, "missing_or_ambiguous_cfi"),
        ):
            with self.subTest(reason=reason, row=row):
                trace = _saved_backtrace(
                    0x1000, 0x8000, saved_ra, 0x8000, memoryview(bytes(32)), {0x1000: row}.get,
                )
                self.assertEqual((trace["status"], trace["stop_reason"]), ("partial", reason))
                self.assertEqual(trace["frames"], [{"pc": "0x00001000", "sp": "0x00008000"}])

    def test_repeated_pc_with_increasing_sp_is_bounded(self):
        data = struct.pack("<" + "I" * (MAX_FRAMES + 1), *([0x1000] * (MAX_FRAMES + 1)))
        rules = {0x1000: cfi(4, ra=("OFFSET", -4)), 0x0fff: cfi(4, ra=("OFFSET", -4))}
        trace = _saved_backtrace(0x1000, 0x8000, 0, 0x8000, memoryview(data), rules.get)
        self.assertEqual((trace["status"], trace["stop_reason"]), ("partial", "frame_limit"))
        self.assertEqual(len(trace["frames"]), MAX_FRAMES)
        self.assertEqual(trace["frames"][-1]["sp"], f"0x{0x8000 + 4 * (MAX_FRAMES - 1):08x}")

    def test_stack_segment_must_belong_to_the_named_task_and_be_exclusive(self):
        memory = memoryview(bytes(64))
        loads = [
            (0x6100, 32, memory[:32]),
            (0x6000, 64, memory),
            (0x7100, 32, memory[:32]),
            (0x7000, 64, memory),
        ]
        self.assertEqual(_captured_stack(loads, 0x6100, 32, 0x6010), (0x6000, memory))
        self.assertIsNone(_captured_stack(loads, 0x6100, 32, 0x7010))
        self.assertIsNone(_captured_stack(loads, 0x6100, 28, 0x6010))
        overlap = loads + [(0x6020, 8, memory[:8])]
        self.assertIsNone(_captured_stack(overlap, 0x6100, 32, 0x6010))
        truncated = [loads[0], (0x6000, 64, memory[:32])]
        self.assertIsNone(_captured_stack(truncated, 0x6100, 32, 0x6010))

    def test_metadata_hook_only_annotates_the_rv32_uart_transport(self):
        module = "esp32_freertos_task_details."
        with patch.dict(sys.modules, {"elftools.elf.elffile": SimpleNamespace(ELFFile=object())}):
            for machine, source, ran in (
                (EM_RISCV, "console_tail", True),
                (EM_RISCV, "stopped_flash", False),
                (EM_XTENSA, "console_tail", False),
            ):
                with self.subTest(machine=machine, source=source), patch(
                    module + "_read_layout", return_value=(16, {}),
                ), patch(module + "core_loads", return_value=[]), patch(
                    module + "annotate_riscv_backtraces",
                ) as annotate:
                    annotate_task_metadata({"tasks": [], "source": source},
                                           b"validated core", Path("fake.elf"), machine=machine)
                    self.assertEqual(annotate.called, ran)
