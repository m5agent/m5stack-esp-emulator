#!/usr/bin/env python3
"""Build a UI API inventory from official docs and real guest reflection.

Reflection is declaration evidence only. It never grants functional coverage.
All files supplied with --runtime-jsonl must be captured from a visible Device
Service session. This helper does not launch an emulator or execute guest code.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess


GUEST_PROBE = '''import sys, json, hashlib
print("M5EMU_API_UI_BEGIN")
print("M5EMU_API_UI " + json.dumps({"kind":"environment", "version":sys.version, "implementation":repr(sys.implementation)}))
api_known = set()
api_anchor = {}
api_anchor_id = None
def api_write(row):
    print("M5EMU_API_UI " + json.dumps(row))
def api_names(obj):
    names = set(dir(obj))
    lazy = getattr(obj, "_attrs", None)
    if isinstance(lazy, dict):
        names.update(lazy)
    return sorted(names)
def api_emit(path, obj):
    global api_anchor, api_anchor_id
    rows = []
    for name in api_names(obj):
        if name.startswith("_"):
            continue
        try:
            member = getattr(obj, name)
            rows.append([name, str(type(member)), bool(callable(member))])
        except Exception as error:
            rows.append([name, "read_error", repr(error)])
    row_map = {row[0]:row for row in rows}
    digest = hashlib.sha256(json.dumps(rows).encode()).digest().hex()
    if digest not in api_known:
        changed = [row for row in rows if api_anchor.get(row[0]) != row]
        removed = [name for name in api_anchor if name not in row_map]
        base = api_anchor_id
        if base is None or len(changed) + len(removed) >= len(rows):
            base = None
            changed = rows
            removed = []
        chunks = (len(changed) + 149) // 150
        api_write({"kind":"member_set", "id":digest,"base":base,"removed":removed,"chunk_count":chunks,"member_count":len(rows)})
        for index in range(chunks):
            api_write({"kind":"member_chunk","id":digest,"index":index,"members":changed[index*150:(index+1)*150]})
        api_known.add(digest)
    api_write({"kind":"surface", "path":path,"member_set":digest,"member_count":len(rows)})
    if path == "lvgl.obj":
        api_anchor = row_map
        api_anchor_id = digest
try:
    import lvgl as api_lv
    api_emit("lvgl.obj", api_lv.obj)
except Exception as error:
    api_write({"kind":"import_error","path":"lvgl.obj","error":repr(error)})
for api_module_name in ("M5", "m5ui", "lvgl", "label_plus", "image_plus"):
    try:
        api_module = __import__(api_module_name)
        api_emit(api_module_name, api_module)
        for api_name in api_names(api_module):
            if api_name.startswith("_"):
                continue
            api_obj = getattr(api_module, api_name)
            if isinstance(api_obj, type) or (api_module_name == "M5" and api_name in ("Display", "Lcd", "Widgets")):
                api_path = api_module_name + "." + api_name
                api_emit(api_path, api_obj)
                if api_path == "M5.Widgets":
                    for api_widget_name in sorted(dir(api_obj)):
                        if not api_widget_name.startswith("_"):
                            api_widget = getattr(api_obj, api_widget_name)
                            if isinstance(api_widget, type):
                                api_emit(api_path + "." + api_widget_name, api_widget)
    except Exception as error:
        print("M5EMU_API_UI " + json.dumps({"kind":"import_error", "path":api_module_name, "error":repr(error)}))
print("M5EMU_API_UI_END")
'''


def document_surface(path: Path, docs_root: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(docs_root).as_posix()
    if path.parent.name == "m5ui":
        if path.stem == "_overview":
            api_path = "m5ui"
        else:
            match = re.search(r"^## `([A-Za-z0-9_]+)`", text, re.M)
            if not match:
                raise ValueError(f"Missing documented constructor: {relative}")
            api_path = "m5ui." + match.group(1)
    elif path.parent.name == "widgets":
        api_path = {
            "_overview": "M5.Widgets", "circle": "M5.Widgets.Circle",
            "image": "M5.Widgets.Image", "label": "M5.Widgets.Label",
            "label+": "label_plus.LabelPlus", "image+": "image_plus.ImagePlus",
        }[path.stem]
    else:
        api_path = "M5.Display"
    constructor = api_path.rsplit(".", 1)[-1]
    members: dict[str, dict] = {}
    in_api = path.parent.name == "widgets"
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## **API**") or line.startswith("## Functions"):
            in_api = True
        if not in_api:
            continue
        match = re.match(r"^(#{2,3}) `([^`]+)`", line)
        if not match:
            continue
        signature = match.group(2).removeprefix("class ")
        raw_name = signature.split("(", 1)[0].strip()
        name = raw_name.rsplit(".", 1)[-1]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            continue
        kind = "constructor" if name == constructor and api_path not in ("m5ui", "M5.Widgets", "M5.Display") else "constant" if name.isupper() else "method"
        if raw_name == "M5.Display":
            continue
        entry = members.setdefault(name, {"name": name, "kind": kind, "documented_signatures": [], "doc_lines": []})
        if signature not in entry["documented_signatures"]:
            entry["documented_signatures"].append(signature)
        entry["doc_lines"].append(line_number)
    if path.name == "_overview.md" and api_path == "m5ui":
        # The overview uses plain headings with a fully qualified function.
        for match in re.finditer(r"^### `(m5ui\.(\w+)\([^`]*\))`", text, re.M):
            name = match.group(2)
            members[name] = {"name": name, "kind": "function", "documented_signatures": [match.group(1)], "doc_lines": [text[:match.start()].count("\n") + 1]}
    return {
        "api_path": api_path, "documentation": relative,
        "documentation_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "recipe": recipe_for(api_path), "members": list(members.values()),
    }


def recipe_for(path: str) -> str:
    if path.startswith(("label_plus.", "image_plus.")):
        return "remote-resource"
    if path == "M5.Display":
        return "display-canvas"
    if path.startswith("M5.Widgets"):
        return "widgets"
    if path == "m5ui":
        return "m5ui-lifecycle"
    if path.endswith(("M5Page", "M5Menu", "M5TabView", "M5Win", "M5Msgbox")):
        return "m5ui-container"
    if path.endswith(("M5Canvas", "M5Chart", "M5Image", "M5Line", "M5Scale")):
        return "m5ui-graphics"
    return "m5ui-control"


RECIPES = {
    "m5ui-lifecycle": {
        "isolation": "Dedicated program and session lifecycle; never mix live M5UI objects with Widgets/Display rendering.",
        "checks": ["init and deinit execute", "fresh page renders after init", "documented repeat lifecycle and same-VM replacement retain control", "exceptions and Ctrl-C produce explicit cleanup evidence"],
    },
    "m5ui-container": {
        "checks": ["construct each class with official parameters", "all child/parent/tab/menu/page accessors and mutation methods execute", "load, navigate and return through injected touch", "all public inherited methods map to a class-appropriate recipe", "inspect before/after framebuffer and event log; retain wrong-parent negative control"],
    },
    "m5ui-control": {
        "checks": ["construct each class", "set/get values, ranges, text, options and public inherited styles", "inject touch/drag/longpress for each advertised event", "state/flag normal, pressed, checked, focused, hidden and disabled behavior", "observe rendered result and actual callback data; programmatic set is separate from physical input"],
    },
    "m5ui-graphics": {
        "checks": ["construct each class", "execute every documented draw, source, series, point, scale and batch method", "verify returned pixel/value/series data where supported", "image decode uses packaged known-hash resources", "inspect fresh framebuffer after each functional group; isolated malformed resource negative control"],
    },
    "display-canvas": {
        "isolation": "Separate program from LVGL and Widgets; reuse offscreen canvas for multi-draw updates.",
        "checks": ["rotation/size/color-depth/cursor round trips", "each documented shape/text/font/QR method", "PNG/JPG/BMP/raw buffer decode using known resources", "newCanvas creates actual object and inventories all public inherited canvas methods", "canvas push gives visible expected primitives, text and colors", "actual pixels and bounds verified from fresh frames"],
    },
    "widgets": {
        "isolation": "Separate program from LVGL; widget parent may be a documented canvas.",
        "checks": ["construct every frozen widget including runtime-only classes absent in skill docs", "text/font/color/cursor/size/visibility state and all public inherited methods", "packaged image replace and relocation", "fresh frames verify values, placement and missing-resource failure"],
    },
    "remote-resource": {
        "checks": ["controlled local HTTP fixture for success, timeout, non-2xx and malformed content", "update/period/enable/validity/value/JSON-key and inherited methods", "timer/IRQ cleanup on deinit and repeated Run", "same session network/data-plane and framebuffer evidence"],
    },
    "lvgl-native": {
        "checks": ["inventory all real module exports and class member sets", "distinguish constants/types/functions/read errors", "pin binding source to firmware where available", "assign every callable a constructor/method/event/render/cleanup recipe before claiming full coverage", "binding declarations and dir/help are never functional PASS"],
    },
}


def runtime_inventory(paths: list[Path]) -> dict:
    records = []
    for path in paths:
        transcript = path.read_text(encoding="utf-8")
        if "M5EMU_API_UI " in transcript and "M5EMU_API_UI_END" not in transcript:
            raise ValueError("Incomplete UI reflection transcript (missing END): " + str(path))
        for line in transcript.splitlines():
            marker = "M5EMU_API_UI "
            if marker in line:
                try:
                    records.append(json.loads(line.split(marker, 1)[1].rstrip("\r")))
                except json.JSONDecodeError:
                    continue
    member_sets = {}
    surfaces = []
    declarations = {record["id"]: record for record in records if record.get("kind") == "member_set"}
    chunks = {}
    for record in records:
        if record.get("kind") == "member_chunk":
            chunks.setdefault(record["id"], {})[record["index"]] = record["members"]
    def expand(key):
        if key in member_sets:
            return member_sets[key]
        declaration = declarations[key]
        pieces = chunks.get(key, {})
        if set(pieces) != set(range(declaration["chunk_count"])):
            raise ValueError("Incomplete runtime member chunks for " + key)
        rows = {row[0]: row for row in expand(declaration["base"])} if declaration["base"] else {}
        for name in declaration["removed"]:
            rows.pop(name, None)
        for index in sorted(pieces):
            rows.update({row[0]: row for row in pieces[index]})
        member_sets[key] = [rows[name] for name in sorted(rows)]
        if len(member_sets[key]) != declaration["member_count"]:
            raise ValueError("Runtime member count mismatch for " + key)
        return member_sets[key]
    for record in records:
        if record.get("kind") == "surface":
            expand(record["member_set"])
            surfaces.append({"api_path": record["path"], "member_set": record["member_set"], "member_count": record["member_count"], "recipe": "lvgl-native" if record["path"].startswith("lvgl") else recipe_for(record["path"])})
    for record in records:
        if record.get("kind") != "members":
            continue
        members = record["members"]
        content = json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
        key = hashlib.sha256(content).hexdigest()
        member_sets[key] = members
        surfaces.append({"api_path": record["path"], "member_set": key, "member_count": len(members), "recipe": "lvgl-native" if record["path"].startswith("lvgl") else recipe_for(record["path"])})
    # Persist the normalized denominator as deltas. Full repeated inherited
    # arrays are raw transcript material and unnecessarily inflate source Git.
    compact_sets = {}
    for key, rows in member_sets.items():
        declaration = declarations.get(key)
        if declaration:
            compact_sets[key] = {"base": declaration["base"], "removed": declaration["removed"], "members": [row for index in sorted(chunks.get(key, {})) for row in chunks[key][index]], "member_count": len(rows)}
        else:
            compact_sets[key] = {"base": None, "removed": [], "members": rows, "member_count": len(rows)}
    return {"reflection_is_functional_evidence": False, "records": [r for r in records if r.get("kind") not in ("members", "member_set", "member_chunk", "surface")], "surfaces": surfaces, "member_sets": compact_sets, "effective_member_references": sum(s["member_count"] for s in surfaces)}


def source_inventory(root: Path | None) -> dict:
    """Read candidate frozen Python and C declaration tables without importing."""
    if root is None:
        return {"status": "not_supplied", "surfaces": []}
    surfaces = []
    python_paths = list((root / "m5stack/libs/m5ui").glob("*.py"))
    python_paths += [root / "m5stack/libs/label_plus.py", root / "m5stack/libs/image_plus.py"]
    for path in sorted(python_paths):
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            prefix = "m5ui" if path.parent.name == "m5ui" else path.stem
            methods = []
            constants = []
            lazy_base = False
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    if child.name == "__getattr__" and "M5Base" in ast.unparse(child):
                        lazy_base = True
                    if child.name.startswith("_") and child.name != "__init__":
                        continue
                    raises = sorted({ast.unparse(x.exc) for x in ast.walk(child) if isinstance(x, ast.Raise) and x.exc is not None})
                    methods.append({"name": child.name, "signature": ast.unparse(child.args), "line": child.lineno, "raises": raises, "pass_only": all(isinstance(x, (ast.Pass, ast.Expr)) for x in child.body)})
                if isinstance(child, ast.Assign):
                    constants.extend(ast.unparse(x) for x in child.targets if isinstance(x, ast.Name) and not x.id.startswith("_"))
            surfaces.append({"api_path": prefix + "." + node.name, "source": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(content.encode()).hexdigest(), "bases": [ast.unparse(b) for b in node.bases], "lazy_M5Base_instance_methods": lazy_base, "methods": methods, "constants": constants})
    native_dir = root / "m5stack/cmodules/m5unified"
    for filename in ("m5unified_gfx.c", "m5unified_widgets.c"):
        path = native_dir / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        macros = {}
        for match in re.finditer(r"^#define (TABLE_PARTS_\w+)[^\n]*\n((?:[^\n]*\\\n)*[^\n]*)", content, re.M):
            macros[match.group(1)] = match.group(2)
        table_paths = {
            "gfxdevice_member_table": "M5.Display", "gfxcanvas_member_table": "M5.Display.Canvas",
            "gfxuserdevice_member_table": "M5.UserDisplay", "fonts_member_table": "M5.Widgets.FONTS",
            "color_pre_define_members_table": "M5.Widgets.COLOR", "epd_mode_define_members_table": "M5.Display.EPD_MODE",
            "widgets_module_member_table": "M5.Widgets",
        }
        for match in re.finditer(r"static const mp_rom_map_elem_t (\w+)\[\] = \{(.*?)\n\};", content, re.S):
            table, body = match.groups()
            api_path = table_paths.get(table)
            if api_path is None and table.startswith("m5widgets_"):
                name = table[len("m5widgets_"):].removesuffix("_member_table")
                api_path = "M5.Widgets." + {"qrcode": "QRCode"}.get(name, name.title())
            if api_path is None:
                continue
            for macro, value in macros.items():
                body = body.replace(macro, value)
            methods = sorted(set(re.findall(r"MAKE_TABLE\(\w+,\s*(\w+)\)", body)))
            symbols = sorted(set(re.findall(r"MP_QSTR_(\w+)", body)))
            surfaces.append({"api_path": api_path, "source": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(content.encode()).hexdigest(), "line": content[:match.start()].count("\n") + 1, "table": table, "methods": [n for n in methods if not n.startswith("_")], "symbols": [n for n in symbols if not n.startswith("_")], "conditional_declarations_require_runtime_confirmation": True})
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"status": "candidate_source_not_bound_to_reference_firmware", "commit": commit, "surfaces": surfaces, "source_is_functional_evidence": False, "binding_rule": "Actual guest exports and functional execution must establish correspondence; a build tree is not a firmware identity proof."}


def functional_recipe_links(surfaces: list[dict]) -> list[dict]:
    helper = Path(__file__).with_name("probe_ui.py")
    if not helper.exists():
        return []
    specification = importlib.util.spec_from_file_location("api_sweep_probe_ui", helper)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    links = []
    for surface in surfaces:
        path = surface["api_path"]
        target = path.rsplit(".", 1)[-1]
        assigned = []
        pending = []
        for member in surface["members"]:
            name = member["name"]
            if member["kind"] == "constant":
                continue
            if path == "m5ui":
                supported = name in ("init", "deinit")
            elif path == "M5.Widgets":
                supported = name in ("setBrightness", "fillScreen", "setRotation")
            elif path.startswith("m5ui.") and target in module.M5UI_CONSTRUCTORS:
                supported = member["kind"] == "constructor" or name in module.method_recipes(target)
            elif path == "M5.Display":
                supported = name in module.DISPLAY_RECIPES
            elif path.startswith("M5.Widgets.") and target in module.WIDGET_CONSTRUCTORS:
                supported = member["kind"] == "constructor" or name in module.WIDGET_RECIPES[target]
            else:
                supported = False
            (assigned if supported else pending).append(name)
        links.append({"api_path": path, "helper": "probe_ui.py", "recipe_assigned": assigned, "requires_recipe": pending, "functional_result": "NOT_RUN", "assignment_is_functional_evidence": False})
    return links


def runtime_doc_mismatches(documented, runtime, candidate_source):
    sources = {surface["api_path"]: surface for surface in candidate_source["surfaces"]}
    sets = runtime["member_sets"]
    def expand(key):
        value = sets[key]
        rows = {row[0]:row for row in expand(value["base"])} if value["base"] else {}
        for name in value["removed"]:
            rows.pop(name, None)
        rows.update({row[0]:row for row in value["members"]})
        return list(rows.values())
    actual = {surface["api_path"]: {row[0] for row in expand(surface["member_set"])} for surface in runtime["surfaces"]}
    base_methods = {method["name"] for method in sources.get("m5ui.M5Base", {}).get("methods", [])}
    differences = []
    for surface in documented:
        path = surface["api_path"]
        if path not in actual:
            continue
        dynamic = base_methods if sources.get(path, {}).get("lazy_M5Base_instance_methods") else set()
        missing = [member["name"] for member in surface["members"] if member["kind"] not in ("constructor", "constant") and member["name"] not in actual[path] and member["name"] not in dynamic]
        if missing:
            differences.append({"api_path": path, "documented_but_not_in_runtime_or_known_lazy_base": missing, "classification": "documentation_or_firmware_api_gap_requires_actual_call_negative", "emulator_result": "UNCLASSIFIED"})
    return differences


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--runtime-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--uiflow-root", type=Path, help="Candidate official UIFlow repository; source declarations do not prove frozen firmware identity")
    parser.add_argument("--runtime-session", type=Path, help="Captured Device Service session metadata; only public identity fields are retained")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("inventory_ui.source.json"))
    parser.add_argument("--guest-probe", type=Path, help="Write a pure reflection MicroPython probe; does not execute it")
    args = parser.parse_args()
    if args.guest_probe:
        args.guest_probe.parent.mkdir(parents=True, exist_ok=True)
        args.guest_probe.write_text(GUEST_PROBE, encoding="utf-8")
        if args.docs_root is None:
            return
    if args.docs_root is None:
        parser.error("--docs-root is required to build the inventory")
    paths = sorted((args.docs_root / "m5ui").glob("*.md")) + sorted((args.docs_root / "widgets").glob("*.md")) + [args.docs_root / "hardware/display.md"]
    surfaces = [document_surface(path, args.docs_root) for path in paths]
    result = {
        "schema_version": 1, "status": "inventory_draft_not_functionally_tested",
        "scope": ["m5ui public constructors and documented methods", "M5.Widgets and plus widgets", "M5.Display/M5.Lcd and dynamically created Canvas", "real firmware LVGL exports, inherited and binding methods"],
        "evidence_rules": {
            "default_result": "NOT_RUN", "declaration_or_import_grants_pass": False,
            "functional_pass_requires": ["firmware SHA and runtime/profile", "actual method invocation", "behavior-specific expected result", "serial/event and relevant controller/data-plane readback", "fresh framebuffer for visible behavior"],
            "hardware_result": "NOT_RUN", "inheritance": "Runtime dir includes inherited public members; pin frozen/binding source to distinguish origin. Missing runtime-only exports remain explicit inventory gaps.",
        },
        "source": {"kind": "bundled official UIFlow2 documentation", "upstream": "https://github.com/m5stack/uiflow-micropython", "upstream_commit": None, "date": "2026-10-27", "docs_root_is_caller_supplied": True},
        "recipes": RECIPES, "documented_surfaces": surfaces,
        "documented_counts": {"surfaces": len(surfaces), "members": sum(len(s["members"]) for s in surfaces)},
        "runtime": runtime_inventory(args.runtime_jsonl),
        "candidate_source": source_inventory(args.uiflow_root),
        "functional_recipe_links": functional_recipe_links(surfaces),
        "open_inventory_gaps": ["Dynamically created Display Canvas public method set requires object reflection after construction", "All native LVGL bindings must be mapped to executable recipes; M5UI docs alone do not enumerate them", "Frozen source API versions may differ from current official docs; discrepancies must be classified, never silently dropped"],
    }
    if not result["runtime"]["surfaces"]:
        result["open_inventory_gaps"].insert(0, "Actual firmware exports and inherited native members must be merged from a visible session")
    if args.runtime_session:
        session = json.loads(args.runtime_session.read_text(encoding="utf-8"))
        metadata = (session.get("firmware_provenance") or {}).get("metadata") or {}
        result["runtime"]["identity"] = {key: session.get(key) for key in ("session_id", "device_id", "runtime", "firmware_sha256")}
        result["runtime"]["identity"]["base_firmware_sha256"] = metadata.get("base_sha256")
        result["runtime"]["identity"]["reflection_transcript_sha256"] = [hashlib.sha256(path.read_bytes()).hexdigest() for path in args.runtime_jsonl]
    result["documentation_runtime_mismatches"] = runtime_doc_mismatches(surfaces, result["runtime"], result["candidate_source"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(), "surfaces": result["documented_counts"], "runtime_surfaces": len(result["runtime"]["surfaces"])}))


if __name__ == "__main__":
    main()
