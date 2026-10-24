#!/usr/bin/env python3
"""Select hot public M5Burner firmware and test it through Device Service.

The tool deliberately performs functional execution through /api/v1 instead of
starting a QEMU or esp-emu process directly. Downloaded binaries and session
evidence stay in ignored cache directories. This produces virtual-device
validation evidence; it must not be labeled as a physical-hardware measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from fetch_firmware import (  # noqa: E402
    DEFAULT_API_BASE,
    resolve_community_firmware,
)
from firmware_analysis import analyze_firmware, expected_chip_id  # noqa: E402


DEFAULT_SERVICE = os.environ.get(
    "M5_DEVICE_SERVICE_URL", "http://device-service:8787"
)
DEFAULT_CACHE = ROOT / "platform" / ".cache" / "user-firmware"
DEFAULT_RESULTS = ROOT / "platform" / ".cache" / "user-firmware-matrix"

# M5Burner models do not map one-to-one to simulator device IDs. StamPLC is
# distributed under Stamp-S3 because the actual controller is the StampS3 core.
BURNER_TARGETS = {
    "atoms3r": ("AtomS3R", "atoms3r"),
    "cardputer-adv": ("Cardputer ADV", "cardputer-adv"),
    "core2": ("Core2", "core2"),
    "cores3": ("CoreS3", "cores3"),
    "nanoc6": ("NanoC6", "nanoc6"),
    "nesso-n1": ("Arduino Nesso N1", "arduino-nesso-n1"),
    "papercolor": ("PaperColor", "paper-color"),
    "papermono": ("PaperMono", "paper-mono"),
    "stackchan": ("StackChan", "stackchan"),
    "stamplc": ("Stamp-S3", "stamp-s3"),
    "sticks3": ("StickS3", "sticks3"),
    "stopwatch": ("StopWatch", "stopwatch"),
    "tab5": ("Tab5", "tab5"),
}

BASELINE_RE = re.compile(r"^\s*UIFlow(?:2(?:\.0)?)?(?:\s|$)", re.IGNORECASE)
ERROR_PATTERNS = (
    re.compile(r"assert failed:", re.IGNORECASE),
    re.compile(r"Guru Meditation", re.IGNORECASE),
    re.compile(r"uru Meditation", re.IGNORECASE),
    re.compile(r"abort\(\) was called", re.IGNORECASE),
    re.compile(r"integer divide by zero", re.IGNORECASE),
    re.compile(r"LoadProhibited|StoreProhibited", re.IGNORECASE),
    re.compile(r"panic'ed", re.IGNORECASE),
    re.compile(r"Rebooting\.\.\.", re.IGNORECASE),
    re.compile(r"invalid header: 0x", re.IGNORECASE),
    re.compile(r"Invalid chip id", re.IGNORECASE),
    re.compile(r"LittleFS is Full", re.IGNORECASE),
    re.compile(r"Task watchdog got triggered", re.IGNORECASE),
    re.compile(r"task_wdt: Task watchdog", re.IGNORECASE),
    re.compile(r"Using PSRAM must when cache is enabled", re.IGNORECASE),
    re.compile(r"xTaskPriorityDisinherit", re.IGNORECASE),
)


class MatrixError(RuntimeError):
    pass


class HttpError(MatrixError):
    def __init__(self, message: str, *, status: int, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize(value: Any) -> str:
    return " ".join(
        str(value or "").replace("_", " ").replace("-", " ").split()
    ).casefold()


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 90,
) -> tuple[bytes, Mapping[str, str]]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "m5stack-user-firmware-matrix/1",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = raw.decode("utf-8", errors="replace")[:2000]
        message = f"HTTP {error.code} for {url}"
        if isinstance(payload, Mapping):
            detail = payload.get("error", payload)
            if isinstance(detail, Mapping):
                message = str(detail.get("message") or detail.get("msg") or message)
        raise HttpError(message, status=error.code, payload=payload) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise MatrixError(f"request failed for {url}: {error}") from error


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any = None,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 90,
) -> Any:
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    raw, _ = request_bytes(
        url,
        method=method,
        body=body,
        headers=request_headers,
        timeout=timeout,
    )
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatrixError(f"invalid JSON from {url}") from error


def burner_devices(base_url: str) -> list[Mapping[str, Any]]:
    payload = request_json(f"{base_url.rstrip('/')}/api/v1/devices")
    if not isinstance(payload, Mapping) or payload.get("code") != 200:
        raise MatrixError(f"M5Burner device query failed: {payload!r}")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MatrixError("M5Burner device response has no data list")
    return [row for row in rows if isinstance(row, Mapping)]


def burner_search(
    base_url: str,
    *,
    device_id: str,
    page_size: int,
) -> list[Mapping[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "deviceId": device_id,
            "sort": "MOST_DOWNLOADED",
            "pageNum": 1,
            "pageSize": page_size,
        }
    )
    payload = request_json(
        f"{base_url.rstrip('/')}/api/v1/firmwares?{query}"
    )
    if not isinstance(payload, Mapping) or payload.get("code") != 200:
        raise MatrixError(f"M5Burner firmware query failed: {payload!r}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise MatrixError("M5Burner firmware response has no rows list")
    return [row for row in rows if isinstance(row, Mapping)]


def baseline_name(name: str) -> bool:
    return bool(BASELINE_RE.match(name))


def png_metrics(data: bytes) -> dict[str, int]:
    """Decode common non-interlaced RGB/RGBA PNGs using the stdlib."""

    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MatrixError("frame is not a PNG")
    offset = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if interlace:
                raise MatrixError("interlaced PNG is unsupported")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None or bit_depth != 8:
        raise MatrixError("unsupported PNG header")
    channels = {2: 3, 6: 4}.get(color_type)
    if channels is None:
        raise MatrixError("unsupported PNG color type")
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    if len(raw) != (stride + 1) * height:
        raise MatrixError("unexpected PNG data length")
    previous = bytearray(stride)
    nonblack = 0
    unique: set[bytes] = set()
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                pa = abs(estimate - left)
                pb = abs(estimate - up)
                pc = abs(estimate - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                row[index] = (row[index] + predictor) & 0xFF
            elif filter_type != 0:
                raise MatrixError(f"unsupported PNG filter {filter_type}")
        for pixel in range(0, stride, channels):
            rgb = bytes(row[pixel : pixel + 3])
            if any(rgb):
                nonblack += 1
                if len(unique) < 512:
                    unique.add(rgb)
        previous = row
    return {
        "width": int(width),
        "height": int(height),
        "nonblack_pixels": nonblack,
        "unique_colors": len(unique),
    }


def download_candidates(
    *,
    device_id: str,
    target_name: str,
    target_slug: str,
    base_url: str,
    cache_dir: Path,
    candidate_limit: int,
    sample_limit: int,
    device_soc: str,
) -> dict[str, Any]:
    devices = burner_devices(base_url)
    target = next(
        (row for row in devices if normalize(row.get("deviceName")) == normalize(target_name)),
        None,
    )
    if target is None:
        raise MatrixError(f"M5Burner device not found: {target_name}")
    target_id = str(target.get("deviceId") or "")
    if not target_id:
        raise MatrixError(f"M5Burner device has no ID: {target_name}")
    rows = burner_search(base_url, device_id=target_id, page_size=candidate_limit)
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    baseline_rows: list[Mapping[str, Any]] = []

    def consider(row: Mapping[str, Any], *, fill: bool = False) -> None:
        if len(selected) >= sample_limit:
            return
        firmware_id = str(row.get("firmwareId") or "")
        name = str(row.get("firmwareName") or firmware_id)
        version = row.get("currentVersion")
        version_name = (
            str(version.get("versionName") or "")
            if isinstance(version, Mapping)
            else ""
        )
        if not firmware_id:
            skipped.append({"firmware_id": firmware_id, "name": name, "reason": "missing ID"})
            return
        if not fill and baseline_name(name):
            baseline_rows.append(row)
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "baseline UIFlow2 excluded while alternatives remain",
                }
            )
            return
        if device_id == "stamplc" and "stamplc" not in normalize(name):
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "generic Stamp-S3 image is not StamPLC-specific",
                }
            )
            return
        destination = cache_dir / device_id / f"{firmware_id}.bin"
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = resolve_community_firmware(
                firmware_id,
                destination,
                api_base=base_url,
                device_slug=target_slug or None,
                force=False,
                analyze=False,
                expected_chip_id_value=None,
            )
            analysis = analyze_firmware(
                destination,
                expected_chip_id_value=expected_chip_id(device_soc),
            )
        except Exception as error:
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": f"download/static analysis failed: {error}",
                }
            )
            return
        if not analysis.get("valid"):
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "static image incompatible",
                    "errors": analysis.get("errors", []),
                    "warnings": analysis.get("warnings", []),
                }
            )
            return
        selected.append(
            {
                "device_id": device_id,
                "device_soc": device_soc,
                "burner_device_name": target_name,
                "burner_device_slug": target_slug,
                "firmware_id": firmware_id,
                "name": name,
                "version": version_name,
                "source": row.get("sourceType"),
                "developer": (
                    row.get("developer", {}).get("nickname")
                    if isinstance(row.get("developer"), Mapping)
                    else None
                ),
                "downloads": (
                    row.get("statistics", {}).get("downloadCount")
                    if isinstance(row.get("statistics"), Mapping)
                    else None
                ),
                "published": (
                    version.get("publishTime")
                    if isinstance(version, Mapping)
                    else None
                ),
                "path": str(destination),
                "bytes": result["bytes"],
                "sha256": result["sha256"],
                "url": result["url"],
                "metadata": result,
                "static_analysis": analysis,
                "rank": len(selected) + 1,
            }
        )

    for row in rows:
        consider(row)
        if len(selected) >= sample_limit:
            break
    if len(selected) < sample_limit:
        for row in baseline_rows:
            consider(row, fill=True)
            if len(selected) >= sample_limit:
                break
    return {
        "device_id": device_id,
        "target_name": target_name,
        "target_slug": target_slug,
        "target_id": target_id,
        "selected": selected,
        "skipped": skipped,
        "coverage": "complete" if len(selected) >= sample_limit else "shortfall",
    }


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 90):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path.lstrip('/')}"

    def get(self, path: str) -> Any:
        return request_json(self.url(path), timeout=self.timeout)

    def post(self, path: str, payload: Any = None) -> Any:
        return request_json(
            self.url(path),
            method="POST",
            payload={} if payload is None else payload,
            timeout=self.timeout,
        )

    def delete(self, path: str) -> Any:
        return request_json(
            self.url(path),
            method="DELETE",
            timeout=self.timeout,
        )

    def upload(self, path: Path, name: str) -> Any:
        return request_json(
            self.url("artifacts"),
            method="POST",
            body=path.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": name,
            },
            timeout=180,
        )

    def frame(self, session_id: str, destination: Path) -> tuple[bytes, Mapping[str, str]]:
        data, headers = request_bytes(
            self.url(f"sessions/{session_id}/frame.png"),
            headers={"Accept": "image/png"},
            timeout=max(self.timeout, 60),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return data, headers


def error_lines(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in ERROR_PATTERNS):
            compact = " ".join(line.replace("\x00", "").split())
            if compact and compact not in found:
                found.append(compact[:500])
            if len(found) >= 20:
                break
    return found


def inputs_for_device(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    display = device.get("display")
    if isinstance(display, Mapping) and display.get("touch"):
        width = int(display.get("width") or 320)
        height = int(display.get("height") or 240)
        return [
            {
                "kind": "touch",
                "x": max(1, width // 2),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {
                "kind": "touch",
                "x": max(1, width // 4),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {
                "kind": "touch",
                "x": max(1, (width * 3) // 4),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {"kind": "key", "key": "a", "settle_seconds": 0.8},
            {"kind": "key", "key": "ret", "settle_seconds": 0.8},
        ]
    return [
        {"kind": "key", "key": "a", "settle_seconds": 0.8},
        {"kind": "key", "key": "ret", "settle_seconds": 0.8},
    ]


def classify_result(
    *,
    has_screenshot: bool,
    nonblack: int,
    running: bool,
    crash: bool,
    serial_bytes: int,
    boot_error: str | None,
    input_observed: bool,
) -> tuple[str, str, list[str]]:
    """Classify runtime evidence without conflating firmware and model gaps."""

    if boot_error:
        return (
            "PARTIAL",
            "device_service_startup_failed",
            [f"runtime_startup: {boot_error}"],
        )
    if has_screenshot:
        if nonblack < 16:
            if crash or not running:
                return (
                    "FAIL",
                    "fatal_before_application_frame",
                    [
                        "application_frame: no non-blank frame",
                        "runtime:" + (" fatal serial signature" if crash else " not running"),
                    ],
                )
            return (
                "PARTIAL",
                "application_frame_not_ready",
                ["application_frame: no non-blank frame"],
            )
        if crash:
            return (
                "PARTIAL",
                "fatal_after_application_frame",
                ["runtime: fatal serial signature after frame capture"],
            )
        if not running:
            return (
                "PARTIAL",
                "session_not_running_after_frame",
                ["runtime: session did not remain running"],
            )
        if not input_observed:
            return (
                "PARTIAL",
                "no_observable_input_response",
                ["input: no frame change or serial response after probes"],
            )
        return "PASS", "application_frame_and_runtime_ok", []
    if serial_bytes <= 0:
        return "FAIL", "serial_not_ready", ["serial: no boot or application output"]
    if crash or not running:
        return (
            "FAIL",
            "fatal_without_display",
            [
                "runtime:" + (" fatal serial signature" if crash else " not running"),
                "display: device profile has no display",
            ],
        )
    return (
        "PARTIAL",
        "serial_only_device",
        ["display: device profile has no display; frame validation is not applicable"],
    )


def wait_until_running(
    client: ServiceClient,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = client.get(f"sessions/{session_id}")
        if last.get("state") == "running":
            return last
        if last.get("state") in {"failed", "stopped"}:
            return last
        time.sleep(0.3)
    return last


def execute_sample(
    sample: Mapping[str, Any],
    *,
    client: ServiceClient,
    device: Mapping[str, Any],
    out_dir: Path,
    observe_seconds: float,
    settle_seconds: float,
) -> dict[str, Any]:
    firmware_path = Path(str(sample["path"]))
    has_screenshot = bool(device.get("features", {}).get("screenshot"))
    result: dict[str, Any] = {
        **{
            key: value
            for key, value in sample.items()
            if key not in {"metadata", "static_analysis"}
        },
        "started_at": utc_now(),
        "scope": "simulation-only-not-hardware-validation",
        "session_id": None,
    }
    session_id: str | None = None
    try:
        artifact = client.upload(
            firmware_path,
            f"{sample['device_id']}-{sample['firmware_id']}.bin",
        )
        result["artifact"] = artifact
        firmware = client.post(
            "firmware",
            {
                "device_id": sample["device_id"],
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        result["firmware"] = firmware
        analysis = client.post(
            "firmware/analyze",
            {"firmware_id": firmware["firmware_id"]},
        )
        result["service_static_analysis"] = analysis
        session = client.post(
            "sessions",
            {
                "device_id": sample["device_id"],
                "firmware_id": firmware["firmware_id"],
                "ttl_seconds": max(600, int(observe_seconds) + 300),
                "ready_timeout_seconds": observe_seconds,
            },
        )
        session_id = str(session["session_id"])
        result["session_id"] = session_id
        snapshot = wait_until_running(
            client,
            session_id,
            timeout=(
                420
                if sample["device_id"] == "tab5"
                else max(120, observe_seconds + 60)
            ),
        )
        result["boot_snapshot"] = snapshot
        if snapshot.get("state") == "running" and has_screenshot:
            try:
                ready = client.post(
                    f"sessions/{session_id}/wait",
                    {
                        "timeout_seconds": observe_seconds,
                        "ready": {
                            "frame_nonblank": True,
                            "frame_min_bytes": 1024,
                            "frame_min_nonblack_pixels": 16,
                            "require_all": True,
                        },
                    },
                )
                result["frame_ready"] = True
                result["ready_snapshot"] = ready
                result["frame_metrics"] = ready.get("frame")
            except HttpError as error:
                result["frame_ready"] = False
                result["frame_wait_error"] = {
                    "status": error.status,
                    "message": str(error),
                }
        else:
            time.sleep(min(observe_seconds, 12))

        snapshot = client.get(f"sessions/{session_id}")
        result["pre_input_snapshot"] = snapshot
        before_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-before.png"
        before_sha = None
        if has_screenshot:
            try:
                before, before_headers = client.frame(session_id, before_path)
                before_sha = hashlib.sha256(before).hexdigest()
                result["before_frame"] = {
                    "path": str(before_path),
                    "sha256": before_sha,
                    "width": before_headers.get("X-Frame-Width"),
                    "height": before_headers.get("X-Frame-Height"),
                    **png_metrics(before),
                }
            except (HttpError, MatrixError) as error:
                result["before_frame_error"] = str(error)

        pre_input_serial_sha = None
        try:
            pre_input_logs = client.get(
                f"sessions/{session_id}/logs?offset=0&limit=262144"
            )
            pre_input_serial = str(pre_input_logs.get("data") or "")
            pre_input_serial_sha = hashlib.sha256(
                pre_input_serial.encode("utf-8", errors="replace")
            ).hexdigest()
        except HttpError:
            pre_input_serial = ""

        input_attempts: list[dict[str, Any]] = []
        if snapshot.get("state") == "running":
            for index, payload in enumerate(inputs_for_device(device)):
                input_result: dict[str, Any] = {"request": payload}
                try:
                    response = client.post(
                        f"sessions/{session_id}/input",
                        payload,
                    )
                    input_result["response"] = response
                    time.sleep(settle_seconds)
                    if has_screenshot:
                        probe_path = out_dir / (
                            f"{sample['device_id']}-{sample['firmware_id']}"
                            f"-input-{index}.png"
                        )
                        probe, probe_headers = client.frame(
                            session_id, probe_path
                        )
                        probe_sha = hashlib.sha256(probe).hexdigest()
                        input_result["frame"] = {
                            "path": str(probe_path),
                            "sha256": probe_sha,
                            "width": probe_headers.get("X-Frame-Width"),
                            "height": probe_headers.get("X-Frame-Height"),
                            **png_metrics(probe),
                        }
                        input_result["frame_changed_from_before"] = bool(
                            before_sha and before_sha != probe_sha
                        )
                except HttpError as error:
                    input_result["error"] = {
                        "status": error.status,
                        "message": str(error),
                    }
                input_attempts.append(input_result)
        result["inputs"] = input_attempts

        after_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-after.png"
        if has_screenshot:
            try:
                after, after_headers = client.frame(session_id, after_path)
                after_metrics = png_metrics(after)
                after_sha = hashlib.sha256(after).hexdigest()
                result["after_frame"] = {
                    "path": str(after_path),
                    "sha256": after_sha,
                    "width": after_headers.get("X-Frame-Width"),
                    "height": after_headers.get("X-Frame-Height"),
                    **after_metrics,
                }
                result["input_changed_frame"] = bool(
                    before_sha and before_sha != after_sha
                )
            except (HttpError, MatrixError) as error:
                result["after_frame_error"] = str(error)

        logs = client.get(f"sessions/{session_id}/logs?offset=0&limit=262144")
        serial = str(logs.get("data") or "")
        stderr = str(logs.get("stderr") or logs.get("qemu_stderr") or "")
        result["serial_bytes"] = len(serial.encode("utf-8", errors="replace"))
        result["serial_sha256"] = hashlib.sha256(serial.encode("utf-8")).hexdigest()
        result["errors"] = error_lines(serial + "\n" + stderr)
        log_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-serial.log"
        log_path.write_text(serial, encoding="utf-8", errors="replace")
        result["serial_log"] = str(log_path)

        final_snapshot = client.get(f"sessions/{session_id}")
        result["final_snapshot"] = final_snapshot
        frame_info = result.get("after_frame") or result.get("before_frame")
        nonblack = int((frame_info or {}).get("nonblack_pixels") or 0)
        running = final_snapshot.get("state") == "running"
        crash = bool(result["errors"])
        frame_changed = any(
            bool(item.get("frame_changed_from_before"))
            for item in input_attempts
        )
        serial_changed = bool(
            pre_input_serial_sha
            and result["serial_sha256"] != pre_input_serial_sha
        )
        input_observed = frame_changed or serial_changed
        result["observable_input_response"] = {
            "frame_changed": frame_changed,
            "serial_changed": serial_changed,
            "observed": input_observed,
        }
        boot_error = (
            str(snapshot["error"])
            if snapshot.get("state") == "failed" and snapshot.get("error")
            else None
        )
        status, status_reason, unmet_requirements = classify_result(
            has_screenshot=has_screenshot,
            nonblack=nonblack,
            running=running,
            crash=crash,
            serial_bytes=int(result["serial_bytes"]),
            boot_error=boot_error,
            input_observed=input_observed,
        )
        result["status"] = status
        result["status_reason"] = status_reason
        result["unmet_requirements"] = unmet_requirements
        result["application_ready"] = nonblack >= 16 or (
            not has_screenshot and result["serial_bytes"] > 0 and running
        )
        result["error"] = None
    except Exception as error:
        result["status"] = "FAIL"
        result["error"] = str(error)
        result["finished_at"] = utc_now()
    finally:
        if session_id:
            try:
                result["stop"] = client.delete(
                    f"sessions/{session_id}?purge=0",
                )
            except Exception as error:
                result["stop_error"] = str(error)
        result["finished_at"] = utc_now()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--service-url",
        default=os.environ.get("M5_DEVICE_SERVICE_URL", DEFAULT_SERVICE),
    )
    parser.add_argument(
        "--burner-url",
        default=os.environ.get("M5BURNER_API_BASE_URL", DEFAULT_API_BASE),
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--devices", default="")
    parser.add_argument("--per-device", type=int, default=3)
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--observe-seconds", type=float, default=35)
    parser.add_argument("--settle-seconds", type=float, default=1.2)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected_devices = [
        item.strip()
        for item in args.devices.split(",")
        if item.strip()
    ]
    if selected_devices:
        unknown = sorted(set(selected_devices) - set(BURNER_TARGETS))
        if unknown:
            raise SystemExit(f"unsupported devices: {', '.join(unknown)}")
    else:
        selected_devices = list(BURNER_TARGETS)

    client = ServiceClient(args.service_url)
    devices_payload = client.get("devices")
    devices = {
        str(row["device_id"]): row
        for row in devices_payload.get("devices", [])
        if isinstance(row, Mapping) and row.get("device_id")
    }
    missing = sorted(set(selected_devices) - set(devices))
    if missing:
        raise SystemExit(f"Device Service does not expose: {', '.join(missing)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.out_dir / "plan.json"
    results_path = args.out_dir / "results.json"
    previous_results: dict[str, Any] = {}
    if args.resume and results_path.is_file():
        payload = json.loads(results_path.read_text())
        previous_results = {
            str(row.get("sample_key")): row
            for row in payload.get("samples", [])
            if isinstance(row, Mapping) and row.get("sample_key")
        }

    selections: list[dict[str, Any]] = []
    if args.resume and plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        existing = {
            str(row.get("device_id")): row
            for row in plan.get("devices", [])
            if isinstance(row, Mapping) and row.get("device_id")
        }
        for device_id in selected_devices:
            if device_id not in existing:
                raise SystemExit(
                    f"resume plan is missing {device_id}; remove --resume or rerun"
                )
            selections.append(existing[device_id])
    else:
        for device_id in selected_devices:
            target_name, target_slug = BURNER_TARGETS[device_id]
            device = devices[device_id]
            print(
                f"PLAN {device_id}: {target_name} / {target_slug}",
                file=sys.stderr,
                flush=True,
            )
            selection = download_candidates(
                device_id=device_id,
                target_name=target_name,
                target_slug=target_slug,
                base_url=args.burner_url,
                cache_dir=args.cache_dir,
                candidate_limit=args.candidate_limit,
                sample_limit=args.per_device,
                device_soc=str(device.get("soc") or ""),
            )
            selections.append(selection)
            print(
                f"  selected {len(selection['selected'])}/{args.per_device}; "
                f"coverage={selection['coverage']}",
                file=sys.stderr,
                flush=True,
            )
            for sample in selection["selected"]:
                print(
                    f"  {sample['rank']}. {sample['name']} "
                    f"({sample['firmware_id']}, {sample['source']}, "
                    f"{sample['downloads']} downloads)",
                    file=sys.stderr,
                    flush=True,
                )
        plan = {
            "schema_version": 1,
            "retrieved_at": utc_now(),
            "burner_url": args.burner_url,
            "device_service_url": args.service_url,
            "selection_policy": (
                "M5Burner MOST_DOWNLOADED; exclude baseline UIFlow2 while "
                "sufficient chip/format-compatible alternatives remain"
            ),
            "devices": selections,
        }
        atomic_write_json(plan_path, plan)
        print(f"PLAN {plan_path}", file=sys.stderr, flush=True)
    if args.plan_only:
        return

    samples_by_rank: list[list[dict[str, Any]]] = []
    for selection in selections:
        for index, sample in enumerate(selection["selected"]):
            while len(samples_by_rank) <= index:
                samples_by_rank.append([])
            sample = dict(sample)
            sample["sample_key"] = f"{sample['device_id']}:{sample['firmware_id']}"
            samples_by_rank[index].append(sample)

    all_results = list(previous_results.values())
    for wave in samples_by_rank:
        pending = [
            sample
            for sample in wave
            if sample["sample_key"] not in previous_results
        ]
        if not pending:
            continue
        print(
            f"RUN wave rank={pending[0]['rank']} samples={len(pending)}",
            file=sys.stderr,
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            futures = {
                executor.submit(
                    execute_sample,
                    sample,
                    client=client,
                    device=devices[sample["device_id"]],
                    out_dir=args.out_dir,
                    observe_seconds=args.observe_seconds,
                    settle_seconds=args.settle_seconds,
                ): sample
                for sample in pending
            }
            for future in as_completed(futures):
                sample = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        **sample,
                        "status": "FAIL",
                        "error": str(error),
                        "finished_at": utc_now(),
                    }
                result["sample_key"] = sample["sample_key"]
                all_results = [
                    row
                    for row in all_results
                    if row.get("sample_key") != sample["sample_key"]
                ]
                all_results.append(result)
                atomic_write_json(
                    results_path,
                    {
                        "schema_version": 1,
                        "scope": "simulation-only-not-hardware-validation",
                        "updated_at": utc_now(),
                        "plan": str(plan_path),
                        "samples": sorted(
                            all_results,
                            key=lambda row: (
                                str(row.get("device_id")),
                                int(row.get("rank") or 0),
                            ),
                        ),
                    },
                )
                print(
                    f"RESULT {sample['device_id']} rank={sample['rank']} "
                    f"status={result.get('status')} "
                    f"session={result.get('session_id')} "
                    f"error={result.get('error')}",
                    file=sys.stderr,
                    flush=True,
                )

    final = json.loads(results_path.read_text())
    counts: dict[str, int] = {}
    for row in final.get("samples", []):
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    print(
        "SUMMARY "
        + " ".join(f"{key}={counts[key]}" for key in sorted(counts)),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
