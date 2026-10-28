#!/usr/bin/env python3
"""Prepare typed native-style recipes from the real generated LVGL binding.

The recipe list is a denominator, never execution evidence. Pointer resources
are retained for separate fixtures instead of being replaced with integers.
"""
import argparse
import json
from pathlib import Path
from ui_native_bindings import parse_bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uiflow-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    bindings = parse_bindings(args.uiflow_root)
    style = next(value for value in bindings["types"].values() if value["name"] == "lv_style_t")
    recipes = []
    for name, value in style["own_methods"].items():
        if not name.startswith("set_") or name == "set_prop":
            continue
        signature = value.get("candidate_c_signature", "")
        argument = signature.rsplit(",", 1)[-1].removesuffix(")").strip()
        recipes.append({"method": name, "property": name[4:].upper(), "argument": argument,
                        "signature": signature, "implementation_owner": value["implementation_owner"]})
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "lvgl-style-recipes.json").write_text(json.dumps({
        "binding_sha256": bindings["source_sha256"], "recipes": recipes}, indent=2) + "\n")


if __name__ == "__main__":
    main()
