"""Read Linux process identity and stop an owned namespace supervisor."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import select
import signal
import stat

from device_service_errors import ServiceError


_BOOT_ID = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_BOOT_ID_TEXT = re.compile(_BOOT_ID.pattern.decode("ascii"))
_LAUNCH_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COLD_RECEIPT_MAX_BYTES = 64 * 1024
_PYTHON = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)?)?d?")
GATEWAY_HANDOFF_LOCK = "gateway-handoff.lock"
_GATEWAY_GUARD_MARKER = b"m5-gateway-handoff-v1\n"
_GATEWAY_GUARD_FLAGS = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class GatewayColdRecoveryConfigError(ValueError):
    """The operator's trusted cold-recovery input is unusable."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GatewayColdRecoveryConfigError("duplicate field in gateway cold recovery receipt")
        result[key] = value
    return result


def _matches(pattern, value) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


@dataclass(frozen=True)
class GatewayColdRecoveryReceipt:
    worker_id: str
    previous_boot_id: str
    successor_boot_id: str
    launches: dict[str, tuple[str, str]]
    sha256: str

    @classmethod
    def from_file(cls, path: Path, state_dir: Path) -> GatewayColdRecoveryReceipt:
        """Read one startup authority supplied outside the restored worker volume."""
        path = Path(path)
        try:
            if not path.is_absolute() or path.resolve(strict=True).is_relative_to(state_dir.resolve()):
                raise GatewayColdRecoveryConfigError("gateway cold recovery receipt must be absolute and outside worker state")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            with os.fdopen(os.open(path, flags), "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_nlink != 1
                        or not 0 < info.st_size <= _COLD_RECEIPT_MAX_BYTES):
                    raise GatewayColdRecoveryConfigError("gateway cold recovery receipt must be a bounded, protected regular file")
                raw = stream.read(_COLD_RECEIPT_MAX_BYTES + 1)
                if len(raw) != info.st_size:
                    raise GatewayColdRecoveryConfigError("gateway cold recovery receipt changed during read")
            value = json.loads(raw, object_pairs_hook=_unique_object)
        except GatewayColdRecoveryConfigError:
            raise
        except (OSError, ValueError, RuntimeError) as error:
            raise GatewayColdRecoveryConfigError("cannot read gateway cold recovery receipt") from error

        fields = {"schema_version", "worker_id", "previous_boot_id", "successor_boot_id", "launches"}
        if (not isinstance(value, dict) or set(value) != fields
                or type(value["schema_version"]) is not int or value["schema_version"] != 1):
            raise GatewayColdRecoveryConfigError("invalid gateway cold recovery receipt schema")
        worker_id = value["worker_id"]
        previous_boot = value["previous_boot_id"]
        successor_boot = value["successor_boot_id"]
        entries = value["launches"]
        if (not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 128
                or any(ord(char) < 32 for char in worker_id)
                or not _matches(_BOOT_ID_TEXT, previous_boot) or not _matches(_BOOT_ID_TEXT, successor_boot)
                or previous_boot == successor_boot or not isinstance(entries, list) or not 1 <= len(entries) <= 128):
            raise GatewayColdRecoveryConfigError("invalid gateway cold recovery receipt scope")

        launches = {}
        launch_ids = set()
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) != {"session_id", "launch_id", "gateway_receipt_sha256"}
                    or not _matches(_LAUNCH_ID, entry["session_id"]) or not _matches(_LAUNCH_ID, entry["launch_id"])
                    or not _matches(_SHA256, entry["gateway_receipt_sha256"])
                    or entry["session_id"] in launches or entry["launch_id"] in launch_ids):
                raise GatewayColdRecoveryConfigError("invalid or duplicate gateway cold recovery launch")
            launches[entry["session_id"]] = (entry["launch_id"], entry["gateway_receipt_sha256"])
            launch_ids.add(entry["launch_id"])
        return cls(worker_id, previous_boot, successor_boot, launches, sha256(raw).hexdigest())

    def match(self, *, worker_id: str, session_worker_id: str | None, session_id: str,
              successor_boot_id: str, journal: dict) -> str | None:
        """Match the stopped gateway journal, never a PID in the successor kernel."""
        scope = journal.get("worker_scope")
        if (worker_id != self.worker_id or session_worker_id != self.worker_id
                or successor_boot_id != self.successor_boot_id or not isinstance(scope, dict)
                or scope.get("boot_id") != self.previous_boot_id or journal.get("schema_version") != 3
                or journal.get("handoff_committed") is not True):
            return None
        old_boot_prefix = f"linux:{self.previous_boot_id}:"
        outer_pid, inner_pid = journal.get("supervisor_pid"), journal.get("handoff_inner_pid")
        if (type(outer_pid) is not int or outer_pid < 1 or type(inner_pid) is not int or inner_pid < 1
                or inner_pid == outer_pid or any(
                    not isinstance(value, str) or not value.startswith(old_boot_prefix)
                    for value in (journal.get("supervisor_start_token"), journal.get("handoff_inner_start_token"))
                )):
            return None
        encoded = json.dumps(journal, sort_keys=True, separators=(",", ":")).encode()
        digest = sha256(encoded).hexdigest()
        return digest if self.launches.get(session_id) == (journal.get("launch_id"), digest) else None


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
