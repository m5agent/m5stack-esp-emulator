#!/usr/bin/env python3
"""Read-only and rejected-admission checks against a real Device Service.

The inventory maps every documented operation, including operations that need
live guests or a disposable control plane. This runner deliberately reports
boundary-only checks separately from successful operation coverage. It never
substitutes a 404/400 response for a working lifecycle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[3]
INVENTORY = Path(__file__).with_name("inventory_api.source.json")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Client:
    def __init__(self, api, token, output):
        self.api = api.rstrip("/")
        self.token = token
        self.output = output
        self.index = 0

    def call(self, method, path, payload=None, *, authenticated=True, extra_headers=None, raw_body=None):
        headers = dict(extra_headers or {})
        if authenticated and self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = raw_body
        if payload is not None:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.api + path, body, headers, method=method)
        started = time.monotonic()
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            status = response.code
            response_headers = dict(response.headers.items())
        self.index += 1
        stem = f"{self.index:04d}"
        (self.output / (stem + ".response")).write_bytes(raw)
        public_headers = {key: value for key, value in response_headers.items()
                          if key.lower() not in {"set-cookie", "authorization"}}
        record = {"method": method, "path": path, "payload": payload,
                  "authenticated": authenticated, "status": status,
                  "headers": public_headers, "response_sha256": hashlib.sha256(raw).hexdigest(),
                  "response_bytes": len(raw), "elapsed_seconds": round(time.monotonic() - started, 4)}
        save(self.output / (stem + ".request.json"), record)
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = None
        return record, data


def run(args):
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if not args.execute:
        print(json.dumps({"operations": len(inventory["operations"]),
                          "safe_cases": len(inventory["safe_cases"]),
                          "mode": "offline-plan", "execute_requires": "--execute --out-dir NEW_DIR"}, indent=2))
        return 0
    if args.out_dir is None:
        raise SystemExit("--out-dir is required with --execute")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    token = args.token_file.read_text(encoding="utf-8").strip() if args.token_file else ""
    client = Client(args.api, token, args.out_dir)
    results = []
    report = {"schema_version": 1, "validation": "live-device-service-http",
              "hardware_validation": "NOT RUN", "created_at": datetime.now(timezone.utc).isoformat(),
              "inventory_sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),
              "operations": len(inventory["operations"]), "cases": results}
    before, before_body = client.call("GET", "/sessions?include_stopped=0")
    before_ids = {row["session_id"] for row in before_body.get("sessions", [])} if before_body else set()
    try:
        for case in inventory["safe_cases"]:
            record, data = client.call(case["method"], case["path"], case.get("payload"),
                                       authenticated=case.get("authenticated", True),
                                       extra_headers=case.get("headers"))
            error = data.get("error") if isinstance(data, dict) else None
            request_id = next((value for key, value in record["headers"].items()
                               if key.lower() == "x-request-id"), None)
            reasons = []
            if record["status"] not in case["expected_status"]:
                reasons.append("unexpected HTTP status")
            if not request_id:
                reasons.append("missing X-Request-ID")
            if record["status"] >= 400 and not (isinstance(error, dict) and
                    isinstance(error.get("code"), str) and isinstance(error.get("message"), str)):
                reasons.append("error is not structured code/message")
            if case.get("error_codes") and (not isinstance(error,dict) or error.get("code") not in case["error_codes"]):
                reasons.append("unexpected error code")
            row = {"case_id": case["case_id"], "operation_id": case["operation_id"],
                   "coverage": case["coverage"], "status": "FAIL" if reasons else "PASS",
                   "http_status": record["status"], "error_code": error.get("code") if isinstance(error,dict) else None,
                   "response_sha256": record["response_sha256"], "response_bytes": record["response_bytes"],
                   "elapsed_seconds": record["elapsed_seconds"], "reasons": reasons}
            results.append(row)
            save(args.out_dir / "report.json", report)
    finally:
        after, after_body = client.call("GET", "/sessions?include_stopped=0")
        after_ids = {row["session_id"] for row in after_body.get("sessions", [])} if after_body else set()
        report["active_session_check"] = {"before_count": len(before_ids), "after_count": len(after_ids),
                                          "created_by_safe_cases": sorted(after_ids - before_ids)}
        report["safe_cases_session_allocation"] = "PASS" if not after_ids - before_ids else "FAIL"
        report["status"] = "PASS" if results and all(row["status"] == "PASS" for row in results) and not after_ids - before_ids else "FAIL"
        report["positive_operations_tested"] = sorted({row["operation_id"] for row in results
                                                      if row["coverage"] == "positive-read" and row["status"] == "PASS"})
        report["boundary_operations_tested"] = sorted({row["operation_id"] for row in results
                                                      if row["coverage"] == "rejection-only" and row["status"] == "PASS"})
        report["positive_operations_not_tested"] = sorted({row["operation_id"] for row in inventory["operations"]} - set(report["positive_operations_tested"]))
        save(args.out_dir / "report.json", report)
    print(json.dumps({key: report[key] for key in ["status", "operations", "safe_cases_session_allocation"]} |
                     {"cases": len(results), "positive_operations": len(report["positive_operations_tested"]),
                      "boundary_operations": len(report["boundary_operations_tested"]),
                      "failures": [row for row in results if row["status"] != "PASS"]}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    raise SystemExit(run(parser.parse_args()))
