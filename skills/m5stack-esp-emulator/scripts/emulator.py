#!/usr/bin/env python3
"""Portable Device Service client (Python 3.10+, standard library only).

Configure M5_EMULATOR_BASE_URL explicitly. Results are samples/evidence, never
automatic functional or physical-hardware PASS judgments.
"""
from __future__ import annotations

import argparse
try:
    import fcntl
except ImportError:  # Windows has a different standard-library file lock.
    fcntl = None
    import msvcrt
import hashlib
from http.client import HTTPException
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid


ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ACTIVE = {"provisioning", "flashing", "booting", "stopping"}
LAN = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class Error(Exception):
    def __init__(self, code, message, *, category="client", status=None, unknown=False):
        self.detail = {"category": category, "code": code, "message": message}
        if status is not None:
            self.detail["http_status"] = status
        if unknown:
            self.detail["outcome_unknown"] = True
        super().__init__(message)


def need(condition, code, message):
    if not condition:
        raise Error(code, message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def scrub(value, token):
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]") if token else value
    if isinstance(value, dict):
        return {scrub(key, token): scrub(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, token) for item in value]
    return value


def json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, UnicodeError, ValueError) as error:
        raise Error("invalid_json_file", "Expected a readable finite UTF-8 JSON file") from error


def origin(value):
    need(bool(value), "base_url_required", "Set M5_EMULATOR_BASE_URL to the intended Device Service origin")
    try:
        parsed = urlsplit(value)
        parsed.port
        need(parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
             and not parsed.password and not parsed.query and not parsed.fragment and parsed.path in {"", "/"},
             "invalid_base_url", "Use a service origin without credentials, path, query or fragment")
        try:
            address = ipaddress.ip_address(parsed.hostname)
            local = address.is_loopback
            lan = isinstance(address, ipaddress.IPv4Address) and any(address in network for network in LAN)
        except ValueError:
            local, lan = parsed.hostname.lower() == "localhost", False
        need(parsed.scheme == "https" or local or lan, "insecure_base_url",
             "HTTP requires loopback or an explicit RFC1918 IPv4 address; other hosts require HTTPS")
        return value.rstrip("/"), local
    except ValueError as error:
        raise Error("invalid_base_url", "Invalid Device Service origin") from error


def credential():
    token = os.environ.get("M5_EMULATOR_TOKEN", "")
    if not token and os.environ.get("M5_EMULATOR_TOKEN_FILE"):
        try:
            token = Path(os.environ["M5_EMULATOR_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise Error("token_unavailable", "Cannot read Device Service credential file") from error
    need(not token or all(33 <= ord(char) <= 126 for char in token), "invalid_token", "Expected one printable ASCII Bearer token")
    return token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def route(value):
    parsed = urlsplit(value)
    need(not parsed.scheme and not parsed.netloc and not parsed.fragment
         and parsed.path.startswith("/api/v1/") and "//" not in parsed.path and "%" not in parsed.path
         and "\\" not in parsed.path and all(part not in {".", ".."} for part in parsed.path.split("/"))
         and not any(ord(char) < 33 or ord(char) > 126 for char in value),
         "invalid_route", "Use an unescaped canonical /api/v1/... API route")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True) if parsed.query else []
    except ValueError as error:
        raise Error("invalid_route", "Malformed API query") from error
    need(not any(re.search(r"token|secret|password|credential|authorization|api.key", key, re.I) for key, _ in pairs),
         "credential_in_url", "Credentials must never appear in an API URL")
    return parsed.path.removeprefix("/api/v1/").split("/")


class Client:
    def __init__(self, base, token="", timeout=10):
        self.base, self.local = origin(base)
        self.token, self.timeout = token, timeout
        # The runtime may enforce its network sandbox through these proxies.
        self.opener = build_opener(ProxyHandler(), NoRedirect())

    def raw(self, method, path, payload=None, *, data=None, headers=None, limit=4 * 1024 * 1024):
        route(path)
        outgoing = {"Accept": "application/json", **(headers or {})}
        if self.token:
            outgoing["Authorization"] = "Bearer " + self.token
        if payload is not None:
            data, outgoing["Content-Type"] = encode(payload), "application/json"
        try:
            with self.opener.open(Request(self.base + path, data=data, headers=outgoing, method=method), timeout=self.timeout) as response:
                body = response.read(limit + 1)
                need(len(body) <= limit, "response_too_large", "API response exceeds the configured client limit")
                return body, {name.lower(): value for name, value in response.headers.items()}
        except HTTPError as error:
            try:
                detail = json.loads(error.read(65536)).get("error", {})
            except (ValueError, AttributeError):
                detail = {}
            detail = detail if isinstance(detail, dict) else {}
            raise Error(str(detail.get("code", "http_error")), str(detail.get("message", "Device Service rejected the request"))[:1000],
                        category="api", status=error.code, unknown=method != "GET" and error.code >= 500) from error
        except (URLError, OSError, TimeoutError, HTTPException) as error:
            raise Error("transport_unavailable", "Device Service connection failed or timed out", category="transport", unknown=method != "GET") from error

    def json(self, method, path, payload=None, **kwargs):
        body, _ = self.raw(method, path, payload, **kwargs)
        try:
            return json.loads(body)
        except (ValueError, UnicodeError) as error:
            raise Error("invalid_api_json", "API response was not valid JSON; use --out for binary responses",
                        category="protocol", unknown=method != "GET") from error


def write(path, data):
    path = Path(path)
    need(not path.is_symlink(), "unsafe_output", "Output must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Journal:
    def __init__(self, path, client):
        self.path, self.client, self.value = Path(path), client, {}

    def __enter__(self):
        need(not self.path.is_symlink(), "unsafe_state", "State must not be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = os.open(self.path.with_name(self.path.name + ".lock"), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.lock = os.fdopen(lock, "w")
        try:
            if fcntl is not None:
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                self.lock.write("0")
                self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            self.lock.close()
            raise Error("state_busy", "Another command owns this journal") from error
        try:
            self.value = json_file(self.path) if self.path.exists() else {"schema_version": 1, "base_url": self.client.base}
            need(isinstance(self.value, dict) and self.value.get("schema_version") == 1, "invalid_state", "Unrecognized journal")
            need(self.value.get("base_url") == self.client.base, "state_origin_mismatch", "Use a separate journal for another service origin")
        except Exception:
            self.lock.close()
            raise
        return self

    def save(self):
        write(self.path, encode(scrub(self.value, self.client.token)) + b"\n")

    def __exit__(self, *_args):
        self.lock.close()


class Agent:
    def __init__(self, client, journal):
        self.client, self.journal, self.state = client, journal, journal.value

    def browser(self):
        base, local = origin(os.environ.get("M5_EMULATOR_PUBLIC_URL") or self.client.base)
        return {"url": base + "/platform/web/sessions.html", "local_only": local,
                "session_id": self.state.get("session", {}).get("session_id"), "token_in_url": False}

    def poll(self, getter, done, seconds):
        deadline, value = time.monotonic() + seconds, getter()
        while not done(value) and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            value = getter()
        return value

    @staticmethod
    def released(value):
        return (value.get("state") in {"stopped", "failed"} and not value.get("stop_pending")
                and (value.get("worker") or {}).get("lease_active") is False)

    def remember(self, kind, value):
        key = "session_id" if kind == "session" else "preview_id"
        need(isinstance(value, dict) and isinstance(value.get(key), str) and ID.fullmatch(value[key]),
             "invalid_identity", "API response has no verifiable resource identity")
        fields = ("session_id", "device_id", "firmware_sha256", "runtime", "created_at") if kind == "session" else ("preview_id", "owner_epoch")
        if kind in self.state:
            need(all(value.get(field) == old for field, old in self.state[kind].items() if field in fields),
                 "identity_changed", "Resource identity changed; mutation was not sent")
        self.state[kind] = {field: value[field] for field in fields if field in value}
        if kind == "preview":
            need(isinstance(value.get("owner_epoch"), str) and ID.fullmatch(value["owner_epoch"]), "invalid_identity", "Preview owner epoch is missing")
            if value.get("session_id"):
                need(not self.state.get("session") or self.state["session"]["session_id"] == value["session_id"],
                     "identity_changed", "Preview changed its managed session identity")
                self.state.setdefault("session", {"session_id": value["session_id"]})
        self.journal.save()
        return value

    def preview(self):
        identity = self.state.get("preview", {}).get("preview_id")
        need(identity, "preview_required", "This journal does not own a Preview")
        return self.remember("preview", self.client.json("GET", "/api/v1/previews/" + identity))

    def session(self):
        if "preview" in self.state:
            self.preview()
        identity = self.state.get("session", {}).get("session_id")
        need(isinstance(identity, str) and ID.fullmatch(identity), "session_required", "Create a session in this journal first")
        value = self.client.json("GET", "/api/v1/sessions/" + identity)
        if "preview" in self.state:
            binding = value.get("management_binding") or {}
            need(binding.get("preview_id") == self.state["preview"]["preview_id"]
                 and binding.get("owner_epoch") == self.state["preview"]["owner_epoch"],
                 "managed_identity_changed", "Session is not bound to this journal's Preview")
        return self.remember("session", value)

    def admit(self, kind, request, wait=0):
        need(isinstance(request, dict), "invalid_create", "Creation JSON must be an object")
        need(scrub(request, self.client.token) == request, "credential_in_request",
             "Do not put the service control credential inside guest creation JSON")
        if kind == "session":
            need(isinstance(request.get("device_id"), str) and isinstance(request.get("runtime"), str),
                 "explicit_target_required", "Session JSON must explicitly declare device_id and runtime")
        pending = self.state.get("pending")
        if pending:
            need(pending.get("kind") == kind and pending["original"] == request,
                 "pending_admission", "Repeat the original creation with unchanged JSON; do not allocate another guest")
        else:
            need(not self.state.get("session") and not self.state.get("preview"), "resource_exists", "Use a new journal for another guest")
            outgoing, key = dict(request), str(uuid.uuid4())
            if kind == "session":
                outgoing["idempotency_key"] = request.get("idempotency_key") or key
            pending = {"kind": kind, "original": request, "request": outgoing, "key": key}
            self.state["pending"] = pending
            self.journal.save()
        path = "/api/v1/sessions" if kind == "session" else "/api/v1/previews"
        headers = {"Idempotency-Key": pending["key"]} if kind == "preview" else {}
        try:
            value = self.client.json("POST", path, pending["request"], headers=headers)
        except Error as error:
            if error.detail.get("http_status") in {400, 401, 403, 404, 409, 413, 422, 429}:
                self.state["rejected_admission"] = self.state.pop("pending")
                self.journal.save()
            raise
        try:
            self.remember(kind, value)
        except Error as error:
            error.detail["outcome_unknown"] = True
            raise
        self.state.pop("pending", None)
        self.journal.save()
        value = self.poll(self.session if kind == "session" else self.preview,
                          lambda row: row.get("state") not in ACTIVE | {"preparing"}, wait)
        return {kind: value, "browser": self.browser(), "functional_pass": None}

    def status(self):
        if self.state.get("pending") and not self.state.get("session") and not self.state.get("preview"):
            return {"outcome_unknown": True, "pending_admission": self.state["pending"]["kind"],
                    "recovery": "Repeat the original creation command and unchanged JSON"}
        return {"session": self.session(), "browser": self.browser(), "functional_pass": None,
                "pending_run_admission": bool(self.state.get("pending_run"))}

    def evidence(self, session_id, out_dir):
        blob, _ = self.client.raw("GET", "/api/v1/sessions/" + session_id + "/evidence", limit=128 * 1024 * 1024)
        need(blob.startswith(b"PK"), "invalid_evidence", "Evidence response is not a ZIP")
        path = Path(out_dir) / ("evidence-" + session_id + ".zip")
        write(path, blob)
        return {"path": str(path), "sha256": digest(blob), "size": len(blob)}

    def observe(self, args):
        session = self.session()
        path = "/api/v1/sessions/" + session["session_id"]
        offset = self.state.get("serial_offset", 0)
        serial = self.client.json("GET", path + "/serial?" + urlencode({"offset": offset, "limit": args.serial_limit}))
        need(serial.get("session_id") == session["session_id"] and type(serial.get("offset")) is int
             and 0 <= serial["offset"] <= offset and type(serial.get("next_offset")) is int
             and serial["offset"] <= serial["next_offset"] <= serial["offset"] + args.serial_limit
             and isinstance(serial.get("data"), str), "invalid_serial", "Serial cursor or session identity could not be verified")
        self.state["serial_offset"] = serial["next_offset"]
        self.journal.save()
        result = {"session": session, "serial": serial, "functional_pass": None, "samples_atomic": False,
                  "browser": self.browser(), "serial_scope": "session_log_not_automatically_application_attributed"}
        for name, suffix in (("device_state", "device-state"), ("units", "units")):
            try:
                result[name] = self.client.json("GET", path + "/" + suffix)
            except Error as error:
                result[name] = {"unavailable": error.detail}
        if args.frame:
            try:
                program = session.get("program")
                if program is None:
                    try:
                        program = self.client.json("GET", path + "/program").get("program")
                    except Error:
                        program = None
                try:
                    png, headers = self.client.raw("GET", path + "/frame.png?max_age_ms=125")
                except Error as error:
                    if error.detail.get("code") != "frame_preview_not_available":
                        raise
                    png, headers = self.client.raw("GET", path + "/frame.png")
                need(png.startswith(b"\x89PNG\r\n\x1a\n") and headers.get("x-frame-sha256") == digest(png),
                     "invalid_frame", "Frame PNG signature or source SHA256 did not verify")
                source = headers.get("x-frame-source")
                matched = False
                if session.get("state") == "running" and source == "live" and isinstance(program, dict) and program.get("execution_id") and program.get("revision_id"):
                    after = self.client.json("GET", path + "/program").get("program") or {}
                    matched = all(program.get(field) == after.get(field) == headers.get("x-frame-" + field.replace("_", "-"))
                                  for field in ("execution_id", "revision_id"))
                    matched = matched and self.session().get("state") == "running"
                output = Path(args.out_dir) / "frame.png"
                write(output, png)
                result["frame"] = {"path": str(output), "sha256": digest(png), "source": source,
                                   "program_identity": "current_program" if matched else "historical_sample" if session.get("state") != "running" or source in {"persisted", "last-known"} else "unattributed_sample",
                                   "visual_review": "not_performed", "headers": headers}
            except Error as error:
                result["frame"] = {"unavailable": error.detail}
        if args.evidence:
            try:
                result["evidence"] = self.evidence(session["session_id"], args.out_dir)
            except Error as error:
                result["evidence"] = {"unavailable": error.detail}
        return result

    def stop(self, args):
        session = self.session()
        unresolved_run = self.state.get("pending_run")
        need(not args.retain_flash or "preview" not in self.state, "preview_flash_retention_unsupported", "Preview close releases mutable Flash; capture its evidence first")
        result = {"functional_pass": None}
        if session.get("state") != "stopped":
            try:
                result["evidence"] = self.evidence(session["session_id"], args.out_dir)
            except Error as error:
                result["evidence"] = {"unavailable": error.detail}
        if "preview" in self.state:
            value = self.client.json("POST", "/api/v1/previews/" + self.state["preview"]["preview_id"] + "/close",
                                     {"expected_owner_epoch": self.state["preview"]["owner_epoch"]})
            value = self.poll(self.preview, lambda row: row.get("state") == "closed", args.wait)
            result["preview"] = value
            result["session"] = self.session()
            result["history_retained"] = value.get("state") == "closed" and self.released(result["session"])
        else:
            need(not session.get("management_binding"), "managed_session", "Legacy mutation of a Preview-managed session is prohibited")
            query = "?purge=0" + ("&retain_flash=1" if args.retain_flash else "")
            self.client.json("DELETE", "/api/v1/sessions/" + session["session_id"] + query)
            value = self.poll(self.session, self.released, args.wait)
            result.update(session=value, history_retained=self.released(value))
        result["cleanup_confirmed"] = result["history_retained"]
        if result["history_retained"] and unresolved_run:
            self.state["unresolved_run_at_close"] = self.state.pop("pending_run")
            self.journal.save()
        result["run_admission_was_unresolved"] = bool(unresolved_run)
        result["browser"] = self.browser()
        return result

    def request(self, args):
        parts = route(args.route)
        if args.idempotency_key:
            need(len(args.idempotency_key) <= 128 and all(33 <= ord(char) <= 126 for char in args.idempotency_key),
                 "invalid_idempotency_key", "Idempotency keys require 1..128 non-whitespace printable ASCII characters")
        payload = json_file(args.json) if args.json else None
        run_admission = False
        read_roots = {"health", "devices", "units", "capacity", "storage", "artifacts", "artifact-uploads", "firmware", "program-revisions", "sessions", "previews", "openapi.yaml"}
        need(parts[0] in read_roots, "route_not_allowed", "Review control-plane and worker/admin routes are outside this client")
        if args.method == "POST":
            need(not urlsplit(args.route).query, "mutation_query_not_allowed", "Mutation routes must not have query parameters")
            if parts == ["sessions"]:
                raise Error("use_create", "Use create --json to preserve admission recovery")
            if parts == ["previews"]:
                need(not args.out, "create_output_not_supported", "Preview admission returns structured JSON")
                return self.admit("preview", payload)
            if parts[0] == "sessions":
                current = self.session()
                need(len(parts) == 3 and parts[1] == current["session_id"] and parts[2] in {
                    "input", "unit-input", "program", "qom", "network-fault", "qom-snapshot", "flash-snapshot", "reset", "renew", "wait"},
                    "session_not_owned", "Mutation must target this journal's session and an admitted action; use stop for teardown")
                need(not current.get("management_binding"), "managed_session", "Use fenced Preview APIs for a Preview-managed session")
            elif parts[0] == "previews":
                current = self.preview()
                need(len(parts) >= 3 and parts[1] == current["preview_id"] and isinstance(payload, dict)
                     and payload.get("expected_owner_epoch") == current["owner_epoch"],
                     "preview_not_owned", "Preview mutation requires this journal's identity and explicit owner epoch")
                action = parts[2:]
                need(action in [["runs"], ["input"], ["renew"]] or len(action) == 3 and action[0] == "runs" and action[2] == "cancel",
                     "preview_action_not_allowed", "Use stop for evidence-preserving Preview close")
                if action == ["runs"]:
                    need(not args.out and bool(args.idempotency_key), "preview_fence_required", "Run requires structured JSON and an explicit stable --idempotency-key")
                    original = {"path": args.route, "request": payload, "key": args.idempotency_key}
                    if self.state.get("pending_run"):
                        need(self.state["pending_run"] == original, "pending_run", "Resolve the original Run with its unchanged body/key, or stop this owned Preview")
                    else:
                        need(type(payload.get("expected_generation")) is int and payload["expected_generation"] == current.get("generation"),
                             "preview_fence_required", "A new Run requires the current expected_generation")
                        need(scrub(original, self.client.token) == original, "credential_in_request", "Do not place the control credential in Run JSON or keys")
                        self.state["pending_run"] = original
                        self.journal.save()
                    run_admission = True
                else:
                    need(not self.state.get("pending_run"), "pending_run", "Resolve pending Run admission or stop this owned Preview before another mutation")
            else:
                allowed = parts in [["firmware"], ["firmware", "import"], ["firmware", "uiflow"], ["firmware", "analyze"], ["program-revisions"], ["artifact-uploads"]]
                allowed |= len(parts) == 3 and parts[0] == "artifact-uploads" and parts[2] == "complete"
                need(allowed, "mutation_not_allowed", "Use upload for bytes; only documented immutable intake routes are allowed here")
        headers = {"Idempotency-Key": args.idempotency_key} if args.idempotency_key else {}
        if args.out:
            blob, metadata = self.client.raw(args.method, args.route, payload, headers=headers, limit=128 * 1024 * 1024)
            write(args.out, blob)
            return {"output": args.out, "sha256": digest(blob), "size": len(blob), "headers": metadata, "functional_pass": None}
        try:
            response = self.client.json(args.method, args.route, payload, headers=headers)
        except Error as error:
            if run_admission and error.detail.get("http_status") in {400, 401, 403, 404, 409, 413, 422, 429}:
                self.state["rejected_run"] = self.state.pop("pending_run")
                self.journal.save()
            raise
        if run_admission:
            if not (isinstance(response, dict) and response.get("preview_id") == parts[1]
                    and isinstance(response.get("run_id"), str) and ID.fullmatch(response["run_id"])
                    and isinstance(response.get("execution_id"), str) and ID.fullmatch(response["execution_id"])
                    and response.get("revision_id") == payload.get("revision_id")
                    and response.get("generation") == payload["expected_generation"] + 1):
                raise Error("invalid_run_receipt", "Run admission receipt did not match the original fenced request", category="protocol", unknown=True)
            self.state["last_run_receipt"] = response
            self.state.pop("pending_run")
            self.journal.save()
        if args.method == "GET" and parts == ["previews", self.state.get("preview", {}).get("preview_id")]:
            self.remember("preview", response)
        return {"response": response, "functional_pass": None}


def number(lower, upper, convert=float):
    def parse(value):
        try:
            result = convert(value)
            if lower <= result <= upper:
                return result
        except ValueError:
            pass
        raise argparse.ArgumentTypeError(f"expected {lower}..{upper}")
    return parse


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--state", default=".m5-emulator/state.json", help="Owned guest recovery journal; use a new file for another guest")
    cli.add_argument("--timeout", type=number(1, 60), default=10, help="Per-request timeout in seconds")
    commands = cli.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="Read devices and Unit inventory/admission")
    discover.add_argument("--device")
    upload = commands.add_parser("upload", help="Upload one explicit binary artifact; no automatic retry")
    upload.add_argument("file")
    upload.add_argument("--name", help="Printable ASCII artifact name, including its meaningful extension")
    compose = commands.add_parser("compose", help="POST an explicit merged/segmented firmware recipe")
    compose.add_argument("--json", required=True)
    create = commands.add_parser("create", help="Create one session from explicit device/runtime JSON with durable idempotency")
    create.add_argument("--json", required=True)
    create.add_argument("--wait", type=number(0, 60), default=30)
    commands.add_parser("status", help="Read only the session owned by this journal")
    observe = commands.add_parser("observe", help="Read incremental session serial/state/Units and optional frame/evidence")
    observe.add_argument("--serial-limit", type=number(1, 65536, int), default=65536, metavar="1..65536")
    observe.add_argument("--frame", action="store_true")
    observe.add_argument("--evidence", action="store_true")
    observe.add_argument("--out-dir", default="artifacts/emulator")
    stop = commands.add_parser("stop", help="Download evidence before close; retain history with purge=0")
    stop.add_argument("--wait", type=number(0, 60), default=20)
    stop.add_argument("--retain-flash", action="store_true", help="Retain mutable Flash only when flash/diff evidence is needed")
    stop.add_argument("--out-dir", default="artifacts/emulator")
    request = commands.add_parser("request", help="Controlled GET/POST for deployed APIs; consult the service OpenAPI contract")
    request.add_argument("method", choices=["GET", "POST"])
    request.add_argument("route", help="Canonical /api/v1/... path; no credentials in query")
    request.add_argument("--json")
    request.add_argument("--out", help="Save binary response without claiming functional validation")
    request.add_argument("--idempotency-key", help="Stable explicit key for Preview Runs; reuse original request after uncertainty")
    return cli


def main(argv=None):
    args, token = parser().parse_args(argv), ""
    try:
        token = credential()
        client = Client(os.environ.get("M5_EMULATOR_BASE_URL"), token, args.timeout)
        if args.command == "discover":
            suffix = "?" + urlencode({"device_id": args.device}) if args.device else ""
            result = {"devices": client.json("GET", "/api/v1/devices"), "units": client.json("GET", "/api/v1/units" + suffix)}
        elif args.command == "upload":
            path = Path(args.file)
            need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 96 * 1024 * 1024,
                 "invalid_artifact_file", "Choose an explicit regular artifact of at most 96 MiB")
            name = args.name or path.name
            need(name and len(name) <= 255 and all(32 <= ord(char) <= 126 for char in name)
                 and "/" not in name and "\\" not in name, "invalid_artifact_name", "Supply a printable ASCII artifact basename with --name")
            blob = path.read_bytes()
            response = client.json("POST", "/api/v1/artifacts", data=blob,
                                   headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": name})
            need(response.get("sha256") == digest(blob) and response.get("artifact_id") == digest(blob)
                 and response.get("size") == len(blob), "artifact_hash_mismatch", "Artifact receipt did not match the uploaded bytes")
            result = {"artifact": response, "functional_pass": None}
        elif args.command == "compose":
            recipe = json_file(args.json)
            need(isinstance(recipe, dict) and recipe.get("kind") in {"merged", "segmented"} and isinstance(recipe.get("device_id"), str),
                 "explicit_firmware_recipe_required", "Recipe must explicitly declare device_id and kind merged/segmented; use firmware/import for manifests")
            result = {"firmware": client.json("POST", "/api/v1/firmware", recipe), "functional_pass": None}
        else:
            with Journal(args.state, client) as journal:
                agent = Agent(client, journal)
                if args.command == "create":
                    result = agent.admit("session", json_file(args.json), args.wait)
                elif args.command == "status":
                    result = agent.status()
                else:
                    result = getattr(agent, args.command)(args)
        output, status = {"ok": True, "command": args.command, **result}, 0
    except Error as error:
        output, status = {"ok": False, "command": args.command, "error": error.detail}, 2
    except (OSError, ValueError, KeyError, TypeError):
        output, status = {"ok": False, "command": args.command, "error": {
            "category": "client", "code": "unverifiable_state", "message": "Local files or API response could not be verified"}}, 2
    print(json.dumps(scrub(output, token), ensure_ascii=False, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
