#!/usr/bin/env python3
"""Exercise the browser transport with machine-none; never load firmware."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parent


def run_case(case, output_dir, reconnect_count, expected_workers):
    session = Path(tempfile.mkdtemp(prefix="m5-wasm-transport-"))
    qmp = session / "qmp.sock"
    environment = dict(
        os.environ,
        M5_WASM_SESSION_ROOT=str(session),
        M5_WASM_MAX_LIFETIME_MS="90000",
    )
    arguments = [
        str(ROOT / "qemu-browser"),
        "-machine", "none",
        "-nodefaults",
        "-display", "none",
        "-monitor", "none",
        "-qmp", f"unix:{qmp},server=on,wait=off",
        "-S",
    ]
    if case == "pipe":
        arguments += [
            "-chardev",
            f"socket,id=program-console,path={session}/console.sock,server=on,wait=off",
            "-mon", "chardev=program-console,mode=readline",
        ]
    else:
        arguments += ["-serial", "none"]

    connection = None
    stream = None
    console = None
    replies = []
    with (output_dir / f"{case}.stdout").open("xb") as stdout, (
        output_dir / f"{case}.stderr"
    ).open("xb") as stderr:
        process = subprocess.Popen(
            arguments, env=environment, stdout=stdout, stderr=stderr
        )
        try:
            deadline = time.monotonic() + 65
            while not qmp.exists() and process.poll() is None:
                if time.monotonic() >= deadline:
                    raise AssertionError("QMP did not become ready")
                time.sleep(0.05)
            assert qmp.exists(), f"QMP unavailable; exit={process.poll()}"

            def connect():
                nonlocal connection, stream
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.settimeout(10)
                connection.connect(str(qmp))
                stream = connection.makefile("rwb", buffering=0)
                greeting = json.loads(stream.readline())
                assert greeting["QMP"]["version"]["qemu"]["major"] == 9
                return greeting

            def command(name, **arguments):
                request = {"execute": name, "arguments": arguments, "id": name}
                stream.write((json.dumps(request) + "\n").encode())
                while True:
                    line = stream.readline()
                    assert line, "QMP disconnected before replying"
                    reply = json.loads(line)
                    replies.append(reply)
                    if reply.get("id") == name:
                        return reply

            greeting = connect()
            assert command("qmp_capabilities")["return"] == {}
            assert command("query-status")["return"]["status"] == "prelaunch"

            completed_reconnects = 0
            if case == "reconnect":
                for _ in range(reconnect_count):
                    assert "error" in command(
                        "qom-get", path="/machine", property="does-not-exist"
                    )
                    stream.close()
                    connection.close()
                    # Deliberately reconnect immediately: the old socket's
                    # close callback may not have reached the adapter yet.
                    connect()
                    assert command("qmp_capabilities")["return"] == {}
                    assert command("query-status")["return"]["status"] == "prelaunch"
                    completed_reconnects += 1

            completed_disconnects = 0
            if case == "disconnect":
                stream.close()
                connection.close()
                for _ in range(reconnect_count):
                    # Leave a real QEMU response unread, then close its UNIX
                    # client while the adapter may still be writing it.
                    abandoned = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    abandoned.settimeout(10)
                    try:
                        abandoned.connect(str(qmp))
                        greeting_bytes = b""
                        while b"\n" not in greeting_bytes:
                            chunk = abandoned.recv(4096)
                            assert chunk, "Abandoned client missed its greeting"
                            greeting_bytes += chunk
                        abandoned.sendall(
                            b'{"execute":"query-qmp-schema","id":"query-status"}\n'
                        )
                        assert abandoned.recv(1, socket.MSG_PEEK), "No real QMP response"
                    finally:
                        abandoned.close()
                    # Also queue a reply that will arrive after disconnect.
                    # Reuse the next healthy client's ID to detect leakage.
                    late = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    late.settimeout(10)
                    try:
                        late.connect(str(qmp))
                        late_greeting = b""
                        while b"\n" not in late_greeting:
                            chunk = late.recv(4096)
                            assert chunk, "Late client missed its greeting"
                            late_greeting += chunk
                        late.sendall(
                            b'{"execute":"query-qmp-schema","id":"query-status"}\n'
                        )
                        late.shutdown(socket.SHUT_WR)
                    finally:
                        late.close()
                    connect()
                    assert command("qmp_capabilities")["return"] == {}
                    assert command("query-status")["return"]["status"] == "prelaunch"
                    completed_disconnects += 1
                    if completed_disconnects < reconnect_count:
                        stream.close()
                        connection.close()

            if case == "pipe":
                console = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                console.settimeout(10)
                console.connect(str(session / "console.sock"))
                console.sendall(b"info version\r\n")
                data = b""
                while b"9.2.2" not in data:
                    chunk = console.recv(4096)
                    assert chunk, "QEMU HMP pipe disconnected"
                    data += chunk

            if case == "cancel":
                process.terminate()
            else:
                assert command("quit")["return"] == {}
            process.wait(timeout=12)

            report_path = session / "browser-wasm-adapter.json"
            report_bytes = report_path.read_bytes()
            report = json.loads(report_bytes)
            assert process.returncode == 0, (process.returncode, report["errors"])
            assert report["cleanup"]["runtime_exit_code"] == 0
            assert report["cleanup"]["workers_before_browser_close"] == 0
            assert report["cleanup"]["browser_pid_gone"] is True
            assert (
                len(report["workers_created"])
                == len(report["workers_closed"])
                == expected_workers
            )
            assert not qmp.exists()
            assert report["errors"] == []
            socket_errors = [
                event for event in report["events"]
                if event["kind"] == "client_socket_error"
            ]
            discarded_replies = [
                event for event in report["events"]
                if event["kind"] == "qmp_response_discarded"
            ]
            if case == "disconnect":
                assert socket_errors, "No real client socket error was exercised"
                assert discarded_replies, "No late reply was discarded"
            shutil.copyfile(report_path, output_dir / f"{case}.adapter.json")
            return {
                "case": case,
                "status": "PASS",
                "expected_workers": expected_workers,
                "session": str(session),
                "greeting": greeting,
                "replies": replies,
                "reconnect_rounds": completed_reconnects,
                "disconnect_rounds": completed_disconnects,
                "client_socket_errors": socket_errors,
                "discarded_qmp_replies": discarded_replies,
                "overlap_events": sum(
                    event["kind"] == "qmp_client_overlap"
                    for event in report["events"]
                ),
                "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                "cleanup": report["cleanup"],
            }
        finally:
            if stream:
                stream.close()
            if connection:
                connection.close()
            if console:
                console.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--case", choices=["all", "qmp", "pipe", "cancel", "reconnect", "disconnect"], default="all"
    )
    parser.add_argument("--reconnect-count", type=int, default=20)
    parser.add_argument(
        "--expected-workers", type=int, default=4,
        help="no-firmware Worker count for the selected runtime (default: 4)",
    )
    arguments = parser.parse_args()
    if arguments.reconnect_count < 1:
        parser.error("--reconnect-count must be positive")
    if arguments.expected_workers < 1:
        parser.error("--expected-workers must be positive")
    if not os.environ.get("M5_WASM_RUNTIME_DIR"):
        parser.error("M5_WASM_RUNTIME_DIR is required")
    output_dir = arguments.out_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = ["qmp", "pipe", "cancel", "reconnect", "disconnect"] if arguments.case == "all" else [arguments.case]
    results = [
        run_case(case, output_dir, arguments.reconnect_count, arguments.expected_workers)
        for case in cases
    ]
    summary = {
        "schema_version": 1,
        "firmware_execution": "NOT RUN",
        "hardware_execution": "NOT RUN",
        "tool_source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ["qemu-browser", "qemu-browser.mjs", "page.js", "browser.mjs", "selftest.py"]
        },
        "results": results,
    }
    with (output_dir / "selftest.json").open("x") as target:
        json.dump(summary, target, indent=2)
        target.write("\n")
    print(json.dumps({"status": "PASS", "cases": cases}))


if __name__ == "__main__":
    main()
