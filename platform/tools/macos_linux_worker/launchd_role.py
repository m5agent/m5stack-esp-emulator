#!/usr/bin/env python3
"""Supervise the separately authorized Linux review role under a macOS LaunchAgent."""

import argparse
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

SERVICE = Path(__file__).resolve().parent
MANIFEST_NAME = "immutable-assets.private.json"
MAX_MANIFEST_BYTES = 512 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
SOURCE_COMMIT = re.compile(r"[0-9a-f]{40}")
ASSET_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+,~@-]*")
HOST_FILES = ("launchd_role.py", "supervisor.py", "stable_bridge.py")
ROLE_FILES = ("vsock-initrd.img", "host-relay.py")
IDENTITY = ("generation", "incarnation", "boot_id", "worker_id", "worker_generation")
RELAY_IMPORT_PROBE = """
import runpy
import sys


def deny_external_io(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("Unexpected external I/O during host relay import")


sys.addaudithook(deny_external_io)
relay = runpy.run_path(sys.argv[1], run_name="m5_host_relay_preflight")
if relay["Endpoints"].__slots__ != ("sntp", "voice"):
    raise RuntimeError("Unexpected host relay endpoint contract")
if not callable(relay["host_sntp"]) or not callable(relay["host_voice"]):
    raise RuntimeError("Host relay callables are absent")
print("M5_HOST_RELAY_IMPORT_OK")
"""


@dataclass(frozen=True)
class Installation:
    device_source: str
    openapi_sha256: str
    relay_python_sha256: str
    kernel_sha256: str
    initrd_sha256: str
    runner_sha256: str


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def open_file(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    return os.fdopen(os.open(path, flags), "rb")


def owned_bytes(path, limit):
    with open_file(path) as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_mode & 0o077 == 0 and info.st_nlink == 1 and info.st_size <= limit,
                "Expected a bounded owner-only file")
        data = stream.read(limit + 1)
    require(len(data) == info.st_size, "Owner-only file changed during read")
    return data


def path_input(value):
    path = Path(value).absolute()
    require(path == path.resolve(strict=True), "Expected an explicit canonical local path")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate key in installation manifest")
        result[key] = value
    return result


def hex_string(value, pattern=HEX_SHA256):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def asset_name(name):
    parts = name.split("/")
    for part in parts:
        lower = part.lower()
        require(ASSET_PART.fullmatch(part)
                and lower not in {"control-token", "secrets", "credentials", "id_rsa", "id_ed25519"}
                and not lower.endswith((".key", ".pem", ".p12", ".pfx", ".env")),
                "Invalid or sensitive installation asset path")
    return Path(*parts)


def asset_kind(path):
    info = path.lstat()
    require(info.st_uid == os.getuid() and info.st_mode & 0o7022 == 0,
            "Installation assets must be owned and protected from modification by other users")
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Installation assets must be regular files")
    return "file"


def asset_tree(package, directory, *, excluded=()):
    require(asset_kind(directory) == "directory", "Installation asset directory is invalid")
    files = set()
    for path in directory.iterdir():
        if path in excluded:
            continue
        if asset_kind(path) == "directory":
            files.update(asset_tree(package, path))
        else:
            files.add(path.relative_to(package).as_posix())
    return files


def verify_asset(path, expected):
    require(isinstance(expected, dict) and set(expected) == {"size", "sha256", "mode"}
            and type(expected["size"]) is int and expected["size"] >= 0 and hex_string(expected["sha256"])
            and isinstance(expected["mode"], str) and re.fullmatch(r"0o[0-7]{1,3}", expected["mode"]),
            "Installation asset metadata is invalid")
    require(path == path.resolve(strict=True) and asset_kind(path) == "file",
            "Installation asset must be a canonical regular file")
    with open_file(path) as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and info.st_size == expected["size"] and oct(stat.S_IMODE(info.st_mode)) == expected["mode"]
                and info.st_mode & 0o7022 == 0,
                "Installation asset metadata differs from the manifest")
        checksum = sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(chunk)
        require(checksum.hexdigest() == expected["sha256"], "Installation asset digest differs from the manifest")


def check_manifest(root, pinned, runner, expected_manifest_sha):
    """Validate the fully populated package against its out-of-package digest."""
    package = root.parent
    require(asset_kind(package) == "directory" and package.stat().st_mode & 0o077 == 0,
            "Installation package must be owner-only")
    require(SERVICE == package / "controller" and pinned == package / "pinned"
            and runner == package / "bin/vz-managed-runner" and root.name not in {"bin", "controller", "pinned"},
            "Controller, runtime assets and role must share the same package")
    require(asset_kind(SERVICE) == "directory" and asset_kind(runner.parent) == "directory",
            "Installation source directories are invalid")
    data = owned_bytes(package / MANIFEST_NAME, MAX_MANIFEST_BYTES)
    require(hex_string(expected_manifest_sha) and sha256(data).hexdigest() == expected_manifest_sha,
            "Installation manifest digest differs from the configured pin")
    inventory = json.loads(data, object_pairs_hook=unique_object)
    require(isinstance(inventory, dict) and set(inventory) == {
                "schema_version", "files", "device_source", "device_openapi_sha256", "relay_python_sha256"
            } and type(inventory["schema_version"]) is int and inventory["schema_version"] == 2
            and hex_string(inventory["device_source"], SOURCE_COMMIT)
            and hex_string(inventory["device_openapi_sha256"]) and hex_string(inventory["relay_python_sha256"])
            and isinstance(inventory["files"], dict) and len(inventory["files"]) <= 2048,
            "Installation manifest schema is invalid")
    scenarios = root / "scenarios"
    for path in (root, scenarios, scenarios / "controller", root / "results"):
        require(asset_kind(path) == "directory" and path.stat().st_mode & 0o077 == 0,
                "Role and lifecycle directories must be owner-only")
    files = inventory["files"]
    required = {f"controller/{name}" for name in HOST_FILES}
    required.update(f"{root.name}/{name}" for name in ROLE_FILES)
    required.update(("bin/vz-managed-runner", "pinned/cloud-kernel", "pinned/readonly-share/trixie-rootfs.tar.gz",
                     f"{root.name}/scenarios/guest.py", f"{root.name}/scenarios/guest-action.sh"))
    required.update(asset_tree(package, pinned))
    required.update(asset_tree(package, scenarios, excluded=(scenarios / "control-token", scenarios / "controller")))
    require(set(files) == required, "Installation manifest does not exactly cover its immutable inputs")
    require(not os.path.lexists(SERVICE / "__pycache__"), "Controller may only import measured source")
    for name, expected in files.items():
        verify_asset(package / asset_name(name), expected)
    return Installation(inventory["device_source"], inventory["device_openapi_sha256"], inventory["relay_python_sha256"],
                        files["pinned/cloud-kernel"]["sha256"], files[f"{root.name}/vsock-initrd.img"]["sha256"],
                        files["bin/vz-managed-runner"]["sha256"])


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=path_input)
    parser.add_argument("--pinned", required=True, type=path_input)
    parser.add_argument("--runner", required=True, type=path_input)
    parser.add_argument("--relay-python", required=True, type=path_input)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--asset-manifest-sha256", required=True)
    parser.add_argument("--check-layout", action="store_true")
    return parser.parse_args()


# On the executable path, measure all package source before importing its
# lifecycle helpers. The caller supplies the manifest digest independently.
if __name__ == "__main__":
    sys.dont_write_bytecode = True
    os.umask(0o077)
    cli_arguments = arguments()
    cli_installation = check_manifest(cli_arguments.root, cli_arguments.pinned, cli_arguments.runner,
                                      cli_arguments.asset_manifest_sha256)

if __package__:
    from .supervisor import ManagedRole, pinned_bytes, private_dir, publish, read_json
    from .stable_bridge import RESERVED_PORTS
else:
    from supervisor import ManagedRole, pinned_bytes, private_dir, publish, read_json
    from stable_bridge import RESERVED_PORTS


def probe_relay_import(root, executable):
    return subprocess.run(
        [str(executable), "-I", "-S", "-B", "-c", RELAY_IMPORT_PROBE, str(root / "host-relay.py")],
        env={"PATH": "/usr/bin:/bin", "LANG": "C"}, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8,
    )


def check_relay_python(root, executable, relay_python_sha256):
    info = executable.lstat()
    require(info.st_uid == os.getuid() and info.st_mode & 0o022 == 0 and os.access(executable, os.X_OK),
            "Expected an owned executable host relay interpreter")
    pinned_bytes(executable, relay_python_sha256)
    result = probe_relay_import(root, executable)
    require(result.returncode == 0 and result.stdout == b"M5_HOST_RELAY_IMPORT_OK\n" and not result.stderr,
            "Pinned host relay interpreter failed the isolated import preflight")


def matched_stop(root, endpoint, openapi_sha256):
    """Admit prior bytes only with an actual VZ stop and durable Device close."""
    generation = endpoint["generation"]
    common = {"schema_version": 1, **{k: endpoint[k] for k in IDENTITY}}
    markers = root / "results/.supervisor"
    ready = read_json(markers / f"ready-{generation}.json")
    stopped = read_json(markers / f"stopped-{generation}.json")
    require(type(generation) is int and generation > 0
            and ready == {**common, "openapi_sha256": openapi_sha256}
            and stopped == {**common, "clean": True, "active_leases": 0, "service_exited": True}
            and stopped["clean"] is True and stopped["service_exited"] is True
            and type(stopped["active_leases"]) is int,
            "Durable shutdown markers do not match the exact role")
    intent = read_json(root / f"scenarios/controller/shutdown-{generation}.json")
    require(intent == {"schema_version": 1, "verb": "shutdown", **{
        key: endpoint[key] for key in ("generation", "incarnation", "boot_id")
    }}, "Persistent shutdown intent or generation differs")
    events = owned_bytes(root / f"runner-{generation}.private.log", 8192).decode("utf-8").splitlines()
    incarnation = endpoint["incarnation"]
    require([row for row in events if row.startswith("M5VZ_EVENT ")] == [
        f"M5VZ_EVENT started {incarnation}", f"M5VZ_EVENT guest-stopped {incarnation}",
    ], "Owned Apple VZ normal shutdown never returned its exact callback")
    worker = read_json(root / "results/worker/worker.json")
    require(worker["worker_id"] == endpoint["worker_id"] and worker["generation"] == endpoint["worker_generation"]
            and worker["state"] == "stopped" and worker["active_leases"] == {},
            "Durable Device Service never reached its exact stopped and empty state")


def check_incumbent(root, installation):
    """Read existing ownership before any launch or port binding."""
    previous = read_json(root / "endpoint.private.json", missing=True)
    if previous is None:
        require(read_json(root / "controller-owner.private.json", missing=True) is None
                and not any((root / "results").iterdir()), "Existing state has no safe lifecycle origin")
        return
    phase = previous.get("phase")
    require(phase in {"idle", "stopped"} and previous.get("ready") is False
            and previous.get("transport_socket") is None and previous.get("runner_pid") is None,
            "Previous controller execution is unresolved or quarantined")
    owner = read_json(root / "controller-owner.private.json")
    require(owner == {
        "schema_version": 1, "root": list(private_dir(root)), "volume": list(private_dir(root / "results")),
        "reports": list(private_dir(root / "results/.supervisor")), "openapi_sha256": installation.openapi_sha256,
        "kernel_sha256": installation.kernel_sha256, "initrd_sha256": installation.initrd_sha256,
        "runner_sha256": installation.runner_sha256,
    }, "Previously authorized durable role inodes or platform source differ")
    if phase == "stopped":
        matched_stop(root, previous, installation.openapi_sha256)
    else:
        require(previous["generation"] == 0 and not any((root / "results/.supervisor").iterdir())
                and set(p.name for p in (root / "results").iterdir()) == {".supervisor"},
                "An idle role may not contain any unresolved worker state")


class AuthenticatedWorker:
    def __init__(self, port, token, openapi_sha256):
        self.port, self.token = port, token
        self.openapi_sha256 = openapi_sha256

    def get(self, name, authorized, limit):
        headers = {"Connection": "close"}
        if authorized:
            headers["Authorization"] = "Bearer " + self.token
        with closing(HTTPConnection("127.0.0.1", self.port, timeout=4)) as link:
            link.request("GET", "/api/v1/" + name, headers=headers)
            with closing(link.getresponse()) as response:
                data = response.read(limit + 1)
                require(len(data) <= limit, "Managed worker response exceeded its budget")
                return response.status, data

    def read(self, expected, *, startup=False):
        if startup:
            code, _ = self.get("worker", False, 65536)
            require(code == 401, "Private Linux gate did not challenge unauthenticated readback")
        code, payload = self.get("worker", True, 65536)
        require(code == 200, "Could not authenticate the current Linux worker")
        row = json.loads(payload)
        require(isinstance(row, dict) and row.get("platform") == "linux" and row.get("stale") is False
                and row.get("session_create_recovery") == "review-v1"
                and row.get("worker_id") == expected["worker_id"] and row.get("generation") == expected["worker_generation"]
                and type(row.get("active_lease_count")) is int and row["active_lease_count"] >= 0,
                "Authenticated peer does not match the selected Linux worker incarnation")
        if startup:
            code, schema = self.get("openapi.yaml", True, 1024 * 1024)
            require(row.get("accepting_leases") is True and code == 200 and sha256(schema).hexdigest() == self.openapi_sha256,
                    "Linux worker is not healthy on the exact admitted API")
        return row


def begin_draining(role, worker):
    # Keep already in-flight work reachable. The guest closes admission as
    # soon as it reads its immutable, generation-scoped shutdown intent.
    role._anchor_current()
    row = worker.read(role.endpoint)
    require(role.process.poll() is None and role.endpoint.get("phase") == "running",
            "Current VZ generation ceased to own the worker")
    role._intent("shutdown", role.endpoint["boot_id"])
    return row["active_lease_count"]


def complete_draining(role):
    role._anchor_current()
    require(role.process.poll() == 0 and role._has_event("guest-stopped"),
            "The exact VZ child did not report normal operating-system shutdown")
    matched_stop(role.root, role.endpoint, role.openapi)
    role._retire_transport()
    role._set(phase="stopped", ready=False, transport_socket=None, runner_pid=None)


class Report:
    def __init__(self, root, installation):
        self.path = root / "launchd-status.private.json"
        self.installation = installation

    def phase(self, phase, role, *, leases=None):
        summary = {"schema_version": 1, "phase": phase, "ready": phase == "running",
                   "device_source": self.installation.device_source,
                   "device_openapi_sha256": self.installation.openapi_sha256,
                   "controller_generation": role.endpoint["generation"], "active_leases_at_signal": leases}
        publish(self.path, summary)
        print(json.dumps(summary, sort_keys=True), flush=True)


def wait_for_owned_listener(bridge, log):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and bridge.poll() is None:
        if b"M5_MANAGED_LOOPBACK_BRIDGE_LISTENING\n" in owned_bytes(log, 8192):
            return
        time.sleep(.08)
    raise RuntimeError("Owned fixed loopback bridge did not acquire its listener")


def wait_startup_auth(bridge, role, worker):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and bridge.poll() is None and role.process.poll() is None:
        try:
            worker.read(role.endpoint, startup=True)
            return
        except (OSError, HTTPException):
            time.sleep(.2)
    raise RuntimeError("No authenticated Linux readiness through the owned fixed bridge")


def supervise(role, worker, bridge, report, stop):
    draining = False
    waiting_auth = False
    while role.process.poll() is None:
        require(bridge.poll() is None, "Owned fixed ingress exited during the role lifetime")
        if stop.is_set() and not draining:
            try:
                leases = begin_draining(role, worker)
            except (OSError, HTTPException, ValueError, RuntimeError):
                # A transport, credential or identity failure supplies no
                # idle evidence. Keep the lease owner and current route alive.
                if not waiting_auth:
                    report.phase("waiting_for_authenticated_stop", role)
                    waiting_auth = True
            else:
                draining = True
                report.phase("draining", role, leases=leases)
        time.sleep(.25)
    require(draining, "The VZ child exited outside an authorized stop transaction")
    complete_draining(role)
    report.phase("stopped", role)


def run(root, pinned, runner, port, token, relay_python, installation):
    stop = threading.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        signal.signal(event, lambda *_: stop.set())
    report = Report(root, installation)
    role = ManagedRole(root, pinned, runner, installation.openapi_sha256, python=str(relay_python),
                       kernel_sha256=installation.kernel_sha256, initrd_sha256=installation.initrd_sha256,
                       runner_sha256=installation.runner_sha256)
    bridge = None
    stage = "verify_incumbent"
    try:
        # Recheck after acquiring the inherited durable-volume flock.
        check_incumbent(root, installation)
        stage = "claim_fixed_ingress"
        log = root / f"launchd-bridge-{uuid.uuid4().hex}.private.log"
        with log.open("xb") as stream:
            bridge = subprocess.Popen(
                ["/usr/bin/python3", "-B", str(SERVICE / "stable_bridge.py"), str(root), str(port)],
                cwd=SERVICE, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
            )
        wait_for_owned_listener(bridge, log)
        if stop.is_set():
            report.phase("stopped_before_boot", role)
            return
        stage = "start_linux_worker"
        report.phase("starting", role)
        role.start()
        stage = "authenticate_linux_worker"
        worker = AuthenticatedWorker(port, token, installation.openapi_sha256)
        wait_startup_auth(bridge, role, worker)
        stage = "supervise_or_drain"
        report.phase("running", role)
        supervise(role, worker, bridge, report, stop)
    except (OSError, HTTPException, ValueError, RuntimeError) as error:
        print(json.dumps({"event": "managed_role_stage_failed", "stage": stage,
                          "error_type": type(error).__name__,
                          "bridge_alive": bridge is not None and bridge.poll() is None,
                          "worker_child_alive": role.process is not None and role.process.poll() is None},
                         sort_keys=True), file=sys.stderr, flush=True)
        if role.process is None:
            raise
        # Neither a failed readiness test nor an unexpected process exit
        # authorizes a new VM or a cold recovery receipt.
        role._anchor_current()
        role._set(phase="uncertain", ready=False, transport_socket=None)
        report.phase("quarantined", role)
        if role.process.poll() is None:
            # Retain supervisor and child ownership when acknowledgement
            # remains unresolved. This entrypoint never sends a force signal.
            role.process.wait()
        raise
    finally:
        if bridge is not None and bridge.poll() is None:
            bridge.terminate()
            bridge.wait(timeout=8)
        if role.process is None or role.process.poll() is not None:
            role.close()


def main(args, installation):
    require(1024 < args.port <= 65535 and args.port not in RESERVED_PORTS,
            "Expected one dedicated non-reserved loopback port")
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(args.runner)], check=True)
    token = owned_bytes(args.root / "scenarios/control-token", 128).strip().decode("ascii")
    require(re.fullmatch(r"[0-9a-f]{64}", token), "Invalid managed Device token file")
    check_relay_python(args.root, args.relay_python, installation.relay_python_sha256)
    check_incumbent(args.root, installation)
    if args.check_layout:
        print(json.dumps({"status": "SOURCE_AND_DURABLE_LAYOUT_OK", "device_source": installation.device_source,
                          "device_openapi_sha256": installation.openapi_sha256,
                          "relay_python_sha256": installation.relay_python_sha256,
                          "relay_import": "PASS", "launch_actions": False}, sort_keys=True))
        return
    run(args.root, args.pinned, args.runner, args.port, token, args.relay_python, installation)


if __name__ == "__main__":
    main(cli_arguments, cli_installation)
