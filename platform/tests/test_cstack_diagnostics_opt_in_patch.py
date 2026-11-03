# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute actual pre/post MMU/fiber functions from complete patch context.

Only the committed patch, this fixture, a host C compiler and git are required.
No checkout cache, network, QEMU executable, firmware or generated build is read.
The original source text is the behavioral oracle. Host helpers are shimmed;
this is C logic validation, not guest, hardware or performance validation.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0028-cstack-diagnostics-opt-in.patch"
FIXTURE = Path(__file__).resolve().parent / "fixtures/cstack_diagnostics_harness.c"
CACHE = "hw/misc/esp32s3_cache.c"
COROUTINE = "util/coroutine-wasm.c"
SOURCE_SHA = {
    "before": {
        CACHE: "5c1ceb02e40056580d95f6b2df76330292c4475a892bbabe9a9497a533b4749a",
        COROUTINE: "9d6623d37889f5096ef06c3646145861da24843800bc5fba39c997b3187f1fa6",
    },
    "after": {
        CACHE: "4db4329a453f99444add015bb8b8cf90b6232897e71e9c15078db51c68397e8a",
        COROUTINE: "93a0857d7213ce5325bf4367028408a2a3ca19d72628ba285e257aa1c746eb1b",
    },
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def complete_patch_sources():
    """Reject partial hunks; source/license bytes come from complete context."""
    result = {"before": {}, "after": {}}
    name = None
    old, new = [], []
    expected = None

    def finish():
        if name is None:
            return
        if expected != (len(old), len(new)):
            raise AssertionError("Patch does not contain the complete source: " + name)
        for kind, rows in (("before", old), ("after", new)):
            text = "".join(rows)
            if digest(text) != SOURCE_SHA[kind][name]:
                raise AssertionError("Exact source identity changed: " + name)
            result[kind][name] = text

    for line in PATCH.read_text().splitlines(keepends=True):
        if line.startswith("diff --git "):
            finish()
            match = re.fullmatch(r"diff --git a/(\S+) b/(\S+)\n", line)
            if not match or match[1] != match[2] or match[1] not in SOURCE_SHA["before"]:
                raise AssertionError("Unexpected patch path")
            name = match[1]
            if name in result["before"]:
                raise AssertionError("Duplicate source file")
            old, new, expected = [], [], None
        elif line.startswith("@@ "):
            if expected is not None:
                raise AssertionError("Complete source must have one hunk")
            match = re.match(r"@@ -1,(\d+) \+1,(\d+) @@", line)
            if not match:
                raise AssertionError("Expected complete file from line one")
            expected = int(match[1]), int(match[2])
        elif expected is not None:
            if line.startswith((" ", "-")):
                old.append(line[1:])
            if line.startswith((" ", "+")):
                new.append(line[1:])
    finish()
    if set(result["before"]) != set(SOURCE_SHA["before"]):
        raise AssertionError("Missing source files")
    return result


def function(text, name):
    match = re.search(r"^.*\b" + re.escape(name) + r"\([^;]*?\)\s*\{", text, re.M)
    if not match:
        raise AssertionError("Actual function missing: " + name)
    at = text.index("{", match.start())
    depth, pos, quote, comment = 1, at + 1, None, None
    while depth:
        c, pair = text[pos], text[pos:pos + 2]
        if comment == "line":
            if c == "\n":
                comment = None
        elif comment == "block":
            if pair == "*/":
                comment, pos = None, pos + 1
        elif quote:
            if c == "\\":
                pos += 1
            elif c == quote:
                quote = None
        elif pair == "//":
            comment, pos = "line", pos + 1
        elif pair == "/*":
            comment, pos = "block", pos + 1
        elif c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        pos += 1
    return text[match.start():pos]


def actual_program(sources):
    cache, coroutine = sources[CACHE], sources[COROUTINE]
    start = coroutine.index("typedef struct {")
    end = coroutine.index("} CoroutineEmscripten;") + len("} CoroutineEmscripten;")
    typedef = coroutine[start:end]
    declarations = "\n".join(re.findall(r"^static __thread [^\n]+;", cache + "\n" + coroutine, re.M))
    functions = []
    if "m5_cache_trace_enabled" in cache:
        functions += [function(cache, "m5_cache_trace_enabled"), function(coroutine, "m5_swap_trace_enabled")]
    functions += [function(cache, name) for name in (
        "esp32s3_mmu_invalidate_page", "m5_cache_stack_log", "esp32s3_write_mmu_value")]
    functions += [function(coroutine, name) for name in ("m5_swap_stack_log", "qemu_coroutine_switch")]
    return FIXTURE.read_text().replace("/* ACTUAL_COROUTINE_TYPE */", typedef).replace(
        "/* ACTUAL_FUNCTIONS */", declarations + "\n" + "\n".join(functions))


def observation(completed):
    behavior = "\n".join(line for line in completed.stdout.splitlines() if line.startswith("BEHAVIOR "))
    metrics = {}
    for line in completed.stdout.splitlines():
        if line.startswith("METRICS "):
            words = line.split()
            metrics[words[1]] = {key: int(value) for key, value in (word.split("=") for word in words[2:])}
    # Only normalize the actual host addresses of coroutine objects for ASLR.
    # Source log phases, IDs, saved stack values, counters and limits stay exact.
    trace = re.sub(r"\b(from|to)=0x[0-9a-f]+", r"\1=<coroutine>", completed.stderr)
    return {"behavior": behavior, "metrics": metrics, "trace": trace}


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "Host C compiler and git required")
class CstackDiagnosticsOptInPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="m5-cstack-gate-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.sources = complete_patch_sources()
        tree = cls.directory / "source"
        for name, text in cls.sources["before"].items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(PATCH)], cwd=tree, check=True, capture_output=True)
        for name, text in cls.sources["after"].items():
            if (tree / name).read_text() != text:
                raise AssertionError("Forward application is not the exact postimage")
        subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=tree, check=True, capture_output=True)
        for name, text in cls.sources["before"].items():
            if (tree / name).read_text() != text:
                raise AssertionError("Reverse application did not restore the exact preimage")
        cls.programs = {kind: actual_program(sources) for kind, sources in cls.sources.items()}
        cls.binaries = {kind: cls.compile(text, kind) for kind, text in cls.programs.items()}
        cls.reference = observation(cls.execute(cls.binaries["before"], "1"))

    @classmethod
    def compile(cls, text, name):
        source = cls.directory / (name + ".c")
        binary = cls.directory / name
        source.write_text(text)
        completed = subprocess.run([shutil.which("cc"), "-std=c11", "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-sign-compare", str(source), "-o", str(binary)],
                       capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise AssertionError("Actual C contract compilation failed:\n" + completed.stderr)
        return binary

    @staticmethod
    def execute(binary, mode):
        return subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)

    def audit(self, result, on):
        self.assertEqual(result["behavior"], self.reference["behavior"], "Actual MMU/fiber behavior changed")
        self.assertEqual(set(result["metrics"]), {"main", "worker"})
        if on:
            self.assertEqual(result["trace"], self.reference["trace"], "Trace phases/IDs/budgets changed")
            for thread, metrics in result["metrics"].items():
                self.assertEqual(metrics["env"], 2)
                self.assertEqual({k: v for k, v in metrics.items() if k != "env"},
                                 {k: v for k, v in self.reference["metrics"][thread].items() if k != "env"})
        else:
            self.assertEqual(result["trace"], "")
            for metrics in result["metrics"].values():
                self.assertEqual(metrics["env"], 2, "Option must be read once per translation unit and thread")
                self.assertTrue(all(metrics[key] == 0 for key in (
                    "sp", "heap", "base", "end", "tid", "logs", "cacheid", "cachelogs", "swapid", "swaplogs")),
                    "Disabled trace still prepared output")

    def test_explicit_one_preserves_actual_behavior_and_original_trace(self):
        p = self.execute(self.binaries["after"], "1")
        self.assertEqual(p.returncode, 0, p.stderr)
        result = observation(p)
        self.audit(result, True)
        ids = [int(value) for value in re.findall(r"M5_CSTACK_CACHE .*?write=(\d+) phase=mmu_entry", result["trace"])]
        self.assertEqual(ids[:5], [1, 3, 7, 8, 12], "Invalid, unchanged, PSRAM and no-backend writes retain original ID gaps")
        for metrics in result["metrics"].values():
            self.assertEqual((metrics["cachelogs"], metrics["swaplogs"]), (256, 256))
            self.assertEqual((metrics["cacheid"], metrics["swapid"]), (173, 151))

    def test_default_off_and_all_other_values_skip_preparation_in_each_thread(self):
        for mode in ("unset", "0", "", "true", "01", "1 "):
            with self.subTest(mode=mode):
                p = self.execute(self.binaries["after"], mode)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.audit(observation(p), False)
        # Fixture flips its mocked ENV after both caches initialize, then does
        # more MMU/fiber work. The two lookups/thread remain unchanged.

    def test_real_source_negative_controls_are_detected(self):
        mutations = (
            ("eager-counter", "unsigned m5_write_id = m5_trace ? ++m5_cache_write_id : 0;",
             "unsigned m5_write_id = ++m5_cache_write_id;"),
            ("eager-sp", "const bool m5_trace = m5_cache_trace_enabled();",
             "emscripten_stack_get_current(); const bool m5_trace = m5_cache_trace_enabled();"),
            ("missing-pread", "blk_pread(s->flash_blk, physical_address, ESP32S3_PAGE_SIZE, cache_data, 0);",
             "(void)cache_data;"),
            ("missing-fiber-swap", "emscripten_fiber_swap(&from->fiber, &to->fiber);",
             "/* intentionally broken negative control */"),
        )
        for name, before, after in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(self.programs["after"].count(before), 1)
                binary = self.compile(self.programs["after"].replace(before, after, 1), name)
                p = self.execute(binary, "unset")
                if p.returncode == 0:
                    with self.assertRaises(AssertionError, msg="Bad real-source mutation escaped the contract"):
                        self.audit(observation(p), False)
                # The removed fiber operation also violates the fixture's
                # direct action/current-coroutine assertion and exits nonzero.


if __name__ == "__main__":
    unittest.main()
