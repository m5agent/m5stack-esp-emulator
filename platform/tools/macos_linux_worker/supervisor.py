"""Single-owner lifecycle for the private, no-NIC Linux VZ role.

The supervisor does not listen on TCP or authorize namespace recovery. A
separate owned bridge reads the current endpoint file. Unknown termination is
persistent quarantine and cannot become a clean restart by retrying.
"""
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid

ROOT_FLOOR = 4 << 30
START_RESERVE = 180 << 20
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def pinned_bytes(path, expected):
    require(path.is_file() and not path.is_symlink(), "Pinned local asset is absent or not regular")
    with path.open("rb") as stream:
        checksum = sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(block)
    require(checksum.hexdigest() == expected, "Pinned local asset digest differs")


def private_dir(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
            "Expected owner-only local directory")
    return (info.st_dev, info.st_ino)


def read_json(path, *, missing=False):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if missing:
            return None
        raise
    with os.fdopen(descriptor, "rb") as data:
        info = os.fstat(data.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0
                and info.st_size <= 8192, "Private JSON must be a bounded owner-only regular file")
        payload = data.read(8193)
        require(len(payload) <= 8192, "Private JSON grew past its read budget")
        result = json.loads(payload)
    require(type(result) is dict, "Private JSON must have an object at its root")
    return result


def publish(path, data):
    require(not path.is_symlink(), "Lifecycle destination must not be a symlink")
    directory = path.parent
    # The temporary name is never opened by the consumer.
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=directory)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write((json.dumps(data, sort_keys=True) + "\n").encode())
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ManagedRole:
    """A single host process supervises owned child generations over an inode fence."""

    def __init__(self, root, pinned, runner, openapi_sha256, *, python,
                 kernel_sha256, initrd_sha256, runner_sha256):
        self.root = Path(root).absolute()
        self.pinned = Path(pinned).absolute()
        self.runner = Path(runner).absolute()
        require(self.root == self.root.resolve(strict=True), "Lifecycle root is not canonical")
        require(all(isinstance(value, str) and HEX_SHA256.fullmatch(value)
                    for value in (openapi_sha256, kernel_sha256, initrd_sha256, runner_sha256)),
                "Expected exact Device OpenAPI and runtime asset digests")
        self.openapi = openapi_sha256
        self.python = Path(python).resolve(strict=True)
        self.kernel_sha = kernel_sha256
        self.initrd_sha = initrd_sha256
        self.runner_sha = runner_sha256
        self.endpoint_path = self.root / "endpoint.private.json"
        self.volume_path = self.root / "results"
        self.command = self.root / "scenarios/controller/lifecycle-command.json"
        self.report_dir = self.volume_path / ".supervisor"
        root_inode, volume_inode = private_dir(self.root), private_dir(self.volume_path)
        for path in (self.command.parent.parent, self.command.parent):
            private_dir(path)
        fd = os.open(self.volume_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            require((opened.st_dev, opened.st_ino) == volume_inode, "Persistent volume changed before fencing")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            anchor_path = self.root / "controller-owner.private.json"
            previous = read_json(anchor_path, missing=True)
            endpoint = read_json(self.endpoint_path, missing=True)
            if previous is None:
                require(endpoint is None and not any(self.volume_path.iterdir()),
                        "A new controller can own only a new empty volume")
                self.report_dir.mkdir(mode=0o700)
            anchor = {"schema_version": 1, "root": list(root_inode), "volume": list(volume_inode),
                      "reports": list(private_dir(self.report_dir)), "openapi_sha256": self.openapi,
                      "kernel_sha256": self.kernel_sha, "initrd_sha256": self.initrd_sha,
                      "runner_sha256": self.runner_sha}
            if previous is None:
                publish(anchor_path, anchor)
            else:
                require(previous == anchor and endpoint is not None, "Volume anchor or old generation differs")
                require(endpoint.get("phase") in {"idle", "stopped"},
                        "Previous VZ termination is unconfirmed or quarantined")
            self.fd = fd
            self.anchor = anchor
            self.process = None
            self.sockdir = None
            self.endpoint = endpoint
            if endpoint is None:
                self.endpoint = {
                    "schema_version": 1, "phase": "idle", "ready": False, "generation": 0,
                    "incarnation": None, "transport_socket": None, "boot_id": None, "worker_id": None,
                    "worker_generation": None, "supervisor_pid": os.getpid(), "runner_pid": None,
                }
                publish(self.endpoint_path, self.endpoint)
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        require(self.process is None or self.process.poll() is not None,
                "A running VZ process still owns the persistent volume")
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _anchor_current(self):
        require(list(private_dir(self.root)) == self.anchor["root"] and
                list(private_dir(self.volume_path)) == self.anchor["volume"],
                "Persistent volume or lifecycle root was replaced")
        require(read_json(self.endpoint_path) == self.endpoint, "Lifecycle endpoint was replaced")

    def _set(self, **fields):
        self.endpoint = dict(self.endpoint, **fields)
        publish(self.endpoint_path, self.endpoint)

    def _intent(self, verb, boot=None):
        generation = self.endpoint["generation"]
        path = self.command if verb == "run" else self.command.with_name(f"shutdown-{generation}.json")
        if verb == "shutdown":
            require(read_json(path, missing=True) is None, "Shutdown intent is immutable for one generation")
        publish(path, {
            "schema_version": 1, "generation": generation,
            "incarnation": self.endpoint["incarnation"], "verb": verb, "boot_id": boot,
        })

    def _guest(self, kind):
        require(list(private_dir(self.report_dir)) == self.anchor["reports"], "Guest receipt directory was replaced")
        return read_json(self.report_dir / f"{kind}-{self.endpoint['generation']}.json", missing=True)

    def _match_identity(self, receipt):
        current = self.endpoint
        require(receipt.get("schema_version") == 1 and
                type(receipt.get("generation")) is int and receipt["generation"] == current["generation"] and
                receipt.get("incarnation") == current["incarnation"] and
                isinstance(receipt.get("boot_id"), str) and UUID.fullmatch(receipt["boot_id"]) and
                isinstance(receipt.get("worker_id"), str) and 0 < len(receipt["worker_id"]) <= 128 and
                type(receipt.get("worker_generation")) is int and receipt["worker_generation"] > 0,
                "Guest lifecycle identity does not bind the exact runner generation")

    def _events(self):
        if not self.log.exists():
            return []
        with self.log.open("rb") as stream:
            data = stream.read(8193)
        require(len(data) <= 8192, "Runner event log exceeded its budget")
        lines = data.decode("utf-8").splitlines()
        return [line for line in lines if line.startswith("M5VZ_EVENT ")]

    def _has_event(self, name):
        return f"M5VZ_EVENT {name} {self.endpoint['incarnation']}" in self._events()

    def _guest_action_exited(self):
        console = self.root / f"serial-{self.endpoint['incarnation']}.private.log"
        try:
            handle = os.open(console, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            return False
        with os.fdopen(handle, "rb") as stream:
            details = os.fstat(stream.fileno())
            require(stat.S_ISREG(details.st_mode) and details.st_uid == os.getuid(),
                    "Runner console is not an owned regular file")
            stream.seek(max(0, details.st_size - 8192))
            return re.search(rb"(?m)^M5VZ_GUEST_EXIT [0-9]+\r?$", stream.read(8192)) is not None

    def _wait(self, predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if result := predicate():
                return result
            time.sleep(.1)
        raise TimeoutError("Owned lifecycle stage exceeded its deadline")

    def _retire_transport(self):
        if self.sockdir is not None:
            require(not (self.sockdir / "d").exists(), "Private runner transport remains open")
            self.sockdir.rmdir()
            self.sockdir = None

    def start(self, timeout=115):
        self._anchor_current()
        before = self.endpoint
        require(before["phase"] in {"idle", "stopped"} and self.fd is not None
                and (self.process is None or self.process.poll() is not None),
                "Lifecycle is not eligible for normal boot")
        require(shutil.disk_usage(self.root).free >= ROOT_FLOOR + START_RESERVE,
                "Host free space is below the existing VZ launch guard")
        pinned_bytes(self.pinned / "cloud-kernel", self.kernel_sha)
        pinned_bytes(self.root / "vsock-initrd.img", self.initrd_sha)
        pinned_bytes(self.runner, self.runner_sha)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(self.runner)], check=True)
        self.sockdir = Path(tempfile.mkdtemp(prefix="m5vz-", dir="/private/tmp"))
        generation = before["generation"] + 1
        incarnation = str(uuid.uuid4())
        self._set(phase="starting", ready=False, generation=generation, incarnation=incarnation,
                  transport_socket=None, boot_id=None, worker_id=None, worker_generation=None,
                  supervisor_pid=os.getpid(), runner_pid=None)
        try:
            require(self._guest("ready") is None and self._guest("stopped") is None,
                    "A future generation receipt already exists")
            self._intent("run")
            self.log = self.root / f"runner-{generation}.private.log"
            with self.log.open("xb") as output:
                self.process = subprocess.Popen(
                    [str(self.runner), str(self.root), str(self.pinned), str(self.python),
                     str(self.sockdir), incarnation, str(self.fd)],
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    cwd=self.root, pass_fds=(self.fd,), start_new_session=True,
                )
            self._set(runner_pid=self.process.pid)

            def ready():
                require(self.process.poll() is None, "VZ exited before guest readiness")
                require(not self._guest_action_exited(), "Linux guest action exited before role readiness")
                row = self._guest("ready")
                if row is None or not self._has_event("started"):
                    return None
                self._match_identity(row)
                require(set(row) == {"schema_version", "generation", "incarnation", "boot_id",
                                     "worker_id", "worker_generation", "openapi_sha256"}
                        and row["openapi_sha256"] == self.openapi, "Guest readiness or OpenAPI bound scope differs")
                return row

            guest = self._wait(ready, timeout)
            if generation > 1:
                require(guest["boot_id"] != before["boot_id"] and guest["worker_id"] == before["worker_id"]
                        and guest["worker_generation"] > before["worker_generation"],
                        "Restart did not prove fresh boot and stable higher-generation worker")
            endpoint = self.sockdir / "d"
            info = endpoint.lstat()
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600,
                    "Per-generation stream is not an owner-only Unix socket")
            private_dir(self.sockdir)
            self._set(phase="running", ready=True, transport_socket=str(endpoint), boot_id=guest["boot_id"],
                      worker_id=guest["worker_id"], worker_generation=guest["worker_generation"])
        except BaseException:
            self._set(phase="uncertain", ready=False, transport_socket=None)
            raise
        return self.endpoint.copy()

    def stop(self, timeout=65):
        self._anchor_current()
        require(self.endpoint["phase"] == "running" and self.process is not None and self.process.poll() is None,
                "No running owned VZ generation is eligible for graceful stop")
        self._set(phase="stopping", ready=False, transport_socket=None)
        try:
            self._intent("shutdown", self.endpoint["boot_id"])

            def exited():
                if self.process.poll() is not None:
                    return True
                require(not self._guest_action_exited(), "Linux guest action exited before graceful stop")
                return False

            self._wait(exited, timeout)
            require(self.process.returncode == 0 and self._has_event("guest-stopped")
                    and not self._has_event("forced-stop-ack"), "Graceful stop requires the Apple VZ guest-stop callback")
            stopped = self._guest("stopped")
            require(stopped is not None, "Guest stopped without a clean worker shutdown marker")
            self._match_identity(stopped)
            require(set(stopped) == {"schema_version", "generation", "incarnation", "boot_id", "worker_id",
                                         "worker_generation", "clean", "active_leases", "service_exited"} and
                    all(stopped[k] == self.endpoint[k] for k in ("boot_id", "worker_id", "worker_generation")) and
                    stopped["clean"] is True and stopped["service_exited"] is True
                    and type(stopped["active_leases"]) is int and stopped["active_leases"] == 0,
                    "Guest clean shutdown marker is incomplete or not for this generation")
            self._retire_transport()
            self._set(phase="stopped", runner_pid=None)
        except BaseException:
            self._set(phase="uncertain", ready=False, transport_socket=None)
            raise
        return self.endpoint.copy()

    def abort(self, timeout=12):
        """Explicitly stop an owned child. Never authorize ordinary restart or a recovery receipt."""
        self._anchor_current()
        require(self.process is not None and self.process.poll() is None,
                "No owned active VZ child to force-stop")
        self._set(phase="uncertain", ready=False, transport_socket=None)
        self.process.send_signal(signal.SIGUSR1)
        code = self.process.wait(timeout=timeout)
        require(code == 70 and self._has_event("forced-stop-ack"),
                "Forced VZ stop was not acknowledged by the owning runner")
        self._retire_transport()
        self._set(phase="quarantined", runner_pid=None)
        return self.endpoint.copy()
