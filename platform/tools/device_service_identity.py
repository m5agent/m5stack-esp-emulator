"""Persistent virtual device identities; no firmware or cloud registration changes."""
from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from pathlib import Path

from device_service_errors import ServiceError

KEY_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
SUPPORTED_EFUSE_DRIVERS = {
    ("qemu-esp32s3", "nvram.esp32s3.efuse"),
    ("qemu-esp32lx6", "nvram.esp32.efuse"),
    ("qemu-esp32c6", "nvram.esp32c6.efuse"),
}


def canonical_mac(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", value
    ):
        raise ServiceError("invalid_device_identity", "identity MAC must contain six hexadecimal octets", 400)
    raw = bytes.fromhex(value.replace(":", ""))
    if raw == bytes(6) or raw[0] & 1:
        raise ServiceError("invalid_device_identity", "identity MAC must be a nonzero unicast address", 400)
    return ":".join(f"{part:02x}" for part in raw)


def parse_device_identity(payload: dict, *, device_id: str, cloud: bool) -> dict | None:
    if "device_identity" not in payload:
        return {"key": f"uiflow-cloud-{device_id}"} if cloud else None
    value = payload["device_identity"]
    if not isinstance(value, dict) or set(value) not in ({"key"}, {"mac"}):
        raise ServiceError("invalid_device_identity", "device_identity requires exactly one of key or mac", 400)
    if "mac" in value:
        return {"mac": canonical_mac(value["mac"])}
    key = value["key"]
    if not isinstance(key, str) or re.fullmatch(KEY_PATTERN, key) is None:
        raise ServiceError("invalid_device_identity", "identity key must be 1-64 ASCII letters, digits, dots, underscores or hyphens, starting with a letter or digit", 400)
    return {"key": key}


def validate_identity_runtime(spec, runtime: str, monitor: bool = False) -> None:
    if (spec.backend, spec.efuse_driver) not in SUPPORTED_EFUSE_DRIVERS or runtime == "network" or monitor:
        raise ServiceError("unsupported_device_identity", "this runtime has no supported attached identity fixture", 409)


def restore_device_identity(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ServiceError("invalid_device_identity_record", "stored device identity is invalid", 409)
    source = value.get("source")
    expected = {"source", "mac", "key"} if source == "persistent-fixture" else {"source", "mac"}
    try:
        if source not in {"persistent-fixture", "explicit-mac"} or set(value) != expected:
            raise ValueError()
        mac = canonical_mac(value["mac"])
        if mac != value["mac"]:
            raise ValueError()
        if source == "persistent-fixture":
            parse_device_identity({"device_identity": {"key": value["key"]}}, device_id="", cloud=False)
        return dict(value)
    except (ServiceError, ValueError, KeyError):
        raise ServiceError("invalid_device_identity_record", "stored device identity is invalid", 409) from None


class DeviceIdentityStore:
    """Mutations are serialized by DeviceService's admission lock/worker fence."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, dict] = {}
        if not path.exists():
            return
        try:
            record = json.loads(path.read_text())
            if not isinstance(record, dict) or set(record) != {"schema_version", "entries"} or record["schema_version"] != 1 or not isinstance(record["entries"], dict):
                raise ValueError()
            for key, entry in record["entries"].items():
                parse_device_identity({"device_identity": {"key": key}}, device_id="", cloud=False)
                if not isinstance(entry, dict) or set(entry) != {"device_id", "mac"} or not isinstance(entry["device_id"], str) or not entry["device_id"]:
                    raise ValueError()
                if canonical_mac(entry["mac"]) != entry["mac"] or not int(entry["mac"][:2], 16) & 2:
                    raise ValueError()
            self.entries = record["entries"]
            path.chmod(0o600)
        except (OSError, ValueError, TypeError, ServiceError):
            raise ServiceError("device_identity_store_invalid", "persistent device identity store cannot be read safely", 503) from None

    def lookup(self, request: dict, device_id: str) -> dict | None:
        if "mac" in request:
            return {"source": "explicit-mac", "mac": request["mac"]}
        key = request["key"]
        entry = self.entries.get(key)
        if entry is not None and entry["device_id"] != device_id:
            raise ServiceError("device_identity_device_mismatch", "persistent identity belongs to a different device profile", 409)
        return ({"source": "persistent-fixture", "key": key, "mac": entry["mac"]}
                if entry is not None else None)

    def resolve(self, request: dict, device_id: str) -> dict:
        existing = self.lookup(request, device_id)
        if existing is not None:
            return existing
        key = request["key"]
        entry = self.entries.get(key)
        if entry is None:
            used = {item["mac"] for item in self.entries.values()}
            while True:
                raw = bytearray(secrets.token_bytes(6))
                raw[0] = (raw[0] | 2) & 0xfe
                mac = ":".join(f"{part:02x}" for part in raw)
                if mac not in used:
                    break
            entry = {"device_id": device_id, "mac": mac}
            updated = {**self.entries, key: entry}
            self._write(updated)
            self.entries = updated
        return {"source": "persistent-fixture", "key": key, "mac": entry["mac"]}

    def _write(self, entries: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump({"schema_version": 1, "entries": entries}, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            # Once published, even a directory fsync failure must not let this
            # process generate a different identity for the same key on retry.
            self.entries = entries
            descriptor = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            raise ServiceError("device_identity_store_unavailable", "persistent device identity could not be saved", 503) from None
        finally:
            temporary.unlink(missing_ok=True)
