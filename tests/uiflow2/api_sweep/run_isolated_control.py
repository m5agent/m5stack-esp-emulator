#!/usr/bin/env python3
"""Exercise real HTTP control/storage mutations in an owned disposable service.

This uses the production Handler and DeviceService with no mocked stores or
runtime. It does not allocate guests, flash firmware, or contact a remote worker.
All mutations are restricted to the fresh state directory inside --out-dir.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import DeviceService  # noqa: E402
from serve import Handler  # noqa: E402
from worker_auth import sign_worker_request  # noqa: E402
from run_device_api import Client, INVENTORY, save  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args):
    if not args.execute:
        print(json.dumps({"mode": "offline-plan", "guests_allocated": 0,
                          "mutations": ["artifact upload/chunk/complete/abort/delete", "immutable package store",
                                        "worker HMAC lifecycle", "job submit/claim/heartbeat/result/cancel",
                                        "local drain/resume", "owned retention prune"]}, indent=2))
        return 0
    if args.out_dir is None:
        raise SystemExit("--out-dir is required with --execute")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    token = secrets.token_urlsafe(32)
    service = DeviceService(state_dir=args.out_dir / "service-state", api_token=token)

    class AuditHandler(Handler):
        api_token = token
        previous_api_token = None

        def log_message(self, *_args):
            pass

    AuditHandler.service = service
    server = ThreadingHTTPServer(("127.0.0.1", 0), AuditHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(f"http://127.0.0.1:{server.server_port}/api/v1", token, args.out_dir)
    results = []
    report = {"schema_version": 1, "validation": "real-http-owned-control-plane",
              "runtime_mocked": False, "hardware_validation": "NOT RUN", "guests_allocated": 0,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "inventory_sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(), "cases": results,
              "status": "FAIL"}

    def call(operation, path=None, payload=None, *, status=200, signed=None, headers=None, raw=None, label=""):
        method, template = operation.split(" ", 1)
        path = path or template
        headers = dict(headers or {})
        if signed:
            body = json.dumps(payload, allow_nan=False).encode("utf-8") if payload is not None else (raw or b"")
            headers.update(sign_worker_request(token, signed, method, "/api/v1" + path, body))
        record, data = client.call(method, path, payload, extra_headers=headers, raw_body=raw)
        row = {"operation_id": operation, "label": label, "coverage": "positive" if status < 400 else "rejection-only",
               "http_status": record["status"], "expected_status": status,
               "response_sha256": record["response_sha256"], "response_bytes": record["response_bytes"],
               "elapsed_seconds": record["elapsed_seconds"], "status": "PASS" if record["status"] == status else "FAIL"}
        results.append(row)
        save(args.out_dir / "report.json", report)
        require(record["status"] == status, f"{operation}: expected {status}, observed {record['status']}: {data}")
        return data

    try:
        local = call("POST /worker/drain")
        require(local["worker"]["state"] == "drained", "local worker did not drain")
        local = call("POST /worker/resume")
        require(local["worker"]["state"] == "ready", "local worker did not resume")

        contents = b"M5 Device Service actual HTTP artifact\n"
        uploaded = call("POST /artifacts", status=201, raw=contents,
                        headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": "api-sweep.txt"})
        artifact_id = hashlib.sha256(contents).hexdigest()
        require(uploaded["artifact_id"] == artifact_id, "artifact bytes not content addressed")
        require(call("GET /artifacts/{artifact_id}", "/artifacts/" + artifact_id)["size"] == len(contents), "artifact size differs")
        require(any(row["artifact_id"] == artifact_id for row in call("GET /artifacts")["artifacts"]), "artifact missing from list")
        call("DELETE /artifacts/{artifact_id}", "/artifacts/" + artifact_id)
        call("GET /artifacts/{artifact_id}", "/artifacts/" + artifact_id, status=404, label="deleted-owned-artifact")

        stream = b"streamed bytes through actual contiguous chunks\x00\xff"
        streaming = call("POST /artifact-uploads", payload={"expected_size": len(stream),
                         "expected_sha256": hashlib.sha256(stream).hexdigest(), "name": "api-stream.bin"}, status=202)
        upload_id = streaming["upload_id"]
        stream_path = "/artifact-uploads/" + upload_id
        call("GET /artifact-uploads/{upload_id}", stream_path)
        call("POST /artifact-uploads/{upload_id}/complete", stream_path + "/complete", status=409, label="incomplete")
        for offset, chunk in ((0, stream[:13]), (13, stream[13:])):
            progress = call("POST /artifact-uploads/{upload_id}/chunks", stream_path + "/chunks", raw=chunk, status=202,
                            headers={"X-Chunk-Offset": str(offset), "X-Chunk-SHA256": hashlib.sha256(chunk).hexdigest()})
            require(progress["next_offset"] == offset + len(chunk), "stream offset not committed")
        call("POST /artifact-uploads/{upload_id}/chunks", stream_path + "/chunks", raw=stream[:13], status=409,
             headers={"X-Chunk-Offset": "0", "X-Chunk-SHA256": hashlib.sha256(stream[:13]).hexdigest()}, label="stale-chunk")
        completed = call("POST /artifact-uploads/{upload_id}/complete", stream_path + "/complete", status=201)
        require(completed["artifact_id"] == hashlib.sha256(stream).hexdigest(), "stream complete digest differs")
        require(call("POST /artifact-uploads/{upload_id}/complete", stream_path + "/complete", status=201)["artifact_id"] == completed["artifact_id"], "complete retry differs")
        aborted = call("POST /artifact-uploads", payload={"expected_size": 1, "expected_sha256": hashlib.sha256(b"x").hexdigest()}, status=202)
        call("DELETE /artifact-uploads/{upload_id}", "/artifact-uploads/" + aborted["upload_id"])
        call("GET /artifact-uploads/{upload_id}", "/artifact-uploads/" + aborted["upload_id"], status=404, label="aborted")

        package = {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {
            "main.py": {"encoding": "utf8", "data": "from app import value\nprint(value)\n"},
            "app.py": {"encoding": "utf8", "data": "value = 42\n"},
            "assets/raw.bin": {"encoding": "base64", "data": base64.b64encode(b"\x00\xff").decode()},
        }}
        stored = call("POST /program-revisions", payload=package, status=201)["revision"]
        revision_id = stored["revision_id"]
        metadata = call("GET /program-revisions/{revision_id}", "/program-revisions/" + revision_id)
        require(metadata["revision"]["revision_id"] == revision_id, "revision metadata identity differs")
        readback = call("GET /program-revisions/{revision_id}/files", "/program-revisions/" + revision_id + "/files")
        report["checkpoint_file_response_keys"] = sorted(readback)
        require(set(readback["files"]) == set(package["files"]), "checkpoint file set differs")
        for name, expected_file in package["files"].items():
            expected_bytes = expected_file["data"].encode() if expected_file["encoding"] == "utf8" else base64.b64decode(expected_file["data"])
            actual = readback["files"][name]
            actual_bytes = actual["data"].encode() if actual["encoding"] == "utf8" else base64.b64decode(actual["data"])
            require(actual_bytes == expected_bytes, "checkpoint bytes differ: " + name)
        alternate = json.loads(json.dumps(package))
        alternate["files"]["app.py"] = {"encoding": "base64", "data": base64.b64encode(b"value = 42\n").decode()}
        retried = call("POST /program-revisions", payload=alternate, status=201)["revision"]
        require(retried["revision_id"] == revision_id and retried["created_at"] == stored["created_at"], "immutable checkpoint retry changed identity/time")

        if args.firmware_device:
            spec = service.specs[args.firmware_device]
            require(spec.reference_available, "exact local reference firmware is unavailable")
            reference = spec.reference_path.read_bytes()
            reference_sha = hashlib.sha256(reference).hexdigest()
            report["firmware_reference"] = {"device_id": spec.id, "sha256": reference_sha, "bytes": len(reference)}
            firmware_artifact = call("POST /artifacts", raw=reference, status=201,
                                     headers={"X-Artifact-Name": "api-sweep-reference.bin", "Content-Type": "application/octet-stream"})
            require(firmware_artifact["artifact_id"] == reference_sha, "reference upload bytes changed")
            firmware = call("POST /firmware", payload={"device_id": spec.id, "kind": "merged",
                            "artifact_id": firmware_artifact["artifact_id"]}, status=201)
            firmware_id = firmware["firmware_id"]
            normalized = reference.ljust(spec.flash_size, b"\xff")
            require(firmware_id == hashlib.sha256(normalized).hexdigest(), "normalized firmware bytes differ")
            require(call("GET /firmware/{firmware_id}", "/firmware/" + firmware_id)["firmware_id"] == firmware_id, "firmware metadata identity differs")
            call("POST /firmware/analyze", payload={"firmware_id": firmware_id})
            call("GET /firmware/{firmware_id}/analysis", "/firmware/" + firmware_id + "/analysis")
            imported = call("POST /firmware/import", payload={"device_id": spec.id, "artifact_id": firmware_artifact["artifact_id"]}, status=201)
            require(imported["firmware_id"] == firmware_id, "BIN import changed normalized bytes")
            composed = call("POST /firmware/uiflow", payload={"device_id": spec.id,
                            "files": {"main.py": "print('API_SWEEP_COMPOSER_READY')\n"}}, status=201)
            require(composed["device_id"] == spec.id and composed["source"]["kind"] == "uiflow", "UIFlow composer did not preserve source provenance")
            report["composed_firmware"] = {"firmware_id": composed["firmware_id"], "sha256": composed["sha256"],
                                            "source_sha256": composed["source"]["metadata"]["source_sha256"],
                                            "execution": "NOT RUN in this control-plane probe"}

        identity = {"worker_id": "api-sweep-owned-worker", "instance_id": "api-sweep-instance", "generation": 1}
        worker = call("POST /workers", payload={**identity, "capabilities": {"qemu": True}, "active_lease_ids": [],
                      "endpoint": "http://127.0.0.1:1", "stale_after_seconds": 30}, status=201)
        require(worker["worker"]["state"] == "ready", "remote directory worker not ready")
        call("GET /workers")
        worker_path = "/workers/" + identity["worker_id"]
        call("POST /workers/{worker_id}/heartbeat", worker_path + "/heartbeat", {**identity, "active_lease_ids": []}, signed=identity)
        job_request = {"request": {"device_id": "cores3"}, "required_capabilities": {"qemu": True},
                       "idempotency_key": "owned-http-audit-job", "max_attempts": 2}
        job = call("POST /jobs", payload=job_request, status=201)["job"]
        require(call("POST /jobs", payload=job_request, status=201)["job"]["job_id"] == job["job_id"], "job idempotency allocated twice")
        call("GET /jobs")
        job_path = "/jobs/" + job["job_id"]
        require(call("GET /jobs/{job_id}", job_path)["job"]["status"] == "queued", "job not queued")
        claimed = call("POST /jobs/claim", payload=identity, signed=identity)["job"]
        require(claimed["job_id"] == job["job_id"] and claimed["status"] == "leased", "job claim did not lease submitted job")
        lease = {**identity, "lease_id": claimed["lease"]["lease_id"]}
        call("POST /jobs/{job_id}/heartbeat", job_path + "/heartbeat", lease, signed=identity)
        result = call("POST /jobs/{job_id}/result", job_path + "/result", {**lease, "state": "PASS", "summary": {"http_control_plane_only": True}}, signed=identity)
        require(result["job"]["status"] == "completed", "job result did not complete")
        cancel = call("POST /jobs", payload={"request": {"device_id": "cores3"}}, status=201)["job"]
        require(call("POST /jobs/{job_id}/cancel", "/jobs/" + cancel["job_id"] + "/cancel", {"reason": "owned audit"})["job"]["status"] == "cancelled", "job cancel did not become terminal")
        call("POST /workers/{worker_id}/results", worker_path + "/results", {**identity, "lease_id": lease["lease_id"], "state": "PASS"}, signed=identity, status=201)
        require(call("POST /workers/{worker_id}/drain", worker_path + "/drain", identity, signed=identity)["worker"]["state"] == "drained", "remote directory worker did not drain")
        require(call("POST /workers/{worker_id}/stop", worker_path + "/stop", identity, signed=identity)["worker"]["state"] == "stopped", "remote directory worker did not stop")

        call("POST /storage/prune", "/storage/prune?include_cache=0")
        require(call("DELETE /sessions", "/sessions?state=stopped&purge=0")["cleared"] == 0, "isolated service unexpectedly had guest history")
        require(call("GET /sessions")["sessions"] == [], "isolated HTTP mutations allocated a guest")
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["positive_operations_tested"] = sorted({row["operation_id"] for row in results if row["coverage"] == "positive" and row["status"] == "PASS"})
        report["guests_allocated"] = len(service.list_sessions()["sessions"])
        save(args.out_dir / "report.json", report)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        service.close_all()
    print(json.dumps({"status": report["status"], "cases": len(results),
                      "positive_operations": len(report["positive_operations_tested"]),
                      "guests_allocated": report["guests_allocated"]}, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--firmware-device", help="also exercise actual reference firmware upload/import/composition; does not execute a guest")
    parser.add_argument("--execute", action="store_true")
    raise SystemExit(run(parser.parse_args()))
