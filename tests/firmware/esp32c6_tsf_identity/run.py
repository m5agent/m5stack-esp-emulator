#!/usr/bin/env python3
"""Run a pinned NanoC6 controller probe in an owned local Device Service session."""
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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_serial(text, kind, mode, reset=False):
    boots = 2 if reset else 1
    assert text.count("ESP-ROM:esp32c6") == boots
    assert not any(marker in text for marker in (
        "assert failed:", "Guru Meditation Error", "abort() was called",
        "Task watchdog got triggered", "Rebooting...",
    ))
    if kind == "tsf":
        lines = re.findall(r"^TSF_CASE index=(\d+) .*result=(PASS|FAIL)$", text, re.M)
        assert [int(index) for index, _ in lines] == list(range(6))
        count = sum(status == "PASS" for _, status in lines)
        assert count == (6 if mode == "after" else 0)
        assert f"TSF_PROBE_DONE passed={count} total=6" in text
        return {"passed": count, "total": 6}
    expected = "PASS" if mode == "after" else "FAIL"
    assert text.count(f"IDENTITY_API result={expected}") == boots
    # This is an explicit negative for the separately unimplemented radio block.
    assert text.count("IEEE_ADDRESS set=0 get=0 result=FAIL") == boots
    assert text.count("IDENTITY_PROBE_DONE") == boots
    values = {name: re.findall(r"IDENTITY name=" + name + r" rc=0 bytes=([0-9a-f]+)", text)
              for name in ("factory", "sta", "ieee")}
    assert all(len(items) == boots for items in values.values())
    if reset:
        assert all(items[0] == items[1] for items in values.values())
    return {"api_passes": boots if mode == "after" else 0,
            "reset_stable": reset, "ieee_address_readback": "EXPECTED_FAIL",
            "identity_sha256": {name: digest(bytes.fromhex(items[0]))
                                for name, items in values.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--kind", choices=("tsf", "identity"), required=True)
    parser.add_argument("--mode", choices=("before", "after"), required=True)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert urlparse(args.base_url).hostname in ("127.0.0.1", "localhost", "::1")
    assert not args.reset or (args.kind == "identity" and args.mode == "after")
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
        start = time.monotonic()
        reset_done = False
        while time.monotonic() - start < 30:
            text = api("GET", route + "/serial?offset=0&limit=262144")["data"]
            done = "TSF_PROBE_DONE" if args.kind == "tsf" else "IDENTITY_PROBE_DONE"
            if args.reset and not reset_done and done in text:
                receipt = api("POST", route + "/reset", {})
                assert receipt["session_id"] == sid and receipt["reset"] is True
                save("controlled-reset.json", receipt)
                reset_done = True
            if text.count(done) == (2 if args.reset else 1):
                validate_serial(text, args.kind, args.mode, args.reset)
                break
            time.sleep(.2)
        else:
            raise TimeoutError("Probe completion timeout")
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
                    flash = archive.read("flash/virtual-flash.bin")
                (out / "serial.log").write_bytes(serial)
                report["oracle"] = validate_serial(serial.decode(errors="replace"), args.kind, args.mode, args.reset)
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
