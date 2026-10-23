#!/usr/bin/env python3
"""Download public UIFlow2 firmware into the simulator cache."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from firmware_analysis import analyze_firmware

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "devices" / "catalog.json"
DEFAULT_CACHE = ROOT / "platform" / ".cache" / "firmware"
DEFAULT_API_BASE = "https://burner.m5stack.com"
MAX_DOWNLOAD_BYTES = 96 * 1024 * 1024
CDN_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")


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


def legacy_download_from_detail(firmware_id: str, detail: dict) -> str:
    data = detail.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"firmware {firmware_id} has no public detail data")
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
    return (
        "https://m5burner-cdn.m5stack.com"
        f"/community/{developer_id}/{firmware_id}/{version_id}/bin/{next_id}.bin"
    )


def current_download_from_detail(
    firmware_id: str,
    detail: dict,
    *,
    device_slug: str | None = None,
) -> tuple[str, dict]:
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
    visibility = str(version.get("visibility") or "").upper()
    status = str(version.get("status") or "").upper()
    if visibility != "PUBLIC":
        raise RuntimeError(
            f"firmware {firmware_id} current version is not public: "
            f"visibility={visibility or '<missing>'}"
        )
    if status != "PUBLISHED":
        raise RuntimeError(
            f"firmware {firmware_id} current version is not published: "
            f"status={status or '<missing>'}"
        )
    supported_devices = data.get("supportedDevices")
    if not isinstance(supported_devices, list) or not supported_devices:
        raise RuntimeError(f"firmware {firmware_id} has no supported devices")
    if device_slug:
        expected = device_slug.lower()
        matching = [
            row
            for row in supported_devices
            if isinstance(row, dict)
            and (
                str(row.get("deviceSlug") or "").lower() == expected
                or str(row.get("deviceCode") or "").lower() == expected
            )
        ]
        if not matching:
            available = ", ".join(
                str(row.get("deviceSlug") or row.get("deviceCode") or "<unknown>")
                for row in supported_devices
                if isinstance(row, dict)
            )
            raise RuntimeError(
                f"firmware {firmware_id} does not support {device_slug!r}; "
                f"available={available}"
            )
    version_id = version.get("versionId")
    bin_file_name = version.get("binFileName")
    if isinstance(bin_file_name, str) and CDN_FILE_NAME.fullmatch(bin_file_name):
        url = (
            "https://m5burner-cdn.m5stack.com"
            f"/firmware/{bin_file_name}"
        )
        url_source = "binFileName"
    else:
        url = legacy_download_from_detail(firmware_id, detail)
        url_source = "legacy-version-id"

    developer_id = developer.get("userId")
    if not isinstance(developer_id, str) or not developer_id:
        raise RuntimeError(f"firmware {firmware_id} has no public developer id")
    metadata = {
        "firmware_id": firmware_id,
        "firmware_name": str(data.get("firmwareName") or ""),
        "source_url": data.get("sourceUrl"),
        "source_type": data.get("sourceType"),
        "developer_id": str(developer_id),
        "resolved_version_id": str(version_id),
        "resolved_version": str(version.get("versionName") or ""),
        "resolved_publish_time": version.get("publishTime"),
        "resolved_visibility": visibility,
        "resolved_status": status,
        "resolved_bin_file_name": (
            bin_file_name
            if isinstance(bin_file_name, str)
            else None
        ),
        "url_source": url_source,
        "supported_devices": [
            {
                "device_id": row.get("deviceId"),
                "device_code": row.get("deviceCode"),
                "device_slug": row.get("deviceSlug"),
                "device_name": row.get("deviceName"),
            }
            for row in supported_devices
            if isinstance(row, dict)
        ],
    }
    return url, metadata


def download_url_from_detail(firmware_id: str, detail: dict) -> tuple[str, dict]:
    return current_download_from_detail(firmware_id, detail)


def merge_current_version(detail: dict, versions_payload: dict) -> dict:
    if versions_payload.get("code") != 200 or not isinstance(
        versions_payload.get("data"), list
    ):
        raise RuntimeError(
            "version API rejected firmware metadata: "
            f"code={versions_payload.get('code')} "
            f"msg={versions_payload.get('msg')}"
        )
    current = next(
        (
            row
            for row in versions_payload["data"]
            if isinstance(row, dict) and row.get("current") is True
        ),
        None,
    )
    if current is None:
        raise RuntimeError("version API did not identify a current version")
    merged = json.loads(json.dumps(detail))
    version = merged.get("data", {}).get("currentVersion")
    if not isinstance(version, dict):
        raise RuntimeError("firmware detail has no current version to merge")
    version.update(
        {
            key: current[key]
            for key in (
                "versionId",
                "versionName",
                "publishTime",
                "visibility",
                "status",
                "binFileName",
            )
            if key in current
        }
    )
    return merged


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
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        advertised_bytes = int(content_length)
                    except ValueError as error:
                        raise RuntimeError(
                            f"invalid Content-Length: {content_length!r}"
                        ) from error
                    if advertised_bytes > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"download advertises {advertised_bytes} bytes, "
                            "above safety limit"
                        )
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"download failed with HTTP {error.code}: {url}"
            ) from error
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise RuntimeError(
                f"download exceeds {MAX_DOWNLOAD_BYTES} byte safety limit"
            )
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


def resolve_community_firmware(
    firmware_id: str,
    destination: Path,
    *,
    api_base: str,
    device_slug: str | None,
    force: bool,
    analyze: bool,
    expected_chip_id_value: int | None,
) -> dict:
    metadata_url = f"{api_base.rstrip('/')}/api/v1/firmwares/{firmware_id}"
    detail = request_json(metadata_url)
    current = detail.get("data", {}).get("currentVersion", {})
    if not isinstance(current, dict) or not {
        "visibility",
        "status",
        "binFileName",
    } <= current.keys():
        versions_url = f"{metadata_url}/versions"
        detail = merge_current_version(
            detail,
            request_json(versions_url),
        )
    url, metadata = current_download_from_detail(
        firmware_id,
        detail,
        device_slug=device_slug,
    )
    extra_metadata = {
        **metadata,
        "metadata_url": metadata_url,
        "url_source": "public-metadata",
    }
    try:
        result = download(
            url,
            destination,
            force,
            extra_metadata=extra_metadata,
        )
    except RuntimeError as error:
        if (
            metadata.get("url_source") != "binFileName"
            or "HTTP 404" not in str(error)
        ):
            raise
        fallback_url = legacy_download_from_detail(firmware_id, detail)
        result = download(
            fallback_url,
            destination,
            force,
            extra_metadata={
                **extra_metadata,
                "primary_url": url,
                "primary_url_error": "HTTP 404",
                "url_source": "legacy-fallback-after-404",
            },
        )
    if analyze:
        analysis = analyze_firmware(
            destination,
            expected_chip_id_value=expected_chip_id_value,
        )
        result["analysis"] = analysis
        destination.with_suffix(".analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
        )
    return result


def intake_status(*, analyze: bool, result: dict) -> str:
    if not analyze:
        return "PASS"
    analysis = result.get("analysis")
    return (
        "PASS"
        if isinstance(analysis, dict) and analysis.get("valid") is True
        else "PARTIAL"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("device", nargs="?", help="device id, e.g. stopwatch")
    parser.add_argument("--all", action="store_true", help="download all supported UIFlow2 firmware")
    parser.add_argument("--list", action="store_true", help="list downloadable devices")
    parser.add_argument(
        "--firmware-id",
        action="append",
        default=[],
        help="download one public M5Burner firmware ID; repeatable",
    )
    parser.add_argument(
        "--device-slug",
        help="require the firmware to support this device slug/code",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="run ESP merged-image/partition/app static analysis",
    )
    parser.add_argument(
        "--chip-id",
        help="expected ESP chip ID for --analyze, decimal or 0x-prefixed",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON results")
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

    if args.firmware_id:
        if args.all or args.device or args.list:
            parser.error("--firmware-id cannot be combined with device/--all/--list")
        try:
            expected_chip_id_value = (
                int(args.chip_id, 0) if args.chip_id is not None else None
            )
        except ValueError:
            parser.error("--chip-id must be an integer")
        results = []
        failures = 0
        for firmware_id in args.firmware_id:
            destination = args.cache / "community" / f"{firmware_id}.bin"
            print(f"==> community firmware {firmware_id}", file=sys.stderr)
            try:
                result = resolve_community_firmware(
                    firmware_id,
                    destination,
                    api_base=args.api_base,
                    device_slug=args.device_slug,
                    force=args.force,
                    analyze=args.analyze,
                    expected_chip_id_value=expected_chip_id_value,
                )
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                RuntimeError,
                ValueError,
            ) as error:
                failures += 1
                results.append(
                    {
                        "firmware_id": firmware_id,
                        "status": "FAIL",
                        "error": str(error),
                    }
                )
                print(f"    FAILED: {error}", file=sys.stderr)
                continue
            result["status"] = intake_status(
                analyze=args.analyze,
                result=result,
            )
            if result["status"] != "PASS":
                failures += 1
            results.append(result)
            print(
                f"    {result['bytes']} bytes  sha256={result['sha256']}",
                file=sys.stderr,
            )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        if failures:
            raise SystemExit(1)
        return

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
