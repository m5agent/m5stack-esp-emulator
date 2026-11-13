#!/usr/bin/env python3
"""Same original BIN, visible Device Service session, independent Pillow oracle.

Output is PRIVATE raw evidence (frames/ZIP/session responses). Publish a reviewed
bounded summary only. This performs no Burner submission or firmware rewriting.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import zipfile

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--device", default="sticks3")
    parser.add_argument("--rotation", required=True, type=int, choices=(0, 90, 180, 270))
    parser.add_argument("--observe-seconds", type=float, default=30)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    token = args.token_file.read_text().strip()

    def request(path, *, method="GET", payload=None, body=None, headers=None):
        if payload is not None:
            body = json.dumps(payload).encode()
        request_headers = {"Authorization": "Bearer " + token,
                           "Content-Type": "application/json" if payload is not None else "application/octet-stream",
                           **(headers or {})}
        req = urllib.request.Request(args.base_url.rstrip("/") + "/api/v1/" + path,
                                     data=body, method=method, headers=request_headers)
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read(), dict(response.headers)

    def api(path, **kwargs):
        data, _ = request(path, **kwargs)
        return json.loads(data)

    def save(name, value):
        (args.out / name).write_text(json.dumps(value, indent=2) + "\n")

    raw = args.firmware.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.sha256:
        raise ValueError("original firmware SHA mismatch")
    artifact = api("artifacts", method="POST", body=raw,
                   headers={"X-Artifact-Name": "original-frame-validation.bin"})
    firmware = api("firmware", method="POST", payload={"device_id": args.device,
                   "kind": "merged", "artifact_id": artifact["artifact_id"]})
    save("firmware.json", firmware)
    created = api("sessions", method="POST", payload={"device_id": args.device,
                  "firmware_id": firmware["firmware_id"], "ttl_seconds": 600,
                  "ready_timeout_seconds": 3})
    save("created.json", created)
    session = created.get("session", created)
    sid = session["session_id"]
    prefix = "sessions/" + sid
    result = {"schema_version": 1, "validation_kind": "virtual-device validation",
              "device_id": args.device, "original_sha256": args.sha256,
              "normalized_sha256": firmware["sha256"], "requested_rotation_cw": args.rotation}
    try:
        until = time.monotonic() + args.observe_seconds
        while time.monotonic() < until:
            snapshot = api(prefix)
            if snapshot.get("state") in {"failed", "stopped"}:
                raise RuntimeError("guest stopped before observation")
            time.sleep(min(2, max(0, until - time.monotonic())))
        raw_png, raw_headers = request(prefix + "/frame.png?max_age_ms=1000")
        display_png, display_headers = request(prefix + "/frame.png?max_age_ms=1000&orient=display")
        (args.out / "raw.png").write_bytes(raw_png)
        (args.out / "display.png").write_bytes(display_png)
        save("raw-headers.json", raw_headers)
        save("display-headers.json", display_headers)
        assert raw_headers["X-Frame-Capture-Seq"] == display_headers["X-Frame-Capture-Seq"]
        assert raw_headers["X-Frame-SHA256"] == display_headers["X-Frame-Raw-SHA256"]
        assert int(raw_headers["X-Frame-Rotation"]) == args.rotation
        image = Image.open(io.BytesIO(raw_png)).convert("RGB")
        transpose = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                     270: Image.Transpose.ROTATE_90}
        expected = image if args.rotation == 0 else image.transpose(transpose[args.rotation])
        actual = Image.open(io.BytesIO(display_png)).convert("RGB")
        assert expected.size == actual.size and expected.tobytes() == actual.tobytes()
        assert any(any(pixel) for pixel in actual.getdata()), "black framebuffer"
        presentation = json.loads(raw_headers["X-Frame-Presentation"])
        result.update(status="PASS", same_sample=True, independent_pixel_comparison=True,
                      rotation_cw=int(raw_headers["X-Frame-Rotation"]),
                      presentation=presentation, raw_size=list(image.size), display_size=list(actual.size),
                      raw_frame_sha256=hashlib.sha256(raw_png).hexdigest(),
                      display_frame_sha256=hashlib.sha256(display_png).hexdigest())
        save("snapshot.json", api(prefix))
        save("serial.json", api(prefix + "/serial?offset=0&limit=262144"))
    except Exception as error:
        result.update(status="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        try:
            bundle, _ = request(prefix + "/evidence?include=frames,manifest,serial")
            (args.out / "evidence.zip").write_bytes(bundle)
            result["evidence_zip_sha256"] = hashlib.sha256(bundle).hexdigest()
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                result["evidence_has_presentation"] = "presentation" in manifest.get("frame", {})
            result["evidence_before_stop"] = True
        finally:
            stopped = api(prefix + "?purge=0", method="DELETE")
            save("stopped.json", stopped)
            history = api(prefix)
            save("history.json", history)
            result["stopped"] = history.get("state") == "stopped"
            result["history_retained"] = True
            result["lease_released"] = history.get("worker", {}).get("lease_active") is False
            result["mutable_flash_released"] = history.get("flash_retained") is False
            save("summary.json", result)
    print(json.dumps({key: result[key] for key in ("device_id", "status", "rotation_cw", "same_sample", "stopped")}, sort_keys=True))


if __name__ == "__main__":
    main()
