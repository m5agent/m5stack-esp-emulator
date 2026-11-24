#!/usr/bin/env python3
"""Run review-sta control firmware through a dedicated Device Service (#238).

Each case uploads one control image, creates a qemu-wifi review-sta session,
waits for the window to close, fetches /network and the evidence ZIP, then
stops with purge=0. Only bounded summaries are written; ZIPs stay in --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Must match main/review_contract.h byte for byte.
GOOD_FIXTURES = {
    "dns": {"A": {"review.test": "10.0.2.2"}},
    "http": {"routes": [
        {"method": "GET", "path": "/review/status", "status": 200, "body": "REVIEW_OK\n"},
        {"method": "POST", "path": "/review/config", "status": 200, "body": "{\"ok\":true}",
         "content_type": "application/json"},
    ]},
    "tcp": {"port": 19193, "request_hex": "4d355443500001", "response_hex": "41434b2d4d355443500001"},
    "udp": {"port": 19090, "request_hex": "4d355544500002", "response_hex": "41434b2d4d355544500002"},
    "mqtt": {"topics": ["review/#"]},
}
GOOD_ASSERTIONS = [
    {"type": "wifi_auth"}, {"type": "dhcp_lease"},
    {"type": "dns_query", "name": "review.test"},
    {"type": "http_request", "method": "GET", "path": "/review/status", "status": 200},
    {"type": "http_request", "method": "POST", "path": "/review/config", "status": 200},
    {"type": "tcp_connect", "port": 19193}, {"type": "udp_exchange", "port": 19090},
    {"type": "mqtt_connect"}, {"type": "mqtt_publish", "topic": "review/ctrl"},
]
SETUP_FIXTURES = {"dns": {"A": {"review.test": "10.0.2.2"}},
                  "http": {"routes": [{"method": "GET", "path": "/review/status", "status": 200,
                                        "body": "REVIEW_OK\n"}]}}
SETUP_ASSERTIONS = [{"type": "wifi_auth"}, {"type": "dhcp_lease"},
                    {"type": "http_request", "method": "GET", "path": "/review/status", "status": 200}]
EXPECTED = {"good": "PASS", "bad": "FAIL", "setup": "PASS", "setup-skip": "PARTIAL", "offline": "NOT_USED"}


def network_for(mode: str, timeout: float) -> dict:
    base = {"profile": "review-sta", "ssid": "M5-REVIEW", "security": "wpa2-psk",
            "password": "review-pass-v1", "timeout_seconds": timeout, "capture_pcap": True}
    if mode == "good":
        return {**base, "fixtures": GOOD_FIXTURES, "assertions": GOOD_ASSERTIONS}
    if mode == "bad":
        return {**base, "assertions": [{"type": "wifi_auth"}, {"type": "dhcp_lease"}]}
    if mode == "setup":
        return {**base, "fixtures": SETUP_FIXTURES, "assertions": SETUP_ASSERTIONS,
                "setup_inputs": [{"kind": "wait", "seconds": 60, "serial_marker": "REVIEW_CTRL SETUP_WAIT"},
                                 {"kind": "button", "control": "b", "action": "hold", "seconds": 2}]}
    if mode == "setup-skip":
        return {**base, "fixtures": SETUP_FIXTURES, "assertions": SETUP_ASSERTIONS}
    return {**base, "assertions": [{"type": "dhcp_lease"}]}


class Api:
    def __init__(self, base: str, token: str):
        self.base, self.token = base.rstrip("/"), token

    def call(self, method: str, path: str, body=None, *, raw: bytes | None = None,
             headers: dict | None = None, binary=False, timeout=120):
        request_headers = {"Authorization": f"Bearer {self.token}", **(headers or {})}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            payload = error.read()
            raise RuntimeError(f"{method} {path} -> {error.code}: {payload[:400]!r}") from None
        return payload if binary else json.loads(payload or b"{}")


def run_case(api: Api, case: dict, out: Path, timeout: float) -> dict:
    image = Path(case["image"]).read_bytes()
    sha = hashlib.sha256(image).hexdigest()
    artifact = api.call("POST", "/api/v1/artifacts", raw=image,
                        headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": Path(case["image"]).name})
    firmware = api.call("POST", "/api/v1/firmware", {
        "device_id": case["device"], "kind": "merged", "artifact_id": artifact["artifact_id"]})
    session = api.call("POST", "/api/v1/sessions", {
        "device_id": case["device"], "firmware_id": firmware["firmware_id"], "runtime": "qemu-wifi",
        "network": network_for(case["mode"], timeout), "ttl_seconds": int(timeout) + 240,
    })
    sid = session["session_id"]
    summary = {"device": case["device"], "mode": case["mode"], "firmware_sha256": sha,
               "expected_status": EXPECTED[case["mode"]], "session_id": sid}
    try:
        deadline = time.time() + timeout + 180
        network = {}
        while time.time() < deadline:
            state = api.call("GET", f"/api/v1/sessions/{sid}")
            if state["state"] in ("failed", "stopped"):
                summary["session_state"] = state["state"]
                summary["session_error"] = state.get("error")
                break
            if state["state"] == "running":
                network = api.call("GET", f"/api/v1/sessions/{sid}/network")
                if (network.get("window") or {}).get("state") == "closed":
                    break
            time.sleep(2)
        frame = None
        try:
            png = api.call("GET", f"/api/v1/sessions/{sid}/frame.png", binary=True)
            frame = {"bytes": len(png), "sha256": hashlib.sha256(png).hexdigest()}
        except RuntimeError as error:
            frame = {"error": str(error)[:200]}
        serial = api.call("GET", f"/api/v1/sessions/{sid}/serial?limit=65536").get("data", "")
        zip_bytes = api.call("GET", f"/api/v1/sessions/{sid}/evidence", binary=True, timeout=300)
        zip_path = out / f"{case['device']}-{case['mode']}-{sid}.zip"
        zip_path.write_bytes(zip_bytes)
        summary.update({
            "status": network.get("status"), "data_plane": network.get("data_plane"),
            "failure_codes": network.get("failure_codes"),
            "assertions": [{k: a.get(k) for k in ("type", "status", "code", "path", "port", "name", "topic")
                            if a.get(k) is not None} for a in network.get("assertions", [])],
            "event_types": sorted({e.get("type") for e in network.get("events", [])}),
            "auth_events": [e for e in network.get("events", []) if e.get("type") == "wifi_auth"],
            "setup": (network.get("window") or {}).get("setup"),
            "isolation": network.get("isolation"), "pcap_isolation": network.get("pcap_isolation"),
            "pcap_sha256": network.get("pcap_sha256"), "fixture_log_sha256": network.get("fixture_log_sha256"),
            "firmware_wifi_stack": network.get("firmware_wifi_stack"),
            "frame": frame,
            "serial_review_lines": [line for line in serial.splitlines() if "REVIEW_CTRL" in line][-12:],
            "evidence_zip": {"bytes": len(zip_bytes), "sha256": hashlib.sha256(zip_bytes).hexdigest()},
        })
    finally:
        stopped = api.call("POST", f"/api/v1/sessions/{sid}/stop", {"purge": False})
        summary["stop"] = {"state": stopped.get("state"), "stop_reason": stopped.get("stop_reason")}
    # The pcap is finalized at stop. Re-read the retained verdict so the
    # isolation proof and capture hash come from the same stopped session.
    final = api.call("GET", f"/api/v1/sessions/{sid}/network")
    summary["final"] = {k: final.get(k) for k in ("status", "data_plane", "failure_codes",
                                                  "pcap_isolation", "pcap_sha256")}
    summary["final"]["isolation_cleanup"] = (final.get("isolation") or {}).get("cleanup_completed")
    if summary.get("status") != final.get("status"):
        summary["status_changed_at_stop"] = [summary.get("status"), final.get("status")]
    summary["status"] = final.get("status")
    summary["result"] = "PASS" if summary.get("status") == summary["expected_status"] else "FAIL"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True, help="JSON list of {device, mode, image}")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=75)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    api = Api(args.base, args.token_file.read_text().strip())
    args.out.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.cases.read_text())
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if f"{c['device']}:{c['mode']}" in wanted or c["device"] in wanted]
    results = []
    for case in cases:
        started = time.time()
        try:
            row = run_case(api, case, args.out, args.timeout)
        except Exception as error:  # record and continue; a later PASS does not erase this
            row = {"device": case["device"], "mode": case["mode"], "result": "ERROR", "error": str(error)[:600]}
        row["wall_seconds"] = round(time.time() - started, 1)
        results.append(row)
        print(json.dumps({k: row.get(k) for k in ("device", "mode", "result", "status", "failure_codes",
                                                   "wall_seconds", "error")}), flush=True)
        (args.out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(r["result"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
