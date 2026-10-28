#!/usr/bin/env python3
"""Copy pinned SDK example resources and generate independent decoder pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uiflow-source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    binding = args.uiflow_source / "m5stack/cmodules/lv_binding_micropython"
    sources = {"fs_driver.py": binding / "lib/fs_driver.py", "font-example.bin": binding / "examples/font/font-PHT-en-20.bin"}
    receipt = {}
    for name, source in sources.items():
        shutil.copyfile(source, args.out_dir / name)
        receipt[name] = {"source": source.relative_to(args.uiflow_source).as_posix(), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    from PIL import Image
    red, blue = Image.new("RGB", (8, 8), "red"), Image.new("RGB", (8, 8), "blue")
    red.save(args.out_dir / "two-frame.gif", save_all=True, append_images=[blue], duration=100, loop=0)
    for extension in ("png", "bmp", "jpg"):
        red.save(args.out_dir / ("red." + extension))
    for path in args.out_dir.iterdir():
        receipt.setdefault(path.name, {"generator": "Pillow solid RGB(255,0,0); GIF second RGB(0,0,255)", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (args.out_dir / "resource-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
