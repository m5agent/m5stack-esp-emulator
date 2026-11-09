"""Bind Unit evidence to the executable observed for its live local session.

The service chooses the runtime (including M5_QEMU_XTENSA). A runner-local
build path is never evidence of what that service or a remote worker executed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from web_ui_bridge import _process_executable


def observe_runtime(client, session):
    worker = session.get("worker") or {}
    proof = {
        "session_id": session["session_id"], "status": "NOT VERIFIED",
        "observed_pid": session.get("pid"),
        "firmware_sha256": session.get("firmware_sha256"),
        "worker_id": worker.get("worker_id", session.get("worker_id")),
        "worker_generation": worker.get("generation", session.get("worker_generation")),
    }
    try:
        if urlparse(client.url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise RuntimeError("remote service needs worker-side executable evidence")
        pid = session.get("pid")
        if not isinstance(pid, int) or pid <= 0 or session.get("state") != "running":
            raise RuntimeError("session has no live running PID")
        local_worker = None
        if proof["worker_id"] is not None:
            local_worker = client.json("worker", via_ui=False)
            if (local_worker.get("worker_id") != proof["worker_id"]
                    or local_worker.get("generation") != proof["worker_generation"]
                    or session["session_id"] not in local_worker.get("active_lease_ids", [])):
                raise RuntimeError("session is not owned by this service's active local worker")
            worker_pid = local_worker.get("pid")
            parent = pid
            for _ in range(8):
                if not isinstance(parent, int) or parent <= 1:
                    break
                parent = int(subprocess.check_output(["ps", "-p", str(parent), "-o", "ppid="], text=True).strip())
                if parent == worker_pid:
                    break
            if parent != worker_pid:
                raise RuntimeError("QEMU PID is not a descendant of the reported local worker")
        executable, source = _process_executable(pid)
        if not executable.name.startswith("qemu-system-"):
            raise RuntimeError("session PID is not a QEMU executable")
        observed = hashlib.sha256(executable.read_bytes()).hexdigest()
        proof.update(runtime_binary_sha256=observed, executable_name=executable.name)
        confirmed = client.json(f"sessions/{session['session_id']}", via_ui=False)
        confirmed_worker = confirmed.get("worker") or {}
        if (any(confirmed.get(key) != session.get(key)
                for key in ("session_id", "pid", "firmware_sha256"))
                or confirmed.get("state") != "running"
                or confirmed_worker.get("worker_id", confirmed.get("worker_id")) != proof["worker_id"]
                or confirmed_worker.get("generation", confirmed.get("worker_generation")) != proof["worker_generation"]):
            raise RuntimeError("session PID, firmware or generation changed while hashing")
        if local_worker:
            after = client.json("worker", via_ui=False)
            if any(after.get(key) != local_worker.get(key)
                   for key in ("pid", "worker_id", "instance_id", "generation")):
                raise RuntimeError("local worker identity changed while hashing")
            proof["local_worker_ancestry_verified"] = True
        expected = os.environ.get("M5_UNIT_EXPECT_RUNTIME_SHA256", "").strip()
        configured = os.environ.get("M5_QEMU_XTENSA", "").strip()
        if not expected and configured:
            expected = hashlib.sha256(Path(configured).read_bytes()).hexdigest()
        if expected:
            proof["expected_runtime_binary_sha256"] = expected
            if observed != expected:
                raise RuntimeError("actual session executable differs from the required runtime")
        proof.update(status="VERIFIED", method=f"Live local session PID; {source}; SHA256; lease/PID/firmware/generation confirmed again")
    except Exception as error:
        proof["error"] = str(error)
    return proof


def finalize_runtime_result(client, result, *, session_id=None):
    """Use the live proof, with an explicit lookup for hash-only result IDs."""
    proof = client.runtime_proofs.get(result.get("session_id", session_id))
    if not proof:
        proof = {"status": "NOT VERIFIED", "error": "no live runtime was observed"}
    elif "session_id" not in result:
        proof = {key: value for key, value in proof.items() if key != "session_id"}
    observed = proof.get("runtime_binary_sha256")
    result["runtime_binary_sha256"] = observed
    result["runtime_provenance"] = proof
    error = str(result.get("error", ""))
    if "Unit model is unavailable:" in error:
        result.update(status="NOT RUN", classification="runtime-infrastructure",
                      blocker="runtime lacks the requested Unit model; select a Unit-enabled runtime with M5_QEMU_XTENSA on the service")
    elif result.get("status") == "PASS" and proof.get("status") != "VERIFIED":
        expected = proof.get("expected_runtime_binary_sha256")
        if observed and expected and observed != expected:
            result.update(status="FAIL", classification="runtime-provenance",
                          blocker="actual session executable differs from the required runtime")
        else:
            result.update(status="PARTIAL", classification="runtime-provenance",
                          blocker="functional observations exist but the executed runtime identity is not verified")
    return result
