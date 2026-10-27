#!/usr/bin/env python3
"""Extract actual controller/model C, compile with synthetic clock/QOM shims.

No guest/API/network calls; output is model/controller C evidence only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def function(text, name):
    point = text.index(name + "(")
    start = text.rfind("\n", 0, point) + 1
    opening = text.index("{", point)
    level = 1
    pos = opening + 1
    while level:
        if text[pos] == "{":
            level += 1
        elif text[pos] == "}":
            level -= 1
        pos += 1
    return start, pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve()
    pieces = []
    extracted = []

    def add(rel, start, end, scope):
        path = source / rel
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        cut = text[start:end]
        pieces.append(cut)
        saved = args.out / (scope + ".source.c.txt")
        saved.write_text(cut)
        extracted.append({"source_path": str(path), "source_sha256": digest(raw),
                          "scope": scope, "start_line": text.count("\n", 0, start) + 1,
                          "end_line": text.count("\n", 0, end) + 1,
                          "fragment_sha256": digest(cut.encode()),
                          "fragment_file": saved.name})

    gpio_rel = Path("hw/gpio/esp32_gpio.c")
    unit_rel = Path("hw/m5stopwatch/m5_unit_gpio.c")
    gpio = (source / gpio_rel).read_text()
    unit = (source / unit_rel).read_text()
    old = (REPO / "docs/evidence/2026-10-27-flashlight-and-uiflow-base/acceptance/route-history/harness.c").read_text()
    shim = old[:old.index("static int pads[49]")]
    shim = shim.replace("QEMUTimer *timers[8]", "QEMUTimer *timers[128]")
    shim = shim.replace("Property properties[64]", "Property properties[1024]")
    shim = shim.replace("for(unsigned i=0;i<property_count;i++)assert(strcmp(name,properties[i].name));", "")
    shim += '''
#include <inttypes.h>
#define BIT(x) (1ULL << (x))
#define HWADDR_PRIx PRIx64
#define A_GPIO_STRAP 0x38
typedef uint64_t hwaddr;
typedef struct Esp32GpioState { unsigned strap_mode; int irq; } Esp32GpioState;
#define ESP32_GPIO(p) ((Esp32GpioState *)(p))
typedef void (*esp32_gpio_out_cb)(void *,int,int);
int esp32_gpio_get_line(int pin);
static unsigned ledc_route_notifications;
static void qemu_set_irq(int irq,int level) { (void)irq; (void)level; }
static void esp32_ledc_gpio_route_changed(bool s3) { ledc_route_notifications++; }
void m5_unit_gpio_route_changed(bool s3,unsigned pin);
'''
    pieces.append(shim)
    add(gpio_rel, gpio.index("#define GPIO_NPINS"), gpio.index("static const MemoryRegionOps"), "actual-gpio-controller")
    a, b = function(gpio, "esp32_gpio_matrix_out_signal")
    add(gpio_rel, a, b, "actual-gpio-route-query")
    a = unit.index("typedef struct AW3641State AW3641State;")
    b = unit.index("/* BEGIN AW3641 NOMINAL DIGITAL MODEL")
    add(unit_rel, a, b, "actual-unit-registry")
    a = b
    b = unit.index("/* END AW3641 NOMINAL DIGITAL MODEL */") + len("/* END AW3641 NOMINAL DIGITAL MODEL */")
    add(unit_rel, a, b, "actual-aw3641-model")
    if "void m5_unit_gpio_route_changed(" in unit:
        a, b = function(unit, "m5_unit_gpio_route_changed")
        add(unit_rel, a, b, "actual-unit-route-notification")
    if "void m5_unit_gpio_initial_complete(" in unit:
        a, b = function(unit, "m5_unit_gpio_initial_complete")
        add(unit_rel, a, b, "actual-unit-initial-complete")
    tests = (HERE / "cases.c").read_text()
    pieces.append(tests)
    harness = args.out / "harness.c"
    harness.write_text("\n".join(pieces))
    compiler = subprocess.run(["/usr/bin/clang", "--version"], capture_output=True)
    (args.out / "compiler.txt").write_bytes(compiler.stdout + compiler.stderr)
    compile_argv = ["/usr/bin/clang", "-std=c11", "-O0", "-g", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-function", str(harness), "-o", str(args.out / "harness")]
    build = subprocess.run(compile_argv, capture_output=True)
    (args.out / "compile.stdout.txt").write_bytes(build.stdout)
    (args.out / "compile.stderr.txt").write_bytes(build.stderr)
    run = None
    run_argv = [str(args.out / "harness")]
    if build.returncode == 0:
        run = subprocess.run(run_argv, capture_output=True)
        (args.out / "stdout.txt").write_bytes(run.stdout)
        (args.out / "stderr.txt").write_bytes(run.stderr)
    receipt = {"schema_version": 1, "scope": "actual extracted GPIO MMIO and AW3641 C with synthetic clock/QOM, no guest/hardware/API claim",
               "source_root": str(source), "api_contacted": False, "guest_execution": "NOT RUN", "hardware_execution": "NOT RUN",
               "fragments": extracted, "shim_source": "formal old route-history harness prefix, with enlarged containers and duplicate property restriction removed for multi-instance tests",
               "tests_sha256": digest(tests.encode()), "generator_sha256": digest(Path(__file__).read_bytes()),
               "harness_sha256": digest(harness.read_bytes()), "compile_argv": compile_argv, "compile_exit": build.returncode,
               "run_argv": run_argv, "run_exit": None if run is None else run.returncode}
    receipt["files"] = [{"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in sorted(args.out.iterdir()) if p.is_file()]
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "compile_exit": build.returncode, "run_exit": receipt["run_exit"], "tests_sha256": receipt["tests_sha256"]}))
    return 0 if build.returncode == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
