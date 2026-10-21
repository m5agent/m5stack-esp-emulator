#!/usr/bin/env python3
"""Download public UIFlow2 firmware into the simulator cache."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "devices" / "catalog.json"
DEFAULT_CACHE = ROOT / "platform" / ".cache" / "firmware"


def load_devices() -> list[dict]:
    return json.loads(CATALOG.read_text())["devices"]


def download(url: str, destination: Path, force: bool = False) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        data = destination.read_bytes()
        source = "cache"
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "m5stack-device-simulator/1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
        destination.write_bytes(data)
        source = "download"
    digest = hashlib.sha256(data).hexdigest()
    metadata = {
        "url": url,
        "path": str(destination.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": digest,
        "source": source,
    }
    destination.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("device", nargs="?", help="device id, e.g. stopwatch")
    parser.add_argument("--all", action="store_true", help="download all supported UIFlow2 firmware")
    parser.add_argument("--list", action="store_true", help="list downloadable devices")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    devices = load_devices()
    downloadable = [item for item in devices if item.get("uiflow2", {}).get("firmware")]
    if args.list:
        for item in downloadable:
            fw = item["uiflow2"]["firmware"]
            print(f"{item['id']:18} {item['group_label']:12} {fw['version']:8} {fw['firmware_id']}")
        return
    if args.all:
        selected = downloadable
    elif args.device:
        selected = [item for item in downloadable if item["id"] == args.device]
        if not selected:
            raise SystemExit(f"no UIFlow2 firmware metadata for device: {args.device}")
    else:
        parser.error("provide a device id, --all, or --list")

    failures = 0
    for item in selected:
        firmware = item["uiflow2"]["firmware"]
        target = args.cache / item["id"] / "uiflow2.bin"
        print(f"==> {item['id']} {firmware['version']}")
        try:
            metadata = download(firmware["download_url"], target, args.force)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            failures += 1
            print(f"    FAILED: {error}", file=sys.stderr)
            continue
        print(f"    {metadata['bytes']} bytes  sha256={metadata['sha256']}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
