#!/usr/bin/env python3
"""Exercise the fail-closed Device Service runtime ACL over real HTTP."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from device_service import DeviceService, DeviceSession, ServiceError  # noqa: E402
from runtime_acl import RuntimeACL, RuntimeACLConfigError, RuntimeACLError  # noqa: E402
from serve import Handler  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deny_policy_document() -> dict:
    return {
        "schema_version": 1,
        "devices": {
            "sticks3": {
                "allow": ["program.read"],
            }
        },
    }


def package_policy_document() -> dict:
    return {
        "schema_version": 1,
        "devices": {
            "sticks3": {
                "allow": [
                    "program.read",
                    "program.execute",
                    "filesystem.write",
                ],
                "execution_entrypoints": ["main.py"],
                "filesystem_write_allow": ["main.py", "lib/"],
                "filesystem_write_deny": ["lib/private/"],
            }
        },
    }


class Evidence:
    def __init__(self):
        self.checks = []

    def add(self, name: str, passed: bool, **detail):
        self.checks.append({"name": name, "status": "PASS" if passed else "FAIL", **detail})
        if not passed:
            raise AssertionError(name)

    def result(self) -> str:
        return "PASS" if all(row["status"] == "PASS" for row in self.checks) else "FAIL"


class RuntimeACLHTTPServer:
    def __init__(self, service, session):
        class RuntimeACLHandler(Handler):
            api_token = "runtime-acl-evidence-token"
            previous_api_token = None

            def log_message(self, *args):
                pass

        RuntimeACLHandler.service = service
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeACLHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method: str, path: str, payload=None):
        headers = {"Authorization": "Bearer runtime-acl-evidence-token"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=3,
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw)
        finally:
            connection.close()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def default_device_session(service: DeviceService, root: Path) -> DeviceSession:
    firmware_path = root / "firmware.bin"
    firmware_path.write_bytes(b"\xff" * 1024)
    session = DeviceSession(
        service,
        session_id="a" * 32,
        spec=service.specs["sticks3"],
        firmware_id="b" * 64,
        firmware_path=firmware_path,
        firmware_sha="b" * 64,
        firmware_source="uploaded",
        source_artifacts=[],
        ttl_seconds=60,
        ready_marker=None,
        ready_timeout=10,
        ready_conditions=None,
        program_transport="uart-repl",
        initial_state="running",
        persist=False,
    )
    service._sessions[session.id] = session
    return session


def expect_denied(evidence: Evidence, operation: str, call, policy_id: str):
    try:
        call()
    except ServiceError as error:
        evidence.add(
            f"{operation} denied",
            error.code == "runtime_acl_denied"
            and error.status == 403
            and error.extra.get("operation") == operation
            and error.extra.get("policy_id") == policy_id,
            code=error.code,
            http_status=error.status,
            policy_id=error.extra.get("policy_id"),
        )
        return
    evidence.add(f"{operation} denied", False)


def request_health(port: int, path: str) -> dict | None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            return None
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        connection.close()


def run(output: Path) -> dict:
    evidence = Evidence()
    started_at = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="m5-runtime-acl-") as temporary:
        root = Path(temporary)
        policy_path = root / "runtime-acl.json"
        deny_document = deny_policy_document()
        policy_path.write_text(json.dumps(deny_document), encoding="utf-8")
        deny_policy = RuntimeACL.from_file(policy_path)
        evidence.add(
            "policy file loads",
            deny_policy.policy_id is not None and len(deny_policy.policy_id) == 64,
            policy_id=deny_policy.policy_id,
        )
        evidence.add(
            "unconfigured policy retains compatibility",
            all(
                RuntimeACL.unconfigured().check("sticks3", operation) is None
                for operation in (
                    "serial.read",
                    "input.write",
                    "guest.reset",
                    "program.execute",
                    "flash.read",
                )
            ),
        )
        try:
            deny_policy.check("cores3", "program.read")
        except RuntimeACLError as error:
            evidence.add(
                "undeclared device denied",
                error.reason == "device_not_allowed",
            )
        else:
            evidence.add("undeclared device denied", False)

        symlink_path = root / "runtime-acl-link.json"
        symlink_path.symlink_to(policy_path)
        try:
            RuntimeACL.from_file(symlink_path)
        except RuntimeACLConfigError:
            evidence.add("policy symlink rejected", True)
        else:
            evidence.add("policy symlink rejected", False)
        invalid_path = root / "invalid-policy.json"
        invalid_path.write_text("{}\n", encoding="utf-8")
        process = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "serve.py"),
                "0",
                "--runtime-acl-file",
                str(invalid_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        cli_output = process.stdout + process.stderr
        evidence.add(
            "invalid policy fails before listener",
            process.returncode != 0
            and "schema_version must be 1" in cli_output
            and "Peripheral interfaces:" not in cli_output,
            returncode=process.returncode,
        )

        reload_path = root / "reload-policy.json"
        reload_path.write_text(json.dumps(deny_document), encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            reload_port = listener.getsockname()[1]
        reload_process = subprocess.Popen(
            [
                sys.executable,
                str(TOOLS / "serve.py"),
                str(reload_port),
                "--bind",
                "127.0.0.1",
                "--state-dir",
                str(root / "reload-state"),
                "--runtime-acl-file",
                str(reload_path),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        reload_evidence = False
        try:
            deadline = time.monotonic() + 10
            capacity = None
            while time.monotonic() < deadline:
                capacity = request_health(reload_port, "/api/v1/capacity")
                if capacity is not None:
                    break
                time.sleep(0.1)
            evidence.add(
                "SIGHUP server reaches capacity",
                capacity is not None
                and capacity["runtime_acl"]["policy_id"] == deny_policy.policy_id,
            )
            reload_document = {
                "schema_version": 1,
                "devices": {"sticks3": {"allow": ["serial.read"]}},
            }
            reload_policy = RuntimeACL.from_document(reload_document)
            reload_path.write_text(json.dumps(reload_document), encoding="utf-8")
            os.kill(reload_process.pid, signal.SIGHUP)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                capacity = request_health(reload_port, "/api/v1/capacity")
                if (
                    capacity is not None
                    and capacity["runtime_acl"]["policy_id"] == reload_policy.policy_id
                ):
                    break
                time.sleep(0.1)
            evidence.add(
                "SIGHUP publishes valid policy",
                capacity is not None
                and capacity["runtime_acl"]["policy_id"] == reload_policy.policy_id,
            )
            reload_path.write_text("{}\n", encoding="utf-8")
            os.kill(reload_process.pid, signal.SIGHUP)
            time.sleep(1.2)
            capacity = request_health(reload_port, "/api/v1/capacity")
            reload_evidence = bool(
                reload_process.poll() is None
                and capacity is not None
                and capacity["runtime_acl"]["policy_id"] == reload_policy.policy_id
            )
        finally:
            reload_process.terminate()
            try:
                reload_output, _ = reload_process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                reload_process.kill()
                reload_output, _ = reload_process.communicate(timeout=5)
        evidence.add(
            "invalid SIGHUP preserves active policy",
            reload_evidence
            and "security configuration reload failed" in reload_output,
        )

        service = DeviceService(
            state_dir=root / "state",
            runtime_acl=deny_policy,
        )
        session = default_device_session(service, root)
        server = RuntimeACLHTTPServer(service, session)
        try:
            status, session_body = server.request(
                "GET",
                f"/api/v1/sessions/{session.id}",
            )
            evidence.add(
                "session exposes effective ACL",
                status == 200
                and session_body["runtime_acl"]["status"] == "ENFORCED"
                and session_body["runtime_acl"]["policy_id"] == deny_policy.policy_id,
            )
            status, capacity = server.request("GET", "/api/v1/capacity")
            evidence.add(
                "capacity exposes semantic policy hash",
                status == 200
                and capacity["runtime_acl"]["policy_id"] == deny_policy.policy_id,
            )

            status, body = server.request(
                "GET",
                f"/api/v1/sessions/{session.id}/program",
            )
            evidence.add(
                "program read allowed",
                status == 200 and body["program"] is None,
            )
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/program",
                {"source": "print(1)", "expected_execution_id": None},
            )
            evidence.add(
                "program execute denied before console",
                status == 403
                and body["error"]["code"] == "runtime_acl_denied"
                and body["error"]["operation"] == "program.execute"
                and body["error"]["policy_id"] == deny_policy.policy_id,
            )
            status, body = server.request(
                "GET",
                f"/api/v1/sessions/{session.id}/serial",
            )
            evidence.add(
                "serial read denied",
                status == 403 and body["error"]["operation"] == "serial.read",
            )
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/wait",
                {"ready_marker": "PASS", "timeout_seconds": 1},
            )
            evidence.add(
                "serial marker wait denied",
                status == 403 and body["error"]["operation"] == "serial.read",
            )
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/input",
                {"kind": "key", "key": "a"},
            )
            evidence.add(
                "input write denied before QMP",
                status == 403 and body["error"]["operation"] == "input.write",
            )
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/reset",
                {},
            )
            evidence.add(
                "guest reset denied before QMP",
                status == 403 and body["error"]["operation"] == "guest.reset",
            )
            status, body = server.request(
                "GET",
                f"/api/v1/sessions/{session.id}/flash",
            )
            evidence.add(
                "flash read denied",
                status == 403 and body["error"]["operation"] == "flash.read",
            )
            expect_denied(
                evidence,
                "program.interrupt",
                lambda: session.interrupt_program(expected_execution_id=None),
                deny_policy.policy_id,
            )

            hidden_policy = RuntimeACL.from_document(
                {
                    "schema_version": 1,
                    "devices": {"sticks3": {"allow": []}},
                }
            )
            service.runtime_acl = hidden_policy
            snapshot = session.snapshot()
            session.virtual_flash = session.firmware_path
            session.serial0.write_text("privileged serial\n")
            bundle = session.evidence_bundle(
                {"manifest", "serial", "logs", "flash"}
            )
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
            evidence.add(
                "snapshot and evidence hide denied runtime data",
                "program" not in snapshot
                and not any(name.startswith("programs/") for name in names)
                and "serial.log" not in names
                and "qemu.stdout" not in names
                and "flash/virtual-flash.bin" not in names
                and manifest["program_redaction"]["reason"]
                == "runtime_acl_program_read_denied"
                and manifest["runtime_output_redaction"]["reason"]
                == "runtime_acl_serial_read_denied"
                and manifest["flash"]["reason"]
                == "runtime_acl_flash_read_denied"
                and snapshot["runtime_acl"]["policy_id"] == hidden_policy.policy_id,
            )

            package_policy = RuntimeACL.from_document(package_policy_document())
            service.runtime_acl = package_policy
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/program",
                {
                    "files": {
                        "main.py": {"encoding": "utf8", "data": "print(1)\n"},
                        "lib/private/key.py": {
                            "encoding": "utf8",
                            "data": "VALUE = 1\n",
                        },
                    },
                    "entrypoint": "main.py",
                    "expected_execution_id": None,
                },
            )
            evidence.add(
                "package deny path wins before console",
                status == 403
                and body["error"]["operation"] == "filesystem.write"
                and body["error"]["reason"] == "path_denied"
                and body["error"]["policy_id"] == package_policy.policy_id,
            )
            evidence.add(
                "denied package created no revision",
                not list(service.program_packages.root.glob("*.json")),
            )
            status, body = server.request(
                "POST",
                f"/api/v1/sessions/{session.id}/program",
                {
                    "files": {
                        "main.py": {"encoding": "utf8", "data": "print(2)\n"},
                    },
                    "entrypoint": "main.py",
                    "expected_execution_id": None,
                },
            )
            evidence.add(
                "allowed package reaches runtime gate",
                status == 409
                and body["error"]["code"] == "program_transport_unavailable",
            )
            denied_events = [
                event
                for event in session.events
                if event.get("event") == "runtime_acl_denied"
            ]
            evidence.add(
                "denials are auditable events",
                len(denied_events) >= 6
                and all(event.get("policy_id") for event in denied_events),
                denied_events=len(denied_events),
            )
        finally:
            server.close()
            service.close_all()

    result = {
        "schema_version": 1,
        "kind": "runtime-acl-http-validation",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "started_at": started_at,
        "validation": "host-runtime validation",
        "status": evidence.result(),
        "checks": evidence.checks,
        "tools": {
            "runtime_acl.py": sha256(TOOLS / "runtime_acl.py"),
            "device_service.py": sha256(TOOLS / "device_service.py"),
            "serve.py": sha256(TOOLS / "serve.py"),
            "run_test.py": sha256(Path(__file__)),
        },
        "boundary": {
            "guest_filesystem_acl": "NOT RUN",
            "qemu_guest": "NOT RUN",
            "native_firmware_sandbox": "NOT RUN",
            "physical_hardware": "NOT RUN",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({"status": result["status"], "checks": len(result["checks"])}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
