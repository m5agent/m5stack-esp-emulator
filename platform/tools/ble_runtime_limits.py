"""Shared bounds for BLE peer workloads used by the service and runners."""

MAX_BLE_RECONNECT_CYCLES = 121
MAX_BLE_RECONNECT_DELAY_SECONDS = 30
MAX_BLE_HOLD_SECONDS = 7200
MAX_BLE_LINGER_SECONDS = MAX_BLE_HOLD_SECONDS + 60
BLE_PEER_MIN_SCAN_TIMEOUT_SECONDS = 40.0
BLE_PEER_MAX_SCAN_TIMEOUT_SECONDS = 120.0
BLE_PEER_SESSION_TIMEOUT_MARGIN_SECONDS = 10.0
BLE_UNIFIED_WRITE_DELAY_SECONDS = 10.0

# The first 121-cycle attempt completed about one Core2 NUS GATT cycle every
# 6.2 seconds at the previous two-second write delay. The unified peer now
# waits ten seconds before its first write so slower guests finish processing
# CCCD state; reserve sixteen seconds per cycle plus reconnect delay, with a
# fixed startup allowance, so the service and runner share a conservative
# bound.
BLE_RECONNECT_STARTUP_SECONDS = 60.0
BLE_RECONNECT_CYCLE_SECONDS = 16.0


def ble_peer_scan_timeout_seconds(session_ready_timeout: float) -> float:
    """Return a bounded advertisement window derived from session readiness."""
    if (
        isinstance(session_ready_timeout, bool)
        or not isinstance(session_ready_timeout, (int, float))
    ):
        raise TypeError("session ready timeout must be numeric")
    if session_ready_timeout <= 0:
        raise ValueError("session ready timeout must be positive")
    return min(
        BLE_PEER_MAX_SCAN_TIMEOUT_SECONDS,
        max(
            BLE_PEER_MIN_SCAN_TIMEOUT_SECONDS,
            float(session_ready_timeout)
            - BLE_PEER_SESSION_TIMEOUT_MARGIN_SECONDS,
        ),
    )


def reconnect_workload_timeout_seconds(
    cycles: int,
    delay_seconds: float,
) -> float:
    """Return a workload-aware budget for one same-guest reconnect run."""
    if isinstance(cycles, bool) or not isinstance(cycles, int):
        raise TypeError("reconnect cycles must be an integer")
    if cycles < 1 or cycles > MAX_BLE_RECONNECT_CYCLES:
        raise ValueError(
            f"reconnect cycles must be from 1 to {MAX_BLE_RECONNECT_CYCLES}"
        )
    if (
        isinstance(delay_seconds, bool)
        or not isinstance(delay_seconds, (int, float))
    ):
        raise TypeError("reconnect delay must be numeric")
    if not 0 <= delay_seconds <= MAX_BLE_RECONNECT_DELAY_SECONDS:
        raise ValueError(
            "reconnect delay must be from 0 to "
            f"{MAX_BLE_RECONNECT_DELAY_SECONDS}"
        )
    return min(
        float(MAX_BLE_HOLD_SECONDS),
        BLE_RECONNECT_STARTUP_SECONDS
        + cycles * (BLE_RECONNECT_CYCLE_SECONDS + float(delay_seconds)),
    )
