#!/usr/bin/env python3
"""Retain each Plus method frame before acknowledging its real HTTP request."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
import time
from types import SimpleNamespace

from PIL import Image
from check_ui_frame import check_frame
import probe_protocols
import probe_ui
import run_guest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    phases, requests, lock = [], [], threading.Lock()
    resources = probe_ui.fixture_files()
    png = base64.b64decode(resources["fixture.png"]["data"])

    class Peer(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path": self.path, "at": time.monotonic()})
            if self.path.startswith("/phase/"):
                phase = {"name": self.path.removeprefix("/phase/"), "ack": threading.Event()}
                with lock:
                    phases.append(phase)
                payload = b"captured" if phase["ack"].wait(30) else b"capture timeout"
                status = 200 if payload == b"captured" else 408
            else:
                payload = png if self.path == "/fixture.png" else b'{"value":"PLUS42"}'
                status = 200
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Type", "image/png" if self.path.endswith(".png") else "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *values):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture = args.out_dir / "fixtures"
    fixture.mkdir()
    for name in ("fixture.png", "fixture-alt.png"):
        (fixture / name).write_bytes(base64.b64decode(resources[name]["data"]))
    provenance = None
    if args.candidate_dir:
        provenance = json.loads((args.candidate_dir / "provenance.json").read_text())
        module = args.candidate_dir / provenance["module"]
        if digest(module) != provenance["module_sha256"]:
            raise ValueError("candidate source digest changed")
        shutil.copyfile(module, fixture / module.name)
        run_guest.save(args.out_dir / "candidate-provenance.json", provenance)
    source = args.out_dir / "main.py"
    source.write_text(("PLUS_CANDIDATE=True\n" if args.candidate_dir else "") +
                      probe_protocols.COMMON + "\nTEST_BASE_URL=" +
                      repr("http://10.0.2.2:" + str(server.server_port)) + "\n" +
                      Path(__file__).with_name("probe_plus_methods.py").read_text())

    def capture(api, session_id, state):
        with lock:
            pending = [phase for phase in phases if not phase["ack"].is_set()]
        for phase in pending:
            folder = args.out_dir / phase["name"]
            folder.mkdir(exist_ok=False)
            frame = api.raw("sessions/" + session_id + "/frame.png")
            (folder / "frame.png").write_bytes(frame)
            phase.update(frame_sha256=hashlib.sha256(frame).hexdigest(),
                         session_id=session_id, runtime_pid=state.get("pid"))
            phase["ack"].set()

    try:
        result = run_guest.run(SimpleNamespace(
            api=args.api, token_file=args.token_file, device=args.device,
            runtime="qemu-wifi", network={"profile": "generic-observe", "capture_pcap": True,
                                         "attempts": 1, "expected_markers": ["PLUS_METHODS_DONE"]},
            source=source, out_dir=args.out_dir / "execution", done_marker="PLUS_METHODS_DONE",
            timeout=180, prepare_timeout=600, base_image=None, expected_base_sha256=None,
            fixture_dir=fixture, firmware_lane="stock-frozen-with-candidate-python-override" if args.candidate_dir else "stock-frozen",
            on_session_poll=capture))
    finally:
        with lock:
            for phase in phases:
                phase["ack"].set()
        server.shutdown()
        server.server_close()
        thread.join()
        run_guest.save(args.out_dir / "peer.json", requests)

    execution = json.loads((args.out_dir / "execution/report.json").read_text())
    serial = (args.out_dir / "execution/serial.txt").read_text()
    rows = [json.loads(line.split(" ", 1)[1]) for line in serial.splitlines() if line.startswith("M5EMU_UI_RESULT ")]
    captured = {phase["name"]: phase for phase in phases if "frame_sha256" in phase}
    cases = []
    for row in rows:
        target, method = row["api_target"], row["method"]
        if target not in ("label_plus.LabelPlus", "image_plus.ImagePlus"):
            continue
        phase = ("label_" if target.startswith("label") else "image_") + method
        item = {"label": phase, "api_target": target, "method": method,
                "execution_id": execution["session_id"], "source_sha256": execution["source_sha256"],
                "results": [row], "frame_oracles": []}
        if phase in captured:
            frame_path = args.out_dir / phase / "frame.png"
            frame = Image.open(frame_path).convert("RGB")
            if target.startswith("label") and method != "setVisible":
                actual = frame.crop((10, 10, 110, 50))
                control = frame.crop((130, 10, 230, 50))
                ink = sum(max(pixel) > 128 for pixel in control.getdata())
                ok = ink > 10 and actual.tobytes() == control.tobytes()
                oracle = {"status": "FRAME_PASS" if ok else "FAIL", "control_ink_pixels": ink,
                          "actual_sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
                          "control_sha256": hashlib.sha256(control.tobytes()).hexdigest(),
                          "scope": "actual Plus mutation matches independently constructed native expected text/font/scale/position, in separate nonoverlapping regions"}
            elif method == "setVisible":
                box = [10, 10, 110, 50] if target.startswith("label") else [10, 10, 26, 26]
                oracle = check_frame(frame_path.read_bytes(), {"kind": "color_region", "rgb": 0x0B1014,
                                    "box": box, "minimum": (box[2]-box[0])*(box[3]-box[1])}, 8)
                before = args.out_dir / (phase + "_before") / "frame.png"
                pixels = Image.open(before).convert("RGB").crop(tuple(box))
                visible = sum(max(pixel) > 128 for pixel in pixels.getdata())
                oracle["before_visible_pixels"] = visible
                if visible <= 10:
                    oracle["status"] = "FAIL"
                oracle["before_frame_sha256"] = digest(before)
            else:
                offset = 26 if method == "setScale" else 12
                colors = [0xFFFF00, 0x0000FF, 0x00FF00, 0xFF0000] if method == "setImage" else [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00]
                positions = [(12, 12), (10+offset, 12), (12, 10+offset), (10+offset, 10+offset)]
                oracle = check_frame(frame_path.read_bytes(), {"kind": "pixels", "points": [[x, y, color] for (x, y), color in zip(positions, colors)]}, 8)
            item["frame_sha256"] = captured[phase]["frame_sha256"]
            item["frame_oracles"] = [{"method": method, **oracle}]
            run_guest.save(args.out_dir / phase / "oracle.json", oracle)
        cases.append(item)
    report = {**execution, "cases": cases,
              "implementation_lane": "candidate-source-override" if args.candidate_dir else "reference-frozen-implementation",
              "scope": "Only actual Plus-object calls and each pre-acknowledgement retained frame; native base controls never grant an unexecuted Plus method PASS."}
    report["source_fixture"] = {"png_sha256": hashlib.sha256(png).hexdigest(),
                                "candidate_provenance": provenance}
    run_guest.save(args.out_dir / "report.json", report)
    print(json.dumps({"device": args.device, "status": report["status"],
                      "frames": {case["label"]: [row["status"] for row in case["frame_oracles"]] for case in cases}}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--device", choices=("cores3", "cardputer-adv"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path)
    raise SystemExit(run(parser.parse_args()))
