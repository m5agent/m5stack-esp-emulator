"""Compile and replay Xtensa high-priority IRQ cooperative scheduling."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0065-xtensa-high-priority-irq-cooperative-yield.patch"
)


def file_hunks(file_marker: str) -> str:
    text = PATCH.read_text()
    start = text.index(file_marker)
    end = text.find("\n--- a/", start + len(file_marker))
    section = text[start:] if end < 0 else text[start:end]
    lines: list[str] = []
    for line in section.splitlines():
        if line.startswith(("@@ ", " ", "+")):
            lines.append(line[1:] if line.startswith((" ", "+")) else line)
    return "\n".join(lines)


def extract_function(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError("unterminated function")


MAIN = r"""
int main(void)
{
    CPUState cpu;

    assert(!icount_high_priority_irq_active());
    icount_note_high_priority_irq(0, true);
    assert(icount_high_priority_irq_active());
    icount_yield_for_high_priority_irq(&cpu);
    assert(exit_count == 1);
    icount_note_high_priority_irq(1, true);
    icount_note_high_priority_irq(0, false);
    assert(icount_high_priority_irq_active());
    icount_note_high_priority_irq(1, false);
    assert(!icount_high_priority_irq_active());
    icount_yield_for_high_priority_irq(&cpu);
    assert(exit_count == 1);
    return 0;
}
"""


class XtensaHighPriorityIrqCooperativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_high_priority_yield_round_trip(self):
        hunks = file_hunks(
            "--- a/accel/tcg/tcg-accel-ops-icount.c"
        )
        note = extract_function(
            hunks, "void icount_note_high_priority_irq("
        )
        yield_function = extract_function(
            hunks, "void icount_yield_for_high_priority_irq("
        )
        active = extract_function(
            hunks, "bool icount_high_priority_irq_active("
        )
        source = "\n".join(
            [
                "#include <assert.h>",
                "#include <stdbool.h>",
                "#include <stdint.h>",
                "#include <stdlib.h>",
                "#define icount_enabled() true",
                "static unsigned icount_high_priority_irq_cpus;",
                "typedef struct CPUState { int unused; } CPUState;",
                "static int exit_count;",
                "static void cpu_exit(CPUState *ignored)",
                "{ (void) ignored; ++exit_count; }",
                note,
                yield_function,
                active,
                MAIN,
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "budget.c"
            binary = Path(directory) / "budget"
            source_path.write_text(source)
            compiled = subprocess.run(
                [
                    shutil.which("cc"),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source_path),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run(
                [str(binary)],
                check=True,
                capture_output=True,
                timeout=5,
            )

    def test_patch_tracks_enter_return_and_reset(self):
        text = PATCH.read_text()
        self.assertIn(
            "env->pending_irq_level >= 4", text
        )
        self.assertIn(
            "icount_note_high_priority_irq(cs->cpu_index, true)", text
        )
        self.assertIn(
            "icount_note_high_priority_irq(env_cpu(env)->cpu_index, false)",
            text,
        )
        self.assertIn(
            "icount_note_high_priority_irq(cs->cpu_index, false)", text
        )
        self.assertEqual(
            text.count("gen_helper_high_priority_irq_return(tcg_env);"),
            2,
        )
        self.assertEqual(
            text.count("gen_helper_high_priority_irq_yield(tcg_env"),
            2,
        )
        self.assertIn("if (!icount_enabled())", text)
        self.assertEqual(text.count("icount_enabled()"), 3)
        self.assertIn("xtensa_get_cintlevel(env) == 4", text)
        self.assertNotIn("M5SW_DISABLE_WDT", text)
        self.assertNotIn("ICOUNT_HIGH_PRIORITY_IRQ_BUDGET", text)


if __name__ == "__main__":
    unittest.main()
