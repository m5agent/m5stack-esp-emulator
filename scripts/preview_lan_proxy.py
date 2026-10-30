#!/usr/bin/env python3
"""Temporary, bounded LAN TCP bridge to the existing loopback Device Service.

This relays opaque bytes and preserves the service's authentication. It is not
a second Device Service, a TLS terminator, or an untrusted-firmware sandbox.
Use manage-preview-lan.sh for lifecycle commands; no request data is logged.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import ProxyHandler, build_opener
import uuid


UPSTREAM = ("127.0.0.1", 8787)
RFC1918 = tuple(ipaddress.ip_network(value) for value in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
SCRIPT = Path(__file__).resolve()
BUFFER_LIMIT = 65536
MAX_CONNECTIONS = 64
IDLE_SECONDS = 30
LIFETIME_SECONDS = 300


def private_ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise ValueError("bind must be one explicit RFC1918 IPv4 address") from error
    if not any(address in network for network in RFC1918):
        raise ValueError("bind must be one explicit RFC1918 IPv4 address")
    return str(address)


def log(message: str) -> None:
    print(datetime.now(timezone.utc).isoformat() + " " + message, flush=True)


def relay(left: socket.socket, right: socket.socket, stopping: threading.Event,
          *, idle_seconds=IDLE_SECONDS, lifetime_seconds=LIFETIME_SECONDS) -> None:
    """Bound both directional buffers; propagate EOF after queued bytes drain."""
    sockets = (left, right)
    peer = {left: right, right: left}
    pending = {left: bytearray(), right: bytearray()}
    eof = {left: False, right: False}
    write_closed = {left: False, right: False}
    started = last_activity = time.monotonic()
    try:
        for stream in sockets:
            stream.setblocking(False)
        with selectors.DefaultSelector() as selector:
            while not stopping.is_set():
                now = time.monotonic()
                if now - last_activity >= idle_seconds or now - started >= lifetime_seconds:
                    break
                if all(eof.values()) and not any(pending.values()):
                    break
                for stream in sockets:
                    if eof[peer[stream]] and not pending[stream] and not write_closed[stream]:
                        try:
                            stream.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                        write_closed[stream] = True
                    events = 0
                    if not eof[stream] and len(pending[peer[stream]]) < BUFFER_LIMIT:
                        events |= selectors.EVENT_READ
                    if pending[stream] and not write_closed[stream]:
                        events |= selectors.EVENT_WRITE
                    try:
                        selector.unregister(stream)
                    except KeyError:
                        pass
                    if events:
                        selector.register(stream, events)
                for key, events in selector.select(min(0.25, idle_seconds, lifetime_seconds)):
                    stream = key.fileobj
                    if events & selectors.EVENT_READ:
                        remaining = BUFFER_LIMIT - len(pending[peer[stream]])
                        try:
                            data = stream.recv(min(16384, remaining))
                        except BlockingIOError:
                            data = None
                        if data:
                            pending[peer[stream]].extend(data)
                            last_activity = time.monotonic()
                        elif data == b"":
                            eof[stream] = True
                    if events & selectors.EVENT_WRITE and pending[stream]:
                        try:
                            sent = stream.send(pending[stream])
                        except BlockingIOError:
                            sent = 0
                        if sent:
                            del pending[stream][:sent]
                            last_activity = time.monotonic()
    except OSError:
        # Deliberately omit exception text, remote addresses and request bytes.
        pass
    finally:
        for stream in sockets:
            stream.close()


def atomic_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("state must not be a symbolic link")
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def lock_file(path: Path, *, nonblocking=False):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        yield stream


def process_info(pid: int) -> tuple[str, str] | None:
    if type(pid) is not int or pid <= 1:
        return None
    try:
        started = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                                 capture_output=True, text=True, check=True).stdout.strip()
        command = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return (started, command) if started and command else None


def read_state(directory: Path) -> dict | None:
    path = directory / "state.json"
    if path.is_symlink():
        raise ValueError("state must not be a symbolic link")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid bridge state")
    return value


def owns_process(state: dict | None) -> bool:
    if not state or state.get("script") != str(SCRIPT):
        return False
    instance = state.get("instance")
    if not isinstance(instance, str) or len(instance) != 32:
        return False
    try:
        int(instance, 16)
    except ValueError:
        return False
    info = process_info(state.get("pid"))
    return bool(info and info[0] == state.get("process_started")
                and str(SCRIPT) in info[1]
                and f"--instance {instance}" in info[1]
                and " serve " in info[1])


def health(state: dict) -> bool:
    try:
        host = private_ipv4(state["bind"])
        port = state["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            return False
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"http://{host}:{port}/api/v1/health", timeout=3) as response:
            value = json.loads(response.read(65537))
            return response.status == 200 and value.get("ok") is True and value.get("service") == "m5stack-device-service"
    except (OSError, ValueError, KeyError):
        return False


def serve(args) -> int:
    host = private_ipv4(args.bind)
    stopping = threading.Event()
    threads: set[threading.Thread] = set()
    connections: set[socket.socket] = set()
    guard = threading.Lock()
    permits = threading.BoundedSemaphore(MAX_CONNECTIONS)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda _signum, _frame: stopping.set())
    with lock_file(args.state_dir / "service.lock", nonblocking=True):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((host, args.port))  # OS also verifies this is a local address.
            listener.listen(16)
            listener.settimeout(0.5)
            info = process_info(os.getpid())
            if info is None:
                raise ValueError("cannot record bridge process identity")
            atomic_json(args.state_dir / "state.json", {
                "pid": os.getpid(), "process_started": info[0], "instance": args.instance,
                "script": str(SCRIPT), "bind": host, "port": args.port,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "upstream": "127.0.0.1:8787",
            })
            log(f"bridge listening on {host}:{args.port}; fixed loopback upstream; request logging disabled")

            def connection(client):
                upstream = None
                try:
                    upstream = socket.create_connection(UPSTREAM, timeout=3)
                    with guard:
                        connections.add(upstream)
                    relay(client, upstream, stopping)
                except OSError:
                    client.close()
                    if upstream is not None:
                        upstream.close()
                finally:
                    with guard:
                        connections.discard(client)
                        connections.discard(upstream)
                        threads.discard(threading.current_thread())
                    permits.release()

            while not stopping.is_set():
                try:
                    client, _address = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not permits.acquire(blocking=False):
                    client.close()
                    continue
                thread = threading.Thread(target=connection, args=(client,), daemon=True)
                with guard:
                    connections.add(client)
                    threads.add(thread)
                thread.start()
        # Interrupt active relays so shutdown has a bounded duration.
        with guard:
            streams, workers = list(connections), list(threads)
        for stream in streams:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = time.monotonic() + 5
        for thread in workers:
            thread.join(max(0, deadline - time.monotonic()))
        log("bridge stopped; upstream service and virtual sessions unchanged")
    return 0


def default_host() -> str:
    value = os.environ.get("PREVIEW_LAN_HOST", "")
    if not value:
        try:
            value = subprocess.run(["/usr/sbin/ipconfig", "getifaddr", "en0"],
                                   capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("set PREVIEW_LAN_HOST to this machine's RFC1918 IPv4 address") from error
    return private_ipv4(value)


def manage(args) -> int:
    if args.command == "logs":
        path = args.state_dir / "bridge.log"
        if path.is_file():
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                stream.seek(max(0, stream.tell() - 65536))
                print(stream.read().decode("utf-8", errors="replace"), end="")
        return 0
    with lock_file(args.state_dir / "manager.lock"):
        state = read_state(args.state_dir)
        owned = owns_process(state)
        if args.command == "status":
            healthy = owned and health(state)
            print(json.dumps({"running": owned, "healthy": healthy,
                              "pid": state.get("pid") if owned else None,
                              "url": f"http://{state['bind']}:{state['port']}" if owned else None}))
            return 0 if healthy else 1
        if args.command == "stop":
            if not owned:
                print("No owned bridge is running; no process was signalled.")
                return 0
            os.kill(state["pid"], signal.SIGTERM)
            deadline = time.monotonic() + 10
            while owns_process(state) and time.monotonic() < deadline:
                time.sleep(0.1)
            if owns_process(state):
                print("Owned bridge has not stopped; no other process was signalled.")
                return 1
            print("Owned bridge stopped; Device Service was not signalled.")
            return 0
        if owned:
            if not health(state):
                raise ValueError("owned bridge is running but LAN health failed; inspect logs")
            print(f"Bridge already healthy: http://{state['bind']}:{state['port']} (pid {state['pid']})")
            return 0
        host = private_ipv4(args.bind) if args.bind else default_host()
        port = args.port
        instance = uuid.uuid4().hex
        logfile = args.state_dir / "bridge.log"
        if logfile.is_symlink():
            raise ValueError("log must not be a symbolic link")
        with logfile.open("ab") as stream:
            os.chmod(logfile, 0o600)
            child = subprocess.Popen([sys.executable, str(SCRIPT), "--state-dir", str(args.state_dir),
                                      "serve", "--bind", host, "--port", str(port), "--instance", instance],
                                     stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                     start_new_session=True, close_fds=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise ValueError("bridge startup failed; inspect logs")
            state = read_state(args.state_dir)
            if state and state.get("instance") == instance and owns_process(state) and health(state):
                print(f"Bridge healthy: http://{host}:{port} (pid {child.pid})")
                return 0
            time.sleep(0.2)
        # This child is still held by Popen, so its process identity cannot be reused.
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise ValueError("LAN health did not become ready; startup child was asked to stop")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=SCRIPT.parent.parent / ".work" / "preview-lan-proxy")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Bridge en0 (or PREVIEW_LAN_HOST) to the existing Device Service")
    start.add_argument("--bind", help="Explicit local RFC1918 IPv4; default: ipconfig getifaddr en0")
    start.add_argument("--port", type=int, default=int(os.environ.get("PREVIEW_LAN_PORT", "8787")))
    for name in ("stop", "status", "logs", "help"):
        commands.add_parser(name)
    server = commands.add_parser("serve", help=argparse.SUPPRESS)
    server.add_argument("--bind", required=True)
    server.add_argument("--port", type=int, default=8787)
    server.add_argument("--instance", required=True)
    args = parser.parse_args(argv)
    if args.command == "help":
        parser.print_help()
        print("\nOnly opaque TCP bytes are relayed. Bearer authentication remains required.\n"
              "Use only on an authorized trusted LAN; HTTP is not encrypted.\n"
              "Limits: 64 connections, 64 KiB buffers/direction, 30 s idle, 300 s lifetime.\n"
              "State/logs: .work/preview-lan-proxy; stop signals only the recorded owned bridge.")
        return 0
    try:
        if hasattr(args, "port") and not 1 <= args.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if args.state_dir.is_symlink():
            raise ValueError("state directory must not be a symbolic link")
        args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.state_dir = args.state_dir.resolve()
        return serve(args) if args.command == "serve" else manage(args)
    except (OSError, ValueError) as error:
        # No network exception contents or request/credential material is emitted.
        print(f"Bridge operation failed: {error if isinstance(error, ValueError) else 'local I/O or socket error'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
