#!/usr/bin/env python3
"""Keep a loopback endpoint stable across isolated VZ worker incarnations."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import threading
import time


RESERVED_PORTS = {8787, 8790, 8830, 18853}
MAX_WIRE = 97 << 20
MAX_CONNECTIONS = 4
MAX_SECONDS = 200


def endpoint(path):
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return None
            data = stream.read(4097)
        if len(data) > 4096:
            return None
        receipt = json.loads(data)
        if (receipt["schema_version"] != 1 or receipt["phase"] != "running" or receipt["ready"] is not True
                or type(receipt["generation"]) is not int or receipt["generation"] <= 0):
            return None
        for field in ("supervisor_pid", "runner_pid"):
            pid = receipt[field]
            if type(pid) is not int or pid <= 1:
                return None
            os.kill(pid, 0)
        transport = Path(receipt["transport_socket"])
        if not re.fullmatch(r"/private/tmp/m5vz-[A-Za-z0-9_-]+/d", str(transport)):
            return None
        for candidate, kind in ((transport.parent, stat.S_ISDIR), (transport, stat.S_ISSOCK)):
            info = candidate.lstat()
            if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return None
        return receipt
    except (OSError, AttributeError, KeyError, ValueError, TypeError):
        return None


def unavailable(client):
    body = b'{"error":{"code":"worker_transport_unavailable"}}'
    header = (f"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n"
              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
    client.settimeout(1)
    try:
        client.sendall(header + body)
    except OSError:
        pass


def relay(a, b):
    deadline = time.monotonic() + MAX_SECONDS
    aborted = threading.Event()

    def pump(source, target):
        remaining = MAX_WIRE
        try:
            while not aborted.is_set() and time.monotonic() < deadline:
                try:
                    chunk = source.recv(min(65536, remaining + 1))
                except socket.timeout:
                    continue
                if not chunk:
                    target.shutdown(socket.SHUT_WR)
                    return
                if len(chunk) > remaining:
                    break
                target.sendall(chunk)
                remaining -= len(chunk)
        except OSError:
            pass
        aborted.set()
        for stream in (source, target):
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    for stream in (a, b):
        stream.settimeout(3)
    request = threading.Thread(target=pump, args=(a, b), daemon=True)
    request.start()
    pump(b, a)
    # A complete response may close before a keep-alive HTTP client sends EOF.
    try:
        a.shutdown(socket.SHUT_RD)
    except OSError:
        pass
    request.join(4)


def serve(root, port):
    info = root.lstat()
    if (root != root.resolve(strict=True) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("bridge root must be an owned private directory")
    if not 1024 < port <= 65535 or port in RESERVED_PORTS:
        raise ValueError("bridge requires a dedicated unreserved loopback port")
    slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
    stopping = threading.Event()
    state = root / "endpoint.private.json"

    def handle(client):
        try:
            with client, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                snapshot = endpoint(state)
                if snapshot is None:
                    unavailable(client)
                    return
                peer.settimeout(2)
                try:
                    peer.connect(snapshot["transport_socket"])
                except OSError:
                    unavailable(client)
                    return
                if endpoint(state) != snapshot:
                    unavailable(client)
                    return
                # Forward once. Disconnects and new generations never replay a request.
                relay(client, peer)
        finally:
            slots.release()

    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(MAX_CONNECTIONS)
        listener.settimeout(.25)
        print("M5_MANAGED_LOOPBACK_BRIDGE_LISTENING", flush=True)
        while not stopping.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            if not slots.acquire(blocking=False):
                with client:
                    unavailable(client)
                continue
            threading.Thread(target=handle, args=(client,), daemon=True).start()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("port", type=int)
    args = cli.parse_args()
    serve(args.root, args.port)


if __name__ == "__main__":
    main()
