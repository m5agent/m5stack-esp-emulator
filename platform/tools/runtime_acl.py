"""Fail-closed runtime ACL for guest-facing Device Service operations.

The policy is operator-owned and loaded from a regular JSON file. It is not
derived from firmware metadata, so a guest cannot grant itself additional
runtime permissions. When no file is configured, the service retains the
historical fully-permissive local-control behavior and reports that state
explicitly as NOT_CONFIGURED.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import unicodedata
from typing import Any


MAX_POLICY_BYTES = 64 * 1024
OPERATIONS = frozenset(
    {
        "serial.read",
        "input.write",
        "guest.reset",
        "program.read",
        "program.execute",
        "program.interrupt",
        "filesystem.write",
        "flash.read",
    }
)
EXECUTION_ENTRYPOINTS = frozenset({"main.py", "main.mpy"})
_TOP_LEVEL_FIELDS = {"schema_version", "devices"}
_DEVICE_FIELDS = {
    "allow",
    "execution_entrypoints",
    "filesystem_write_allow",
    "filesystem_write_deny",
}


class RuntimeACLConfigError(ValueError):
    """The operator policy is invalid or cannot be loaded safely."""


class RuntimeACLError(PermissionError):
    """A requested guest-facing operation is denied by the active policy."""

    code = "runtime_acl_denied"
    status = 403

    def __init__(
        self,
        *,
        operation: str,
        device_id: str,
        policy_id: str | None,
        reason: str,
        path: str | None = None,
        entrypoint: str | None = None,
    ):
        super().__init__(f"runtime ACL denied {operation} for {device_id}")
        self.operation = operation
        self.device_id = device_id
        self.policy_id = policy_id
        self.reason = reason
        self.path = path
        self.entrypoint = entrypoint


@dataclass(frozen=True)
class DeviceRule:
    allow: frozenset[str]
    execution_entrypoints: tuple[str, ...]
    filesystem_write_allow: tuple[str, ...]
    filesystem_write_deny: tuple[str, ...]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeACLConfigError("runtime ACL policy contains duplicate JSON fields")
        result[key] = value
    return result


def _string_list(value: Any, field: str, *, maximum: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise RuntimeACLConfigError(f"{field} must be an array with at most {maximum} entries")
    if any(not isinstance(item, str) or not item for item in value):
        raise RuntimeACLConfigError(f"{field} entries must be non-empty strings")
    if len(value) != len(set(value)):
        raise RuntimeACLConfigError(f"{field} entries must be unique")
    return value


def _normalize_guest_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeACLConfigError(f"{field} paths must be non-empty strings")
    directory = value.endswith("/")
    candidate = value[:-1] if directory else value
    parts = candidate.split("/")
    try:
        encoded = candidate.encode("utf-8")
    except UnicodeEncodeError as error:
        raise RuntimeACLConfigError(f"{field} paths must be valid UTF-8") from error
    if (
        not candidate
        or "\\" in candidate
        or ":" in candidate
        or any(unicodedata.category(char) == "Cc" for char in candidate)
        or any(part in {"", ".", ".."} for part in parts)
        or PurePosixPath(candidate).is_absolute()
        or PurePosixPath(candidate).as_posix() != candidate
        or unicodedata.normalize("NFC", candidate) != candidate
        or len(encoded) > 192
        or len(parts) > 8
    ):
        raise RuntimeACLConfigError(
            f"{field} paths must be canonical relative POSIX paths; "
            "append / for a directory prefix"
        )
    return value


def _normalize_rule(value: Any, device_id: str) -> DeviceRule:
    if not isinstance(value, dict):
        raise RuntimeACLConfigError(f"runtime ACL rule for {device_id} must be an object")
    unknown = sorted(set(value) - _DEVICE_FIELDS)
    if unknown:
        raise RuntimeACLConfigError(
            f"runtime ACL rule for {device_id} has unknown fields: {', '.join(unknown)}"
        )
    allow = _string_list(
        value.get("allow", []),
        f"devices.{device_id}.allow",
        maximum=len(OPERATIONS),
    )
    unknown_operations = sorted(set(allow) - OPERATIONS)
    if unknown_operations:
        raise RuntimeACLConfigError(
            "runtime ACL contains unknown operations: "
            + ", ".join(unknown_operations)
        )
    entrypoints = _string_list(
        value.get("execution_entrypoints", []),
        f"devices.{device_id}.execution_entrypoints",
        maximum=len(EXECUTION_ENTRYPOINTS),
    )
    unknown_entrypoints = sorted(set(entrypoints) - EXECUTION_ENTRYPOINTS)
    if unknown_entrypoints:
        raise RuntimeACLConfigError(
            "runtime ACL contains unsupported entrypoints: "
            + ", ".join(unknown_entrypoints)
        )
    write_allow = [
        _normalize_guest_path(path, f"devices.{device_id}.filesystem_write_allow")
        for path in _string_list(
            value.get("filesystem_write_allow", []),
            f"devices.{device_id}.filesystem_write_allow",
            maximum=128,
        )
    ]
    write_deny = [
        _normalize_guest_path(path, f"devices.{device_id}.filesystem_write_deny")
        for path in _string_list(
            value.get("filesystem_write_deny", []),
            f"devices.{device_id}.filesystem_write_deny",
            maximum=128,
        )
    ]
    if "program.execute" in allow and not entrypoints:
        raise RuntimeACLConfigError(
            f"devices.{device_id}.execution_entrypoints is required when program.execute is allowed"
        )
    if "program.execute" not in allow and entrypoints:
        raise RuntimeACLConfigError(
            f"devices.{device_id}.execution_entrypoints requires program.execute"
        )
    if "filesystem.write" in allow and not write_allow:
        raise RuntimeACLConfigError(
            f"devices.{device_id}.filesystem_write_allow is required when filesystem.write is allowed"
        )
    if "filesystem.write" not in allow and (write_allow or write_deny):
        raise RuntimeACLConfigError(
            f"filesystem write paths require the filesystem.write operation for {device_id}"
        )
    if (
        {"program.execute", "program.interrupt"} & set(allow)
        and "program.read" not in allow
    ):
        raise RuntimeACLConfigError(
            f"devices.{device_id}.allow must include program.read with program execution or interruption"
        )
    return DeviceRule(
        allow=frozenset(allow),
        execution_entrypoints=tuple(sorted(entrypoints)),
        filesystem_write_allow=tuple(write_allow),
        filesystem_write_deny=tuple(write_deny),
    )


def _path_matches(path: str, rule: str) -> bool:
    return path.startswith(rule) if rule.endswith("/") else path == rule


class RuntimeACL:
    def __init__(
        self,
        *,
        devices: dict[str, DeviceRule] | None = None,
        policy_id: str | None = None,
    ):
        self._devices = dict(devices or {})
        self.policy_id = policy_id
        self.configured = policy_id is not None

    @classmethod
    def unconfigured(cls) -> "RuntimeACL":
        return cls()

    @classmethod
    def from_document(cls, document: Any) -> "RuntimeACL":
        if not isinstance(document, dict):
            raise RuntimeACLConfigError("runtime ACL policy must be a JSON object")
        unknown = sorted(set(document) - _TOP_LEVEL_FIELDS)
        if unknown:
            raise RuntimeACLConfigError(
                "runtime ACL policy has unknown fields: " + ", ".join(unknown)
            )
        if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
            raise RuntimeACLConfigError("runtime ACL schema_version must be 1")
        raw_devices = document.get("devices")
        if not isinstance(raw_devices, dict) or not raw_devices:
            raise RuntimeACLConfigError("runtime ACL devices must be a non-empty object")
        if len(raw_devices) > 256:
            raise RuntimeACLConfigError("runtime ACL may define at most 256 device rules")
        normalized_devices: dict[str, dict[str, Any]] = {}
        devices: dict[str, DeviceRule] = {}
        for device_id, raw_rule in raw_devices.items():
            if (
                not isinstance(device_id, str)
                or not device_id
                or device_id != device_id.strip()
                or any(ord(char) < 33 or ord(char) > 126 for char in device_id)
                or len(device_id) > 64
            ):
                raise RuntimeACLConfigError(
                    "runtime ACL device IDs must be 1-64 printable ASCII characters"
                )
            rule = _normalize_rule(raw_rule, device_id)
            devices[device_id] = rule
            normalized_devices[device_id] = {
                "allow": sorted(rule.allow),
                "execution_entrypoints": list(rule.execution_entrypoints),
                "filesystem_write_allow": list(rule.filesystem_write_allow),
                "filesystem_write_deny": list(rule.filesystem_write_deny),
            }
        normalized = {"schema_version": 1, "devices": normalized_devices}
        return cls(
            devices=devices,
            policy_id=hashlib.sha256(_canonical(normalized)).hexdigest(),
        )

    @classmethod
    def from_file(cls, path: Path) -> "RuntimeACL":
        policy_path = Path(path)
        try:
            if policy_path.is_symlink():
                raise RuntimeACLConfigError("runtime ACL policy must not be a symlink")
            descriptor = os.open(
                policy_path,
                os.O_RDONLY
                | os.O_NONBLOCK
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise RuntimeACLConfigError("runtime ACL policy must be a regular file")
                if metadata.st_size > MAX_POLICY_BYTES:
                    raise RuntimeACLConfigError("runtime ACL policy exceeds 64 KiB")
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    data = stream.read(MAX_POLICY_BYTES + 1)
            finally:
                os.close(descriptor)
        except RuntimeACLConfigError:
            raise
        except OSError as error:
            raise RuntimeACLConfigError("runtime ACL policy is unavailable") from error
        if len(data) > MAX_POLICY_BYTES:
            raise RuntimeACLConfigError("runtime ACL policy exceeds 64 KiB")
        try:
            document = json.loads(
                data.decode("utf-8"),
                object_pairs_hook=_unique_object,
            )
        except RuntimeACLConfigError:
            raise
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeACLConfigError("runtime ACL policy is not valid UTF-8 JSON") from error
        return cls.from_document(document)

    @property
    def device_ids(self) -> frozenset[str]:
        return frozenset(self._devices)

    def validate_device_ids(self, known: set[str]) -> None:
        unknown = sorted(
            device_id
            for device_id in self._devices
            if device_id != "*" and device_id not in known
        )
        if unknown:
            raise RuntimeACLConfigError(
                "runtime ACL references unknown devices: " + ", ".join(unknown)
            )

    def rule(self, device_id: str) -> DeviceRule | None:
        return self._devices.get(device_id, self._devices.get("*"))

    def summary(self, device_id: str) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "NOT_CONFIGURED",
                "configured": False,
                "policy_id": None,
                "device_id": device_id,
                "default_effect": "allow",
                "allowed_operations": sorted(OPERATIONS),
                "execution_entrypoints": sorted(EXECUTION_ENTRYPOINTS),
                "filesystem_write_allow": [],
                "filesystem_write_deny": [],
            }
        rule = self.rule(device_id)
        return {
            "status": "ENFORCED",
            "configured": True,
            "policy_id": self.policy_id,
            "device_id": device_id,
            "default_effect": "deny",
            "allowed_operations": sorted(rule.allow) if rule else [],
            "execution_entrypoints": list(rule.execution_entrypoints) if rule else [],
            "filesystem_write_allow": list(rule.filesystem_write_allow) if rule else [],
            "filesystem_write_deny": list(rule.filesystem_write_deny) if rule else [],
        }

    def policy_summary(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "NOT_CONFIGURED",
                "configured": False,
                "policy_id": None,
                "default_effect": "allow",
                "devices": {},
            }
        return {
            "status": "ENFORCED",
            "configured": True,
            "policy_id": self.policy_id,
            "default_effect": "deny",
            "devices": {
                device_id: {
                    "allowed_operations": sorted(rule.allow),
                    "execution_entrypoints": list(rule.execution_entrypoints),
                    "filesystem_write_allow": list(rule.filesystem_write_allow),
                    "filesystem_write_deny": list(rule.filesystem_write_deny),
                }
                for device_id, rule in sorted(self._devices.items())
            },
        }

    def check(
        self,
        device_id: str,
        operation: str,
        *,
        path: str | None = None,
        entrypoint: str | None = None,
    ) -> str | None:
        policy_id = self.allow_operation(device_id, operation)
        if policy_id is None:
            return None
        rule = self.rule(device_id)
        assert rule is not None
        if operation == "program.execute":
            if entrypoint is None:
                raise RuntimeACLError(
                    operation=operation,
                    device_id=device_id,
                    policy_id=self.policy_id,
                    reason="entrypoint_required",
                )
            if entrypoint not in rule.execution_entrypoints:
                raise RuntimeACLError(
                    operation=operation,
                    device_id=device_id,
                    policy_id=self.policy_id,
                    reason="entrypoint_not_allowed",
                    entrypoint=entrypoint,
                )
        if operation == "filesystem.write":
            if not path:
                raise RuntimeACLError(
                    operation=operation,
                    device_id=device_id,
                    policy_id=self.policy_id,
                    reason="path_required",
                )
            if any(_path_matches(path, denied) for denied in rule.filesystem_write_deny):
                raise RuntimeACLError(
                    operation=operation,
                    device_id=device_id,
                    policy_id=self.policy_id,
                    reason="path_denied",
                    path=path,
                )
            if not any(_path_matches(path, allowed) for allowed in rule.filesystem_write_allow):
                raise RuntimeACLError(
                    operation=operation,
                    device_id=device_id,
                    policy_id=self.policy_id,
                    reason="path_not_allowed",
                    path=path,
                )
        return policy_id

    def allow_operation(self, device_id: str, operation: str) -> str | None:
        if operation not in OPERATIONS:
            raise RuntimeACLConfigError(f"unknown runtime ACL operation: {operation}")
        if not self.configured:
            return None
        rule = self.rule(device_id)
        if rule is None:
            raise RuntimeACLError(
                operation=operation,
                device_id=device_id,
                policy_id=self.policy_id,
                reason="device_not_allowed",
            )
        if operation not in rule.allow:
            raise RuntimeACLError(
                operation=operation,
                device_id=device_id,
                policy_id=self.policy_id,
                reason="operation_not_allowed",
            )
        return self.policy_id
