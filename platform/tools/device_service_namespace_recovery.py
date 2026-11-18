"""Read Linux process identity and stop an owned namespace supervisor."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import re
import select
import signal

from device_service_errors import ServiceError


_BOOT_ID = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_PYTHON = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)?)?d?")


def _pending(message: str) -> ServiceError:
    return ServiceError("session_cleanup_pending", message, 503)


def namespace_supervisor_identity(pid: int, *, proc_root: Path = Path("/proc")) -> str | None:
    """Return this Linux boot and process start tick, or None for a dead process."""
    if type(pid) is not int or pid <= 0:
        raise _pending("namespace supervisor PID is invalid")
    try:
        boot_id = (proc_root / "sys/kernel/random/boot_id").read_bytes().strip()
        try:
            stat = (proc_root / str(pid) / "stat").read_bytes()
        except FileNotFoundError:
            return None
    except OSError as error:
        raise _pending("cannot read namespace supervisor process identity") from error

    before, boundary, fields = stat.rpartition(b") ")
    values = fields.split()
    # Field 3 is the state and field 22 is the start time in clock ticks.
    # The process name in parentheses can itself contain spaces and parentheses.
    if (not _BOOT_ID.fullmatch(boot_id) or not boundary
            or not before.startswith(f"{pid} (".encode()) or len(values) < 20
            or len(values[0]) != 1 or not values[19].isdigit()):
        raise _pending("namespace supervisor process identity is malformed")
    if values[0] in (b"Z", b"X", b"x"):
        return None
    return f"linux:{boot_id.decode()}:{int(values[19])}"


def stop_namespace_supervisor(
    pid: int,
    *,
    start_token: str | None,
    config_path: Path,
    sandbox_path: Path,
    legacy_start_token: Callable[[int], str | None] | None = None,
    timeout: float = 20.0,
    proc_root: Path = Path("/proc"),
) -> None:
    """Wait for this exact supervisor to exit. The caller verifies its cleanup receipt."""
    if type(pid) is not int or pid <= 0 or not isinstance(start_token, str) or not start_token:
        raise _pending("namespace supervisor has no saved process identity")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise _pending("namespace supervisor cooperative stop requires Linux pidfd support")
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    except OSError as error:
        raise _pending("cannot acquire namespace supervisor process handle") from error

    try:
        poller = select.poll()
        poller.register(fd, select.POLLIN)

        def exited(wait_ms: int) -> bool:
            return any(event & (select.POLLIN | select.POLLHUP) for _, event in poller.poll(wait_ms))

        if exited(0):
            return
        identity = namespace_supervisor_identity(pid, proc_root=proc_root)
        if identity is None:
            if exited(0):
                return
            raise _pending("namespace supervisor process identity is unreadable")
        observed_token = identity
        if not start_token.startswith("linux:") and legacy_start_token is not None:
            observed_token = legacy_start_token(pid)
        if observed_token != start_token:
            raise _pending("namespace supervisor start identity changed")

        try:
            arguments = (proc_root / str(pid) / "cmdline").read_bytes().split(b"\0")
        except FileNotFoundError:
            if exited(0):
                return
            raise
        executable = Path(os.fsdecode(arguments[0]))
        if (not executable.is_absolute() or not _PYTHON.fullmatch(executable.name)
                or arguments[1:5] != [os.fsencode(sandbox_path), b"--config", os.fsencode(config_path), b"--"]
                or len(arguments) < 6 or not arguments[5]):
            raise _pending("namespace supervisor command does not match the saved launch")
        if exited(0):
            return
        if namespace_supervisor_identity(pid, proc_root=proc_root) != identity:
            if exited(0):
                return
            raise _pending("namespace supervisor process identity changed during verification")

        try:
            signal.pidfd_send_signal(fd, signal.SIGTERM)
        except ProcessLookupError:
            return
        if not exited(max(0, min(20_000, int(timeout * 1000)))):
            raise _pending("namespace supervisor did not finish cooperative stop")
    except OSError as error:
        raise _pending("cannot verify or stop the namespace supervisor") from error
    finally:
        os.close(fd)
