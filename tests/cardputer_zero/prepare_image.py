#!/usr/bin/env python3
"""Download, verify and expand the official CardputerZero ARM64 image."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_URL = (
    "https://cardputer-zero-repo.oss-cn-shenzhen.aliyuncs.com/os-list.json"
)
TARGET_DEVICE = "m5-cardputerzero"
IMAGE_SIZE = 8 * 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(16 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"missing required tool: {name}")
    return path


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url) as response, temporary.open("wb") as out:
        shutil.copyfileobj(response, out, length=16 << 20)
    temporary.replace(destination)


def official_image() -> dict:
    with urllib.request.urlopen(MANIFEST_URL, timeout=30) as response:
        manifest = json.load(response)
    for entry in manifest["os_list"]:
        if (
            entry.get("architecture") == "armv8"
            and TARGET_DEVICE in entry.get("devices", [])
            and entry.get("url", "").endswith(".img.xz")
        ):
            return entry
    raise SystemExit("CardputerZero arm64 image not found in official manifest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / ".work/cardputerzero"
    )
    parser.add_argument(
        "--image", type=Path,
        default=ROOT / ".work/cardputerzero/cardputerzero-work.img",
    )
    parser.add_argument("--skip-guest-install", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    image_info = official_image()
    archive = args.cache_dir / Path(image_info["url"]).name
    if args.force and archive.exists():
        archive.unlink()
    if not archive.exists():
        print(f"downloading {image_info['url']}")
        download(image_info["url"], archive)
    if archive.stat().st_size != image_info["image_download_size"]:
        raise SystemExit("compressed image size mismatch")
    archive_hash = sha256(archive)
    if archive_hash != image_info["image_download_sha256"]:
        raise SystemExit(
            f"compressed image sha256 mismatch: {archive_hash}"
        )

    if args.force and args.image.exists():
        args.image.unlink()
    if not args.image.exists():
        args.image.parent.mkdir(parents=True, exist_ok=True)
        print(f"extracting to {args.image}")
        with args.image.open("wb") as output:
            subprocess.run(
                [require_tool("xz"), "-dc", str(archive)],
                check=True,
                stdout=output,
            )
    if args.image.stat().st_size != image_info["extract_size"]:
        raise SystemExit("extracted image size mismatch")
    image_hash = sha256(args.image)
    if image_hash != image_info["extract_sha256"]:
        raise SystemExit(f"extracted image sha256 mismatch: {image_hash}")

    os.truncate(args.image, IMAGE_SIZE)
    if not args.skip_guest_install:
        subprocess.run(
            [
                shutil.which("python3") or "python3",
                str(ROOT / "tests/cardputer_zero/install_guest.py"),
                "--image",
                str(args.image),
            ],
            check=True,
        )

    print(f"prepared {args.image}")
    print(
        "next: python3 tests/cardputer_zero/build_dtb.py "
        "--base-dtb <bcm2710-rpi-cm0.dtb> "
        "--overlay-dir <boot/overlays> "
        "--out <cardputerzero-v5-test.dtb>"
    )


if __name__ == "__main__":
    main()
