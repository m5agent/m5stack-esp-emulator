"""Replay bootstrap patches and compile actual GPIO/AW/RTC-pad source as standard C.

No .work checkout, generated QEMU configuration, glib, downloads or QEMU runtime
are required. The pinned upstream GPIO stub/header below are replay seeds, not
an implementation oracle. Controller/MMIO/observer/AW/aux algorithm bytes come
only from the committed patch stack. Only host OS/QOM/timer/MR glue is shimmed.
This establishes C logic behavior, never guest or physical-hardware evidence.
"""
import ast
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "platform/tests/fixtures/flashlight_cold_pad_harness.c"
PATCH = "patches/qemu-m5stack-peripherals/0047-unit-flashlight-cold-pad-observation.patch"
QEMU_COMMIT = "40edccac415693c5130f91c01d84176ae6008566"
GPIO = "hw/gpio/esp32_gpio.c"
HEADER = "include/hw/gpio/esp32_gpio.h"
UNIT = "hw/m5stopwatch/m5_unit_gpio.c"
AUX = "hw/gpio/esp32s3_gpio_pad_aux.c"
AUX_HEADER = "include/hw/gpio/esp32s3_gpio_pad_aux.h"
RUNTIME_HEADER = "hw/m5stopwatch/m5_unit_runtime.h"
REPLAY_FILES = (GPIO, HEADER, UNIT, AUX, AUX_HEADER, RUNTIME_HEADER)

# Exact upstream QEMU_COMMIT input bytes. Its GPIO model has empty OUT/MMIO
# behavior; the functional GPIO resolver/MMIO is supplied by bootstrap patches.
BASE_GPIO = r'''/*
 * ESP32 GPIO emulation
 *
 * Copyright (c) 2019 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/hw.h"
#include "hw/sysbus.h"
#include "hw/registerfields.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "hw/gpio/esp32_gpio.h"



static uint64_t esp32_gpio_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    uint64_t r = 0;
    switch (addr) {
    case A_GPIO_STRAP:
        r = s->strap_mode;
        break;

    default:
        break;
    }
    return r;
}

static void esp32_gpio_write(void *opaque, hwaddr addr,
                       uint64_t value, unsigned int size)
{
}

static const MemoryRegionOps uart_ops = {
    .read =  esp32_gpio_read,
    .write = esp32_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32_gpio_reset_hold(Object *obj, ResetType type)
{
}

static void esp32_gpio_realize(DeviceState *dev, Error **errp)
{
}

static void esp32_gpio_init(Object *obj)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    /* Set the default value for the strap_mode property */
    object_property_set_int(obj, "strap_mode", ESP32_STRAP_MODE_FLASH_BOOT, &error_fatal);

    memory_region_init_io(&s->iomem, obj, &uart_ops, s,
                          TYPE_ESP32_GPIO, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
}

static Property esp32_gpio_properties[] = {
    /* The strap_mode needs to be explicitly set in the instance init, thus, set
     * the default value to 0. */
    DEFINE_PROP_UINT32("strap_mode", Esp32GpioState, strap_mode, 0),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32_gpio_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = esp32_gpio_reset_hold;
    dc->realize = esp32_gpio_realize;
    device_class_set_props(dc, esp32_gpio_properties);
}

static const TypeInfo esp32_gpio_info = {
    .name = TYPE_ESP32_GPIO,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32GpioState),
    .instance_init = esp32_gpio_init,
    .class_init = esp32_gpio_class_init,
    .class_size = sizeof(Esp32GpioClass),
};

static void esp32_gpio_register_types(void)
{
    type_register_static(&esp32_gpio_info);
}

type_init(esp32_gpio_register_types)
'''
BASE_HEADER = r'''#pragma once

#include "hw/sysbus.h"
#include "hw/hw.h"
#include "hw/registerfields.h"

#define TYPE_ESP32_GPIO "esp32.gpio"
#define ESP32_GPIO(obj)             OBJECT_CHECK(Esp32GpioState, (obj), TYPE_ESP32_GPIO)
#define ESP32_GPIO_GET_CLASS(obj)   OBJECT_GET_CLASS(Esp32GpioClass, obj, TYPE_ESP32_GPIO)
#define ESP32_GPIO_CLASS(klass)     OBJECT_CLASS_CHECK(Esp32GpioClass, klass, TYPE_ESP32_GPIO)

REG32(GPIO_STRAP, 0x0038)

#define ESP32_STRAP_MODE_FLASH_BOOT 0x12
#define ESP32_STRAP_MODE_UART_BOOT  0x0f

typedef struct Esp32GpioState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;
    uint32_t strap_mode;
} Esp32GpioState;

typedef struct Esp32GpioClass {
    SysBusDeviceClass parent_class;
} Esp32GpioClass;
'''

def digest(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def bootstrap_stack():
    tree = ast.parse((ROOT / "scripts/bootstrap-unit-runtime.py").read_text())
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("PATCHES", "QEMU_COMMIT"):
                    values[target.id] = ast.literal_eval(node.value)
    if values["QEMU_COMMIT"] != QEMU_COMMIT:
        raise AssertionError("upstream QEMU pin changed; update the exact replay seeds")
    if len(values["PATCHES"]) != len(set(values["PATCHES"])) or PATCH not in values["PATCHES"]:
        raise AssertionError("cold-pad patch missing or duplicated in bootstrap")
    return values["PATCHES"]


def replay(root, current=True):
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    for name, data in ((GPIO, BASE_GPIO), (HEADER, BASE_HEADER)):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    patches = [name for name in bootstrap_stack() if current or name != PATCH]
    for name in patches:
        command = ["git", "apply", *["--include=" + item for item in REPLAY_FILES]]
        subprocess.run(command + ["--check", str(ROOT / name)], cwd=root, check=True, capture_output=True)
        subprocess.run(command + [str(ROOT / name)], cwd=root, check=True, capture_output=True)
    names = REPLAY_FILES if current else (GPIO, HEADER, UNIT, RUNTIME_HEADER)
    return {name: (root / name).read_text() for name in names}


def span(source, first, last):
    start = source.index(first)
    end = source.index(last, start)
    return source[start:end]


def function(source, name):
    match = re.search(r"^[^\n;]*\b" + re.escape(name) + r"\([^;]*?\)\n\{", source, re.M)
    if not match:
        raise AssertionError("missing actual source function: " + name)
    depth = 0
    # Skip braces inside C comments and literals while preserving exact bytes.
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', re.S)
    for token in tokens.finditer(source, source.index("{", match.start())):
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():token.end()]
    raise AssertionError("unclosed source function: " + name)


def without_includes(source):
    # Environment includes alone are replaced by fixture types. Every model
    # statement, register definition, function and data table stays unchanged.
    return "".join(line for line in source.splitlines(keepends=True)
                   if not line.lstrip().startswith("#include "))


def program(sources, current=True):
    gpio, unit = sources[GPIO], sources[UNIT]
    pieces = {}
    if current:
        pieces["pad-header"] = without_includes(sources[HEADER][sources[HEADER].index("#define ESP32_GPIO_PAD_SOURCE_GPIO"):])
        pieces["aux-header"] = without_includes(sources[AUX_HEADER])
    pieces["gpio-core-mmio-reset-iomux-init"] = span(gpio, "/*\n * Minimal functional GPIO model", "static Property esp32_gpio_properties[]")
    pieces["gpio-matrix-readers"] = gpio[gpio.index("/* ESP-IDF GPIO matrix register/signal maps"):]
    pieces["unit-registry"] = span(unit, "typedef struct AW3641State AW3641State;", "/* BEGIN AW3641 NOMINAL DIGITAL MODEL")
    model_start = unit.index("/* BEGIN AW3641 NOMINAL DIGITAL MODEL")
    model_end = unit.index("/* END AW3641 NOMINAL DIGITAL MODEL */") + len("/* END AW3641 NOMINAL DIGITAL MODEL */")
    pieces["aw-entire-model"] = unit[model_start:model_end]
    pieces["aw-freeze-hook"] = function(unit, "m5_unit_gpio_initial_complete")
    if not current:
        pieces["legacy-route-hook"] = function(unit, "m5_unit_gpio_route_changed")
    if current:
        pieces["aux-entire-source-except-environment-includes"] = without_includes(sources[AUX])
    for name in ("gpio-core-mmio-reset-iomux-init", "gpio-matrix-readers"):
        if pieces[name] not in gpio:
            raise AssertionError("GPIO fragment changed during extraction")
    if pieces["aw-entire-model"] not in unit:
        raise AssertionError("AW fragment changed during extraction")
    fixture = FIXTURE.read_text()
    if fixture.count("/* REPLAYED_SOURCE */") != 1:
        raise AssertionError("fixture must have exactly one replay insertion point")
    combined = fixture.replace("/* REPLAYED_SOURCE */", "\n".join(pieces.values()))
    manifest = {"files": {name: digest(data) for name, data in sources.items()},
                "fragments": {name: digest(data) for name, data in pieces.items()},
                "fixture": digest(fixture), "program": digest(combined)}
    return combined, manifest


CASES = (
    "cold", "cold-pin9", "cold-pin10", "cold-pin39", "known-low-baseline",
    "same-low", "equivalent-oe", "inverted-edges", "writer-route", "writer-oe-source",
    "writer-iomux", "writer-pull-conflict", "writer-external", "writer-force", "writer-bias",
    "writer-rtc-mux", "writer-rtc-hold", "writer-digital-hold", "writer-rtc-force-hold",
    "writer-digital-force-hold", "writer-rtc-isolation", "writer-digital-isolation",
    "writer-wrapper-isolation", "pad-out", "pad-enable", "pad-external",
    "open-drain-direct", "open-drain-mmio", "high-roundtrip-flash", "high-roundtrip-torch",
    "unsupported-low", "late-reset-500000", "late-reset-500001", "gpio-reset-low",
    "gpio-reset-retains-hold", "gpio-reset-retains-mux", "gpio-reset-active",
    "sticky-sleep", "sticky-force-pd", "release-owner",
)


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class FlashLightColdPadPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.sources = replay(cls.directory / "current")
        cls.old_sources = replay(cls.directory / "old", current=False)
        cls.binary = cls.compile(cls.sources, True)
        cls.old_binary = cls.compile(cls.old_sources, False)

    @classmethod
    def compile(cls, sources, current):
        source, manifest = program(sources, current)
        path = cls.directory / ("candidate.c" if current else "old.c")
        path.write_text(source)
        binary = path.with_suffix(".bin")
        # Preserve replayed GPIO bytes, including its signed -1 sentinels in
        # unsigned ternaries. GCC diagnoses those under -Wextra; every other
        # enabled warning remains an error in this standalone host harness.
        result = subprocess.run([shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                                 "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                                 "-Wno-sign-compare",
                                 "-DOLD_RUNTIME=" + str(int(not current)), str(path), "-o", str(binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    def test_exact_pinned_upstream_replay_seeds(self):
        self.assertEqual(digest(BASE_GPIO), "1e8bb5b945a7a20910695c63052265ddb1cf23ca0e3c34f5c2c37d2a721050a6")
        self.assertEqual(digest(BASE_HEADER), "b14af13713ff86ad406a55c0d04c52259129e412cd4e45dd3b844db34ee7b836")

    def test_full_bootstrap_replay_builds_real_algorithms_without_work_or_glib(self):
        source, manifest = program(self.sources)
        origins = {
            GPIO: ("gpio_snapshot_internal", "esp32_gpio_write", "esp32_gpio_iomux_write",
                   "esp32_gpio_reset_hold", "esp32_gpio_notify_pads"),
            UNIT: ("aw3641_pad_event", "aw3641_pad_edge", "aw3641_finish_reset"),
            AUX: ("esp32s3_gpio_pad_aux_cntl_write",),
        }
        for origin, names in origins.items():
            for name in names:
                self.assertEqual(function(source, name), function(self.sources[origin], name))
        self.assertNotIn("GPIO_SOURCE", source)
        self.assertEqual(set(manifest["files"]), set(REPLAY_FILES))

    def test_same_cold_mmio_path_is_a_real_old_source_failure(self):
        result = subprocess.run([str(self.old_binary), "cold"], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at-500001ns at=500001 known=0", result.stdout)
        self.assertIn("low=-1 reset_at=-1 edges=0 rising=0", result.stdout)
        # The pre-0047 board mapped IO_MUX to an unimplemented region. The old
        # harness therefore uses the same GPIO MMIO, and no fabricated IO_MUX.
        self.assertNotIn("esp32_gpio_iomux_write", self.old_sources[GPIO])

    def test_all_controller_aw_aux_integration_cases(self):
        for case in CASES:
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS " + case, result.stdout)


if __name__ == "__main__":
    unittest.main()
