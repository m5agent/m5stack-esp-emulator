#!/usr/bin/env python3
"""Build the hardware API denominator from official UIFlow sources.

This is an inventory, not runtime evidence.  Pass an official UIFlow checkout;
the selected firmware exports must still be compared before reporting results.
"""

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uiflow", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("inventory_hardware.source.json"))
    args = parser.parse_args()
    root = args.uiflow
    rows = {}
    sources = {}

    def source(path):
        relative = str(path.relative_to(root))
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return relative

    def normalize(name, stem):
        if name.startswith("ALS."):
            return "M5.Als." + name.split(".", 1)[1]
        if name.startswith("mic_config_t."):
            return "M5.Mic.config." + name.split(".", 1)[1]
        if name.startswith("speaker_config_t."):
            return "M5.Speaker.config." + name.split(".", 1)[1]
        if stem == "touch" and "." not in name:
            name = "M5.Touch." + name
        elif stem in ("sht30", "sht4x") and "." not in name:
            name = stem.upper() + "." + name
        elif stem == "lora" and "." not in name:
            name = "LoRa." + name
        if name.startswith("Callback_Type."):
            return "M5.Button.CB_TYPE." + name.split(".", 1)[1]
        if name.startswith("IMU_TYPE."):
            return "M5.Imu." + name
        if name.startswith("PORT."):
            return "M5.Power." + name
        if name.startswith(("M5.", "camera.", "hardware.", "machine.")):
            return name
        first = name.split(".")[0]
        if first in ("Power", "IMU", "Imu", "Button", "Touch", "Mic", "Speaker", "ALS", "speaker_config_t", "mic_config_t", "IMU_TYPE", "PORT"):
            return "M5." + name.replace("IMU.", "Imu.")
        if first in ("Pin", "ADC", "ADCBlock", "I2C", "SoftI2C", "SPI", "SoftSPI", "PWM", "UART", "RTC", "WDT", "Timer", "I2S"):
            return "machine." + name
        return "hardware." + name

    def recipe(api, kind):
        if kind == "constant":
            return ("constant-reflection", "VALUE_ONLY", "Check value/type and public export; never count a constant as peripheral functional evidence.")
        parts = api.split(".")
        group = next((item for item in parts[1:] if item and item[0].isupper()), parts[0])
        if group in ("IMU_TYPE", "PORT", "speaker_config_t", "mic_config_t"):
            return ("config-roundtrip", "CONFIG_ONLY", "Read configuration field/type; mutate only non-pin fields while subsystem is stopped, then restore.")
        if group == "Power":
            if api.endswith(("powerOff", "timerSleep", "deepSleep", "lightSleep")):
                return ("power-lifecycle", "DISPOSABLE_SESSION", "Execute once in a dedicated visible session; require guest sleep/reset/wake or stopped-state evidence; no return-value PASS.")
            return ("power-registers", "CONTROLLER_EVIDENCE", "Compare getters to PMIC/ADC injection; change each supported setting, read corresponding controller register/QOM output, restore baseline.")
        if group == "Imu":
            return ("imu-dynamic", "CONTROLLER_EVIDENCE", "Inject two distinct BMI270/BMM150 physical vectors via QOM; call M5.update then compare typed tuples to expected axes and scales; inspect enable/type.")
        if group == "Button":
            return ("button-transitions", "INPUT_EVIDENCE", "For every board-supported Btn object inject press/release, single/double click and hold; sample each query and callbacks with bounded M5.update loops.")
        if group == "Touch":
            return ("touch-transitions", "INPUT_EVIDENCE", "CoreS3: inject down/move/up at two coordinates and compare count, position, raw/detail fields. Cardputer-ADV: prove no-touch capability boundary.")
        if group in ("ALS", "Als"):
            return ("als-dynamic", "CONTROLLER_EVIDENCE", "CoreS3: inject light/proximity at LTR553 register model and compare both getters; Cardputer-ADV has no onboard ALS.")
        if group == "Speaker":
            return ("speaker-pcm", "DATA_PLANE", "Exercise config/lifecycle/volume/channel controls and tone/raw/WAV/file playback; require nonempty decoded controller PCM, expected sample/rate/channel/duration and stop counters.")
        if group == "Mic":
            return ("mic-pcm", "DATA_PLANE", "Disable Speaker; inject deterministic I2S/PDM PCM; exercise config/rate/lifecycle/record state and compare captured PCM bytes; restore Speaker only after end.")
        if group == "camera" or api.startswith("camera."):
            return ("camera-frame", "DATA_PLANE", "CoreS3: inject identifiable DVP frame, init RGB565/resolution, capture pixels, test mirror/flip readback and resulting orientation; Cardputer-ADV has no camera.")
        if group in ("Keyboard", "KeyboardI2C", "KeysState", "KeyEvent", "HIDInputReport", "Point2D", "KeyValue"):
            return ("keyboard-fifo", "INPUT_EVIDENCE", "Cardputer-ADV KeyboardI2C: inject TCA8418 key events including shift/fn, assert key state/event callback and HID report; deinit must disable IRQ/clear local queues. Matrix Keyboard applies only to original Cardputer.")
        if group == "RGB":
            return ("rgb-rmt", "DATA_PLANE", "Cardputer-ADV: instantiate onboard RGB, set two colors/brightness and require RMT-decoded LED QOM state; CoreS3 has no onboard addressable RGB.")
        if group == "IR":
            return ("ir-nec", "DATA_PLANE", "Cardputer-ADV: send known NEC command/data and inspect RMT decoded pulses; no onboard RX. CoreS3 has no onboard IR. Callback registration alone is not RX PASS.")
        if group in ("Pin", "PWM"):
            return ("gpio-waveform", "DATA_PLANE", "Use a free Grove pad; verify output latch, pad receiver, pull/open-drain, IRQ or PWM frequency/duty via GPIO/RMT observer. Restore pin ownership; no host-invented pad values.")
        if group in ("I2C", "SoftI2C"):
            return ("i2c-roundtrip", "DATA_PLANE", "Use Grove Unit controller/fixture; exercise scan, direct/repeated-start/register/into/vector forms with exact byte comparison, NACK and deinit/reinit. Do not reconfigure internal M5 I2C.")
        if group == "SDCard":
            return ("sd-storage", "DATA_PLANE", "Mount the board-wired SD controller with a session-owned storage artifact; write/read/fsync distinct bytes through /sd, verify the isolated card image changes and the source artifact does not. Factory return alone is not storage evidence.")
        if group in ("SPI", "SoftSPI"):
            return ("spi-roundtrip", "DATA_PLANE", "Use documented free SPI wiring and controller-attached SD/NFC fixture; compare write/read/into/full-duplex byte transfers and CS/reset; restore display bus ownership.")
        if group in ("UART", "PWR485"):
            return ("uart-loopback", "DATA_PLANE", "Use a free UART with real controller peer/loopback; compare bytes/readinto/line, any/flush/txdone, IRQ and break, test timeout then deinit; never seize live REPL UART.")
        if group in ("ADC", "ADCBlock"):
            return ("adc-injection", "CONTROLLER_EVIDENCE", "Inject two in-range voltages through SARADC/eFuse model, check raw/scaled/calibrated readings, attenuation/width/init/block and restore configuration; failure to inject is MODEL_GAP.")
        if group == "RTC":
            return ("rtc-clock", "CONTROLLER_EVIDENCE", "Set/get an explicit calendar tuple and observe elapsed seconds plus reset semantics; separate ESP32 RTC from absent Cardputer external RTC and CoreS3 BM8563.")
        if group == "WDT":
            return ("wdt-reset", "DISPOSABLE_SESSION", "Dedicated visible session: feed beyond timeout without reset, then stop feeding and require guest reset reason and reboot; API return alone is insufficient.")
        if group == "Timer":
            return ("timer-callback", "CONTROLLER_EVIDENCE", "Bounded one-shot/periodic callbacks, frequency/period conversion, deinit stops count; require elapsed guest ticks.")
        if group == "I2S":
            return ("i2s-pcm", "DATA_PLANE", "Separate raw I2S session; deterministic TX/RX PCM through controller FIFO/DMA and exact byte/rate/format comparison; avoid concurrent M5 audio ownership.")
        return ("other-board-hardware", "BOARD_BOUNDARY", "Reflect exported API, then record explicit absent-hardware boundary on both selected boards; functional coverage requires a matching board/controller and cannot inherit import success.")

    def add(api, signature, kind, path, line, declared_by):
        if not api or api.endswith("."):
            return
        row = rows.setdefault(api, {"api": api, "kind": kind, "signatures": [], "sources": [], "declared_by": [], "runtime_exports": "PENDING", "results": {"cores3": "NOT_RUN", "cardputer-adv": "NOT_RUN"}})
        if signature not in row["signatures"]:
            row["signatures"].append(signature)
        ref = f"{path}:{line}"
        if ref not in row["sources"]:
            row["sources"].append(ref)
        if declared_by not in row["declared_by"]:
            row["declared_by"].append(declared_by)
        rid, level, strategy = recipe(api, kind)
        row.update(recipe_id=rid, required_evidence=level, test_strategy=strategy)
        if api.startswith("M5.Button."):
            row["runtime_paths"] = [api.replace("M5.Button.", "M5." + item + ".") for item in ("BtnA", "BtnB", "BtnC", "BtnPWR", "BtnEXT")]
        else:
            row["runtime_paths"] = [api]
        if api.startswith(("M5.Mic.config.", "M5.Speaker.config.")):
            row["runtime_paths"] = [api.replace(".config.", ".config().")]
            row["recipe_id"] = "config-roundtrip"
            row["required_evidence"] = "CONFIG_ONLY"

    docs = sorted((root / "docs/source/hardware").glob("*.rst"))
    docs += [root / "docs/source/system/power.rst", root / "docs/source/advanced/camera.rst"]
    for path in docs:
        if path.stem in ("index", "display") or not path.is_file():
            continue
        relative = source(path)
        lines = path.read_text().splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"\s*\.\. (?:py:)?(class|method|function|data|attribute|classmethod|staticmethod)::\s*(.+)", line)
            if not match:
                continue
            directive, signature = match.groups()
            signatures = [signature]
            # RST overloads/constants can continue at the directive content indent.
            for continuation in lines[index + 1:]:
                stripped = continuation.strip()
                if not stripped or stripped.startswith(":"):
                    break
                if re.match(r"(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:\(|$)", stripped) and ("(" in stripped or directive == "data"):
                    signatures.append(stripped)
                else:
                    break
            for signature in signatures:
                name = signature.split("(", 1)[0].split(" ->", 1)[0].strip()
                kind = "constructor" if directive == "class" else "constant" if directive == "data" else "property" if directive == "attribute" else "method"
                add(normalize(name, path.stem), signature, kind, relative, index + 1, "official-docs")

    # C-bound public methods not yet documented still belong to the denominator.
    for stem, owner in (("power", "Power"), ("imu", "Imu"), ("button", "Button"), ("touch", "Touch"), ("speaker", "Speaker"), ("mic", "Mic"), ("als", "Als")):
        path = root / f"m5stack/cmodules/m5unified/m5unified_{stem}.c"
        relative = source(path)
        for index, line in enumerate(path.read_text().splitlines()):
            match = re.search(r"MAKE_TABLE\(\w+,\s*(\w+)\)", line)
            if match:
                method = match.group(1)
                add(f"M5.{owner}.{method}", f"{owner}.{method} (C binding)", "method", relative, index + 1, "official-source-public-export")

    # Config objects use an attr callback rather than a public locals table.
    # In particular, Speaker's documented methods do not enumerate these fields.
    for stem, owner in (("mic", "Mic"), ("speaker", "Speaker")):
        path = root / f"m5stack/cmodules/m5unified/{stem}_config_t.c"
        relative = source(path)
        for index, line in enumerate(path.read_text().splitlines()):
            match = re.search(r"attr\s*==\s*MP_QSTR_(\w+)", line)
            if match:
                field = match.group(1)
                add(f"M5.{owner}.config.{field}", f"{stem}_config_t.{field} (C attr binding)", "property", relative, index + 1, "official-source-public-export")

    # hardware's lazy exports and class-specific public Python methods.
    library = root / "m5stack/libs/hardware"
    init_tree = ast.parse((library / "__init__.py").read_text())
    lazy_exports = {}
    for node in init_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_attrs" for target in node.targets):
            lazy_exports = ast.literal_eval(node.value)
    for path in sorted(library.rglob("*.py")):
        relative = source(path)
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            module = str(path.relative_to(library).with_suffix("")).replace("/", ".").removesuffix(".__init__")
            owner = "hardware." + node.name if node.name in lazy_exports else "hardware." + module + "." + node.name
            add(owner, node.name + "(...) -> object", "constructor", relative, node.lineno, "official-source-public-export")
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                    arguments = ast.unparse(method.args)
                    signature = f"{node.name}.{method.name}({arguments})"
                    kind = "property" if any(isinstance(x, ast.Name) and x.id == "property" for x in method.decorator_list) else "method"
                    add(owner + "." + method.name, signature, kind, relative, method.lineno, "official-source-public-export")

    # Public lazy exports may be closures or singleton objects, not classes.
    # SDCard is a closure that mounts /sd and therefore has no class statement.
    for export, module in lazy_exports.items():
        api = "hardware." + export
        if api in rows:
            continue
        path = library / (module + ".py")
        if not path.is_file():
            path = library / module / "__init__.py"
        relative = source(path)
        tree = ast.parse(path.read_text())
        assignment = next((node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == export for target in node.targets)), None)
        if assignment is not None:
            signature = export + " (public lazy export; inspect runtime type/callability)"
            kind = "property"
            if export == "SDCard":
                factory = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "sdcard")
                signature = "SDCard(" + ast.unparse(factory.args) + ")"
                kind = "constructor"
            add(api, signature, kind, relative, assignment.lineno, "official-source-lazy-export")

    # These factory/base classes expose inherited methods on returned objects.
    # Inspecting only hardware.RGB's class dictionary would miss NeoPixel's API.
    inherited = (
        ("hardware.RGB", "driver/neopixel/__init__.py", "NeoPixel"),
        ("hardware.NFC", "driver/nfc.py", "NFCReader"),
        ("hardware.Rotary", "driver/rotary/rotary.py", "Rotary"),
        ("hardware.Rotary", "driver/rotary/rotary_irq_esp.py", "RotaryIRQ"),
    )
    for owner, module_path, class_name in inherited:
        path = root / "m5stack/libs" / module_path
        relative = source(path)
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and not method.name.startswith("_"):
                    api = owner + "." + method.name
                    add(api, f"{class_name}.{method.name}({ast.unparse(method.args)})", "method", relative, method.lineno, "official-source-inherited-export")
                    rows[api]["instance_factory"] = owner + "()"

    # UIFlow hardware forwards unknown names to machine. These public classes
    # need their own recipes even where the UIFlow docs do not list every alias.
    machine = {
        "I2C": "init deinit scan readfrom readfrom_into writeto writevto readfrom_mem readfrom_mem_into writeto_mem",
        "SoftI2C": "init deinit scan start stop readinto write readfrom readfrom_into writeto writevto readfrom_mem readfrom_mem_into writeto_mem",
        "SPI": "init deinit read readinto write write_readinto",
        "SoftSPI": "init deinit read readinto write write_readinto",
        "PWM": "init deinit freq duty duty_u16 duty_ns",
        "Pin": "init value on off irq drive mode pull",
        "ADC": "init atten width read read_u16 read_uv block",
        "ADCBlock": "init connect",
        "UART": "init deinit any read readinto readline write sendbreak flush txdone irq",
        "RTC": "init datetime memory",
        "WDT": "feed",
        "Timer": "init deinit value",
        "I2S": "init deinit readinto write irq shift",
    }
    for owner, methods in machine.items():
        if "machine." + owner not in rows:
            add("machine." + owner, f"{owner} (runtime constructor candidate)", "constructor", "m5stack/libs/hardware/__init__.py", 38, "machine-alias-export-candidate")
        for method in methods.split():
            api = f"machine.{owner}.{method}"
            if api not in rows:
                # Mark as an export candidate; reflection decides applicability.
                add(api, f"{owner}.{method} (runtime export candidate)", "method", "m5stack/libs/hardware/__init__.py", 38, "machine-alias-export-candidate")

    result = {"schema_version": 1, "scope": "All official UIFlow hardware docs except Display/Widgets, plus M5 binding/hardware Python public exports and forwarded machine candidates", "devices": ["cores3", "cardputer-adv"], "result_rule": "NOT_RUN is the initial state. Reflection/import is presence evidence only. Functional PASS requires the recipe's controller/data-plane evidence on the exact selected firmware SHA.", "official_source_sha256": sources, "entries": sorted(rows.values(), key=lambda x: x["api"])}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"entries": len(rows), "sources": len(sources), "out": str(args.out)}))


if __name__ == "__main__":
    main()
