"""Read Linux process identity and stop an owned namespace supervisor."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import select
import signal
import stat

from device_service_errors import ServiceError


_BOOT_ID = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_PYTHON = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)?)?d?")
GATEWAY_HANDOFF_LOCK = "gateway-handoff.lock"
_GATEWAY_GUARD_MARKER = b"m5-gateway-handoff-v1\n"
_GATEWAY_GUARD_FLAGS = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _pending(message: str) -> ServiceError:
    return ServiceError("session_cleanup_pending", message, 503)


def verify_inherited_gateway_handoff_guard(fd: int, path: Path, expected_identity: object) -> None:
    """Validate an owned guard descriptor without operating on its shared lock."""
    if (type(fd) is not int or fd < 0 or not isinstance(expected_identity, list)
            or len(expected_identity) != 2 or any(type(value) is not int or value <= 0 for value in expected_identity)):
        raise _pending("gateway handoff guard identity is invalid")
    try:
        opened = os.fstat(fd)
        bound = path.lstat()
        if ([opened.st_dev, opened.st_ino] != expected_identity
                or [bound.st_dev, bound.st_ino] != expected_identity
                or not stat.S_ISREG(opened.st_mode) or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_uid != os.geteuid() or opened.st_nlink != 1):
            raise _pending("gateway handoff guard no longer matches its owned file")
        marker = os.pread(fd, len(_GATEWAY_GUARD_MARKER) + 1, 0)
        if marker != _GATEWAY_GUARD_MARKER:
            raise _pending("gateway handoff guard is truncated or malformed")
    except OSError as error:
        raise _pending("cannot verify gateway handoff guard") from error


def open_gateway_handoff_guard(path: Path) -> tuple[int, list[int]]:
    """Create and lock this launch's private guard before any child is started."""
    try:
        fd = os.open(path, _GATEWAY_GUARD_FLAGS | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fchmod(fd, 0o600)
            if os.write(fd, _GATEWAY_GUARD_MARKER) != len(_GATEWAY_GUARD_MARKER):
                raise _pending("could not initialize gateway handoff guard")
            os.fsync(fd)
            identity = os.fstat(fd)
            owned = [identity.st_dev, identity.st_ino]
            verify_inherited_gateway_handoff_guard(fd, path, owned)
            return fd, owned
        except BaseException:
            os.close(fd)
            raise
    except OSError as error:
        raise _pending("cannot create private gateway handoff guard") from error


@contextmanager
def claim_drained_gateway_handoff(path: Path, expected_identity: object):
    """Hold an independent exclusive lock after all launch descriptors close."""
    fd = None
    try:
        try:
            fd = os.open(path, _GATEWAY_GUARD_FLAGS)
            verify_inherited_gateway_handoff_guard(fd, path, expected_identity)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            verify_inherited_gateway_handoff_guard(fd, path, expected_identity)
        except OSError as error:
            raise _pending("gateway handoff has not drained") from error
        yield
    finally:
        if fd is not None:
            os.close(fd)


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


def namespace_runtime_scope(*, proc_root: Path = Path("/proc")) -> dict:
    """Identify the kernel and the worker context that originally owned a gateway."""
    try:
        boot_id = (proc_root / "sys/kernel/random/boot_id").read_bytes().strip()
        if not _BOOT_ID.fullmatch(boot_id):
            raise _pending("gateway boot identity is malformed")
        scope = {"boot_id": boot_id.decode()}
        for name in ("net", "mnt", "pid"):
            identity = (proc_root / "self" / "ns" / name).stat()
            scope[name] = [identity.st_dev, identity.st_ino]
        return scope
    except OSError as error:
        raise _pending("cannot verify the original gateway worker context") from error


def stop_namespace_supervisor(
    pid: int,
    *,
    start_token: str | None,
    config_path: Path,
    sandbox_path: Path,
    legacy_start_token: Callable[[int], str | None] | None = None,
    inner_namespace: tuple[int, int] | None = None,
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
        command_prefix = [os.fsencode(sandbox_path)]
        if inner_namespace is not None:
            command_prefix.append(b"--inner")
        command_prefix.extend([b"--config", os.fsencode(config_path), b"--"])
        command_end = len(command_prefix) + 1
        if (not executable.is_absolute() or not _PYTHON.fullmatch(executable.name)
                or arguments[1:command_end] != command_prefix
                or len(arguments) <= command_end or not arguments[command_end]):
            raise _pending("namespace supervisor command does not match the saved launch")
        if inner_namespace is not None:
            try:
                identity_stat = (proc_root / str(pid) / "ns" / "net").stat()
            except FileNotFoundError:
                if exited(0):
                    return
                raise
            if (identity_stat.st_dev, identity_stat.st_ino) != inner_namespace:
                raise _pending("inner supervisor left the original network namespace")
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
