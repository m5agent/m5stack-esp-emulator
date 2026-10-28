#!/usr/bin/env python3
"""Normalize generated LVGL bindings into explicit implementation owners.

The source tree is a candidate until matched to the observed firmware exports.
This module never imports LVGL, calls C functions, or grants test coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def parse_bindings(uiflow_root: Path) -> dict:
    generated = uiflow_root / "m5stack/build-M5STACK_CoreS3/lv_mp.c"
    text = generated.read_text(encoding="utf-8")
    tables = {}
    for match in re.finditer(r"static const mp_rom_map_elem_t (\w+)\[\]\s*=\s*\{(.*?)\n\};", text, re.S):
        table, body = match.groups()
        members = {}
        for item in re.finditer(r"MP_ROM_QSTR\(MP_QSTR_(\w+)\)\s*,\s*MP_ROM_PTR\(&?(\w+)\)", body):
            name, symbol = item.groups()
            if not name.startswith("_"):
                members[name] = symbol
        tables[table] = members
    types = {}
    for match in re.finditer(r"(?:static\s+)?MP_DEFINE_CONST_OBJ_TYPE\(\s*(\w+)\s*,\s*MP_QSTR_(\w+)\s*,(.*?)\n\);", text, re.S):
        symbol, name, body = match.groups()
        parent = re.search(r"\bparent\s*,\s*&?(\w+)", body)
        locals_dict = re.search(r"\blocals_dict\s*,\s*&?(\w+)", body)
        attr = re.search(r"\battr\s*,\s*(\w+)", body)
        types[symbol] = {"name": name, "parent": parent.group(1) if parent else None, "table": locals_dict.group(1) + "_table" if locals_dict else None, "attr_handler": attr.group(1) if attr else None}
    functions = {}
    for match in re.finditer(r"(?:static\s+)?MP_DEFINE_CONST_LV_FUN_OBJ_(STATIC_VAR|VAR)\((\w+)\s*,\s*(\d+)\s*,\s*(\w+)\s*,\s*(\w+)\)", text):
        macro, symbol, arity, wrapper, implementation = match.groups()
        functions[symbol] = {"implementation_owner": implementation, "binding_wrapper": wrapper, "minimum_binding_arity": int(arity),
                             "binding_kind": "static" if macro == "STATIC_VAR" else "instance"}
    prototypes = {}
    for match in re.finditer(r"/\*\s*\n\s*\* lvgl extension definition for:(.*?)\*/\s*static mp_obj_t (\w+)\(", text, re.S):
        comment, wrapper = match.groups()
        prototype = " ".join(re.sub(r"^\s*\*\s?", "", line) for line in comment.strip().splitlines()).strip()
        prototypes[wrapper] = prototype
    preprocessed = generated.with_suffix(".c.pp")
    actual_prototypes = {}
    if preprocessed.exists():
        preprocessed_text = preprocessed.read_text(encoding="utf-8")
        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_\s*]*?\b(lv_[A-Za-z0-9_]+)\s*\([^;{}]*?\))\s*(?:;|\{)", preprocessed_text):
            signature, implementation = match.groups()
            actual_prototypes[implementation] = " ".join(signature.split())
    def with_signature(function):
        implementation = function["implementation_owner"]
        return {**function, "candidate_c_signature": actual_prototypes.get(implementation) or prototypes.get(function["binding_wrapper"]), "signature_scope": "actual_preprocessed_declaration" if implementation in actual_prototypes else "shared_wrapper_abi"}
    globals_table = tables.get("lvgl_globals_table", {})
    exports = {}
    for name, symbol in globals_table.items():
        if symbol in types:
            exports[name] = {"kind": "type", "type_symbol": symbol}
        elif symbol in functions:
            exports[name] = {"kind": "function", **with_signature(functions[symbol])}
        else:
            exports[name] = {"kind": "data_or_unclassified", "symbol": symbol}
    normalized_types = {}
    for symbol, declaration in types.items():
        own_methods = {}
        for name, value in tables.get(declaration["table"], {}).items():
            if value in functions:
                own_methods[name] = with_signature(functions[value])
        dynamic_fields = []
        handler = declaration["attr_handler"]
        if handler:
            start = re.search(r"static void " + re.escape(handler) + r"\([^)]*\)\s*\{", text)
            if start:
                position = start.end()
                depth = 1
                while position < len(text) and depth:
                    if text[position] == "{":
                        depth += 1
                    elif text[position] == "}":
                        depth -= 1
                    position += 1
                body = text[start.end():position - 1]
                dynamic_fields = sorted({name for name in re.findall(r"case\s+MP_QSTR_(\w+)\s*:", body) if not name.startswith("_")})
        if own_methods or dynamic_fields or declaration["parent"]:
            normalized_types[symbol] = {**declaration, "own_methods": own_methods, "dynamic_struct_fields": dynamic_fields}
    return {
        "schema_version": 1,
        "status": "candidate_generated_binding_not_functional_evidence",
        "source": generated.relative_to(uiflow_root).as_posix(),
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "exports": exports,
        "types": normalized_types,
        "coverage_rule": "Owner identity allows implementation deduplication only. It does not grant PASS to an untested device, constructor, argument/resource shape, widget override or alias call domain.",
    }


def resolve_method(bindings: dict, surface: str, method: str) -> dict | None:
    if surface == "lvgl":
        value = bindings["exports"].get(method)
        return value if value and value["kind"] == "function" else None
    export = bindings["exports"].get(surface.removeprefix("lvgl."))
    if not export:
        return None
    symbol = export.get("type_symbol")
    seen = set()
    while symbol and symbol not in seen:
        seen.add(symbol)
        declaration = bindings["types"].get(symbol)
        if not declaration:
            break
        if method in declaration["own_methods"]:
            return {"declaring_type": declaration["name"], **declaration["own_methods"][method]}
        symbol = declaration["parent"]
    return None


def split_owners(bindings: dict) -> dict:
    exports = {entry.get("type_symbol"): name for name, entry in bindings["exports"].items() if entry["kind"] == "type"}
    object_symbol = bindings["exports"]["obj"]["type_symbol"]
    def is_object(symbol):
        seen = set()
        while symbol and symbol not in seen:
            seen.add(symbol)
            if symbol == object_symbol:
                return True
            symbol = bindings["types"].get(symbol, {}).get("parent")
        return False
    result = {}
    for role, object_types in (("core", False), ("objects", True)):
        types = {symbol: {**entry, "runtime_surface": "lvgl." + exports[symbol] if symbol in exports else None}
                 for symbol, entry in bindings["types"].items() if is_object(symbol) == object_types and entry["own_methods"]}
        result[role] = {"binding_sha256": bindings["source_sha256"], "types": types,
                        "module_functions": {name: entry for name, entry in bindings["exports"].items() if entry["kind"] == "function"} if role == "core" else {},
                        "coverage_rule": bindings["coverage_rule"]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uiflow-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path)
    args = parser.parse_args()
    result = parse_bindings(args.uiflow_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.split_dir:
        args.split_dir.mkdir(parents=True, exist_ok=True)
        for role, data in split_owners(result).items():
            (args.split_dir / ("lvgl-" + role + "-own-methods.json")).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exports": len(result["exports"]), "module_functions": sum(value["kind"] == "function" for value in result["exports"].values()), "types": len(result["types"]), "own_methods": sum(len(value["own_methods"]) for value in result["types"].values()), "dynamic_struct_fields": sum(len(value["dynamic_struct_fields"]) for value in result["types"].values())}))


if __name__ == "__main__":
    main()
