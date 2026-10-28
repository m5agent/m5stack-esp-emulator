#!/usr/bin/env python3
"""Run a cold UIFlow2 probe through a visible Device Service session.

Only LittleFS preparation is local. Firmware execution and all observations
use /api/v1; raw firmware and evidence remain in an ignored output directory.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tests/uiflow2"), str(ROOT / "tests/firmware/core2_startup")]
from run_profile_ui_test import build_image
from run_service_test import Api, process_identity, runtime_executable
from firmware_analysis import parse_partition_table


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def serial_pages(api, session_id, offset=0):
    """Drain the byte cursor instead of assuming a requested limit was honored."""
    chunks, pages = [], []
    for _ in range(128):
        row = api.json(f"sessions/{session_id}/serial?offset={offset}&limit=262144")
        next_offset = row["next_offset"]
        if row["bytes"] < 0 or next_offset < offset or next_offset != row["offset"] + row["bytes"]:
            raise RuntimeError("serial byte cursor is inconsistent")
        if row["bytes"] and next_offset <= offset:
            raise RuntimeError("serial byte cursor made no progress")
        chunks.append(row["data"])
        pages.append({key: row[key] for key in ("offset", "next_offset", "bytes")})
        offset = next_offset
        if not row["bytes"]:
            return "".join(chunks), offset, pages
    raise RuntimeError("serial exceeds the bounded 32 MiB observation window")


def fixture_files(fixture_dir):
    """Yield explicit guest fixture files, excluding host-generated caches."""
    if fixture_dir.is_symlink() or not fixture_dir.is_dir():
        raise ValueError("fixtures require a real directory, not a symlink")
    for fixture in sorted(fixture_dir.rglob("*")):
        # Reject links even when their name would otherwise be filtered out.
        if fixture.is_symlink():
            raise ValueError("fixture symlinks are not supported")
        relative = fixture.relative_to(fixture_dir)
        if "__pycache__" in relative.parts or fixture.name == ".DS_Store" or fixture.suffix.lower() in {".pyc", ".pyo"}:
            continue
        if not fixture.is_file():
            continue
        if relative.as_posix() in {"boot.py", "main.py"}:
            raise ValueError("fixtures must not replace the probe entry points")
        yield fixture, relative


def copy_fixtures(fixture_dir, destination):
    """Copy and hash the same original bytes once, including native .mpy files."""
    hashes = {}
    for fixture, relative in fixture_files(fixture_dir):
        payload = fixture.read_bytes()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
    return hashes


def companion_cleanup(before_stop, stopped, *, runtime_pid_gone, worker_identity=None, inspect_process=None):
    """Check resource lifetime without requiring a shared service PID to exit."""
    inspect_process = inspect_process or process_identity
    before_worker = before_stop.get("worker", {})
    after_worker = stopped.get("worker", {})
    worker_identity = worker_identity or {}
    same_worker = (
        all(before_worker.get(key) == after_worker.get(key) == worker_identity.get(key)
            for key in ("worker_id", "generation"))
        and all(isinstance(worker_identity.get(key), str) and worker_identity[key]
                for key in ("worker_id", "instance_id"))
        and type(worker_identity.get("generation")) is int
        and worker_identity["generation"] > 0
        and type(worker_identity.get("pid")) is int
        and worker_identity["pid"] > 0
    )
    terminal = stopped.get("state") in {"stopped", "failed"}
    after_companions = stopped.get("companions", {})
    process_gone, lifecycle = {}, {}
    for name, metadata in before_stop.get("companions", {}).items():
        if not isinstance(metadata, dict):
            lifecycle[name] = {"mode": "invalid-metadata", "complete": False}
            continue
        if metadata.get("required") is False and not any(
            key in metadata for key in ("pid", "state", "generation")
        ):
            continue
        current = after_companions.get(name, {})
        pid = metadata.get("pid")
        positive_pid = type(pid) is int and pid > 0
        route_terminated = (
            terminal and current.get("state") == "terminated"
            and current.get("ownership_verified") is False
            and current.get("adopted") is False
            and type(metadata.get("generation")) is int and metadata["generation"] > 0
            and type(metadata.get("port")) is int and 0 < metadata["port"] <= 65535
            and all(current.get(key) == metadata.get(key)
                    for key in ("pid", "port", "generation", "recovery_action"))
        )
        if (
            name == "http_fixture" and positive_pid
            and metadata.get("recovery_action") in {"keep-running", "recreate"}
            and metadata.get("kind", "in-process-http-fixture") == "in-process-http-fixture"
            and pid == worker_identity.get("pid") and same_worker
        ):
            # The API binds this listener to the exact worker process. Its
            # terminated state is published only after shutdown/server_close,
            # so the service itself must remain alive for history/API reads.
            lifecycle[name] = {"mode": "shared-service-fixture", "pid": pid,
                               "route_terminated": route_terminated, "complete": route_terminated}
        elif (
            name == "http_fixture" and pid is None
            and metadata.get("recovery_action") == "qemu-process-owned"
            and metadata.get("kind", "qemu-guestfwd-command") == "qemu-guestfwd-command"
        ):
            complete = route_terminated and runtime_pid_gone
            lifecycle[name] = {"mode": "qemu-guestfwd", "route_terminated": route_terminated,
                               "runtime_pid_gone": runtime_pid_gone, "complete": complete}
        elif positive_pid:
            gone = not inspect_process(pid)["exists"]
            process_gone[name] = gone
            lifecycle[name] = {"mode": "owned-process", "pid": pid, "pid_gone": gone, "complete": gone}
        else:
            lifecycle[name] = {"mode": "unverified-companion", "complete": False}
    return {"companions_pid_gone": process_gone, "companions_lifecycle": lifecycle,
            "companions_cleanup_complete": all(row["complete"] for row in lifecycle.values())}


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    api = Api(args.api, args.token_file)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device = next(row for row in matrix["devices"] if row["id"] == args.device)
    source = args.source.read_text(encoding="utf-8")
    base_path = args.base_image if getattr(args, "base_image", None) else ROOT / device["base"]
    base = base_path.read_bytes()
    firmware_lane=getattr(args,"firmware_lane",None) or ("caller-pinned-candidate" if getattr(args,"base_image",None) else "stock-frozen")
    if getattr(args, "base_image", None):
        if firmware_lane=="stock-frozen":
            raise ValueError("an alternate base cannot be labelled as stock-frozen")
        if not args.expected_base_sha256 or hashlib.sha256(base).hexdigest() != args.expected_base_sha256:
            raise ValueError("an alternate base requires its exact --expected-base-sha256")
    table = parse_partition_table(base, image_size=int(device["flash_size"], 0))
    if not table["valid"]:
        raise RuntimeError("reference firmware has an invalid partition table")
    partitions = [row for row in table["partitions"]
                  if row["label"] == "vfs" and row["type"] == 1 and row["subtype"] == 0x81]
    if len(partitions) != 1:
        raise RuntimeError("reference firmware requires one unambiguous LittleFS VFS partition")
    vfs = partitions[0]
    files = args.out_dir / "files"
    files.mkdir()
    (files / "boot.py").write_text(
        'from machine import UART\nimport os\n'
        '_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)\n'
        'os.dupterm(_repl_uart, 0)\n'
        '_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)\n'
        '_uiflow_run_main = True\n', encoding="utf-8")
    (files / "main.py").write_text('print("M5EMU_API_SWEEP_READY")\n' + source, encoding="utf-8")
    fixture_hashes = {}
    fixture_dir = getattr(args, "fixture_dir", None)
    if fixture_dir is not None:
        fixture_hashes = copy_fixtures(fixture_dir, files)
    with contextlib.redirect_stdout(io.StringIO()):
        image = build_image(SimpleNamespace(
            base=base_path, flash_size=int(device["flash_size"], 0),
            files_dir=files, mklittlefs=None, preserve_vfs=False,
            vfs_offset=vfs["offset"], vfs_size=vfs["size"],
            prog_size=32, out_dir=args.out_dir))
    if fixture_dir is not None:
        # The regression helper deliberately includes only Python text files.
        # Add explicit binary/JSON fixtures to its real LittleFS partition.
        import littlefs
        composed = bytearray(image.read_bytes())
        vfs_data = bytearray(composed[vfs["offset"]:vfs["offset"] + vfs["size"]])
        fs = littlefs.LittleFS(context=littlefs.UserContext(buffer=vfs_data),
                             block_size=4096, block_count=vfs["size"] // 4096,
                             read_size=128, prog_size=32, lookahead_size=128,
                             block_cycles=100, mount=False)
        fs.mount()
        for relative in fixture_hashes:
            parts = Path(relative).parts[:-1]
            for count in range(1, len(parts) + 1):
                directory = "/" + "/".join(parts[:count])
                try:
                    fs.mkdir(directory)
                except FileExistsError:
                    pass
            with fs.open("/" + relative, "wb") as handle:
                handle.write((files / relative).read_bytes())
        fs.unmount()
        composed[vfs["offset"]:vfs["offset"] + vfs["size"]] = vfs_data
        image.write_bytes(composed)
    raw = image.read_bytes()
    report = {"schema_version": 1, "device_id": args.device,
              "validation": "virtual-device validation", "hardware_validation": "NOT RUN",
              "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
              "fixture_sha256": fixture_hashes,
              "base_sha256": hashlib.sha256(base).hexdigest(),
              "base_lane": "caller-pinned-candidate" if getattr(args, "base_image", None) else "device-matrix-reference",
              "firmware_lane":firmware_lane,
              "vfs": vfs, "declared_layout_matches": (vfs["offset"] == int(device["vfs_offset"], 0)
                  and vfs["size"] == int(device["vfs_size"], 0)),
              "firmware_sha256": hashlib.sha256(raw).hexdigest(), "status": "FAIL"}
    session_id = None
    serial_text, serial_offset, observed_pages = "", 0, []
    try:
        artifact = api.json("artifacts", "POST", body=raw, headers={
            "Content-Type": "application/octet-stream", "X-Artifact-Name": args.device + "-api-sweep.bin"})
        firmware = api.json("firmware", "POST", {"device_id": args.device, "kind": "merged", "artifact_id": artifact["artifact_id"]})
        prepare_timeout = getattr(args, "prepare_timeout", 600)
        session_request = {"device_id": args.device, "firmware_id": firmware["firmware_id"],
            "runtime": args.runtime, "ttl_seconds": min(3600, prepare_timeout + args.timeout + 120),
            "ready_marker": "M5EMU_API_SWEEP_READY", "ready_timeout_seconds": 60}
        if getattr(args, "network", None) is not None:
            session_request["network"] = args.network
        if getattr(args, "runtime_env", None) is not None:
            session_request["runtime_env"] = args.runtime_env
        if getattr(args, "units", None) is not None:
            session_request["units"] = args.units
        session = api.json("sessions", "POST", session_request)
        session_id = session["session_id"]
        report["session_id"] = session_id
        save(args.out_dir / "created.json", session)
        print(json.dumps({"device_id": args.device, "session_id": session_id, "phase": "created"}), flush=True)
        # Flash preparation is serialized/cached by the service and can take
        # longer under concurrent sweeps. Start the guest execution deadline
        # only when the service has launched its owned runtime process.
        prepare_started = time.monotonic()
        deadline = prepare_started + prepare_timeout
        runtime_started = None
        while time.monotonic() < deadline:
            current = api.json(f"sessions/{session_id}")
            if getattr(args, "on_session_poll", None) is not None:
                args.on_session_poll(api, session_id, current)
            if current.get("pid") and not report.get("runtime_binary_sha256"):
                if runtime_started is None:
                    runtime_started = time.monotonic()
                    deadline = runtime_started + args.timeout
                    report["prepare_seconds"] = round(runtime_started - prepare_started, 3)
                report["runtime_pid"] = current["pid"]
                report["process_identity"] = process_identity(current["pid"])
                executable = runtime_executable(current["pid"])
                report["runtime_binary_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
                report["runtime_executable_name"] = executable.name
            appended, serial_offset, pages = serial_pages(api, session_id, serial_offset)
            serial_text += appended
            observed_pages.extend(pages)
            (args.out_dir / "serial.txt").write_text(serial_text, encoding="utf-8")
            save(args.out_dir / "serial-pages.json", observed_pages)
            save(args.out_dir / "session.json", current)
            if current["state"] in {"failed", "stopped"}:
                raise RuntimeError("session ended: " + str(current.get("error")))
            if args.done_marker in serial_text:
                report["status"] = "EXECUTED"  # individual behavioral oracles decide PASS
                break
            time.sleep(.2)
        else:
            raise RuntimeError("runtime preparation deadline exceeded" if runtime_started is None else
                               "guest probe did not reach its completion marker")
    except Exception as error:
        report["error"] = str(error)
    finally:
        if session_id:
            prefix = f"sessions/{session_id}"
            try:
                frame = api.raw(prefix + "/frame.png")
                (args.out_dir / "frame.png").write_bytes(frame)
                report["frame_sha256"] = hashlib.sha256(frame).hexdigest()
            except Exception as error:
                report["frame_error"] = str(error)
            try:
                bundle = api.raw(prefix + "/evidence")
                (args.out_dir / "evidence.zip").write_bytes(bundle)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    if archive.testzip():
                        raise RuntimeError("evidence ZIP is corrupt")
                report["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
            except Exception as error:
                report["evidence_error"] = str(error)
                report["status"] = "FAIL"
            try:
                appended, serial_offset, pages = serial_pages(api, session_id, serial_offset)
                serial_text += appended
                observed_pages.extend(pages)
                (args.out_dir / "serial.txt").write_text(serial_text, encoding="utf-8")
                save(args.out_dir / "serial-pages.json", observed_pages)
            except Exception as error:
                report["serial_error"] = str(error)
                report["status"] = "FAIL"
            try:
                try:
                    before_stop = api.json(prefix)
                except Exception:
                    before_stop = session
                try:
                    worker_before_stop = api.json("worker")
                    save(args.out_dir / "worker-before-stop.json", worker_before_stop)
                except Exception:
                    worker_before_stop = {}
                stop_response = api.json(prefix + "?purge=0", "DELETE")
                save(args.out_dir / "stop-response.json", stop_response)
                stop_deadline = time.monotonic() + 15
                while True:
                    stopped = api.json(prefix)
                    if stopped["state"] in {"stopped", "failed"} or time.monotonic() >= stop_deadline:
                        break
                    time.sleep(.2)
                save(args.out_dir / "stopped.json", stopped)
                old_pid = before_stop.get("pid")
                runtime_gone = old_pid is None or not process_identity(old_pid)["exists"]
                try:
                    worker_after_stop = api.json("worker")
                    save(args.out_dir / "worker-after-stop.json", worker_after_stop)
                except Exception:
                    worker_after_stop = {}
                worker_identity = worker_after_stop if all(
                    worker_before_stop.get(key) == worker_after_stop.get(key)
                    for key in ("worker_id", "instance_id", "generation", "pid")
                ) else {}
                companions = companion_cleanup(
                    before_stop, stopped, runtime_pid_gone=runtime_gone, worker_identity=worker_identity,
                )
                failed_preserved = before_stop["state"] != "failed" or (
                    stopped["state"] == "failed" and stopped.get("error") == before_stop.get("error"))
                history_preserved = all(stopped.get(key) == session.get(key) for key in (
                    "session_id", "device_id", "firmware_id", "firmware_sha256", "runtime"))
                report["stopped"] = stopped["state"] == "stopped"
                report["cleanup"] = {"terminal_state": stopped["state"], "runtime_pid_gone": runtime_gone,
                                     "failed_state_preserved": failed_preserved, "history_preserved": history_preserved}
                report["cleanup"].update(companions)
                if not companions["companions_cleanup_complete"]:report["status"]="FAIL"
                if stopped["state"] not in {"stopped", "failed"} or not all((runtime_gone, failed_preserved, history_preserved)):
                    report["status"] = "FAIL"
            except Exception as error:
                report["stop_error"] = str(error)
                report["status"] = "FAIL"
        report["serial_bytes_observed"] = serial_offset
        report["serial_pages_observed"] = len(observed_pages)
        save(args.out_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "EXECUTED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--device", choices=("cores3", "cardputer-adv"), required=True)
    parser.add_argument("--runtime", default="qemu")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base-image", type=Path, help="explicit compatible candidate image; never changes the device-matrix reference")
    parser.add_argument("--expected-base-sha256", help="required exact SHA256 when --base-image is supplied")
    parser.add_argument("--fixture-dir", type=Path, help="local files copied into the guest VFS, with hashes in the report")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--done-marker", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--prepare-timeout", type=int, default=600)
    raise SystemExit(run(parser.parse_args()))
