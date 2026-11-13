#!/usr/bin/env python3
"""Run a pinned NanoC6 USB endpoint probe in an owned local Device Service session."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import struct
import subprocess
import time
import urllib.request
from urllib.parse import urlparse
import zipfile
import socket


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_serial(uart, usb, kind, mode):
    assert uart.count("ESP-ROM:esp32c6") == 1
    assert usb.count(b"ESP-ROM:esp32c6") == 1
    for channel in (uart, usb.decode(errors="replace")):
        assert not any(marker in channel for marker in (
            "assert failed:", "Guru Meditation Error", "abort() was called",
            "Task watchdog got triggered", "Rebooting..."))
    if kind == "uiflow":
        assert mode == "after" and b"USJ_REPL_RX_OK 2016" in usb
        return {"repl_result": True}
    expected = b"USJ_TX_BEGIN\n" + bytes((i * 37 + 19) & 255 for i in range(257)) + b"\nUSJ_TX_END\n"
    tx = expected in usb
    rx = "USJ_RX bytes=197 result=PASS" in uart
    ack = b"USJ_RX_ACK bytes=197 result=PASS" in usb
    assert "USB_PROBE_DONE" in uart
    if mode == "after":
        assert tx and rx and ack
    else:
        assert not tx and not rx and not ack and "USJ_RX bytes=0 result=FAIL" in uart
    return {"tx_exact_257": tx, "guest_rx_exact_197": rx, "usb_ack": ack}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--kind", choices=("arduino", "uiflow"), required=True)
    parser.add_argument("--mode", choices=("before", "after"), required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert urlparse(args.base_url).hostname in ("127.0.0.1", "localhost", "::1")
    assert args.kind != "uiflow" or args.mode == "after"
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (out / name).write_text(json.dumps(value, indent=2) + "\n")

    def api(method, path, body=None, timeout=20):
        headers = {}
        if args.token_file:
            headers["Authorization"] = "Bearer " + args.token_file.read_text().strip()
        if isinstance(body, bytes):
            raw = body
            headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            raw = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            raw = None
        request = urllib.request.Request(args.base_url.rstrip("/") + "/api/v1/" + path,
                                         data=raw, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            return json.loads(data) if "json" in response.headers.get("Content-Type", "") else data

    image = args.firmware.read_bytes()
    assert digest(image) == args.firmware_sha256
    artifact = api("POST", "artifacts", image)
    firmware = api("POST", "firmware/import", {"device_id": "nanoc6", "artifact_id": artifact["artifact_id"]})
    payload = {"device_id": "nanoc6", "firmware_id": firmware["firmware_id"], "runtime": "qemu",
               "ttl_seconds": 180, "idempotency_key": "c6-controller-" + secrets.token_hex(16)}
    save("create-request.json", payload)
    sid = pid = pid_start = None
    error = None
    cleanup = []
    report = {"status": "FAIL", "kind": args.kind, "mode": args.mode,
              "firmware_sha256": digest(image), "runtime_sha256": args.runtime_sha256,
              "validation": "virtual-device validation"}
    try:
        created = api("POST", "sessions", payload, timeout=60)
        sid = created["session_id"]
        save("created.json", created)
        route = "sessions/" + sid
        deadline = time.monotonic() + 40
        while True:
            session = api("GET", route)
            if session["state"] == "running" and session.get("pid"):
                break
            assert session["state"] not in ("failed", "stopped")
            assert time.monotonic() < deadline, "Guest startup timeout"
            time.sleep(.2)
        pid = session["pid"]
        executable = Path(subprocess.check_output(["ps", "-p", str(pid), "-o", "comm="], text=True).strip())
        pid_start = subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()
        assert digest(executable.read_bytes()) == args.runtime_sha256
        save("runtime-identity.json", {"binary_sha256": args.runtime_sha256, "binary": str(executable),
                                       "pid": pid, "start": pid_start})
        command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True)
        match = re.search(r"-qmp unix:([^, ]+),", command)
        assert match and "chardev:c6-usj-probe" in command
        endpoint = match.group(1) + ".usj"
        monitor_path = match.group(1) + ".hmp"
        def resume():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as monitor:
                monitor.settimeout(5)
                monitor.connect(monitor_path)
                data = b""
                while b"(qemu)" not in data:
                    chunk = monitor.recv(65536)
                    assert chunk, "HMP disconnected"
                    data += chunk
                monitor.sendall(b"cont\n")
                data = b""
                while b"(qemu)" not in data:
                    chunk = monitor.recv(65536)
                    assert chunk, "HMP disconnected"
                    data += chunk
        start = time.monotonic()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as host:
            host.settimeout(.1)
            host.connect(endpoint)
            resume()
            observed = bytearray()
            sent = interrupted = False
            while time.monotonic() - start < (20 if args.kind == "uiflow" else 8):
                elapsed = time.monotonic() - start
                uart = api("GET", route + "/serial?offset=0&limit=262144")["data"]
                if args.kind == "uiflow":
                    if elapsed > 3 and not interrupted:
                        host.sendall(b"\x03\x03\r\n")
                        interrupted = True
                    ready = elapsed > 4
                    request = b'print("USJ_REPL_RX_OK", sum(bytes(range(64))))\r\n'
                else:
                    ready = "USB_PROBE_WAIT_RX" in uart
                    request = bytes((i * 53 + 7) & 255 for i in range(197))
                if ready and not sent:
                    host.sendall(request)
                    sent = True
                    report["host_request_sha256"] = digest(request)
                try:
                    chunk = host.recv(65536)
                    assert chunk, "USB host disconnected"
                    observed.extend(chunk)
                except socket.timeout:
                    pass
            assert sent
            report["oracle"] = validate_serial(uart, bytes(observed), args.kind, args.mode)
            report["host_received_sha256"] = digest(observed)
            report["host_received_bytes"] = len(observed)
            (out / "host-received.bin").write_bytes(observed)
        report["observed_seconds"] = time.monotonic() - start
    except BaseException as exc:
        error = repr(exc)
    finally:
        if sid is None:
            try:
                recovered = api("POST", "sessions", payload, timeout=30)
                sid = recovered["session_id"]
                save("create-recovery.json", recovered)
            except BaseException as exc:
                cleanup.append("same-key recovery: " + repr(exc))
        if sid:
            route = "sessions/" + sid
            try:
                bundle = api("GET", route + "/evidence?include=manifest,serial,logs,qom,flash", timeout=30)
                (out / "evidence.zip").write_bytes(bundle)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                    assert manifest["session"]["session_id"] == sid
                    assert manifest["session"]["firmware_sha256"] == firmware["sha256"]
                    serial = archive.read("serial.log")
                    usb = archive.read("usb-serial-jtag.log")
                    flash = archive.read("flash/virtual-flash.bin")
                (out / "serial.log").write_bytes(serial)
                report["oracle"] = validate_serial(serial.decode(errors="replace"), usb, args.kind, args.mode)
                assert usb.startswith((out / "host-received.bin").read_bytes())
                (out / "usb-serial-jtag.log").write_bytes(usb)
                report["usb_serial_sha256"] = digest(usb)
                parts = []
                for offset in range(0x8000, 0x9000, 32):
                    magic, kind, sub, address, size, label, flags = struct.unpack_from("<HBBII16sI", image, offset)
                    if magic != 0x50aa:
                        break
                    if kind == 0:
                        before = image[address:address + size].ljust(size, b"\xff")
                        after = flash[address:address + size]
                        assert before == after
                        parts.append({"offset": address, "size": size, "sha256": digest(after), "unchanged": True})
                assert parts
                report.update(zip_before_stop=True, evidence_zip_sha256=digest(bundle), serial_sha256=digest(serial),
                              app_partitions=parts, same_session_verified=True)
            except BaseException as exc:
                cleanup.append("final evidence/oracle: " + repr(exc))
            try:
                try:
                    api("DELETE", route + "?purge=0&retain_flash=0", timeout=10)
                except Exception:
                    pass
                deadline = time.monotonic() + 45
                while True:
                    terminal = api("GET", route, timeout=5)
                    if (terminal["state"] == "stopped" and not terminal.get("stop_pending")
                            and terminal["flash_retained"] is False and terminal["worker"]["lease_active"] is False):
                        break
                    assert time.monotonic() < deadline, "Cleanup deadline exceeded"
                    time.sleep(.2)
                save("terminal-state.json", terminal)
                if pid is not None:
                    current = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True)
                    assert current.returncode != 0 or current.stdout.strip() != pid_start
                report.update(terminal_state="stopped", flash_released=True, lease_released=True, native_pid_exited=True)
            except BaseException as exc:
                cleanup.append("stop: " + repr(exc))
        report.update(status="FAIL" if error or cleanup else "EXPECTED_FAIL" if args.mode == "before" else "PASS",
                      error=error, cleanup_errors=cleanup)
        save("summary-private.json", report)
    if error or cleanup:
        raise RuntimeError("Probe failed; inspect private summary")


if __name__ == "__main__":
    main()
