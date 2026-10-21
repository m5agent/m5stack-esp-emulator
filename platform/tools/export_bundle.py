#!/usr/bin/env python3
"""Export selected simulator devices into a portable ZIP bundle."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "devices" / "catalog.json"


def copy_tree(source: Path, destination: Path, ignore=None) -> None:
    shutil.copytree(source, destination, ignore=ignore)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--device", action="append", help="device id; repeat for multiple devices")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--name")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text())
    selected = catalog["devices"] if args.all else [item for item in catalog["devices"] if item["id"] in set(args.device or [])]
    if not selected:
        raise SystemExit("no matching devices")
    missing = set(args.device or []) - {item["id"] for item in selected}
    if missing:
        raise SystemExit(f"unknown devices: {', '.join(sorted(missing))}")

    args.out.mkdir(parents=True, exist_ok=True)
    name = args.name or ("m5stack-sim-all" if args.all else "m5stack-sim-" + "-".join(item["id"] for item in selected))
    archive = args.out / f"{name}.zip"

    with tempfile.TemporaryDirectory() as temp:
        bundle = Path(temp) / name
        bundle.mkdir()
        platform_ignore = shutil.ignore_patterns(
            ".cache", "__pycache__", "*.pyc", "node_modules", "package-lock.json"
        )
        copy_tree(ROOT / "platform", bundle / "platform", ignore=platform_ignore)
        copy_tree(ROOT / "docs", bundle / "docs")
        (bundle / "devices").mkdir()
        for item in selected:
            source = ROOT / "devices" / item["path"]
            destination = bundle / "devices" / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_tree(source, destination)
        filtered = dict(catalog)
        filtered["devices"] = selected
        (bundle / "devices" / "catalog.json").write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + "\n")
        source = json.loads((ROOT / "devices" / "catalog.source.json").read_text())
        selected_ids = {item["id"] for item in selected}
        source["devices"] = [item for item in source["devices"] if item["id"] in selected_ids]
        (bundle / "devices" / "catalog.source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n")
        for filename in ("README.md", "start.sh", "start.command", ".gitignore"):
            shutil.copy2(ROOT / filename, bundle / filename)
        (bundle / "BUNDLE.json").write_text(json.dumps({
            "name": name,
            "devices": [item["id"] for item in selected],
            "entry": "platform/web/index.html",
            "server": "python3 platform/tools/serve.py 8080",
        }, ensure_ascii=False, indent=2) + "\n")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for path in bundle.rglob("*"):
                if path.is_file():
                    output.write(path, path.relative_to(temp))
    print(archive)
    print(f"{archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
