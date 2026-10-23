#!/usr/bin/env python3
"""Run a QEMU session inside a Linux network namespace with no egress route."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import json
import os
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
IFNAMSIZ = 16
IFREQ_SIZE = 40
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18


class SandboxError(RuntimeError):
    pass


def install_controlled_resolv_conf() -> Path:
    try:
        os.unshare(os.CLONE_NEWNS)
    except (AttributeError, OSError) as error:
        raise SandboxError(
            f"controlled DNS requires a private mount namespace: {error}"
        ) from error

    descriptor, raw_path = tempfile.mkstemp(
        prefix="m5-resolv-",
        suffix=".conf",
    )
    path = Path(raw_path)
    try:
        os.write(
            descriptor,
            b"nameserver 127.0.0.1\n"
            b"options timeout:1 attempts:1\n",
        )
    finally:
        os.close(descriptor)

    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    libc.mount.restype = ctypes.c_int
    if libc.mount(
        None,
        b"/",
        None,
        MS_REC | MS_PRIVATE,
        None,
    ) != 0:
        error = ctypes.get_errno()
        path.unlink(missing_ok=True)
        raise SandboxError(
            "cannot make mount namespace private: "
            f"{os.strerror(error)}"
        )
    target = Path("/etc/resolv.conf").resolve()
    if libc.mount(
        str(path).encode(),
        str(target).encode(),
        None,
        MS_BIND,
        None,
    ) != 0:
        error = ctypes.get_errno()
        path.unlink(missing_ok=True)
        raise SandboxError(
            "cannot bind controlled resolv.conf: "
            f"{os.strerror(error)}"
        )
    return path


def bring_loopback_up(interface: str = "lo") -> None:
    encoded = interface.encode("ascii")
    if not encoded or len(encoded) >= IFNAMSIZ:
        raise SandboxError(f"invalid interface name: {interface!r}")
    request = bytearray(IFREQ_SIZE)
    request[: len(encoded)] = encoded
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        response = fcntl.ioctl(sock.fileno(), SIOCGIFFLAGS, bytes(request))
        flags = struct.unpack_from("H", response, IFNAMSIZ)[0]
        struct.pack_into("H", request, IFNAMSIZ, flags | IFF_UP)
        fcntl.ioctl(sock.fileno(), SIOCSIFFLAGS, bytes(request))


def route_table_has_external_route() -> bool:
    path = Path("/proc/net/route")
    if not path.is_file():
        return True
    for line in path.read_text(errors="replace").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        flags = int(fields[3], 16)
        if fields[0] != "lo" and flags & 0x1:
            return True
    ipv6 = Path("/proc/net/ipv6_route")
    if ipv6.is_file():
        for line in ipv6.read_text(errors="replace").splitlines():
            fields = line.split()
            if fields and fields[-1] != "lo":
                return True
    return False


def write_isolation_evidence(
    path: Path,
    config: dict[str, Any] | None = None,
) -> None:
    interfaces = sorted(name for _, name in socket.if_nameindex())
    policy = (config or {}).get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    http = (config or {}).get("http", {})
    if not isinstance(http, dict):
        http = {}
    dns = (config or {}).get("dns", {})
    if not isinstance(dns, dict):
        dns = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": sys.platform,
                "private_network_namespace": True,
                "interfaces": interfaces,
                "external_route": False,
                "egress": policy.get("egress", "deny-all"),
                "dns": policy.get("dns", "deny"),
                "allowed_hosts": policy.get("allowed_hosts", []),
                "tls_gateway": bool(http.get("tls")),
                "controlled_dns": dns.get("mode") == "controlled",
                "dns_records": dns.get("hosts", {}),
            },
            indent=2,
        )
        + "\n"
    )


class ControlledHttp:
    def __init__(
        self,
        *,
        port: int,
        body: bytes,
        log_path: Path | None,
        allowed_hosts: tuple[str, ...] | None = None,
        tls: dict[str, Any] | None = None,
    ):
        self.requests: list[dict[str, str]] = []
        self.lock = threading.Lock()
        self.allowed_hosts = (
            set(allowed_hosts or ())
            if allowed_hosts is not None
            else None
        )
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                host_header = self.headers.get("Host", "")
                host = host_header.rsplit(":", 1)[0].lower()
                allowed = (
                    owner.allowed_hosts is None
                    or host in owner.allowed_hosts
                )
                status = 200 if allowed else 403
                request = {
                    "path": self.path,
                    "host": self.headers.get("Host", ""),
                }
                if owner.allowed_hosts is not None:
                    request.update(
                        {
                            "decision": "allow" if allowed else "deny",
                            "status": str(status),
                        }
                    )
                with owner.lock:
                    owner.requests.append(request)
                    owner.persist()
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                response_body = body if allowed else b"host not allowed\n"
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.log_path = log_path
        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        if tls is not None:
            certfile = tls.get("certfile")
            keyfile = tls.get("keyfile")
            if not isinstance(certfile, str) or not isinstance(keyfile, str):
                raise SandboxError("sandbox TLS certfile/keyfile are required")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile, keyfile)
            self.server.socket = context.wrap_socket(
                self.server.socket,
                server_side=True,
            )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="m5-sandbox-http",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def persist(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.log_path.with_name(
            f".{self.log_path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(self.requests, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(self.log_path)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        with self.lock:
            self.persist()


class ControlledDns:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        records: dict[str, str],
        log_path: Path | None,
    ):
        self.records = {
            name.lower(): address for name, address in records.items()
        }
        self.requests: list[dict[str, str]] = []
        self.lock = threading.Lock()
        self.log_path = log_path
        self.stop_event = threading.Event()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.settimeout(0.2)
        self.thread = threading.Thread(
            target=self.serve,
            name="m5-sandbox-dns",
            daemon=True,
        )

    @staticmethod
    def parse_question(query: bytes) -> tuple[str, int, int] | None:
        if len(query) < 17:
            return None
        offset = 12
        labels: list[str] = []
        while offset < len(query):
            length = query[offset]
            offset += 1
            if length == 0:
                break
            if length & 0xC0 or offset + length > len(query):
                return None
            label = query[offset : offset + length].decode(
                "ascii",
                errors="ignore",
            )
            if not label:
                return None
            labels.append(label)
            offset += length
        else:
            return None
        if not labels or offset + 4 > len(query):
            return None
        qtype, qclass = struct.unpack_from("!HH", query, offset)
        return ".".join(labels).lower(), qtype, offset + 4

    def response(self, query: bytes) -> bytes:
        question = self.parse_question(query)
        if question is None:
            return b""
        name, qtype, question_end = question
        address = self.records.get(name)
        allowed = address is not None
        answer = b""
        if allowed and qtype == 1:
            answer = (
                b"\xc0\x0c"
                + struct.pack("!HHIH", 1, 1, 60, 4)
                + socket.inet_aton(address)
            )
        flags = 0x8180 if allowed else 0x8183
        response = (
            query[:2]
            + struct.pack("!HHHHH", flags, 1, 1 if answer else 0, 0, 0)
            + query[12:question_end]
            + answer
        )
        status = (
            "A"
            if answer
            else "NOERROR_NO_A"
            if allowed
            else "NXDOMAIN"
        )
        with self.lock:
            self.requests.append(
                {
                    "name": name,
                    "qtype": str(qtype),
                    "decision": "allow" if allowed else "deny",
                    "status": status,
                }
            )
            self.persist()
        return response

    def serve(self) -> None:
        while not self.stop_event.is_set():
            try:
                query, peer = self.socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            response = self.response(query)
            if response:
                try:
                    self.socket.sendto(response, peer)
                except OSError:
                    break

    def persist(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.log_path.with_name(
            f".{self.log_path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(self.requests, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(self.log_path)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self.socket.close()
        self.thread.join(timeout=5)
        with self.lock:
            self.persist()


def start_logged_process(
    command: list[str],
    *,
    log_path: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w")
    environment = os.environ.copy()
    environment.update(env_overrides or {})
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    setattr(process, "_m5_log", log)
    return process


def wait_for_text(
    path: Path,
    marker: str,
    *,
    timeout: float,
    process: subprocess.Popen,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and marker in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise SandboxError(
                f"process exited before log marker {marker!r}: "
                f"{process.returncode}"
            )
        time.sleep(0.1)
    raise SandboxError(f"timed out waiting for log marker {marker!r}")


def terminate_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SandboxError(f"invalid sandbox config: {error}") from error
    if not isinstance(value, dict):
        raise SandboxError("sandbox config must be an object")
    return value


def run(config: dict[str, Any], command: list[str]) -> int:
    if sys.platform != "linux":
        raise SandboxError("network namespace isolation requires Linux")
    if not command:
        raise SandboxError("a command is required after --")
    try:
        os.unshare(os.CLONE_NEWNET)
    except (AttributeError, OSError) as error:
        raise SandboxError(f"cannot create network namespace: {error}") from error
    dns_config = config.get("dns")
    resolv_path: Path | None = None
    if dns_config is not None:
        resolv_path = install_controlled_resolv_conf()
    bring_loopback_up()
    if route_table_has_external_route():
        raise SandboxError(
            "network namespace still has an external route; refusing to run"
        )
    evidence_path = config.get("isolation_evidence")
    if evidence_path:
        write_isolation_evidence(Path(str(evidence_path)), config)

    http_config = config.get("http")
    http: ControlledHttp | None = None
    dns: ControlledDns | None = None
    ble_process: subprocess.Popen[str] | None = None
    qemu_process: subprocess.Popen | None = None
    previous: dict[int, Any] = {}
    terminating = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal terminating
        if terminating:
            return
        terminating = True
        terminate_process(qemu_process)
        terminate_process(ble_process)
        raise SystemExit(143)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, stop)
    try:
        if dns_config is not None:
            if not isinstance(dns_config, dict):
                raise SandboxError("sandbox DNS config must be an object")
            records = dns_config.get("hosts")
            if (
                not isinstance(records, dict)
                or not records
                or any(
                    not isinstance(name, str)
                    or not isinstance(address, str)
                    for name, address in records.items()
                )
            ):
                raise SandboxError(
                    "sandbox DNS hosts must be a non-empty string map"
                )
            raw_log = dns_config.get("log")
            dns = ControlledDns(
                host=str(dns_config.get("host", "127.0.0.1")),
                port=int(dns_config.get("port", 53)),
                records=records,
                log_path=Path(str(raw_log)) if raw_log else None,
            )
            dns.start()

        if http_config is not None:
            if not isinstance(http_config, dict):
                raise SandboxError("sandbox http config must be an object")
            port = int(http_config.get("port", 0))
            body = http_config.get("body", "M5_SANDBOX_OK\n")
            if not isinstance(body, str):
                raise SandboxError("sandbox HTTP body must be a string")
            raw_log = http_config.get("log")
            raw_allowed_hosts = http_config.get("allowed_hosts")
            if raw_allowed_hosts is not None and (
                not isinstance(raw_allowed_hosts, list)
                or any(
                    not isinstance(host, str)
                    for host in raw_allowed_hosts
                )
            ):
                raise SandboxError(
                    "sandbox http allowed_hosts must be a string list"
                )
            tls_config = http_config.get("tls")
            if tls_config is not None and not isinstance(tls_config, dict):
                raise SandboxError("sandbox TLS config must be an object")
            http = ControlledHttp(
                port=port,
                body=body.encode(),
                log_path=Path(str(raw_log)) if raw_log else None,
                allowed_hosts=(
                    tuple(raw_allowed_hosts)
                    if raw_allowed_hosts is not None
                    else None
                ),
                tls=tls_config,
            )
            http.start()

        ble_config = config.get("ble_probe")
        if ble_config is not None:
            if not isinstance(ble_config, dict):
                raise SandboxError("sandbox ble_probe config must be an object")
            ble_command = ble_config.get("command")
            ble_log = ble_config.get("log")
            if (
                not isinstance(ble_command, list)
                or not ble_command
                or any(not isinstance(item, str) for item in ble_command)
                or not isinstance(ble_log, str)
            ):
                raise SandboxError("sandbox ble_probe config is invalid")
            ble_env = ble_config.get("env", {})
            if not isinstance(ble_env, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in ble_env.items()
            ):
                raise SandboxError("sandbox ble_probe env is invalid")
            ble_process = start_logged_process(
                ble_command,
                log_path=Path(ble_log),
                env_overrides=ble_env,
            )
            wait_for_text(
                Path(ble_log),
                str(ble_config.get("ready_marker", "BLE_PROBE_READY")),
                timeout=float(ble_config.get("ready_timeout_seconds", 10)),
                process=ble_process,
            )

        qemu_process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return qemu_process.wait()
    finally:
        terminate_process(qemu_process)
        terminate_process(ble_process)
        if ble_process is not None:
            log = getattr(ble_process, "_m5_log", None)
            if log is not None:
                log.close()
        if http is not None:
            http.close()
        if dns is not None:
            dns.close()
        if resolv_path is not None:
            resolv_path.unlink(missing_ok=True)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a QEMU command inside a no-egress network namespace"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    try:
        return run(load_config(args.config), command)
    except (OSError, SandboxError) as error:
        print(f"network sandbox failed: {error}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
