#!/usr/bin/env python3
"""Leased, on-demand virtual M5Stack device service.

This module is intentionally a local, trusted-workstation service. It owns the
process lifecycle for QEMU/esp-emu-backed ESP32 devices and exposes an HTTP
API through serve.py. Network emulation is outside this first service scope;
Tab5 is supported with an explicit partial-peripheral warning.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
PROFILES = ROOT / "platform/qemu/profiles.json"
DEVICE_CATALOG = ROOT / "devices/catalog.source.json"
TEST_TOOLS = ROOT / "tests/uiflow2"
if str(TEST_TOOLS) not in sys.path:
    sys.path.insert(0, str(TEST_TOOLS))

from esp_flash import default_env, flash_with_esp_emu, flash_with_qemu  # noqa: E402
from run_profile_ui_test import (  # noqa: E402
    QMP,
    read_ppm,
    send_input,
    wait_qmp,
    write_rgb_png,
)
from run_tab5_ui_test import (  # noqa: E402
    capture_framebuffer,
    free_tcp_port,
    inject_touch,
    logical_to_raw_touch,
    orient_rgb565,
    rgb565_to_rgb,
    wait_for_path as wait_for_fs_path,
    wait_for_port as wait_for_tcp_port,
    write_png as write_tab5_png,
)
from firmware_analysis import analyze_firmware, expected_chip_id  # noqa: E402

DEFAULT_STATE_DIR = ROOT / "platform/.cache/service"
DEFAULT_MAX_SESSIONS = 12
DEFAULT_MAX_PER_DEVICE = 8
QMP_COMMAND_TIMEOUT = 10
EXCLUDED_DEVICES = {
    "cardputer-zero": "CardputerZero uses a separate Linux backend",
}
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_SERIAL_READ = 256 * 1024
ACTIVE_STATES = {"provisioning", "flashing", "booting", "running"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise ServiceError("invalid_request", f"{field} must be an integer", 400)


def parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON without exposing a partially-written session record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    os.replace(temporary, path)


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


@dataclass(frozen=True)
class DeviceSpec:
    id: str
    name: str
    group: str
    soc: str
    sku: str
    device_codes: list[str]
    backend: str
    machine: str
    flash_size: int
    display: dict | None
    reference_path: Path | None
    qemu: Path
    rom_dir: Path
    efuse_driver: str | None
    memory: str | None
    env: dict[str, str]
    mode: str
    expected_size: tuple[int, int] | None
    supported: bool
    flash_emulator: Path | None
    service_kind: str
    emulator: Path | None
    elf: Path | None
    rom: Path | None
    efuse: Path | None
    c6_firmware: Path | None
    peripheral_status: str
    warnings: list[str]
    state_probes: dict[str, dict[str, Any]]
    reason: str | None

    @property
    def has_display(self) -> bool:
        display = self.display or {}
        return bool(display.get("width") and display.get("height"))

    @property
    def reference_available(self) -> bool:
        return bool(self.reference_path and self.reference_path.is_file())

    @property
    def backend_ready(self) -> bool:
        if self.service_kind == "tab5":
            return all(
                path is not None and path.is_file()
                for path in (
                    self.emulator,
                    self.rom,
                    self.efuse,
                    self.c6_firmware,
                    self.reference_path,
                )
            )
        return (
            self.qemu.is_file()
            and self.rom_dir.is_dir()
            and (self.flash_emulator is None or self.flash_emulator.is_file())
        )


def load_device_specs() -> dict[str, DeviceSpec]:
    matrix = json.loads(MATRIX.read_text())
    profiles = json.loads(PROFILES.read_text())
    catalog_source = json.loads(DEVICE_CATALOG.read_text())
    profiles_by_id = {row["id"]: row for row in profiles["devices"]}
    source_by_id = {row["id"]: row for row in catalog_source["devices"]}
    specs = {}
    for row in matrix["devices"]:
        device_id = row["id"]
        backend = matrix["backends"].get(row["backend"], {})
        profile = profiles_by_id.get(device_id, {})
        source = source_by_id.get(device_id, {})
        uiflow_source = source.get("uiflow2") or {}
        excluded_reason = EXCLUDED_DEVICES.get(device_id)
        reference = ROOT / row["base"] if row.get("base") else None
        if device_id == "tab5":
            supported = True
            service_kind = "tab5"
            qemu = ROOT / "__missing_qemu__"
            rom_dir = ROOT / "__missing_rom__"
            emulator = ROOT / row["emulator"]
            elf = ROOT / row["elf"]
            rom = ROOT / row["rom"]
            efuse = ROOT / row["efuse"]
            c6_firmware = ROOT / row["c6_firmware"]
            flash_emulator = emulator
            reason = None
        else:
            supported = (
                excluded_reason is None
                and bool(backend)
                and row["backend"].startswith("qemu-esp32")
                and row["mode"] in {"ui", "console"}
            )
            service_kind = "qemu"
            qemu = (
                ROOT / backend["qemu"]
                if backend.get("qemu")
                else ROOT / "__missing_qemu__"
            )
            rom_dir = (
                ROOT / backend["rom_dir"]
                if backend.get("rom_dir")
                else ROOT / "__missing_rom__"
            )
            emulator = None
            elf = None
            rom = None
            efuse = None
            c6_firmware = None
            flash_emulator = (
                ROOT / ".work/bin/esp-emu"
                if backend.get("esp_emu_chip")
                else None
            )
            reason = excluded_reason
            if not backend and reason is None:
                reason = (
                    f"backend {row['backend']} is not registered for service execution"
                )
            if not supported and reason is None:
                reason = f"backend mode {row.get('mode')} is not enabled for this service"
        specs[device_id] = DeviceSpec(
            id=device_id,
            name=profile.get("name", device_id),
            group=profile.get("group", ""),
            soc=profile.get("soc", ""),
            sku=source.get("sku", ""),
            device_codes=(
                [source["uiflow2"]["firmware"]["firmware_id"]]
                if (uiflow_source.get("firmware") or {}).get("firmware_id")
                else []
            ),
            backend=row["backend"],
            machine=row.get("machine", ""),
            flash_size=(
                16 << 20
                if device_id == "tab5"
                else int(row.get("flash_size", "0"), 0)
            ),
            display=profile.get("display"),
            reference_path=reference,
            qemu=qemu,
            rom_dir=rom_dir,
            efuse_driver=backend.get("efuse_driver"),
            memory=row.get("memory"),
            env=row.get("env", {}),
            mode=row["mode"],
            expected_size=parse_size(row.get("expected_size")),
            supported=supported,
            flash_emulator=flash_emulator,
            service_kind=service_kind,
            emulator=emulator,
            elf=elf,
            rom=rom,
            efuse=efuse,
            c6_firmware=c6_firmware,
            peripheral_status=profile.get(
                "peripheral_status",
                "simulated" if supported else "not-applicable",
            ),
            warnings=list(profile.get("blockers", [])),
            state_probes=(
                profile.get("runtime_state", {})
                if isinstance(profile.get("runtime_state", {}), dict)
                else {}
            ),
            reason=reason,
        )
    return specs


class ArtifactStore:
    """Content-addressed binary artifacts used by firmware manifests."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _meta(self, artifact_id: str) -> Path:
        return self.root / f"{artifact_id}.json"

    def _data(self, artifact_id: str) -> Path:
        return self.root / f"{artifact_id}.bin"

    def create(
        self,
        data: bytes,
        *,
        name: str = "",
        content_type: str = "application/octet-stream",
    ) -> dict:
        if not data:
            raise ServiceError("empty_artifact", "artifact must not be empty", 400)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ServiceError(
                "artifact_too_large",
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes",
                413,
            )
        artifact_id = hashlib.sha256(data).hexdigest()
        with self._lock:
            if not self._data(artifact_id).exists():
                temp = self.root / f".{artifact_id}.{uuid.uuid4().hex}.tmp"
                temp.write_bytes(data)
                temp.replace(self._data(artifact_id))
            record = {
                "artifact_id": artifact_id,
                "sha256": artifact_id,
                "size": len(data),
                "name": name or f"artifact-{artifact_id[:12]}.bin",
                "content_type": content_type,
                "created_at": iso_now(),
            }
            self._meta(artifact_id).write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )
        return record

    def read(self, artifact_id: str) -> bytes:
        if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
            raise ServiceError("unknown_artifact", "invalid artifact id", 404)
        with self._lock:
            path = self._data(artifact_id)
            if not path.is_file():
                raise ServiceError(
                    "unknown_artifact", f"unknown artifact: {artifact_id}", 404
                )
            return path.read_bytes()

    def get(self, artifact_id: str) -> dict:
        if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
            raise ServiceError("unknown_artifact", "invalid artifact id", 404)
        with self._lock:
            meta = self._meta(artifact_id)
            if not meta.is_file():
                raise ServiceError(
                    "unknown_artifact", f"unknown artifact: {artifact_id}", 404
                )
            return json.loads(meta.read_text())

    def list(self) -> list[dict]:
        with self._lock:
            records = [
                json.loads(path.read_text())
                for path in self.root.glob("*.json")
            ]
        return sorted(
            records,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def delete(self, artifact_id: str) -> dict:
        record = self.get(artifact_id)
        with self._lock:
            self._data(artifact_id).unlink(missing_ok=True)
            self._meta(artifact_id).unlink(missing_ok=True)
        return {"artifact_id": artifact_id, "deleted": True, "record": record}


class FirmwareStore:
    """Build complete/flash-sized images from uploaded or segmented artifacts."""

    def __init__(self, root: Path, artifacts: ArtifactStore, specs: dict[str, DeviceSpec]):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = artifacts
        self.specs = specs
        self._lock = threading.RLock()

    def _meta(self, firmware_id: str) -> Path:
        return self.root / f"{firmware_id}.json"

    def _data(self, firmware_id: str) -> Path:
        return self.root / f"{firmware_id}.bin"

    def create(self, payload: dict) -> dict:
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or device_id not in self.specs:
            raise ServiceError("unknown_device", "device_id is required", 400)
        spec = self.specs[device_id]
        if not spec.supported:
            raise ServiceError(
                "unsupported_device",
                spec.reason or "device is not enabled for this service",
                409,
            )
        kind = payload.get("kind", "merged")
        image = bytearray(b"\xff" * spec.flash_size)
        intervals: list[tuple[int, int]] = []

        if kind == "merged":
            artifact_id = payload.get("artifact_id")
            data = self.artifacts.read(artifact_id)
            if len(data) > spec.flash_size:
                raise ServiceError(
                    "firmware_too_large",
                    f"firmware is {len(data)} bytes; device flash is {spec.flash_size}",
                    413,
                )
            image[: len(data)] = data
            intervals.append((0, len(data)))
            source = {"kind": "merged", "artifact_id": artifact_id}
        elif kind == "segmented":
            segments = payload.get("segments")
            if not isinstance(segments, list) or not segments:
                raise ServiceError(
                    "invalid_segments", "segments must be a non-empty list", 400
                )
            source_segments = []
            for index, segment in enumerate(segments):
                if not isinstance(segment, dict):
                    raise ServiceError(
                        "invalid_segments",
                        f"segments[{index}] must be an object",
                        400,
                    )
                offset = parse_int(segment.get("offset"), f"segments[{index}].offset")
                artifact_id = segment.get("artifact_id")
                data = self.artifacts.read(artifact_id)
                end = offset + len(data)
                if offset < 0 or end > spec.flash_size:
                    raise ServiceError(
                        "segment_out_of_range",
                        f"segment {index} range 0x{offset:x}-0x{end:x} "
                        f"exceeds flash size 0x{spec.flash_size:x}",
                        400,
                    )
                if not data:
                    raise ServiceError(
                        "empty_artifact",
                        f"segment {index} artifact is empty",
                        400,
                    )
                for start, existing_end in intervals:
                    if offset < existing_end and start < end:
                        raise ServiceError(
                            "overlapping_segments",
                            f"segment {index} overlaps another segment",
                            400,
                        )
                image[offset:end] = data
                intervals.append((offset, end))
                source_segments.append({"offset": offset, "artifact_id": artifact_id})
            source = {"kind": "segmented", "segments": source_segments}
        else:
            raise ServiceError(
                "unsupported_firmware_kind",
                "kind must be 'merged' or 'segmented'",
                400,
            )

        if not intervals:
            raise ServiceError("empty_firmware", "firmware has no data", 400)
        image_bytes = bytes(image)
        firmware_id = hashlib.sha256(image_bytes).hexdigest()
        record = {
            "firmware_id": firmware_id,
            "sha256": firmware_id,
            "device_id": device_id,
            "flash_size": spec.flash_size,
            "size": len(image_bytes),
            "kind": kind,
            "source": source,
            "header_magic": image_bytes[0],
            "created_at": iso_now(),
        }
        with self._lock:
            data_path = self._data(firmware_id)
            if not data_path.exists():
                temp = self.root / f".{firmware_id}.{uuid.uuid4().hex}.tmp"
                temp.write_bytes(image_bytes)
                temp.replace(data_path)
            self._meta(firmware_id).write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )
        return record

    def get(self, firmware_id: str) -> dict:
        if not _is_sha256(firmware_id):
            raise ServiceError("unknown_firmware", "invalid firmware id", 404)
        with self._lock:
            meta = self._meta(firmware_id)
            if not meta.is_file():
                raise ServiceError(
                    "unknown_firmware", f"unknown firmware: {firmware_id}", 404
                )
            return json.loads(meta.read_text())

    def path(self, firmware_id: str) -> Path:
        self.get(firmware_id)
        path = self._data(firmware_id)
        if not path.is_file():
            raise ServiceError("unknown_firmware", "firmware data missing", 404)
        return path

    def analyze(self, firmware_id: str) -> dict:
        record = self.get(firmware_id)
        spec = self.specs[record["device_id"]]
        result = analyze_firmware(
            self.path(firmware_id),
            expected_chip_id_value=expected_chip_id(spec.soc),
        )
        analysis = {
            "firmware_id": firmware_id,
            "device_id": record["device_id"],
            "device_chip": spec.soc,
            **result,
        }
        analysis_path = self.root / f"{firmware_id}.analysis.json"
        analysis_path.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
        )
        return analysis

    def get_analysis(self, firmware_id: str) -> dict:
        self.get(firmware_id)
        analysis_path = self.root / f"{firmware_id}.analysis.json"
        if not analysis_path.is_file():
            return self.analyze(firmware_id)
        return json.loads(analysis_path.read_text())


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def rgb_metrics(pixels: bytes) -> tuple[int, int]:
    nonblack = 0
    colors = set()
    for offset in range(0, len(pixels) - 2, 3):
        rgb = pixels[offset:offset + 3]
        if any(rgb):
            nonblack += 1
            if len(colors) < 512:
                colors.add(rgb)
    return nonblack, len(colors)


def default_flash_preparer(
    spec: DeviceSpec, image: Path, firmware_sha: str, out_dir: Path
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = default_env()
    env.update(spec.env)
    if spec.service_kind == "tab5":
        return flash_with_esp_emu(
            chip="esp32p4",
            image=image,
            flash_size=spec.flash_size,
            out_dir=out_dir,
            env=env,
            timeout=900,
            emulator=spec.emulator,
            rom=spec.rom,
            efuse=spec.efuse,
            extra_args=["--psram-size", "32M"],
            no_stub=True,
            chunk_size=1 << 20,
            chunk_ranges=[(0, 0x500000), (0x610000, 0x7F0000)],
            restart_per_chunk=True,
        )
    matrix_backend = json.loads(MATRIX.read_text())["backends"][spec.backend]
    if "esp_emu_chip" in matrix_backend:
        emulator = Path(
            os.environ.get(
                "M5_SERVICE_ESP_EMU",
                str(spec.flash_emulator or ROOT / ".work/bin/esp-emu"),
            )
        )
        return flash_with_esp_emu(
            chip=matrix_backend["esp_emu_chip"],
            image=image,
            flash_size=spec.flash_size,
            out_dir=out_dir,
            env=env,
            timeout=600,
            emulator=emulator,
        )
    return flash_with_qemu(
        chip=matrix_backend["qemu_esptool_chip"],
        machine=spec.machine,
        image=image,
        flash_size=spec.flash_size,
        out_dir=out_dir,
        env=env,
        qemu=spec.qemu,
        rom_dir=spec.rom_dir,
        timeout=900,
        memory=spec.memory,
    )


class DeviceSession:
    def __init__(
        self,
        service: "DeviceService",
        *,
        session_id: str,
        spec: DeviceSpec,
        firmware_id: str,
        firmware_path: Path,
        firmware_sha: str,
        firmware_source: str,
        source_artifacts: list[str],
        ttl_seconds: int,
        ready_marker: str | None,
        ready_timeout: float,
        ready_conditions: dict | None,
        events: list[dict] | None = None,
        created_at: str | None = None,
        completed_at: str | None = None,
        expires_at: float | None = None,
        initial_state: str = "provisioning",
        error: str | None = None,
        flash_info: dict | None = None,
        restored: bool = False,
        interrupted: bool = False,
    ):
        self.service = service
        self.id = session_id
        self.spec = spec
        self.firmware_id = firmware_id
        self.firmware_path = firmware_path
        self.firmware_sha = firmware_sha
        self.firmware_source = firmware_source
        self.source_artifacts = source_artifacts
        self.ttl_seconds = ttl_seconds
        self.ready_marker = ready_marker
        self.ready_timeout = ready_timeout
        self.ready_conditions = ready_conditions or {}
        self.created_at = created_at or iso_now()
        self.completed_at = completed_at
        self.expires_at = (
            expires_at if expires_at is not None else time.time() + ttl_seconds
        )
        self.state = initial_state
        self.error = error
        self.pid: int | None = None
        self.flash_info = flash_info
        self.virtual_flash: Path | None = None
        self.qmp_path = Path("/tmp") / f"m5-service-{session_id}.sock"
        self.dir = service.state_dir / "sessions" / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.serial0 = self.dir / "serial.log"
        self.serial1 = self.dir / "serial1.log"
        self.last_frame_path = self.dir / "last-frame.png"
        self.last_frame_meta_path = self.dir / "last-frame.json"
        self.device_state_path = self.dir / "device-state.json"
        self.session_record_path = self.dir / "session.json"
        self.events_path = self.dir / "events.json"
        self.stdout_path = self.dir / "qemu.stdout"
        self.stderr_path = self.dir / "qemu.stderr"
        self._proc: subprocess.Popen | None = None
        self._qmp: QMP | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self.events: list[dict] = [dict(event) for event in (events or [])]
        self.restored = restored
        self.interrupted = interrupted
        if events is None:
            self._record_event(
                "created", device_id=spec.id, firmware_id=firmware_id
            )
        self._persist_session()

    def _record_event(self, event: str, **details) -> None:
        self.events.append(
            {
                "at": iso_now(),
                "event": event,
                **details,
            }
        )
        self._persist_events()

    def _persist_events(self) -> None:
        atomic_write_json(self.events_path, self.events)

    def _session_record(self) -> dict:
        return {
            "schema_version": 1,
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": self.state,
            "pid": self.pid,
            "firmware_id": self.firmware_id,
            "firmware_sha256": self.firmware_sha,
            "firmware_source": self.firmware_source,
            "source_artifacts": list(self.source_artifacts),
            "flash": self.flash_info,
            "ttl_seconds": self.ttl_seconds,
            "ready_marker": self.ready_marker,
            "ready_timeout_seconds": self.ready_timeout,
            "ready_conditions": self.ready_conditions,
            "created_at": self.created_at,
            "expires_at": datetime.fromtimestamp(
                self.expires_at, timezone.utc
            ).isoformat(),
            "completed_at": self.completed_at,
            "error": self.error,
            "restored": self.restored,
            "interrupted": self.interrupted,
        }

    def _persist_session(self) -> None:
        atomic_write_json(self.session_record_path, self._session_record())

    def snapshot(self) -> dict:
        with self._lock:
            if (
                self._proc is not None
                and self._proc.poll() is not None
                and self.state in ACTIVE_STATES
            ):
                self.state = "failed"
                self.error = self.error or f"process exited with code {self._proc.returncode}"
                self.completed_at = self.completed_at or iso_now()
                self._record_event(
                    "process_exited", returncode=self._proc.returncode
                )
                self._persist_session()
            serial_size = self.serial0.stat().st_size if self.serial0.exists() else 0
            frame_meta = {}
            if self.last_frame_meta_path.is_file():
                try:
                    frame_meta = json.loads(self.last_frame_meta_path.read_text())
                except json.JSONDecodeError:
                    frame_meta = {}
            state_meta = {}
            if self.device_state_path.is_file():
                try:
                    state_meta = json.loads(self.device_state_path.read_text())
                except json.JSONDecodeError:
                    state_meta = {}
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "pid": self.pid,
                "firmware_id": self.firmware_id,
                "firmware_sha256": self.firmware_sha,
                "firmware_source": self.firmware_source,
                "artifact_sha256": (
                    self.source_artifacts[0] if self.source_artifacts else None
                ),
                "source_artifacts": list(self.source_artifacts),
                "flash": self.flash_info,
                "serial_bytes": serial_size,
                "created_at": self.created_at,
                "expires_at": datetime.fromtimestamp(
                    self.expires_at, timezone.utc
                ).isoformat(),
                "error": self.error,
                "display": self.spec.display,
                "last_frame_available": self.last_frame_path.is_file(),
                "last_frame_captured_at": frame_meta.get("captured_at"),
                "device_state_supported": bool(self.spec.state_probes),
                "last_device_state_available": self.device_state_path.is_file(),
                "last_device_state_at": state_meta.get("captured_at"),
                "completed_at": self.completed_at,
                "event_count": len(self.events),
                "restored": self.restored,
                "interrupted": self.interrupted,
            }

    def start(self) -> None:
        thread = threading.Thread(
            target=self._provision,
            name=f"m5-session-{self.id}",
            daemon=True,
        )
        thread.start()

    def _set_state(self, state: str) -> None:
        with self._lock:
            previous = self.state
            self.state = state
            self._record_event("state", **{"from": previous, "to": state})
            self._persist_session()

    def _provision(self) -> None:
        try:
            self._set_state("flashing")
            prepared = self.service.prepare_flash(
                self.spec, self.firmware_path, self.firmware_sha
            )
            self.virtual_flash = self.dir / "virtual-flash.bin"
            shutil.copyfile(prepared["path"], self.virtual_flash)
            self.flash_info = {
                **prepared["info"],
                "session_isolated_copy": True,
            }
            self._record_event("flash_prepared", **self.flash_info)
            self._persist_session()
            self._set_state("booting")
            self._launch()
            if self.ready_conditions:
                self.wait_ready(
                    {
                        "timeout_seconds": self.ready_timeout,
                        **self.ready_conditions,
                    }
                )
            elif self.ready_marker:
                self.wait_for_marker(self.ready_marker, self.ready_timeout)
            self._set_state("running")
        except Exception as error:
            with self._lock:
                self.error = str(error)
                self.state = "failed"
                self.completed_at = self.completed_at or iso_now()
                self._record_event("failed", error=str(error))
                self._persist_session()
            self._terminate_process()

    def _launch(self) -> None:
        assert self.virtual_flash is not None
        efuse = self.dir / "efuse.bin"
        efuse_data = bytearray(4096)
        # The device matrix uses the same package-version encoding as the
        # existing profile runner.
        if "efuse_pkg_version" in self.service.raw_device(self.spec.id):
            pkg = int(self.service.raw_device(self.spec.id)["efuse_pkg_version"])
            efuse_data[36:40] = (pkg << 21).to_bytes(4, "little")
        efuse.write_bytes(efuse_data)
        try:
            self.qmp_path.unlink()
        except FileNotFoundError:
            pass
        command = [
            str(self.spec.qemu),
            "-M", self.spec.machine,
            "-drive", f"file={self.virtual_flash},if=mtd,format=raw",
            "-L", str(self.spec.rom_dir),
            "-display", "none",
            "-serial", f"file:{self.serial0}",
            "-serial", f"file:{self.serial1}",
            "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
        ]
        if self.spec.efuse_driver != "none":
            command.extend(
                [
                    "-drive", f"if=none,id=efuse,file={efuse},format=raw",
                    "-global",
                    f"driver={self.spec.efuse_driver},property=drive,value=efuse",
                ]
            )
        if self.spec.memory is not None:
            command.extend(["-m", str(self.spec.memory)])
        env = os.environ.copy()
        env.update(self.spec.env)
        stdout = self.stdout_path.open("wb")
        stderr = self.stderr_path.open("wb")
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            stdout.close()
            stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        self._qmp = wait_qmp(self.qmp_path, timeout=20)
        self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)

    def _qmp_call(self, name: str, **arguments):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                raise ServiceError("session_not_running", "device process is not running", 409)
            if self._qmp is None:
                self._qmp = wait_qmp(self.qmp_path, timeout=5)
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
            try:
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
                return self._qmp.cmd(name, **arguments)
            except (OSError, RuntimeError) as error:
                try:
                    self._qmp.close()
                except OSError:
                    pass
                self._qmp = None
                timeout = isinstance(error, TimeoutError)
                raise ServiceError(
                    "qmp_timeout" if timeout else "qmp_error",
                    f"QMP command {'timed out' if timeout else 'failed'}: {error}",
                    504 if timeout else 503,
                ) from error

    def wait_for_marker(self, marker: str, timeout: float) -> dict:
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            if self.serial0.exists() and marker in self.serial0.read_text(
                errors="replace"
            ):
                self._record_event("serial_marker", marker=marker)
                return self.snapshot()
            if self._proc and self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    f"device exited before marker {marker!r}",
                    409,
                )
            time.sleep(0.1)
        raise ServiceError(
            "ready_timeout",
            f"timed out waiting for serial marker {marker!r}",
            408,
        )

    def wait_ready(self, payload: dict) -> dict:
        """Wait for application-level serial and/or framebuffer readiness."""

        timeout = float(payload.get("timeout_seconds", 30))
        conditions = payload.get("ready", payload)
        if not isinstance(conditions, dict):
            raise ServiceError("invalid_ready", "ready must be an object", 400)
        serial_markers = conditions.get("serial_markers", [])
        if isinstance(serial_markers, str):
            serial_markers = [serial_markers]
        if not isinstance(serial_markers, list):
            raise ServiceError(
                "invalid_ready", "serial_markers must be a list", 400
            )
        frame_nonblank = bool(conditions.get("frame_nonblank", False))
        frame_min_bytes = int(conditions.get("frame_min_bytes", 1024))
        frame_min_nonblack = int(
            conditions.get("frame_min_nonblack_pixels", 16)
        )
        require_all = bool(conditions.get("require_all", True))
        if frame_nonblank and not self.spec.has_display:
            raise ServiceError(
                "display_not_available",
                "frame_nonblank was requested for a serial-only device",
                400,
            )
        if not serial_markers and not frame_nonblank:
            return self.snapshot()

        deadline = time.time() + max(0.1, timeout)
        found_markers: list[str] = []
        first_serial_at: str | None = None
        first_frame_at: str | None = None
        last_frame: dict | None = None
        while time.time() < deadline:
            if serial_markers:
                serial_text = (
                    self.serial0.read_text(errors="replace")
                    if self.serial0.exists()
                    else ""
                )
                for marker in serial_markers:
                    if marker in serial_text and marker not in found_markers:
                        found_markers.append(marker)
                        first_serial_at = first_serial_at or iso_now()
                        self._record_event("serial_marker", marker=marker)
            frame_ready = False
            if frame_nonblank:
                try:
                    last_frame = self.frame_metrics()
                    frame_ready = (
                        last_frame["png_bytes"] >= frame_min_bytes
                        and last_frame["nonblack_pixels"] >= frame_min_nonblack
                    )
                    if frame_ready and first_frame_at is None:
                        first_frame_at = iso_now()
                        self._record_event(
                            "frame_nonblank",
                            nonblack_pixels=last_frame["nonblack_pixels"],
                            png_bytes=last_frame["png_bytes"],
                        )
                except ServiceError:
                    frame_ready = False
            serial_ready = (
                not serial_markers
                or (
                    len(found_markers) == len(serial_markers)
                    if require_all
                    else bool(found_markers)
                )
            )
            criteria = [
                criterion
                for criterion, matched in (
                    ("serial_marker", serial_ready),
                    ("frame_nonblank", frame_ready),
                )
                if criterion in conditions or (
                    criterion == "serial_marker" and serial_markers
                ) or (criterion == "frame_nonblank" and frame_nonblank)
                if matched
            ]
            ready = (
                serial_ready and (frame_ready or not frame_nonblank)
                if require_all
                else bool(criteria)
            )
            if ready:
                self._record_event("application_ready", criteria=criteria)
                return {
                    **self.snapshot(),
                    "ready": True,
                    "ready_reason": criteria,
                    "serial_markers": found_markers,
                    "first_serial_at": first_serial_at,
                    "first_frame_at": first_frame_at,
                    "frame": (
                        {
                            key: value
                            for key, value in last_frame.items()
                            if key != "png"
                        }
                        if last_frame
                        else None
                    ),
                }
            if self._proc is not None and self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    "device exited before application readiness",
                    409,
                )
            time.sleep(0.75)
        raise ServiceError(
            "ready_timeout",
            "application did not satisfy the requested readiness conditions",
            408,
            serial_markers=found_markers,
        )

    def serial_read(self, offset: int = 0, limit: int = 65536) -> dict:
        limit = min(max(int(limit), 1), MAX_SERIAL_READ)
        with self._lock:
            if not self.serial0.exists():
                return {
                    "session_id": self.id,
                    "offset": offset,
                    "next_offset": offset,
                    "data": "",
                    "bytes": 0,
                }
            data = self.serial0.read_bytes()
        offset = min(max(int(offset), 0), len(data))
        chunk = data[offset:offset + limit]
        return {
            "session_id": self.id,
            "offset": offset,
            "next_offset": offset + len(chunk),
            "data": chunk.decode("utf-8", errors="replace"),
            "bytes": len(chunk),
        }

    def frame_metrics(self) -> dict:
        if not self.spec.has_display:
            raise ServiceError(
                "display_not_available",
                "this device has no framebuffer display",
                409,
            )
        if self.state not in {"running", "booting"}:
            persisted = self.persisted_frame_metrics()
            if persisted:
                return persisted
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        with self._lock:
            ppm = self.dir / f"frame-{uuid.uuid4().hex}.ppm"
            png = ppm.with_suffix(".png")
            try:
                self._qmp_call("screendump", filename=str(ppm))
                width, height, pixels = read_ppm(ppm)
                write_rgb_png(png, width, height, pixels)
                png_bytes = png.read_bytes()
                nonblack, unique_colors = rgb_metrics(pixels)
                metrics = {
                    "png": png_bytes,
                    "width": width,
                    "height": height,
                    "nonblack_pixels": nonblack,
                    "unique_colors": unique_colors,
                    "png_bytes": len(png_bytes),
                    "source": "live",
                }
                self._persist_frame(metrics)
                return metrics
            finally:
                ppm.unlink(missing_ok=True)
                png.unlink(missing_ok=True)

    def _persist_frame(self, metrics: dict) -> None:
        self.last_frame_path.write_bytes(metrics["png"])
        self.last_frame_meta_path.write_text(
            json.dumps(
                {
                    key: value
                    for key, value in metrics.items()
                    if key != "png"
                }
                | {"captured_at": iso_now()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )

    def persisted_frame_metrics(self) -> dict | None:
        if not self.last_frame_path.is_file():
            return None
        meta = {}
        if self.last_frame_meta_path.is_file():
            try:
                meta = json.loads(self.last_frame_meta_path.read_text())
            except json.JSONDecodeError:
                meta = {}
        png = self.last_frame_path.read_bytes()
        return {
            **meta,
            "png": png,
            "png_bytes": len(png),
            "source": "persisted",
        }

    def frame_png(self) -> tuple[bytes, int, int]:
        metrics = self.frame_metrics()
        return metrics["png"], metrics["width"], metrics["height"]

    def device_state(self) -> dict:
        if not self.spec.state_probes:
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "supported": False,
                "available": False,
                "reason": "device_state_not_modelled",
                "components": {},
                "errors": {},
            }
        if self.state not in {"running", "booting"}:
            if self.device_state_path.is_file():
                try:
                    persisted = json.loads(self.device_state_path.read_text())
                    return {
                        **persisted,
                        "state": self.state,
                        "source": "persisted",
                    }
                except json.JSONDecodeError:
                    pass
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "supported": True,
                "available": False,
                "reason": "session_not_running",
                "components": {},
                "errors": {},
            }

        components: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, str]] = {}
        for component_id, probe in self.spec.state_probes.items():
            path = probe.get("path")
            properties = probe.get("properties", [])
            if not isinstance(path, str) or not isinstance(properties, list):
                errors[component_id] = {
                    "probe": "invalid runtime_state probe"
                }
                continue
            values: dict[str, Any] = {}
            component_errors: dict[str, str] = {}
            for prop in properties:
                if not isinstance(prop, str):
                    continue
                try:
                    with self._lock:
                        result = self._qmp_call(
                            "qom-get", path=path, property=prop
                        )
                    values[prop] = result.get("return")
                except ServiceError as error:
                    component_errors[prop] = error.message
            if values:
                components[component_id] = {
                    "path": path,
                    "properties": values,
                }
            if component_errors:
                errors[component_id] = component_errors

        response = {
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": self.state,
            "supported": True,
            "available": bool(components),
            "source": "live",
            "captured_at": iso_now(),
            "components": components,
            "errors": errors,
        }
        if components:
            self.device_state_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n"
            )
        return response

    def inject(self, payload: dict) -> dict:
        if self.state != "running":
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        settle = float(payload.get("settle_seconds", 0.3))
        kind = payload.get("kind")
        if kind == "key":
            key = str(payload.get("key", ""))
            if not key:
                raise ServiceError("invalid_input", "key is required", 400)
            spec = f"key:{key}"
        elif kind == "touch":
            spec = f"touch:{int(payload.get('x', 0))},{int(payload.get('y', 0))}"
        elif kind == "longpress":
            spec = (
                f"longpress:{int(payload.get('x', 0))},"
                f"{int(payload.get('y', 0))},{float(payload.get('hold_seconds', 0.5))}"
            )
        elif kind == "drag":
            spec = (
                f"drag:{int(payload.get('x1', 0))},{int(payload.get('y1', 0))},"
                f"{int(payload.get('x2', 0))},{int(payload.get('y2', 0))}"
            )
        else:
            raise ServiceError(
                "invalid_input",
                "kind must be key, touch, longpress or drag",
                400,
            )
        frame_size = self.spec.expected_size or (1, 1)
        with self._lock:
            send_input(self._qmp, spec, frame_size, settle)
            self._record_event("input", spec=spec)
        return {"session_id": self.id, "input": spec, "accepted": True}

    def qom_set(self, payload: dict) -> dict:
        path = payload.get("path")
        prop = payload.get("property")
        if not isinstance(path, str) or not isinstance(prop, str):
            raise ServiceError(
                "invalid_qom", "path and property are required strings", 400
            )
        value = payload.get("value")
        with self._lock:
            result = self._qmp_call("qom-set", path=path, property=prop, value=value)
            self._record_event(
                "qom_set", path=path, property=prop, value=value
            )
        return {"session_id": self.id, "qom_set": result}

    def qom_get(self, path: str, prop: str) -> dict:
        with self._lock:
            result = self._qmp_call("qom-get", path=path, property=prop)
        return {
            "session_id": self.id,
            "path": path,
            "property": prop,
            "value": result.get("return"),
        }

    def qom_list(self, path: str = "/machine") -> dict:
        with self._lock:
            result = self._qmp_call("qom-list", path=path)
        fields = sorted(
            result.get("return", []), key=lambda item: item.get("name", "")
        )
        return {"session_id": self.id, "path": path, "properties": fields}

    def qom_snapshot(
        self, path: str = "/machine", depth: int = 2, max_nodes: int = 500
    ) -> dict:
        depth = max(0, min(int(depth), 8))
        max_nodes = max(1, min(int(max_nodes), 5000))
        budget = {"remaining": max_nodes}

        def walk(current_path: str, current_depth: int) -> dict:
            if budget["remaining"] <= 0:
                return {"truncated": True}
            with self._lock:
                fields = self._qmp_call("qom-list", path=current_path).get(
                    "return", []
                )
            output = {}
            for field in sorted(fields, key=lambda item: item.get("name", "")):
                if budget["remaining"] <= 0:
                    output["__truncated__"] = True
                    break
                name = field.get("name")
                field_type = str(field.get("type", ""))
                if not name:
                    continue
                budget["remaining"] -= 1
                if field_type.startswith("child<") and current_depth < depth:
                    output[name] = {
                        "__type__": field_type,
                        "children": walk(f"{current_path}/{name}", current_depth + 1),
                    }
                    continue
                try:
                    with self._lock:
                        value = self._qmp_call(
                            "qom-get", path=current_path, property=name
                        ).get("return")
                    output[name] = {"type": field_type, "value": value}
                except ServiceError as error:
                    output[name] = {
                        "type": field_type,
                        "error": error.message,
                    }
            return output

        snapshot = {
            "path": path,
            "depth": depth,
            "created_at": iso_now(),
            "nodes": walk(path, 0),
        }
        snapshot_id = uuid.uuid4().hex
        snapshot_path = self.dir / f"qom-{snapshot_id}.json"
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        )
        self._record_event("qom_snapshot", snapshot_id=snapshot_id, path=path)
        return {
            "session_id": self.id,
            "snapshot_id": snapshot_id,
            **snapshot,
        }

    def _load_qom_snapshot(self, snapshot_id: str) -> dict:
        if not isinstance(snapshot_id, str) or not all(
            char in "0123456789abcdef" for char in snapshot_id
        ):
            raise ServiceError("unknown_snapshot", "invalid qom snapshot id", 404)
        path = self.dir / f"qom-{snapshot_id}.json"
        if not path.is_file():
            raise ServiceError(
                "unknown_snapshot", f"unknown qom snapshot: {snapshot_id}", 404
            )
        return json.loads(path.read_text())

    def qom_diff(self, before: str, after: str) -> dict:
        before_snapshot = self._load_qom_snapshot(before)
        after_snapshot = self._load_qom_snapshot(after)

        def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
            output = {}
            if isinstance(value, dict):
                for key, child in value.items():
                    child_prefix = f"{prefix}/{key}" if prefix else key
                    output.update(flatten(child, child_prefix))
            else:
                output[prefix] = value
            return output

        left = flatten(before_snapshot["nodes"])
        right = flatten(after_snapshot["nodes"])
        added = {key: right[key] for key in sorted(right.keys() - left.keys())}
        removed = {key: left[key] for key in sorted(left.keys() - right.keys())}
        changed = {
            key: {"before": left[key], "after": right[key]}
            for key in sorted(left.keys() & right.keys())
            if left[key] != right[key]
        }
        self._record_event(
            "qom_diff",
            before=before,
            after=after,
            added=len(added),
            removed=len(removed),
            changed=len(changed),
        )
        return {
            "session_id": self.id,
            "before": before,
            "after": after,
            "added": added,
            "removed": removed,
            "changed": changed,
        }

    def flash_get(self, output_format: str = "sha256") -> tuple[bytes | None, dict]:
        if self.virtual_flash is None or not self.virtual_flash.is_file():
            raise ServiceError("flash_not_available", "session flash is unavailable", 409)
        data = self.virtual_flash.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        metadata = {
            "session_id": self.id,
            "format": output_format,
            "size": len(data),
            "sha256": digest,
        }
        if output_format == "bin":
            return data, metadata
        if output_format != "sha256":
            raise ServiceError(
                "invalid_format", "format must be bin or sha256", 400
            )
        return None, metadata

    def flash_snapshot(self) -> dict:
        _, metadata = self.flash_get("sha256")
        assert self.virtual_flash is not None
        snapshot_id = uuid.uuid4().hex
        target = self.dir / f"flash-{snapshot_id}.bin"
        shutil.copyfile(self.virtual_flash, target)
        self._record_event(
            "flash_snapshot", snapshot_id=snapshot_id, sha256=metadata["sha256"]
        )
        return {
            "session_id": self.id,
            "snapshot_id": snapshot_id,
            "size": metadata["size"],
            "sha256": metadata["sha256"],
            "created_at": iso_now(),
        }

    def _flash_snapshot_path(self, snapshot_id: str) -> Path:
        if not isinstance(snapshot_id, str) or not all(
            char in "0123456789abcdef" for char in snapshot_id
        ):
            raise ServiceError("unknown_snapshot", "invalid flash snapshot id", 404)
        path = self.dir / f"flash-{snapshot_id}.bin"
        if not path.is_file():
            raise ServiceError(
                "unknown_snapshot", f"unknown flash snapshot: {snapshot_id}", 404
            )
        return path

    def flash_diff(self, before: str, after: str) -> dict:
        before_path = self._flash_snapshot_path(before)
        after_path = self._flash_snapshot_path(after)
        left = before_path.read_bytes()
        right = after_path.read_bytes()
        if len(left) != len(right):
            raise ServiceError(
                "flash_size_mismatch",
                f"snapshot sizes differ: {len(left)} != {len(right)}",
                409,
            )
        ranges = []
        changed_bytes = 0
        start = None
        for index, (old, new) in enumerate(zip(left, right)):
            if old != new:
                changed_bytes += 1
                if start is None:
                    start = index
            elif start is not None:
                ranges.append({"offset": start, "length": index - start})
                start = None
        if start is not None:
            ranges.append({"offset": start, "length": len(left) - start})
        self._record_event(
            "flash_diff",
            before=before,
            after=after,
            changed_bytes=changed_bytes,
            ranges=len(ranges),
        )
        return {
            "session_id": self.id,
            "before": before,
            "after": after,
            "size": len(left),
            "changed_bytes": changed_bytes,
            "ranges": ranges[:1000],
            "truncated_ranges": len(ranges) > 1000,
        }

    def evidence_bundle(self, include: set[str] | None = None) -> bytes:
        include = include or {
            "manifest",
            "serial",
            "frames",
            "logs",
            "qom",
        }
        files: dict[str, bytes] = {}
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "session": self.snapshot(),
            "device": self.service.get_device(self.spec.id),
            "timeline": list(self.events),
            "included": sorted(include),
            "files": {},
        }
        if "serial" in include:
            for name, path in (("serial.log", self.serial0), ("serial1.log", self.serial1)):
                if path.is_file():
                    files[name] = path.read_bytes()
        if "logs" in include:
            for name, path in (
                ("qemu.stdout", self.stdout_path),
                ("qemu.stderr", self.stderr_path),
                ("c6.log", self.dir / "c6.log"),
            ):
                if path.is_file():
                    files[name] = path.read_bytes()
        if "frames" in include and self.spec.has_display:
            try:
                frame = self.frame_metrics()
                files["frames/current.png"] = frame["png"]
                manifest["frame"] = {
                    key: value for key, value in frame.items() if key != "png"
                }
            except ServiceError as error:
                manifest["frame"] = {"status": "NOT_AVAILABLE", "reason": error.message}
        if "qom" in include and self.spec.service_kind == "qemu":
            try:
                snapshot = self.qom_snapshot(path="/machine", depth=2, max_nodes=500)
                qom_bytes = (
                    self.dir / f"qom-{snapshot['snapshot_id']}.json"
                ).read_bytes()
                files["qom/snapshot.json"] = qom_bytes
                manifest["qom"] = {
                    "snapshot_id": snapshot["snapshot_id"],
                    "path": snapshot["path"],
                    "depth": snapshot["depth"],
                    "created_at": snapshot["created_at"],
                }
            except ServiceError as error:
                manifest["qom"] = {"status": "NOT_AVAILABLE", "reason": error.message}
        if self.virtual_flash and self.virtual_flash.is_file():
            flash_data = self.virtual_flash.read_bytes()
            manifest["flash"] = {
                "size": len(flash_data),
                "sha256": hashlib.sha256(flash_data).hexdigest(),
            }
            if "flash" in include:
                files["flash/virtual-flash.bin"] = flash_data
        for name, data in files.items():
            manifest["files"][name] = {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        files["manifest.json"] = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        self._record_event("evidence_bundle", included=sorted(include))
        return output.getvalue()

    def reset(self) -> dict:
        with self._lock:
            self._qmp_call("system_reset")
            self._record_event("reset")
        return {"session_id": self.id, "state": self.state, "reset": True}

    def renew(self, ttl_seconds: int) -> dict:
        self.ttl_seconds = ttl_seconds
        self.expires_at = time.time() + ttl_seconds
        self._persist_session()
        return self.snapshot()

    def _terminate_process(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if self._qmp is not None:
            try:
                self._qmp.close()
            except OSError:
                pass
            self._qmp = None
        try:
            self.qmp_path.unlink()
        except FileNotFoundError:
            pass

    def stop(self, purge: bool = False) -> dict:
        with self._lock:
            if self.state in {"stopped", "failed"}:
                result = self.snapshot()
                if purge:
                    shutil.rmtree(self.dir, ignore_errors=True)
                return result
            if self.state == "running" and self.spec.has_display:
                try:
                    self.frame_metrics()
                except ServiceError:
                    pass
            if self.state == "running" and self.spec.state_probes:
                try:
                    self.device_state()
                except ServiceError:
                    pass
            self.state = "stopping"
            if self._qmp is not None:
                try:
                    self._qmp.cmd("quit")
                except (OSError, RuntimeError):
                    pass
            self._terminate_process()
            self.state = "stopped"
            self.completed_at = iso_now()
            self._record_event("stopped", purge=purge)
            result = self.snapshot()
            self._persist_session()
        if purge:
            shutil.rmtree(self.dir, ignore_errors=True)
        return result


class Tab5DeviceSession(DeviceSession):
    """Tab5 esp-emu session with serial, GDB framebuffer and touch support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._c6_proc: subprocess.Popen | None = None
        self._gdb_port: int | None = None
        self._hosted_socket = Path("/tmp") / f"m5-service-tab5-{self.id}.sock"

    def _provision(self) -> None:
        try:
            self._set_state("flashing")
            prepared = self.service.prepare_flash(
                self.spec, self.firmware_path, self.firmware_sha
            )
            self.virtual_flash = self.dir / "virtual-flash.bin"
            shutil.copyfile(prepared["path"], self.virtual_flash)
            self.flash_info = {
                **prepared["info"],
                "session_isolated_copy": True,
            }
            self._record_event("flash_prepared", **self.flash_info)
            self._persist_session()
            self._set_state("booting")
            self._launch_tab5()
            if self.ready_conditions:
                self.wait_ready(
                    {
                        "timeout_seconds": self.ready_timeout,
                        **self.ready_conditions,
                    }
                )
            elif self.ready_marker:
                self.wait_for_marker(self.ready_marker, self.ready_timeout)
            self._set_state("running")
        except Exception as error:
            with self._lock:
                self.error = str(error)
                self.state = "failed"
                self.completed_at = self.completed_at or iso_now()
                self._record_event("failed", error=str(error))
                self._persist_session()
            self._terminate_tab5()

    def _launch_tab5(self) -> None:
        assert self.virtual_flash is not None
        assert self.spec.emulator is not None
        assert self.spec.elf is not None
        assert self.spec.rom is not None
        assert self.spec.efuse is not None
        assert self.spec.c6_firmware is not None
        try:
            self._hosted_socket.unlink()
        except FileNotFoundError:
            pass
        c6_stdout = (self.dir / "c6.log").open("wb")
        self._c6_proc = subprocess.Popen(
            [
                str(self.spec.emulator),
                "--chip", "esp32c6",
                "--firmware", str(self.spec.c6_firmware),
                "--hosted", f"bridge:slave:{self._hosted_socket}",
            ],
            cwd=ROOT,
            stdout=c6_stdout,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for_fs_path(self._hosted_socket, self._c6_proc, 25)
        finally:
            c6_stdout.close()
        self._gdb_port = free_tcp_port()
        p4_stdout = self.serial0.open("wb")
        p4_stderr = self.stderr_path.open("wb")
        command = [
            str(self.spec.emulator),
            "--chip", "esp32p4",
            "--firmware", str(self.virtual_flash),
            "--elf", str(self.spec.elf),
            "--rom", str(self.spec.rom),
            "--efuse", str(self.spec.efuse),
            "--hosted", f"bridge:host:{self._hosted_socket}",
            "--hosted-reset-gpio", "15",
            "--hosted-reset-active-high",
            "--psram-size", "32M",
            "--console", "uart0",
            "--gdb", str(self._gdb_port),
            "--timeout", f"{int(self.ttl_seconds + 120)}s",
        ]
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=p4_stdout,
                stderr=p4_stderr,
            )
        finally:
            p4_stdout.close()
            p4_stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        wait_for_tcp_port(self._gdb_port, self._proc, 25)

    def _terminate_tab5(self) -> None:
        for proc in (self._proc, self._c6_proc):
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
        for proc in (self._proc, self._c6_proc):
            if proc is None:
                continue
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._proc = None
        self._c6_proc = None
        try:
            self._hosted_socket.unlink()
        except FileNotFoundError:
            pass

    def frame_metrics(self) -> dict:
        if self.state not in {"running", "booting"} or self._gdb_port is None:
            persisted = self.persisted_frame_metrics()
            if persisted:
                return persisted
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        if self.firmware_source != "reference":
            raise ServiceError(
                "screenshot_requires_matching_elf",
                "Tab5 screenshot capture requires the reference ELF; "
                "uploaded firmware has no matching symbol file yet",
                409,
            )
        assert self.spec.elf is not None
        name = f"api-frame-{uuid.uuid4().hex}"
        raw_width, raw_height, raw565, _ = capture_framebuffer(
            self.spec.elf, self._gdb_port, self.dir, name
        )
        width, height, oriented = orient_rgb565(
            raw565, raw_width, raw_height, 1
        )
        pixels = rgb565_to_rgb(oriented)
        png = self.dir / f"{name}.png"
        write_tab5_png(png, width, height, pixels)
        try:
            png_bytes = png.read_bytes()
            nonblack, unique_colors = rgb_metrics(pixels)
            metrics = {
                "png": png_bytes,
                "width": width,
                "height": height,
                "nonblack_pixels": nonblack,
                "unique_colors": unique_colors,
                "png_bytes": len(png_bytes),
                "source": "live",
            }
            self._persist_frame(metrics)
            return metrics
        finally:
            png.unlink(missing_ok=True)
            (self.dir / f"{name}.rgb565").unlink(missing_ok=True)

    def frame_png(self) -> tuple[bytes, int, int]:
        metrics = self.frame_metrics()
        return metrics["png"], metrics["width"], metrics["height"]

    def inject(self, payload: dict) -> dict:
        if self.state != "running" or self._gdb_port is None:
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        if self.firmware_source != "reference":
            raise ServiceError(
                "input_requires_matching_elf",
                "Tab5 touch injection currently requires the reference ELF",
                409,
            )
        kind = payload.get("kind")
        if kind not in {"touch", "longpress"}:
            raise ServiceError(
                "unsupported_input",
                "Tab5 service currently supports touch and longpress only",
                409,
            )
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        hold = (
            float(payload.get("hold_seconds", 0.5))
            if kind == "longpress"
            else float(payload.get("settle_seconds", 0.15))
        )
        raw_x, raw_y = logical_to_raw_touch(x, y, 720, 1280, 1)
        assert self.spec.elf is not None
        inject_touch(
            self.spec.elf,
            self._gdb_port,
            self.dir,
            f"api-touch-down-{uuid.uuid4().hex}",
            down=True,
            x=raw_x,
            y=raw_y,
        )
        time.sleep(max(0.05, hold))
        inject_touch(
            self.spec.elf,
            self._gdb_port,
            self.dir,
            f"api-touch-up-{uuid.uuid4().hex}",
            down=False,
            x=raw_x,
            y=raw_y,
        )
        return {
            "session_id": self.id,
            "input": kind,
            "logical": [x, y],
            "raw": [raw_x, raw_y],
            "accepted": True,
        }

    def qom_set(self, payload: dict) -> dict:
        raise ServiceError(
            "qom_not_supported",
            "Tab5 esp-emu sessions do not expose QMP QOM",
            409,
        )

    def qom_get(self, path: str, prop: str) -> dict:
        raise ServiceError(
            "qom_not_supported",
            "Tab5 esp-emu sessions do not expose QMP QOM",
            409,
        )

    def reset(self) -> dict:
        if self.state != "running":
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        self._set_state("booting")
        self.serial0.write_bytes(b"")
        self._terminate_tab5()
        self._launch_tab5()
        self._set_state("running")
        self._record_event("reset")
        return {"session_id": self.id, "state": self.state, "reset": True}

    def stop(self, purge: bool = False) -> dict:
        with self._lock:
            if self.state in {"stopped", "failed"}:
                result = self.snapshot()
                if purge:
                    shutil.rmtree(self.dir, ignore_errors=True)
                return result
            if self.state == "running" and self.spec.has_display:
                try:
                    self.frame_metrics()
                except ServiceError:
                    pass
            self.state = "stopping"
            self._terminate_tab5()
            self.state = "stopped"
            self.completed_at = iso_now()
            self._record_event("stopped", purge=purge)
            result = self.snapshot()
            self._persist_session()
        if purge:
            shutil.rmtree(self.dir, ignore_errors=True)
        return result


class DeviceService:
    def __init__(
        self,
        *,
        state_dir: Path = DEFAULT_STATE_DIR,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_per_device: int = DEFAULT_MAX_PER_DEVICE,
        default_ttl: int = 1800,
        api_token: str | None = None,
        flash_preparer=None,
    ):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.specs = load_device_specs()
        self.raw_matrix = json.loads(MATRIX.read_text())
        self.artifacts = ArtifactStore(self.state_dir / "artifacts")
        self.firmware = FirmwareStore(
            self.state_dir / "firmware", self.artifacts, self.specs
        )
        self.max_sessions = max(1, int(max_sessions))
        self.max_per_device = max(1, int(max_per_device))
        self.default_ttl = max(30, int(default_ttl))
        self.api_token = api_token
        self.flash_preparer = flash_preparer or default_flash_preparer
        self._sessions: dict[str, DeviceSession] = {}
        self._lock = threading.RLock()
        self._flash_lock = threading.Lock()
        self._reference_cache: dict[str, dict] = {}
        self._restore_history()
        self._stop = threading.Event()
        self._janitor = threading.Thread(
            target=self._janitor_loop,
            name="m5-session-janitor",
            daemon=True,
        )
        self._janitor.start()

    def _restore_history(self) -> None:
        """Restore retained metadata without reviving old QEMU processes."""

        sessions_root = self.state_dir / "sessions"
        if not sessions_root.is_dir():
            return
        for record_path in sorted(
            sessions_root.glob("*/session.json"),
            key=lambda path: path.name,
        ):
            try:
                record = json.loads(record_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            session_id = record.get("session_id")
            device_id = record.get("device_id")
            if (
                not isinstance(session_id, str)
                or session_id != record_path.parent.name
                or not isinstance(device_id, str)
            ):
                continue
            spec = self.specs.get(device_id)
            if spec is None or session_id in self._sessions:
                continue
            persisted_state = str(record.get("state") or "failed")
            interrupted = persisted_state in ACTIVE_STATES or persisted_state == "stopping"
            restored_state = "failed" if interrupted else persisted_state
            if restored_state not in {"stopped", "failed"}:
                restored_state = "failed"
                interrupted = True
            events: list[dict] = []
            events_path = record_path.parent / "events.json"
            if events_path.is_file():
                try:
                    loaded_events = json.loads(events_path.read_text())
                    if isinstance(loaded_events, list):
                        events = [
                            event for event in loaded_events if isinstance(event, dict)
                        ]
                except (OSError, json.JSONDecodeError):
                    events = []
            try:
                expires_at = datetime.fromisoformat(
                    str(record.get("expires_at")).replace("Z", "+00:00")
                ).timestamp()
            except (TypeError, ValueError):
                expires_at = time.time()
            completed_at = record.get("completed_at")
            if interrupted and not completed_at:
                completed_at = iso_now()
            error = record.get("error")
            if interrupted:
                error = (
                    "service restarted before the session completed; "
                    f"previous state was {persisted_state}"
                )
            source_artifacts = record.get("source_artifacts")
            if not isinstance(source_artifacts, list):
                source_artifacts = []
            try:
                ttl_seconds = max(30, int(record.get("ttl_seconds") or 30))
                ready_timeout = float(
                    record.get("ready_timeout_seconds") or 30
                )
            except (TypeError, ValueError):
                continue
            session = DeviceSession(
                self,
                session_id=session_id,
                spec=spec,
                firmware_id=str(record.get("firmware_id") or ""),
                firmware_path=record_path.parent / "firmware.bin",
                firmware_sha=str(record.get("firmware_sha256") or ""),
                firmware_source=str(record.get("firmware_source") or "unknown"),
                source_artifacts=[
                    artifact
                    for artifact in source_artifacts
                    if isinstance(artifact, str)
                ],
                ttl_seconds=ttl_seconds,
                ready_marker=(
                    record.get("ready_marker")
                    if isinstance(record.get("ready_marker"), str)
                    else None
                ),
                ready_timeout=ready_timeout,
                ready_conditions=(
                    record.get("ready_conditions")
                    if isinstance(record.get("ready_conditions"), dict)
                    else None
                ),
                events=events,
                created_at=(
                    record.get("created_at")
                    if isinstance(record.get("created_at"), str)
                    else None
                ),
                completed_at=(
                    completed_at if isinstance(completed_at, str) else None
                ),
                expires_at=expires_at,
                initial_state=restored_state,
                error=error if isinstance(error, str) else None,
                flash_info=(
                    record.get("flash")
                    if isinstance(record.get("flash"), dict)
                    else None
                ),
                restored=True,
                interrupted=interrupted,
            )
            virtual_flash = record_path.parent / "virtual-flash.bin"
            session.virtual_flash = virtual_flash if virtual_flash.is_file() else None
            if interrupted:
                session._record_event(
                    "interrupted",
                    previous_state=persisted_state,
                    reason="service restarted before session completion",
                )
                session._persist_session()
            self._sessions[session.id] = session

    def raw_device(self, device_id: str) -> dict:
        for row in self.raw_matrix["devices"]:
            if row["id"] == device_id:
                return row
        raise KeyError(device_id)

    def _public_device(self, spec: DeviceSpec) -> dict:
        reference_available = spec.reference_available
        backend_ready = spec.backend_ready
        return {
            "device_id": spec.id,
            "name": spec.name,
            "group": spec.group,
            "soc": spec.soc,
            "sku": spec.sku,
            "device_codes": spec.device_codes,
            "supported": spec.supported,
            "creatable": spec.supported and backend_ready,
            "backend_ready": backend_ready,
            "reference_available": reference_available,
            "backend": spec.backend,
            "machine": spec.machine,
            "flash_size": spec.flash_size,
            "display": spec.display,
            "peripheral_status": spec.peripheral_status,
            "warnings": spec.warnings,
            "firmware_families": ["uiflow2", "generic-flash"],
            "coverage": {
                "peripheral_status": spec.peripheral_status,
                "complete": spec.peripheral_status == "simulated",
            },
            "features": {
                "flash": spec.supported,
                "serial": spec.supported,
                "screenshot": spec.supported and spec.has_display,
                "input": spec.supported,
                "qom": spec.supported and spec.service_kind == "qemu",
                "device_state": bool(spec.state_probes),
                "network": False,
            },
            "reason": spec.reason,
        }

    def list_devices(self, include_unsupported: bool = True) -> dict:
        devices = [
            self._public_device(spec)
            for spec in sorted(self.specs.values(), key=lambda row: row.id)
            if include_unsupported or spec.supported
        ]
        return {
            "service": "m5stack-device-service",
            "api_version": "v1",
            "network_enabled": False,
            "tab5_enabled": False,
            "devices": devices,
        }

    def get_device(self, device_id: str) -> dict:
        spec = self.specs.get(device_id)
        if spec is None:
            raise ServiceError("unknown_device", f"unknown device: {device_id}", 404)
        return self._public_device(spec)

    def upload_artifact(
        self, data: bytes, *, name: str = "", content_type: str = ""
    ) -> dict:
        return self.artifacts.create(
            data, name=name, content_type=content_type or "application/octet-stream"
        )

    def create_firmware(self, payload: dict) -> dict:
        return self.firmware.create(payload)

    def reference_info(self, spec: DeviceSpec) -> dict:
        with self._lock:
            if spec.id in self._reference_cache:
                return self._reference_cache[spec.id]
            if not spec.reference_path or not spec.reference_path.is_file():
                raise ServiceError(
                    "reference_firmware_missing",
                    f"reference firmware is not cached for {spec.id}",
                    409,
                )
            reference_path = spec.reference_path
            if spec.service_kind == "tab5":
                reference_path = self._tab5_reference_image(spec)
            data = reference_path.read_bytes()
            if len(data) > spec.flash_size:
                raise ServiceError(
                    "reference_firmware_too_large",
                    "reference firmware exceeds device flash size",
                    409,
                )
            record = {
                "firmware_id": hashlib.sha256(data).hexdigest(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "path": reference_path,
            }
            self._reference_cache[spec.id] = record
            return record

    def _tab5_reference_image(self, spec: DeviceSpec) -> Path:
        assert spec.reference_path is not None
        target = self.state_dir / "references" / "tab5-uiflow2-service.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            not target.is_file()
            or target.stat().st_mtime < spec.reference_path.stat().st_mtime
        ):
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/tab5_ui_test/make_image.py"),
                    "--base",
                    str(spec.reference_path),
                    "--out",
                    str(target),
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        return target

    def prepare_flash(
        self, spec: DeviceSpec, image: Path, firmware_sha: str
    ) -> dict:
        cache_dir = self.state_dir / "flash-cache" / spec.id
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{firmware_sha}.bin"
        work_dir = cache_dir / f".work-{uuid.uuid4().hex}"
        with self._flash_lock:
            if cache_path.is_file() and cache_path.stat().st_size == spec.flash_size:
                return {
                    "path": cache_path,
                        "info": _public_flash_info({
                        "transport": "cache",
                        "verified": True,
                        "flash_size": spec.flash_size,
                        "firmware_sha256": firmware_sha,
                        }),
                }
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                if os.environ.get("M5_SERVICE_FLASH_MODE", "esptool") == "host-image":
                    info = {
                        "transport": "host-image",
                        "verified": True,
                        "flash_size": spec.flash_size,
                        "firmware_sha256": firmware_sha,
                    }
                    work_dir.joinpath("virtual-flash.bin").write_bytes(
                        _padded(image.read_bytes(), spec.flash_size)
                    )
                else:
                    info = self.flash_preparer(spec, image, firmware_sha, work_dir)
                produced = Path(info["virtual_flash"])
                if produced.stat().st_size != spec.flash_size:
                    raise ServiceError(
                        "flash_size_mismatch",
                        f"prepared flash size {produced.stat().st_size} "
                        f"!= {spec.flash_size}",
                        500,
                    )
                shutil.copyfile(produced, cache_path)
                return {"path": cache_path, "info": _public_flash_info(info)}
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    def create_session(self, payload: dict) -> dict:
        device_id = payload.get("device_id")
        if not isinstance(device_id, str):
            raise ServiceError("invalid_request", "device_id is required", 400)
        spec = self.specs.get(device_id)
        if spec is None:
            raise ServiceError("unknown_device", f"unknown device: {device_id}", 404)
        if not spec.supported:
            raise ServiceError(
                "unsupported_device", spec.reason or "device is not enabled", 409
            )
        if not spec.backend_ready:
            raise ServiceError(
                "backend_not_ready",
                f"runtime files are missing for {device_id}",
                503,
            )
        firmware_id = payload.get("firmware_id")
        if firmware_id:
            firmware = self.firmware.get(str(firmware_id))
            if firmware["device_id"] != device_id:
                raise ServiceError(
                    "firmware_device_mismatch",
                    f"firmware belongs to {firmware['device_id']}",
                    409,
                )
            firmware_path = self.firmware.path(str(firmware_id))
            firmware_sha = firmware["sha256"]
            source = "uploaded"
            firmware_source = firmware.get("source", {})
            source_artifacts = (
                [firmware_source["artifact_id"]]
                if firmware_source.get("kind") == "merged"
                and firmware_source.get("artifact_id")
                else [
                    segment["artifact_id"]
                    for segment in firmware_source.get("segments", [])
                    if segment.get("artifact_id")
                ]
            )
        else:
            reference = self.reference_info(spec)
            firmware_id = reference["firmware_id"]
            firmware_path = reference["path"]
            firmware_sha = reference["sha256"]
            source = "reference"
            source_artifacts = []

        with self._lock:
            active = [
                session
                for session in self._sessions.values()
                if session.state in ACTIVE_STATES
            ]
            if len(active) >= self.max_sessions:
                raise ServiceError(
                    "capacity_exhausted",
                    f"maximum active sessions is {self.max_sessions}",
                    429,
                )
            same_device = [session for session in active if session.spec.id == device_id]
            if len(same_device) >= self.max_per_device:
                raise ServiceError(
                    "device_capacity_exhausted",
                    f"maximum active sessions for {device_id} is {self.max_per_device}",
                    429,
                )
            ttl = int(payload.get("ttl_seconds", self.default_ttl))
            if ttl < 30:
                raise ServiceError("invalid_ttl", "ttl_seconds must be >= 30", 400)
            ready_marker = payload.get("ready_marker")
            if ready_marker is not None and not isinstance(ready_marker, str):
                raise ServiceError("invalid_request", "ready_marker must be a string", 400)
            ready_conditions = payload.get("ready")
            if ready_conditions is not None and not isinstance(
                ready_conditions, dict
            ):
                raise ServiceError("invalid_ready", "ready must be an object", 400)
            ready_timeout = float(payload.get("ready_timeout_seconds", 30))
            session_class = (
                Tab5DeviceSession
                if spec.service_kind == "tab5"
                else DeviceSession
            )
            session = session_class(
                self,
                session_id=uuid.uuid4().hex,
                spec=spec,
                firmware_id=firmware_id,
                firmware_path=firmware_path,
                firmware_sha=firmware_sha,
                firmware_source=source,
                source_artifacts=source_artifacts,
                ttl_seconds=ttl,
                ready_marker=ready_marker,
                ready_timeout=ready_timeout,
                ready_conditions=ready_conditions,
            )
            self._sessions[session.id] = session
        session.start()
        return session.snapshot()

    def get_session(self, session_id: str) -> DeviceSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise ServiceError("unknown_session", f"unknown session: {session_id}", 404)
        return session

    def list_sessions(self, include_stopped: bool = True) -> dict:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if include_stopped or session.state in ACTIVE_STATES
            ]
        return {"sessions": [session.snapshot() for session in sessions]}

    def delete_session(self, session_id: str, purge: bool = False) -> dict:
        session = self.get_session(session_id)
        result = session.stop(purge=purge)
        if purge:
            with self._lock:
                self._sessions.pop(session_id, None)
        return result

    def clear_stopped(self, purge: bool = True) -> dict:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if session.state in {"stopped", "failed"}
            ]
            known_ids = set(self._sessions)
        for session in sessions:
            session.stop(purge=purge)
            if purge:
                with self._lock:
                    self._sessions.pop(session.id, None)
        orphaned = []
        if purge:
            sessions_root = self.state_dir / "sessions"
            if sessions_root.is_dir():
                orphaned = [
                    path
                    for path in sessions_root.iterdir()
                    if path.is_dir() and path.name not in known_ids
                ]
                for path in orphaned:
                    shutil.rmtree(path, ignore_errors=True)
        return {
            "cleared": len(sessions),
            "orphaned_cleared": len(orphaned),
            "purged": purge,
        }

    def session_events(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        return {
            "session_id": session.id,
            "events": list(session.events),
        }

    def capacity(self) -> dict:
        with self._lock:
            active = [
                session for session in self._sessions.values()
                if session.state in ACTIVE_STATES
            ]
            by_device: dict[str, int] = {}
            for session in active:
                by_device[session.spec.id] = by_device.get(session.spec.id, 0) + 1
        return {
            "max_sessions": self.max_sessions,
            "active_sessions": len(active),
            "available_sessions": max(0, self.max_sessions - len(active)),
            "max_per_device": self.max_per_device,
            "by_device": by_device,
            "modes": {
                "network": "disabled",
                "tab5": "enabled-partial",
                "flash": "prepared-cache + exact artifact",
            },
        }

    def _janitor_loop(self) -> None:
        while not self._stop.wait(2):
            now = time.time()
            expired = []
            with self._lock:
                for session in self._sessions.values():
                    if (
                        session.state in ACTIVE_STATES
                        and session._proc is not None
                        and session._proc.poll() is not None
                    ):
                        session.state = "failed"
                        session.error = (
                            session.error
                            or f"process exited with code {session._proc.returncode}"
                        )
                        session.completed_at = session.completed_at or iso_now()
                        session._record_event(
                            "process_exited",
                            returncode=session._proc.returncode,
                        )
                        session._persist_session()
                    if session.state in ACTIVE_STATES and session.expires_at <= now:
                        expired.append(session)
            for session in expired:
                try:
                    session.stop()
                except Exception:
                    pass

    def close_all(self) -> None:
        self._stop.set()
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            try:
                session.stop()
            except Exception:
                pass


def _padded(data: bytes, size: int) -> bytes:
    if len(data) > size:
        raise ServiceError(
            "firmware_too_large",
            f"firmware is {len(data)} bytes; flash is {size}",
            413,
        )
    return data + b"\xff" * (size - len(data))


def _public_flash_info(info: dict) -> dict:
    return {
        key: value
        for key, value in info.items()
        if key not in {"image", "virtual_flash", "qemu", "rom_dir"}
    }
