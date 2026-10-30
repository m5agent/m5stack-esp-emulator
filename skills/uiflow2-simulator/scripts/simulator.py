#!/usr/bin/env python3
"""Bounded, stdlib-only client for Device Service Preview/Run workflows.

All mutations are scoped to the Preview created in the selected state file.
The state file is a recovery journal, not an authentication credential.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
from http.client import HTTPException
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import sys
import tempfile
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid


TERMINAL_RUNS = {"completed", "failed", "cancelled", "superseded", "interrupted"}
IDENTITY = re.compile(r"[a-zA-Z0-9_-]{1,128}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_CONFIG = Path(__file__).resolve().parents[1] / "config.local.json"
PRIVATE_LAN = tuple(ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class SimulatorError(Exception):
    def __init__(self, code, message, *, category="client", status=None, ambiguous=False):
        super().__init__(message)
        self.result = {"category": category, "code": code, "message": message}
        if status is not None:
            self.result["http_status"] = status
        if ambiguous:
            self.result["outcome_unknown"] = True


def require(condition, code, message):
    if not condition:
        raise SimulatorError(code, message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def redact(value, token):
    if not token:
        return value
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]")
    if isinstance(value, dict):
        return {redact(key, token): redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    return value


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, UnicodeError, ValueError) as error:
        raise SimulatorError("invalid_json_file", "Cannot read a finite UTF-8 JSON file") from error


def valid_url(value):
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port
        del valid_port
        require(parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment
                and parsed.path in {"", "/"}, "invalid_base_url",
                "Use an HTTP loopback/private-LAN or HTTPS origin, without credentials, path or query")
        host = parsed.hostname.lower()
        private_lan = False
        try:
            address = ipaddress.ip_address(host)
            loopback = address.is_loopback
            private_lan = isinstance(address, ipaddress.IPv4Address) and any(address in network for network in PRIVATE_LAN)
        except ValueError:
            loopback = host == "localhost"
        require(parsed.scheme == "https" or loopback or private_lan, "insecure_base_url",
                "Cleartext HTTP requires loopback or an explicit RFC1918 IPv4 address; other remote services require HTTPS")
        return value.rstrip("/"), loopback
    except ValueError as error:
        raise SimulatorError("invalid_base_url", "Invalid service origin") from error


def load_token():
    token = os.environ.get("AIFLOW_SIMULATOR_TOKEN", "")
    token_file = os.environ.get("AIFLOW_SIMULATOR_TOKEN_FILE", "")
    if not token and token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise SimulatorError("token_unavailable", "Cannot read simulator credential file") from error
    require(not token or all(33 <= ord(char) <= 126 for char in token), "invalid_token",
            "The simulator credential must be a single printable ASCII token")
    return token


def local_config():
    config = read_json(LOCAL_CONFIG) if LOCAL_CONFIG.exists() else {}
    require(isinstance(config, dict) and not set(config) - {"base_url", "public_url"},
            "invalid_local_config", "Local simulator config accepts only base_url and public_url; credentials use environment or token-file")
    for value in config.values():
        require(isinstance(value, str), "invalid_local_config", "Simulator origins must be strings")
        valid_url(value)
    return config


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base, token, timeout=10, public_url=None):
        self.base, self.loopback = valid_url(base)
        self.token, self.timeout = token, timeout
        self.public_url = public_url
        # Honor the Agent runtime's network-sandbox proxy and NO_PROXY policy.
        # Redirects remain disabled, so a service cannot move the Bearer token
        # to a different destination through an HTTP redirect.
        self.opener = build_opener(ProxyHandler(), NoRedirect())

    def request(self, method, path, payload=None, *, key=None, binary=False,
                max_bytes=4 * 1024 * 1024, timeout=None):
        require(path.startswith("/") and not path.startswith("//"), "invalid_route", "Invalid API route")
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if key:
            headers["Idempotency-Key"] = key
        data = None
        if payload is not None:
            data = canonical(payload)
            headers["Content-Type"] = "application/json"
        try:
            with self.opener.open(Request(self.base + "/api/v1" + path, data=data,
                                         headers=headers, method=method),
                                  timeout=timeout or self.timeout) as response:
                body = response.read(max_bytes + 1)
                require(len(body) <= max_bytes, "response_too_large", "API response exceeds the client limit")
                if binary:
                    return body, {key.lower(): value for key, value in response.headers.items()}
                return json.loads(body)
        except HTTPError as error:
            raw = error.read(65537)
            detail = {}
            try:
                detail = json.loads(raw[:65536])
                detail = detail.get("error", detail)
            except (ValueError, AttributeError):
                pass
            if not isinstance(detail, dict):
                detail = {}
            raise SimulatorError(str(detail.get("code", "http_error")),
                                 str(detail.get("message", "Device Service rejected the request"))[:1000],
                                 category="api", status=error.code,
                                 ambiguous=method != "GET" and error.code >= 500) from error
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError, HTTPException) as error:
            raise SimulatorError("transport_unavailable", "Device Service connection failed or timed out",
                                 category="transport", ambiguous=method != "GET") from error
        except (ValueError, UnicodeError) as error:
            raise SimulatorError("invalid_response", "Device Service did not return valid JSON",
                                 category="protocol", ambiguous=method != "GET") from error


def atomic_bytes(path, value):
    path = Path(path)
    require(not path.is_symlink(), "unsafe_output", "Output must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class State:
    def __init__(self, path, base, token=""):
        self.path = Path(path)
        self.base = base
        self.token = token
        self.value = {}
        self.lock = None

    def __enter__(self):
        require(not self.path.is_symlink(), "unsafe_state", "State must not be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(descriptor, "w")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close()
            raise SimulatorError("state_busy", "Another simulator command owns this state file") from error
        self.value = read_json(self.path) if self.path.exists() else {"schema_version": 1, "base_url": self.base}
        require(isinstance(self.value, dict) and self.value.get("schema_version") == 1,
                "invalid_state", "Unrecognized simulator state")
        require(self.value.get("base_url") == self.base, "state_origin_mismatch",
                "This state belongs to another simulator origin; use a separate state file")
        return self

    def save(self):
        atomic_bytes(self.path, canonical(redact(self.value, self.token)) + b"\n")

    def __exit__(self, *_args):
        if self.lock:
            self.lock.close()


def package_path(value):
    require(isinstance(value, str), "unsafe_package_path", "Package paths must be strings")
    parts = value.split("/")
    require(value and "\\" not in value and ":" not in value and not PurePosixPath(value).is_absolute()
            and all(part not in {"", ".", ".."} for part in parts)
            and len(parts) <= 8 and len(value.encode("utf-8")) <= 192
            and unicodedata.normalize("NFC", value) == value
            and not any(unicodedata.category(char) == "Cc" for char in value),
            "unsafe_package_path", "Use canonical relative UTF-8 POSIX paths without traversal")
    for part in parts:
        lower = part.casefold()
        require(not lower.startswith(".") and lower not in {"credentials", "credentials.json", "id_rsa", "id_ed25519"}
                and not lower.endswith((".pem", ".key", ".p12", ".pfx"))
                and not lower.startswith("service-account") and lower != "boot.py",
                "sensitive_package_path", "Hidden files, credentials and boot.py cannot be uploaded")
    return value


def build_package(project_dir, files=None, manifest=None):
    root = Path(project_dir).resolve(strict=True)
    require(root.is_dir(), "invalid_project", "Project directory is required")
    mapping = read_json(manifest) if manifest else {name: name for name in (files or [])}
    require(isinstance(mapping, dict) and mapping and len(mapping) <= 64,
            "invalid_manifest", "Manifest must map 1 to 64 explicit source paths to guest paths")
    package, seen, total = {}, set(), 0
    for source, target in mapping.items():
        source, target = package_path(source), package_path(target)
        folded = target.casefold()
        require(folded not in seen, "package_path_collision", "Guest paths collide after case folding")
        seen.add(folded)
        candidate = root
        for part in source.split("/"):
            candidate = candidate / part
            require(not candidate.is_symlink(), "unsafe_package_symlink", "Project files cannot traverse symbolic links")
        try:
            require(candidate.is_file() and candidate.resolve().is_relative_to(root),
                    "unsafe_package_file", "Every explicit project file must exist within the project directory")
            require(candidate.stat().st_size <= 256 * 1024, "package_too_large", "A file exceeds 256 KiB")
            content = candidate.read_bytes()
        except OSError as error:
            raise SimulatorError("project_file_unavailable", "Cannot read an explicit project file") from error
        require(len(content) <= 256 * 1024, "package_too_large", "A file exceeds 256 KiB")
        total += len(content)
        require(total <= 1024 * 1024, "package_too_large", "Package exceeds 1 MiB")
        package[target] = {"encoding": "base64", "data": base64.b64encode(content).decode("ascii")}
    require("main.py" in package, "main_py_required", "This client requires a source main.py entrypoint")
    for name in package:
        require(not any(name.casefold().startswith(other.casefold() + "/") for other in package if other != name),
                "package_path_collision", "Guest file and directory paths collide")
    return {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": package}


class Workflow:
    def __init__(self, client, state):
        self.client, self.state = client, state
        self.data = state.value

    def route(self):
        identity = self.data.get("preview_id")
        require(isinstance(identity, str) and IDENTITY.fullmatch(identity), "preview_required",
                "Create a Preview in this state file first")
        return "/previews/" + identity

    def browser(self):
        public = os.environ.get("AIFLOW_SIMULATOR_PUBLIC_URL") or self.client.public_url
        origin, loopback = valid_url(public or self.client.base)
        return {"url": origin + "/platform/web/sessions.html", "local_only": loopback,
                "session_id": self.data.get("session_id"),
                "authentication": "Enter the service control token separately; it is never included in the URL"}

    def remember_preview(self, preview):
        require(isinstance(preview, dict) and isinstance(preview.get("preview_id"), str)
                and IDENTITY.fullmatch(preview["preview_id"]) and isinstance(preview.get("owner_epoch"), str)
                and IDENTITY.fullmatch(preview["owner_epoch"]) and type(preview.get("generation")) is int,
                "invalid_preview_response", "Preview identity or generation is missing")
        if "preview_id" in self.data:
            require(preview["preview_id"] == self.data["preview_id"]
                    and preview["owner_epoch"] == self.data["owner_epoch"],
                    "preview_identity_mismatch", "Preview identity changed; no mutation was sent")
        for field in ("preview_id", "owner_epoch", "generation", "session_id"):
            self.data[field] = preview.get(field)
        self.state.save()
        return preview

    def preview(self):
        return self.remember_preview(self.client.request("GET", self.route()))

    def get_run(self, run_id=None):
        run_id = run_id or self.data.get("run_id")
        require(isinstance(run_id, str) and IDENTITY.fullmatch(run_id), "run_required", "Submit a Run first")
        run = self.client.request("GET", self.route() + "/runs/" + run_id)
        require(isinstance(run, dict) and run.get("run_id") == run_id
                and run.get("preview_id") == self.data["preview_id"]
                and isinstance(run.get("execution_id"), str) and IDENTITY.fullmatch(run["execution_id"])
                and isinstance(run.get("revision_id"), str) and DIGEST.fullmatch(run["revision_id"]),
                "run_identity_mismatch", "Run identity does not match the requested Preview")
        return run

    def poll(self, getter, stop, seconds):
        deadline = time.monotonic() + seconds
        value = getter()
        while not stop(value) and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            value = getter()
        return value

    def pending_write(self, path, payload, key=None):
        try:
            return self.client.request("POST", path, payload, key=key)
        except SimulatorError as error:
            # A definite validation/auth/quota rejection is a resolved attempt.
            # Keep its original request/key for audit, but permit a later explicit
            # command to capture fresh fencing. Transport/5xx/408 stay pending.
            if error.result.get("http_status") in {400, 401, 403, 404, 409, 413, 422, 429}:
                rejected = self.data.pop("pending")
                rejected["rejection"] = {name: value for name, value in error.result.items() if name != "message"}
                self.data["last_rejected_operation"] = rejected
                self.state.save()
            raise

    def create(self, args):
        units = read_json(args.units_json) if args.units_json else []
        require(isinstance(units, list), "invalid_units", "Units JSON must be an explicit attachment array")
        request = {"device_id": args.device, "runtime": "qemu", "units": units, "ttl_seconds": args.ttl}
        pending = self.data.get("pending")
        if self.data.get("preview_id") and not pending:
            raise SimulatorError("preview_exists", "This state already owns a Preview; use status or a new state file")
        if pending:
            require(pending.get("kind") == "create" and pending["request"] == request,
                    "pending_operation", "Resolve the original pending operation with the same command and inputs")
        else:
            pending = {"kind": "create", "request": request, "key": str(uuid.uuid4())}
            self.data["pending"] = pending
            self.state.save()
        receipt = self.pending_write("/previews", pending["request"], key=pending["key"])
        self.remember_preview(receipt)
        self.data["create_receipt"] = receipt
        self.data.pop("pending", None)
        self.state.save()
        preview = self.poll(self.preview, lambda row: row.get("state") != "preparing", args.wait)
        return {"preview": preview, "browser": self.browser(), "ready": preview.get("state") == "ready"}

    def status(self, _args):
        if self.data.get("pending", {}).get("kind") == "create" and not self.data.get("preview_id"):
            return {"preview": None, "outcome_unknown": True,
                    "pending_operation": {"kind": "create", "request": self.data["pending"]["request"],
                                          "recovery": "Repeat the original create command and unchanged inputs; do not create a second state"}}
        result = {"preview": self.preview(), "browser": self.browser()}
        if self.data.get("run_id"):
            result["run"] = self.get_run()
        if self.data.get("pending"):
            result["pending_operation"] = {"kind": self.data["pending"]["kind"],
                                           "recovery": "Repeat the original command and unchanged inputs to replay its original key"}
        return result

    def run(self, args):
        package = build_package(args.project_dir, args.file, args.manifest)
        fingerprint = sha(canonical(package))
        pending = self.data.get("pending")
        if pending:
            require(pending.get("kind") == "run" and pending.get("package_sha256") == fingerprint
                    and pending.get("timeout_seconds") == args.transfer_timeout,
                    "pending_operation", "A pending operation must be resolved using its original complete package")
        else:
            preview = self.preview()
            require(preview.get("state") == "ready", "preview_not_ready", "Preview must be ready before submitting code")
            removed = set(self.data.get("package_paths", [])) - package["files"].keys()
            require(not removed or args.allow_delete, "incomplete_package",
                    "The complete package omitted previous files; include them or explicitly use --allow-delete")
            pending = {"kind": "run", "key": str(uuid.uuid4()), "package_sha256": fingerprint,
                       "expected_generation": preview["generation"], "timeout_seconds": args.transfer_timeout,
                       "client_generation": str(uuid.uuid4())}
            self.data["pending"] = pending
            self.state.save()
        if "request" not in pending:
            saved = self.pending_write("/program-revisions", package)
            revision = saved.get("revision", {}).get("revision_id")
            require(isinstance(revision, str) and DIGEST.fullmatch(revision),
                    "invalid_revision_response", "Immutable package receipt has no valid revision ID")
            pending["request"] = {"revision_id": revision, "expected_owner_epoch": self.data["owner_epoch"],
                                  "expected_generation": pending["expected_generation"],
                                  "client_generation": pending["client_generation"],
                                  "timeout_seconds": pending["timeout_seconds"]}
            self.state.save()
        # No automatic write retry: an ambiguous response remains in the journal.
        receipt = self.pending_write(self.route() + "/runs", pending["request"], key=pending["key"])
        require(receipt.get("preview_id") == self.data["preview_id"]
                and isinstance(receipt.get("run_id"), str) and IDENTITY.fullmatch(receipt["run_id"])
                and receipt.get("revision_id") == pending["request"]["revision_id"]
                and receipt.get("generation") == pending["expected_generation"] + 1,
                "invalid_run_response", "Run receipt does not match the persisted submission")
        self.data.update(run_id=receipt["run_id"], execution_id=receipt.get("execution_id"),
                         revision_id=receipt["revision_id"], generation=receipt["generation"],
                         package_paths=sorted(package["files"]), serial_execution_id=None,
                         serial_offset=None, serial_tail="")
        self.data.pop("pending", None)
        self.state.save()
        run = self.poll(self.get_run, lambda row: row.get("state") in TERMINAL_RUNS | {"running", "unknown"}, args.wait)
        return {"run": run, "browser": self.browser(), "application_ready": "unknown",
                "verification": "execution_started" if run.get("state") == "running" else run.get("state", "unknown")}

    def session_route(self, preview):
        session = preview.get("session_id")
        require(isinstance(session, str) and IDENTITY.fullmatch(session), "session_unavailable", "Preview has no managed session yet")
        return "/sessions/" + session

    @staticmethod
    def program_matches(program, run):
        return (isinstance(program, dict) and program.get("execution_id") == run["execution_id"]
                and program.get("revision_id") == run["revision_id"])

    def inspect(self, args):
        preview, run = self.preview(), self.get_run()
        session = self.session_route(preview)
        result = {"preview": preview, "run": run, "browser": self.browser(),
                  "application_ready": "unknown", "samples_atomic": False}
        program = self.client.request("GET", session + "/program").get("program")
        require(self.program_matches(program, run), "serial_execution_changed",
                "Current guest program is not the selected Run; serial was not attributed")
        baseline = program.get("serial_offset")
        require(type(baseline) is int and baseline >= 0, "serial_offset_unavailable", "Run serial start offset is unavailable")
        same = self.data.get("serial_execution_id") == run["execution_id"]
        offset = max(baseline, self.data.get("serial_offset") or baseline) if same else baseline
        serial = self.client.request("GET", session + "/serial?" + urlencode({"offset": offset, "limit": args.serial_limit}))
        require(serial.get("session_id") == preview["session_id"] and serial.get("offset") == offset
                and type(serial.get("next_offset")) is int and serial["next_offset"] >= offset
                and serial["next_offset"] - offset <= args.serial_limit and isinstance(serial.get("data"), str),
                "invalid_serial_response", "Serial offsets or session identity do not match")
        device_state = self.client.request("GET", session + "/device-state")
        units = self.client.request("GET", session + "/units")
        after = self.client.request("GET", session + "/program").get("program")
        final_run = self.get_run()
        require(self.program_matches(after, run) and final_run["execution_id"] == run["execution_id"]
                and final_run["revision_id"] == run["revision_id"],
                "serial_execution_changed", "Guest program changed during collection; serial was not attributed")
        text = serial["data"]
        tail = (self.data.get("serial_tail", "") if same else "") + text
        traceback_seen = "Traceback (most recent call last):" in tail
        # A source echo, exception quoting the marker, or partial line is not
        # application output proving readiness. Only a complete standalone line
        # in this execution's serial window is eligible.
        lines = tail.replace("\r\n", "\n").replace("\r", "\n").split("\n")[:-1]
        marker_seen = bool(args.ready_marker and args.ready_marker in lines
                           and not traceback_seen and final_run.get("state") != "failed")
        self.data.update(serial_execution_id=run["execution_id"], serial_offset=serial["next_offset"],
                         serial_tail=tail[-8192:])
        self.state.save()
        result.update(serial=serial, program=after, device_state=device_state, units=units,
                      application_ready="marker_observed" if marker_seen else "unknown",
                      ready_marker=args.ready_marker, traceback_observed=traceback_seen)
        try:
            png, headers = self.client.request("GET", self.route() + "/runs/" + run["run_id"] + "/frame.png?max_age_ms=125", binary=True)
            expected = {"x-preview-id": preview["preview_id"], "x-run-id": run["run_id"],
                        "x-frame-execution-id": run["execution_id"], "x-frame-revision-id": run["revision_id"],
                        "x-frame-sha256": sha(png)}
            require(png.startswith(b"\x89PNG\r\n\x1a\n") and all(headers.get(key) == value for key, value in expected.items()),
                    "frame_identity_mismatch", "Frame PNG, run identity or SHA256 verification failed")
            output = Path(args.out_dir) / "latest.png"
            atomic_bytes(output, png)
            atomic_bytes(Path(args.out_dir) / "latest.frame.json", canonical(redact(headers, self.client.token)) + b"\n")
            result["frame"] = {"status": "captured", "path": str(output), "headers": headers,
                               "visual_review": "not_performed"}
        except SimulatorError as error:
            result["frame"] = {"status": "unavailable", "error": error.result}
        return result

    def input(self, args):
        preview, run = self.preview(), self.get_run()
        require(preview.get("state") == "ready" and run.get("state") == "running"
                and preview.get("active_run_id") == run["run_id"], "run_not_active", "Input requires this state's active running Run")
        value = read_json(args.host_json or args.unit_json)
        require(isinstance(value, dict), "invalid_input", "Input JSON must be an object")
        request = {"expected_owner_epoch": self.data["owner_epoch"], "expected_run_id": run["run_id"],
                   "input" if args.host_json else "unit_input": value}
        receipt = self.client.request("POST", self.route() + "/input", request)
        require(isinstance(receipt, dict) and receipt.get("preview_id") == preview["preview_id"]
                and receipt.get("run_id") == run["run_id"] and receipt.get("execution_id") == run["execution_id"],
                "input_receipt_mismatch", "Input receipt does not match the held Run; an effect may already have occurred")
        return {"receipt": receipt}

    def renew(self, args):
        self.preview()
        value = self.client.request("POST", self.route() + "/renew",
                                    {"expected_owner_epoch": self.data["owner_epoch"], "ttl_seconds": args.ttl})
        return {"preview": self.remember_preview(value), "browser": self.browser()}

    def cancel(self, args):
        require(not self.data.get("pending"), "pending_operation",
                "Resolve pending admission before cancelling a selected Run, or close this owned Preview")
        self.preview()
        run = self.get_run()
        self.client.request("POST", self.route() + "/runs/" + run["run_id"] + "/cancel",
                            {"expected_owner_epoch": self.data["owner_epoch"]})
        run = self.poll(self.get_run, lambda row: row.get("state") in TERMINAL_RUNS, args.wait)
        return {"run": run, "cancellation_confirmed": run.get("state") in {"cancelled", "superseded"}
                and run.get("interrupt_ack") in {"confirmed", "not-required"}}

    def close(self, args):
        pending = self.data.get("pending")
        require(not pending or pending.get("kind") == "run", "pending_operation",
                "Resolve the original pending creation before closing its unknown allocation")
        preview = self.preview()
        evidence = self.data.get("evidence_receipt")
        if preview.get("state") != "closed" and preview.get("session_id") and not evidence:
            try:
                blob, headers = self.client.request("GET", self.session_route(preview) + "/evidence", binary=True,
                                                    max_bytes=128 * 1024 * 1024)
                require(blob.startswith(b"PK"), "invalid_evidence", "Evidence response is not a ZIP")
                output = Path(args.out_dir) / ("evidence-" + preview["preview_id"] + ".zip")
                atomic_bytes(output, blob)
                evidence = {"status": "captured", "path": str(output), "sha256": sha(blob), "size": len(blob)}
                self.data["evidence_receipt"] = evidence
                self.state.save()
            except SimulatorError as error:
                evidence = {"status": "unavailable", "error": error.result}
        if preview.get("state") != "closed":
            self.client.request("POST", self.route() + "/close", {"expected_owner_epoch": self.data["owner_epoch"]})
            preview = self.poll(self.preview, lambda row: row.get("state") == "closed", args.wait)
        if preview.get("state") == "closed" and pending:
            # Closing our own Preview is safe even when Run admission is
            # ambiguous. Preserve that uncertainty; never replay it as cleanup.
            self.data["unresolved_operation_at_close"] = self.data.pop("pending")
            self.state.save()
        return {"preview": preview, "evidence": evidence, "before_close_evidence": preview.get("close_evidence"),
                "run_admission_was_unresolved": bool(pending),
                "history": {"retained": preview.get("state") == "closed", "session_id": preview.get("session_id")},
                "browser": self.browser()}


def bounded_number(lower, upper, converter=int):
    def parse(value):
        try:
            number = converter(value)
            if lower <= number <= upper:
                return number
        except ValueError:
            pass
        raise argparse.ArgumentTypeError(f"must be between {lower} and {upper}")
    return parse


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state", default=".aiflow/simulator-state.json", help="Owned Preview recovery journal; use a new file for another topology")
    result.add_argument("--timeout", type=bounded_number(1, 60, float), default=10, help="Per-request timeout in seconds")
    commands = result.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="Read device and Unit inventory/admission")
    discover.add_argument("--device")
    create = commands.add_parser("create", help="Create one visible persistent UIFlow QEMU Preview")
    create.add_argument("--device", required=True)
    create.add_argument("--units-json", help="JSON array of explicit Unit attachments")
    create.add_argument("--ttl", type=bounded_number(30, 3600), default=300)
    create.add_argument("--wait", type=bounded_number(0, 60, float), default=45)
    commands.add_parser("status", help="Read only this state's Preview and latest Run")
    run = commands.add_parser("run", help="Save and run a complete explicit package; omitted previous files require --allow-delete")
    run.add_argument("--project-dir", default=".")
    selection = run.add_mutually_exclusive_group(required=True)
    selection.add_argument("--file", action="append", help="Explicit project-relative file; repeat for all dependencies/resources")
    selection.add_argument("--manifest", help="JSON object mapping project-relative source paths to guest paths")
    run.add_argument("--allow-delete", action="store_true", help="Confirm intentional omission of files from the previous complete package")
    run.add_argument("--transfer-timeout", type=bounded_number(1, 120, float), default=120)
    run.add_argument("--wait", type=bounded_number(0, 60, float), default=20)
    inspect = commands.add_parser("inspect", help="Collect incrementally fenced serial/state/Units and a run-bound PNG")
    inspect.add_argument("--out-dir", default="artifacts/simulator")
    inspect.add_argument("--ready-marker", help="Application-owned marker; execution START alone is never readiness")
    inspect.add_argument("--serial-limit", type=bounded_number(1, 65536), default=65536)
    input_command = commands.add_parser("input", help="Inject a host or Unit input fenced to the active Run")
    inputs = input_command.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--host-json")
    inputs.add_argument("--unit-json")
    renew = commands.add_parser("renew", help="Extend the owned Preview lease")
    renew.add_argument("--ttl", type=bounded_number(30, 3600), default=300)
    cancel = commands.add_parser("cancel", help="Cancel this state's latest Run and confirm interrupt acknowledgement")
    cancel.add_argument("--wait", type=bounded_number(0, 60, float), default=10)
    close = commands.add_parser("close", help="Capture ZIP before close; retain session history and release mutable Flash")
    close.add_argument("--wait", type=bounded_number(0, 60, float), default=20)
    close.add_argument("--out-dir", default="artifacts/simulator")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    token = ""
    try:
        token = load_token()
        config = local_config()
        base_url = os.environ.get("AIFLOW_SIMULATOR_BASE_URL") or config.get("base_url")
        require(bool(base_url), "base_url_required",
                "Configure an explicit dedicated Device Service origin before using the simulator")
        client = Client(base_url, token, args.timeout, config.get("public_url"))
        if args.command == "discover":
            suffix = "?" + urlencode({"device_id": args.device}) if args.device else ""
            result = {"devices": client.request("GET", "/devices"), "units": client.request("GET", "/units" + suffix)}
        else:
            require(bool(token), "token_required", "Preview operations require a configured simulator control credential")
            with State(args.state, client.base, token) as state:
                workflow = Workflow(client, state)
                result = getattr(workflow, args.command)(args)
        output, exit_code = {"ok": True, "command": args.command, **result}, 0
        if result.get("run", {}).get("state") == "failed" or result.get("traceback_observed"):
            exit_code = 3
    except SimulatorError as error:
        output, exit_code = {"ok": False, "command": args.command, "error": error.result}, 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        # No repr(error): local filesystem paths or server-supplied credentials may occur there.
        output, exit_code = {"ok": False, "command": args.command,
                             "error": {"category": "client", "code": "invalid_local_or_api_state",
                                       "message": "Local files or API response could not be verified"}}, 2
    encoded = json.dumps(redact(output, token), ensure_ascii=False, allow_nan=False)
    print(encoded)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
