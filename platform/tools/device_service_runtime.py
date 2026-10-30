"""Pure Device Service runtime parameter and redaction helpers."""
from __future__ import annotations

from typing import Any


PRIVATE_RUNTIME_ENV = frozenset({
    "M5SW_ESPNOW_PEER_LMK",
    "M5SW_ESPNOW_PEER_PUBLIC_MAC",
    "M5SW_ESPNOW_PEER_PMK",
})

_CORE2_NATIVE_CONTROLLER_PROFILES = frozenset({
    "core2-native-vhci",
    "core2-native-hci",
})


def redacted_runtime_env(
    runtime_env: dict[str, str] | None,
) -> dict[str, str]:
    return {
        key: "<redacted>" if key in PRIVATE_RUNTIME_ENV else value
        for key, value in (runtime_env or {}).items()
    }


def qemu_runtime_memory(
    memory: str | None,
    profile: str | None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Describe the QEMU PSRAM selection without claiming physical timing."""
    requested: int | None
    try:
        requested = int(memory) if memory is not None else None
    except (TypeError, ValueError):
        requested = None
    native_controller = profile in _CORE2_NATIVE_CONTROLLER_PROFILES
    cli_requested = 0 if native_controller else requested
    effective = cli_requested
    effective_source = "qemu-cli-request"
    if native_controller and device_id == "core2":
        effective = 8
        effective_source = "validated-m5core2-qom"
    if native_controller:
        policy = "native-controller-machine-default-psram"
    elif effective == 0:
        policy = "qemu-no-psram"
    elif effective is not None:
        policy = "qemu-emulated-psram"
    else:
        policy = "not-configured"
    return {
        "requested_psram_mib": requested,
        "cli_requested_psram_mib": cli_requested,
        "effective_psram_mib": effective,
        "effective_source": effective_source,
        "policy": policy,
        "claim": "qemu-memory-configuration-only",
        "physical_cache_psram_timing": "NOT RUN",
    }


def runtime_psram_mismatch(
    memory: str | None,
    profile: str | None,
    required_bytes: object,
    device_id: str | None = None,
) -> dict[str, Any] | None:
    """Return a structured preflight issue for an undersized QEMU lane."""
    if not isinstance(required_bytes, int) or required_bytes <= 0:
        return None
    runtime_memory = qemu_runtime_memory(memory, profile, device_id)
    effective_mib = runtime_memory["effective_psram_mib"]
    if not isinstance(effective_mib, int):
        return None
    available_bytes = effective_mib << 20
    if required_bytes <= available_bytes:
        return None
    return {
        "code": "runtime_psram_mismatch",
        "message": (
            f"firmware declares {required_bytes} bytes of PSRAM; "
            f"runtime profile provides {available_bytes}"
        ),
        "requirement": required_bytes,
        "available": available_bytes,
        "path": "target.psram_size",
        "runtime_profile": profile,
        "memory_policy": runtime_memory["policy"],
    }
