#!/usr/bin/env python3
"""Stage and operate an isolated macOS-hosted Linux review worker."""

import argparse
from contextlib import closing
import ctypes
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time


SOURCE = Path(__file__).resolve().parent
ASSETS = "immutable-assets.private.json"
RECEIPT = "install-receipt.private.json"
CONTROLLER_FILES = ("launchd_role.py", "supervisor.py", "stable_bridge.py")
REQUIRED_PAYLOAD = {"pinned/cloud-kernel", "pinned/readonly-share/trixie-rootfs.tar.gz",
                    "scenario/vsock-initrd.img", "scenario/host-relay.py",
                    "scenario/scenarios/guest.py", "scenario/scenarios/guest-action.sh"}
SCENARIO_FILES = {"guest.py", "review_route.py", "guest-action.sh", "dictproof.py", "pilot.py",
                  "topology.py", "guest-relay.py", "scope_c9.py", "trusted.py", "fixed_egress.py",
                  "run-mode", "device-source-1993.tar.gz", "device-source-1993.sha256",
                  "linux-runtime.sha256", "egress.private.json", "adv-sd.seed.img", "original-adv.bin"}
RESERVED_PORTS = {8787, 8790, 8830, 18853}
MANIFEST_LIMIT = 512 << 10
HOST_FLOOR = (4 << 30) + (180 << 20)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        checksum = sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def is_hash(value, size=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None


def unique_fields(items):
    result = dict(items)
    require(len(result) == len(items), "Duplicate JSON field")
    return result


def canonical(value, *, exists=True):
    path = Path(value).expanduser().absolute()
    require(path == path.resolve(strict=exists), "Expected an explicit local path without symlinks")
    return path


def owned_file(path):
    require(path.resolve(strict=True) == path, "Asset path includes a symlink")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
            "Expected an owned regular file without group or other write permissions")
    return info


def inspect_file(path):
    info = owned_file(path)
    return {"size": info.st_size, "mode": oct(stat.S_IMODE(info.st_mode)), "sha256": digest(path)}


def payload_name(name):
    if not isinstance(name, str) or len(name) > 240:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or not all(
            re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9+_.~%,-]*", part) for part in path.parts):
        return False
    parts = path.parts
    return (name in {"pinned/cloud-kernel", "scenario/vsock-initrd.img", "scenario/host-relay.py"}
            or len(parts) >= 3 and parts[:2] == ("pinned", "readonly-share")
            or len(parts) == 3 and parts[:2] == ("scenario", "scenarios") and parts[2] in SCENARIO_FILES
            or len(parts) >= 4 and parts[:3] == ("scenario", "scenarios", "service")
            and "__pycache__" not in parts and path.suffix in {".py", ".md", ".sh", ".yml", ".html", ".css", ".png"})


def validate_payload(value):
    require(type(value) is dict and set(value) == {"schema_version", "files", "device_source", "device_openapi_sha256"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and is_hash(value["device_source"], 40) and is_hash(value["device_openapi_sha256"]),
            "Invalid payload manifest schema or source identity")
    files = value["files"]
    require(type(files) is dict and REQUIRED_PAYLOAD <= files.keys() and len(files) <= 2048,
            "Payload manifest is missing required inputs or exceeds the inventory limit")
    for name, item in files.items():
        require(payload_name(name), "Invalid or mutable payload path")
        require(type(item) is dict and set(item) == {"size", "mode", "sha256"}
                and type(item["size"]) is int and item["size"] >= 0 and is_hash(item["sha256"])
                and isinstance(item["mode"], str) and re.fullmatch(r"0o[0-7]{3}", item["mode"])
                and not int(item["mode"], 8) & 0o022, "Invalid payload file metadata")
    return value


def read_payload(path, expected_sha256):
    info = owned_file(path)
    require(is_hash(expected_sha256) and 0 < info.st_size <= MANIFEST_LIMIT,
            "Invalid payload manifest pin or size")
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == expected_sha256, "Payload manifest SHA-256 differs")
    return validate_payload(json.loads(raw, object_pairs_hook=unique_fields))


def save(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(data, output, sort_keys=True, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def build_manifest(args):
    pinned = canonical(args.pinned)
    scenario = canonical(args.scenario)
    inputs = {"pinned/cloud-kernel": pinned / "cloud-kernel",
              "scenario/vsock-initrd.img": scenario / "vsock-initrd.img",
              "scenario/host-relay.py": scenario / "host-relay.py"}
    share = pinned / "readonly-share"
    require(share.is_dir() and share.resolve(strict=True) == share, "Expected an owned read-only share tree")
    for path in sorted(share.rglob("*")):
        require(not path.is_symlink(), "Read-only share contains a symlink")
        if not path.is_dir():
            inputs["pinned/" + path.relative_to(pinned).as_posix()] = path
    for name in sorted(SCENARIO_FILES):
        path = scenario / "scenarios" / name
        if path.exists():
            inputs["scenario/" + path.relative_to(scenario).as_posix()] = path
    service = scenario / "scenarios/service"
    require(service.is_dir() and service.resolve(strict=True) == service, "Missing qualified guest review helpers")
    for path in sorted(service.rglob("*")):
        key = "scenario/" + path.relative_to(scenario).as_posix()
        require(not path.is_symlink(), "Guest review helper tree contains a symlink")
        if not path.is_dir() and payload_name(key):
            inputs[key] = path
    manifest = validate_payload({"schema_version": 1, "device_source": args.device_source,
                                 "device_openapi_sha256": args.device_openapi_sha256,
                                 "files": {name: inspect_file(path) for name, path in inputs.items()}})
    output = canonical(args.output, exists=False)
    save(output, manifest)
    return {"status": "payload_sealed", "payload_files": len(inputs), "sha256": digest(output)}


def copy_asset(source, target, expected):
    require(inspect_file(source) == expected, "Payload size, SHA-256 or file mode differs")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    clonefile = getattr(ctypes.CDLL(None, use_errno=True), "clonefile", None)
    if clonefile is not None:
        clonefile.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
        clonefile.restype = ctypes.c_int
    if clonefile is None or clonefile(os.fsencode(source), os.fsencode(target), 0):
        with source.open("rb") as original, target.open("xb") as destination:
            shutil.copyfileobj(original, destination)
    target.chmod(int(expected["mode"], 8))
    require(inspect_file(target) == expected, "Staged asset differs from the sealed bytes")


def launch_environment():
    return {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}


def check_layout(plist_path):
    definition = plistlib.loads(plist_path.read_bytes())
    result = subprocess.run(definition["ProgramArguments"] + ["--check-layout"],
                            check=True, capture_output=True, text=True, timeout=45, env=launch_environment())
    status = json.loads(result.stdout)
    require(status["status"] == "SOURCE_AND_DURABLE_LAYOUT_OK", "Controller did not confirm the layout")
    return status


def label_for(package, instance):
    suffix = sha256(os.fsencode(package)).hexdigest()[:12]
    return f"dev.m5stack.emulator.review-worker-linux.{instance}.{suffix}"


def stage(args):
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.instance), "Invalid instance label")
    require(1024 < args.port <= 65535 and args.port not in RESERVED_PORTS, "Expected a dedicated non-reserved port")
    package = canonical(args.package, exists=False)
    require(not package.exists() and package.parent.is_dir(), "Installation must use a new package directory")
    require(shutil.disk_usage(package.parent).free >= HOST_FLOOR, "Available storage is below the worker setup reserve")
    scenario, pinned = canonical(args.scenario), canonical(args.pinned)
    payload = read_payload(canonical(args.payload_manifest), args.payload_manifest_sha256)
    runner, relay = canonical(args.runner), canonical(args.relay_python)
    runner_info, relay_info = inspect_file(runner), inspect_file(relay)
    require(is_hash(args.runner_sha256) and runner_info["sha256"] == args.runner_sha256
            and is_hash(args.relay_python_sha256) and relay_info["sha256"] == args.relay_python_sha256
            and os.access(runner, os.X_OK) and os.access(relay, os.X_OK), "Runner or relay interpreter does not match its executable pin")
    package.mkdir(mode=0o700)
    owned_inode = package.stat().st_ino
    try:
        root = package / args.instance
        for directory in (root, root / "scenarios", root / "scenarios/controller", root / "results"):
            directory.mkdir(mode=0o700)
        installed = {"bin/vz-managed-runner": (runner, runner_info)}
        for name, expected in payload["files"].items():
            source_kind, relative = name.split("/", 1)
            if source_kind == "pinned":
                installed[name] = (pinned / relative, expected)
            else:
                installed[f"{args.instance}/{relative}"] = (scenario / relative, expected)
        for name in CONTROLLER_FILES:
            source = SOURCE / name
            installed[f"controller/{name}"] = (source, inspect_file(source))
        for name, (source, expected) in installed.items():
            copy_asset(source, package / name, expected)
        inventory = {"schema_version": 2, "device_source": payload["device_source"],
                     "device_openapi_sha256": payload["device_openapi_sha256"], "relay_python_sha256": args.relay_python_sha256,
                     "files": {name: expected for name, (_, expected) in installed.items()}}
        save(package / ASSETS, inventory)
        inventory_sha = digest(package / ASSETS)
        token = root / "scenarios/control-token"
        with token.open("x") as output:
            output.write(secrets.token_hex(32) + "\n")
        token.chmod(0o600)
        label = label_for(package, args.instance)
        plist_path = package / f"{label}.plist"
        config = {"Label": label, "ProgramArguments": ["/usr/bin/python3", "-B",
                  str(package / "controller/launchd_role.py"), "--root", str(root), "--pinned", str(package / "pinned"),
                  "--runner", str(package / "bin/vz-managed-runner"), "--relay-python", str(relay),
                  "--port", str(args.port), "--asset-manifest-sha256", inventory_sha],
                  "WorkingDirectory": str(package / "controller"), "EnvironmentVariables": launch_environment(),
                  "RunAtLoad": False, "KeepAlive": False, "ProcessType": "Background", "ExitTimeOut": 120,
                  "Umask": 0o077, "StandardOutPath": str(root / "controller-stdout.private.log"),
                  "StandardErrorPath": str(root / "controller-stderr.private.log")}
        with plist_path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            plistlib.dump(config, stream)
        check_layout(plist_path)
        receipt = {"schema_version": 1, "instance": args.instance, "port": args.port,
                   "asset_manifest_sha256": inventory_sha, "plist_sha256": digest(plist_path),
                   "payload_sha256": args.payload_manifest_sha256, "device_openapi_sha256": payload["device_openapi_sha256"]}
        save(package / RECEIPT, receipt)
    except BaseException:
        if not package.is_symlink() and package.stat().st_ino == owned_inode:
            shutil.rmtree(package)
        raise
    return {"status": "staged", "instance": args.instance, "asset_manifest_sha256": inventory_sha,
            "device_openapi_sha256": inventory["device_openapi_sha256"]}


def launchctl(*args, check=True):
    return subprocess.run(["/bin/launchctl", *args], check=check, capture_output=True, text=True, timeout=12)


def load_installation(package):
    receipt_path = package / RECEIPT
    info = owned_file(receipt_path)
    require(info.st_size <= 8192 and not info.st_mode & 0o077, "Invalid installed receipt permissions or size")
    receipt = json.loads(receipt_path.read_bytes(), object_pairs_hook=unique_fields)
    instance, port = receipt["instance"], receipt["port"]
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", instance) and type(port) is int
            and 1024 < port <= 65535 and port not in RESERVED_PORTS, "Invalid installed instance identity")
    label = label_for(package, instance)
    plist = package / f"{label}.plist"
    owned_file(plist)
    owned_file(package / ASSETS)
    require(digest(plist) == receipt["plist_sha256"] and digest(package / ASSETS) == receipt["asset_manifest_sha256"],
            "Installed launch definition or its asset manifest differs from staging")
    return receipt, package / instance, label, plist


def worker_ready(root, expected_openapi, port):
    endpoint = root / "endpoint.private.json"
    try:
        identity = json.loads(endpoint.read_bytes())
        if identity["phase"] != "running" or identity["ready"] is not True:
            return False
        headers = {"Authorization": "Bearer " + (root / "scenarios/control-token").read_text().strip()}
        checks = {}
        for name in ("worker", "openapi.yaml"):
            with closing(HTTPConnection("127.0.0.1", port, timeout=2)) as connection:
                connection.request("GET", "/api/v1/" + name, headers=headers)
                with closing(connection.getresponse()) as response:
                    if response.status != 200:
                        return False
                    checks[name] = response.read(1 << 20)
        worker = json.loads(checks["worker"])
        return (sha256(checks["openapi.yaml"]).hexdigest() == expected_openapi
                and worker["platform"] == "linux" and worker["worker_id"] == identity["worker_id"]
                and worker["generation"] == identity["worker_generation"] and worker["accepting_leases"] is True
                and worker["stale"] is False and worker["session_create_recovery"] == "review-v1")
    except (HTTPException, OSError, ValueError, KeyError, TypeError):
        return False


def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Match the bridge's bind semantics so a closed TCP connection in
        # TIME_WAIT does not block an otherwise idle port.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))


def control(args):
    receipt, root, label, plist = load_installation(canonical(args.package))
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{label}"
    registered = launchctl("print", service, check=False)
    loaded = registered.returncode == 0
    if loaded:
        require(f"path = {plist}" in (line.strip() for line in registered.stdout.splitlines()),
                "Registered launch definition does not match the staged package")
    report_path = root / "launchd-status.private.json"
    report = json.loads(report_path.read_bytes()) if report_path.exists() else {}
    if args.action == "check":
        check_layout(plist)
        return {"status": "layout_ready"}
    if args.action == "status":
        phase = report.get("phase", "staged")
        if phase == "stopped" and loaded and "state = not running" not in registered.stdout:
            phase = "draining"
        return {"status": phase, "loaded": loaded,
                "worker_ready": phase == "running" and loaded
                and worker_ready(root, receipt["device_openapi_sha256"], receipt["port"])}
    if args.action == "start":
        require(not loaded and shutil.disk_usage(root).free >= HOST_FLOOR, "Worker already registered or disk reserve too low")
        check_layout(plist)
        check_port(receipt["port"])
        launchctl("bootstrap", domain, str(plist))
        launchctl("kickstart", service)
        deadline = time.monotonic() + 130
        while time.monotonic() < deadline:
            status = json.loads(report_path.read_bytes()) if report_path.exists() else {}
            if status.get("phase") == "quarantined":
                raise RuntimeError("Worker entered quarantine during startup")
            if status.get("phase") == "running" and worker_ready(root, receipt["device_openapi_sha256"], receipt["port"]):
                return {"status": "running", "worker_ready": True}
            time.sleep(0.3)
        raise RuntimeError("Worker readiness timed out. Inspect the existing job before any retry.")
    require(loaded, "Worker is not registered in the current user domain")
    if args.action == "drain":
        require(report.get("phase") in {"running", "draining", "waiting_for_authenticated_stop"}, "Worker is not in a drainable phase")
        launchctl("kill", "SIGTERM", service)
        return {"status": "drain_requested"}
    require(report.get("phase", "staged") in {"staged", "stopped", "quarantined"}
            and "state = not running" in registered.stdout,
            "Unload requires a stopped or quarantined controller process")
    launchctl("bootout", service)
    return {"status": "unloaded", "volume_phase": report.get("phase", "staged")}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help="seal owner-supplied qualified guest inputs")
    for flag in ("pinned", "scenario", "output", "device-source", "device-openapi-sha256"):
        manifest.add_argument("--" + flag, required=True)
    install = commands.add_parser("stage", help="install one worker without starting it")
    for flag in ("package", "instance", "pinned", "scenario", "payload-manifest", "payload-manifest-sha256",
                 "runner", "runner-sha256", "relay-python", "relay-python-sha256"):
        install.add_argument("--" + flag, required=True)
    install.add_argument("--port", type=int, required=True)
    operate = commands.add_parser("control", help="operate only this worker's recorded launch definition")
    operate.add_argument("--package", required=True)
    operate.add_argument("action", choices=("check", "start", "status", "drain", "unload"))
    args = parser.parse_args()
    try:
        result = {"manifest": build_manifest, "stage": stage, "control": control}[args.command](args)
    except (KeyError, ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
