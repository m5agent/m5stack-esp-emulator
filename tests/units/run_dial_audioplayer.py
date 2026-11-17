#!/usr/bin/env python3
"""Exercise the native Dial AudioPlayer through a dedicated Device Service."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlparse
from zipfile import ZipFile

from run_service_cases import Client, wait_for
from uiflow_source import build_uiflow_source_image
from user_firmware_matrix import png_metrics

PROBE = Path(__file__).with_name("dial_audioplayer_probe")
DRIVER_HASH = "061aea42a9c40760dfd806672e968d24762c75a78398e439c45b570ca3cae435"
ORIGINAL_HASH = "7778656ee942bb5e87fbc780955c452f752059c9cf9325d7e026b83ec6c7ffaf"


def digest(data):
    return sha256(data).hexdigest()


def compose(args, pins):
    driver = args.driver.read_bytes()
    assert digest(driver) == DRIVER_HASH
    files = {path.name: path.read_text() for path in PROBE.glob("*.py")}
    files["u197_driver.py"] = driver.decode()
    files["probe_config.py"] = (
        f"PORT = {(pins['white'], pins['yellow'])!r}\nTRACKS = {args.tracks}\n"
    )
    return build_uiflow_source_image(args.base_firmware.read_bytes(), 8 << 20, files)[0]


def wait_for_state(read, predicate, timeout=90):
    end = monotonic() + timeout
    while monotonic() < end:
        state = read()
        if predicate(state):
            return state
        sleep(0.25)
    raise RuntimeError("expected controller state did not arrive before deadline")


def exercise_original(client, route, properties):
    initial = wait_for_state(properties, lambda value: value["playback-status"] == 1)
    assert initial["selected-track"] == 1
    assert initial["frames-injected"] >= 2
    assert "04fb01080804fb010d0d" in initial["tx-hex"]
    results = []
    for delta, index, command in ((3, 4, "04fb030600040c"), (-2, 2, "04fb030600020a")):
        before = properties()
        receipt = client.json(f"{route}/input", method="POST", payload={
            "kind": "encoder", "delta": delta, "settle_seconds": 0,
        })["controller"]
        assert receipt["edge_period_ms"] == 35
        after = wait_for_state(properties, lambda value: value["selected-track"] == index, 15)
        assert command in after["tx-hex"][len(before["tx-hex"]):]
        edges = client.json(f"{route}/device-state")["components"]["encoder"]["properties"]
        assert edges["delivered-detents"] == receipt["target_detents"]
        assert edges["gpio-edges"] - receipt["previous_gpio_edges"] == 4 * abs(delta)
        results.append({"delta": delta, "track": index, "command_hex": command,
                        "total_gpio_edges": edges["gpio-edges"]})
    return results


def run(client, args):
    out = args.out_dir
    out.mkdir(mode=0o700)
    host = client.json("units?device_id=dial")["hosts"][0]
    port = next(port for port in host["ports"] if port["id"] == args.port)
    image = args.original_bin.read_bytes() if args.original_bin else compose(args, port["pins"])
    image_hash = digest(image)
    if args.original_bin:
        assert image_hash == ORIGINAL_HASH
    report = {"status": "FAIL", "device": "dial", "firmware_sha256": image_hash,
              "port": args.port, "pins": port["pins"], "media_tracks": args.tracks,
              "validation": "virtual-device validation", "hardware": "NOT RUN"}
    route = None
    session_id = None
    try:
        uploaded = client.json("artifacts", method="POST", body=image, headers={
            "Content-Type": "application/octet-stream", "X-Artifact-Name": "dial-audioplayer.bin",
        })
        assert uploaded["sha256"] == image_hash
        firmware = client.json("firmware", method="POST", payload={
            "device_id": "dial", "kind": "merged", "artifact_id": uploaded["artifact_id"],
        })
        assert firmware["sha256"] == image_hash
        session = client.json("sessions", method="POST", payload={
            "device_id": "dial", "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 240, "units": [{
                "id": "player", "unit_id": "audioplayer", "port_id": args.port,
                "initial": {"media-track-count": args.tracks},
            }],
        })
        session_id = session["session_id"]
        route = f"sessions/{session_id}"

        def properties():
            unit, = client.json(f"{route}/units")["units"]
            assert unit["available"]
            return unit["properties"]

        serial = wait_for(client, session_id, lambda value: (
            "N9301_PROBE_PASS" in value if not args.original_bin else bool(value)
        ), timeout=100)
        if args.original_bin:
            report["input"] = exercise_original(client, route, properties)
        else:
            assert "Traceback" not in serial
            state = properties()
            if args.tracks:
                assert "N9301_PROBE_CONTROLS 0 5 15 1" in serial
                assert state["invalid-frames"] == 3
                assert state["frames-sent"] == 32 and state["frames-injected"] == 30
            else:
                assert "N9301_PROBE_NO_MEDIA" in serial
                assert state["frames-sent"] == 2 and state["frames-injected"] == 0
        report["controller"] = properties()
        report["guest_markers"] = [line for line in serial.splitlines() if line.startswith("N9301_PROBE_")]
        frame = client.raw(f"{route}/frame.png")
        (out / "frame.png").write_bytes(frame)
        report["frame"] = {"sha256": digest(frame), **png_metrics(frame)}
        report["status"] = "PASS"
    finally:
        try:
            if route:
                try:
                    evidence = client.raw(f"{route}/evidence")
                    (out / "evidence.zip").write_bytes(evidence)
                    with ZipFile(BytesIO(evidence)) as archive:
                        required = {"manifest.json", "serial.log", "units/runtime.json",
                                    "units/state.json", "units/contract.json"}
                        assert archive.testzip() is None and required.issubset(archive.namelist())
                    report["evidence_sha256"] = digest(evidence)
                finally:
                    stopped = client.json(f"{route}?purge=0&retain_flash=0", method="DELETE")
                    report["cleanup"] = {
                        "state": stopped["state"], "flash_retained": stopped.get("flash_retained"),
                        "active_leases": client.json("worker")["active_lease_count"],
                    }
                    assert report["cleanup"] == {
                        "state": "stopped", "flash_retained": False, "active_leases": 0,
                    }
        except Exception:
            report["status"] = "FAIL"
            raise
        finally:
            client.finalize_result(report, session_id=session_id)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--port", choices=("port-a", "port-b"), default="port-b")
    parser.add_argument("--tracks", type=int, choices=(0, 7), default=7)
    parser.add_argument("--driver", type=Path)
    image = parser.add_mutually_exclusive_group(required=True)
    image.add_argument("--base-firmware", type=Path)
    image.add_argument("--original-bin", type=Path)
    args = parser.parse_args()
    url = urlparse(args.api_url)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or
            url.port in (None, 8787, 8790, 8830) or url.path or url.query or url.fragment):
        parser.error("use the loopback address of a dedicated Device Service")
    if not args.original_bin and not args.driver:
        parser.error("--base-firmware requires the pinned official --driver")
    if args.original_bin and (args.port, args.tracks) != ("port-b", 7):
        parser.error("the original BIN probe requires port-b with seven indexed tracks")
    result = run(Client(args.api_url, token=args.token_file.read_text().strip()), args)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
