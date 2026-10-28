#!/usr/bin/env python3
"""Cold Device Service probe with bounded marker-triggered host observations.

The underlying runner owns upload/session/evidence-before-stop lifecycle. This
wrapper adds real API input/QOM operations after guest readiness markers; it
does not start QEMU directly or synthesize guest sensor values.
"""

import argparse
import json
from pathlib import Path
import time

import run_guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--device", choices=run_guest.DEVICE_CHOICES, required=True)
    parser.add_argument("--runtime", default="qemu")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--append-code", action="append")
    parser.add_argument("--base-image", type=Path)
    parser.add_argument("--expected-base-sha256")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--done-marker", required=True)
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--drive-json", type=Path, help="mapping from guest marker to API action list")
    parser.add_argument("--runtime-env-json", type=Path, help="explicit local diagnostic runtime environment, sent through /sessions")
    parser.add_argument("--sd-image", type=Path, help="isolated writable raw SD fixture uploaded through the artifact API")
    parser.add_argument("--fixture-dir", type=Path, help="explicit guest fixture directory copied into LittleFS")
    args = parser.parse_args()
    schedule = json.loads(args.drive_json.read_text()) if args.drive_json else {}
    runtime_env = json.loads(args.runtime_env_json.read_text()) if args.runtime_env_json else None
    actions = []

    class HardwareApi(run_guest.Api):
        session_id = None
        observed = ""

        def json(self, path, method="GET", payload=None, **kwargs):
            if path == "sessions" and method == "POST":
                payload = dict(payload)
                if runtime_env is not None:
                    payload["runtime_env"] = runtime_env
                if args.sd_image is not None:
                    artifact = super().json("artifacts", "POST", body=args.sd_image.read_bytes(), headers={
                        "Content-Type": "application/octet-stream", "X-Artifact-Name": "api-sweep-sd.img"})
                    payload["storage"] = {"sd_image_artifact_id": artifact["artifact_id"]}
            response = super().json(path, method, payload, **kwargs)
            if path == "sessions" and method == "POST":
                self.session_id = response["session_id"]
            if method == "GET" and self.session_id and path.startswith("sessions/" + self.session_id + "/serial?"):
                self.observed += response["data"]
                for marker in list(schedule):
                    if marker not in self.observed:
                        continue
                    pending = schedule.pop(marker)
                    for action in pending:
                        if "sleep_seconds" in action:
                            delay = float(action["sleep_seconds"])
                            if not 0 <= delay <= 10:
                                raise ValueError("host action delay must be 0..10 seconds")
                            time.sleep(delay)
                            continue
                        endpoint = "sessions/" + self.session_id + "/" + action["endpoint"].lstrip("/")
                        row = {"marker": marker, "endpoint": action["endpoint"], "method": action.get("method", "POST"), "payload": action.get("payload")}
                        try:
                            row["response"] = super().json(endpoint, action.get("method", "POST"), action.get("payload"))
                            row["status"] = "OBSERVED"
                        except Exception as error:
                            row["status"] = "ERROR"
                            row["error"] = str(error)
                        actions.append(row)
                        run_guest.save(args.out_dir / "host-actions.json", actions)
            return response

    run_guest.Api = HardwareApi
    result = run_guest.run(args)
    run_guest.save(args.out_dir / "host-actions.json", actions)
    run_guest.save(args.out_dir / "pending-host-markers.json", schedule)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
