#!/usr/bin/env python3
"""Download public UIFlow2 firmware into the simulator cache."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "devices" / "catalog.json"
DEFAULT_CACHE = ROOT / "platform" / ".cache" / "firmware"
DEFAULT_API_BASE = "https://burner.m5stack.com"


def load_devices() -> list[dict]:
    return json.loads(CATALOG.read_text())["devices"]


def request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "m5stack-device-simulator/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("firmware metadata response is not an object")
    return payload


def download_url_from_detail(firmware_id: str, detail: dict) -> tuple[str, dict]:
    if detail.get("code") != 200 or not isinstance(detail.get("data"), dict):
        raise RuntimeError(
            f"metadata API rejected firmware {firmware_id}: "
            f"code={detail.get('code')} msg={detail.get('msg')}"
        )
    data = detail["data"]
    version = data.get("currentVersion")
    developer = data.get("developer")
    if not isinstance(version, dict) or not isinstance(developer, dict):
        raise RuntimeError(f"firmware {firmware_id} has incomplete version metadata")
    version_id = version.get("versionId")
    developer_id = developer.get("userId")
    try:
        next_id = str(int(version_id) + 1)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f"firmware {firmware_id} has invalid version id: {version_id!r}"
        ) from error
    if not isinstance(developer_id, str) or not developer_id:
        raise RuntimeError(f"firmware {firmware_id} has no public developer id")
    url = (
        "https://m5burner-cdn.m5stack.com"
        f"/community/{developer_id}/{firmware_id}/{version_id}/bin/{next_id}.bin"
    )
    metadata = {
        "resolved_version_id": str(version_id),
        "resolved_version": str(version.get("versionName") or ""),
        "resolved_publish_time": version.get("publishTime"),
    }
    return url, metadata


def resolve_current_download(
    firmware_id: str,
    fallback_url: str,
    api_base: str,
) -> tuple[str, dict]:
    metadata_url = (
        f"{api_base.rstrip('/')}/api/v1/firmwares/{firmware_id}"
    )
    detail = request_json(metadata_url)
    url, metadata = download_url_from_detail(firmware_id, detail)
    return url, {
        **metadata,
        "metadata_url": metadata_url,
        "url_source": "public-metadata",
        "fallback_url": fallback_url,
    }


def download(
    url: str,
    destination: Path,
    force: bool = False,
    extra_metadata: dict | None = None,
) -> dict:
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
    try:
        display_path = str(destination.relative_to(ROOT))
    except ValueError:
        display_path = str(destination.resolve())
    metadata = {
        **(extra_metadata or {}),
        "url": url,
        "path": display_path,
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
    parser.add_argument(
        "--api-base",
        default=os.environ.get("M5BURNER_API_BASE_URL", DEFAULT_API_BASE),
    )
    parser.add_argument(
        "--no-resolve",
        action="store_true",
        help="use the catalog URL without checking the current public version",
    )
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
            resolved_url = firmware["download_url"]
            resolution = {"url_source": "catalog"}
            if not args.no_resolve:
                try:
                    resolved_url, resolution = resolve_current_download(
                        firmware["firmware_id"],
                        firmware["download_url"],
                        args.api_base,
                    )
                except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as error:
                    resolution = {
                        "url_source": "catalog-after-resolution-error",
                        "resolution_error": str(error),
                    }
                    print(
                        f"    WARNING: current-version lookup failed; "
                        f"using catalog URL: {error}",
                        file=sys.stderr,
                    )
            metadata = download(
                resolved_url,
                target,
                args.force,
                extra_metadata=resolution,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            failures += 1
            print(f"    FAILED: {error}", file=sys.stderr)
            continue
        print(f"    {metadata['bytes']} bytes  sha256={metadata['sha256']}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
