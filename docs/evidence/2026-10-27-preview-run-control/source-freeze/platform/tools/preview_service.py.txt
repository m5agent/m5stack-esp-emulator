"""Local Preview/Run coordination over one real Device Service guest per preview.

The ledger persists intent before UART work. A worker owns each console; input
permits drain before replacement. A START marker is never application readiness.
"""
from __future__ import annotations

from contextlib import nullcontext
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import threading
import time

from device_service import ServiceError, _validate_checkpoint_bytecode
from program_packages import ProgramPackageError
from preview_store import PreviewStore, PreviewStoreError, LOCAL_OWNER
from uiflow_runtime import LIVE_PROGRAM_DEVICES
from unit_runtime import UnitRegistry, UnitError


TERMINAL = {"completed", "failed", "cancelled", "superseded", "interrupted"}
CAPABILITIES = {
    "execution_mode": "same-guest-uart-repl", "cleanup_mode": "interrupt-only",
    "latest_wins": True, "run_cancellation": True, "input": True,
    "frame": "on-demand", "events": "polling", "application_ready": "unknown",
    "main_mpy": False, "hotplug": False, "gc_enabled": False,
    "principal_mode": "shared-control-bearer-local-control",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def plain(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ServiceError("invalid_preview_request", "finite JSON values are required", 400) from error


def error_info(error):
    return {"code": getattr(error, "code", "preview_internal_error"),
            "message": getattr(error, "message", "Preview operation could not be verified")}


class _Context:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.input_lock = threading.Lock()
        self.renew_lock = threading.Lock()
        self.wake = threading.Event()
        self.inputs = 0
        self.admission = False
        self.cancel_event = None
        self.run_id = None
        self.handle = None
        self.interrupt_blocked = False
        self.thread = None
        self.expires_at = None


class PreviewService:
    def __init__(self, service, *, _start_workers=True):
        self.service = service
        self.store = PreviewStore(service.state_dir / "preview-state.sqlite")
        self._lock = threading.Lock()
        self._contexts = {}
        self._shutdown = threading.Event()
        self._start_workers = _start_workers
        # Recovery observes persisted allocations and execution records only.
        # It never repeats an allocation marked creating or replays a Run.
        for preview in self._db(self.store.list_previews):
            if preview["state"] not in {"closed", "failed"}:
                self._recover(preview)
                self._context(preview["preview_id"])

    @staticmethod
    def _db(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PreviewStoreError as error:
            raise ServiceError(error.code, error.message, error.status) from error

    def _context(self, preview_id):
        with self._lock:
            context = self._contexts.get(preview_id)
            if context is None:
                context = self._contexts[preview_id] = _Context()
                if self._start_workers and not self._shutdown.is_set():
                    context.thread = threading.Thread(target=self._worker, args=(preview_id, context),
                                                      name=f"m5-preview-{preview_id[:8]}", daemon=True)
                    context.thread.start()
            return context

    @staticmethod
    def _public(preview):
        result = copy.deepcopy(preview)
        result["capabilities"] = copy.deepcopy(result["session_request"]["preview_capabilities"])
        return result

    def _get(self, preview_id, owner=LOCAL_OWNER):
        return self._db(self.store.get_preview, owner, preview_id)

    def _mutate(self, preview_id, callback):
        return self._db(self.store.mutate, preview_id, callback)

    def create(self, payload, *, owner, idempotency_key):
        payload = plain(payload)
        if not isinstance(payload, dict) or set(payload) - {"device_id", "runtime", "units", "ttl_seconds"}:
            raise ServiceError("invalid_preview_request", "device_id, runtime, units and ttl_seconds are accepted", 400)
        device_id, runtime, ttl = payload.get("device_id"), payload.get("runtime", "qemu"), payload.get("ttl_seconds", 300)
        if not isinstance(device_id, str) or not isinstance(runtime, str):
            raise ServiceError("invalid_preview_request", "device_id and runtime must be strings", 400)
        if device_id not in LIVE_PROGRAM_DEVICES or runtime != "qemu":
            raise ServiceError("unsupported_preview_target", "an admitted UIFlow QEMU reference device is required", 409)
        if type(ttl) is not int or not 30 <= ttl <= 3600:
            raise ServiceError("invalid_preview_request", "ttl_seconds must be an integer between 30 and 3600", 400)
        request = {"device_id": device_id, "runtime": runtime, "units": payload.get("units", []), "ttl_seconds": ttl}
        replay = self._db(self.store.lookup_replay, owner, "create-preview", idempotency_key, request)
        if replay is not None:
            return self._public(replay)
        if self._shutdown.is_set():
            raise ServiceError("service_stopping", "Preview service is stopping", 503)
        try:
            registry = UnitRegistry()
            units = registry.attachments(device_id, runtime, request["units"])
            contract = registry.freeze([unit["unit_id"] for unit in units]) if units else None
        except UnitError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        spec = self.service.specs.get(device_id)
        if spec is None or not spec.supported or not spec.backend_ready:
            raise ServiceError("backend_not_ready", "Preview runtime is unavailable", 503)
        with self._allocation_guard():
            reference = self.service.reference_info(spec)
            session_request = {
                **request, "program_mode": "uiflow-live", "ready_timeout_seconds": 40,
                "reference_sha256": reference["sha256"], "frozen_units": units,
                "frozen_unit_contract": contract, "preview_capabilities": CAPABILITIES,
            }
            expiry = datetime.fromtimestamp(time.time() + ttl, timezone.utc).isoformat()
            receipt, replayed = self._db(self.store.create, owner, idempotency_key, request, session_request, expiry)
        if not replayed:
            self._context(receipt["preview_id"]).wake.set()
        return self._public(receipt)

    def list(self, *, owner):
        return {"previews": [self._public(row) for row in self._db(self.store.list_previews, owner)],
                "limits": self.store.limits()}

    def get(self, preview_id, *, owner):
        return self._public(self._get(preview_id, owner))

    def run(self, preview_id, run_id, *, owner):
        return self._db(self.store.get_run, owner, preview_id, run_id)

    def submit(self, preview_id, payload, *, owner, idempotency_key):
        payload = plain(payload)
        scope = f"preview:{preview_id}:runs"
        replay = self._db(self.store.lookup_replay, owner, scope, idempotency_key, payload)
        if replay is not None:
            return replay
        preview = self._get(preview_id, owner)
        if self._shutdown.is_set():
            raise ServiceError("service_stopping", "Preview service is stopping", 503)
        if stamp(preview["expires_at"]) <= time.time():
            raise ServiceError("preview_closing", "Preview lease expired", 409)
        try:
            self.store._run_payload(payload)
        except PreviewStoreError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        # Known host rejection must precede any cancellation of the old program.
        try:
            self.service.program_packages.get(payload["revision_id"])
            files = self.service.program_packages.read_files(payload["revision_id"])
            _validate_checkpoint_bytecode(files)
        except ProgramPackageError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        context = self._context(preview_id)
        with context.condition:
            if self._shutdown.is_set():
                raise ServiceError("service_stopping", "Preview service is stopping", 503)
            if stamp(self._get(preview_id, owner)["expires_at"]) <= time.time():
                raise ServiceError("preview_closing", "Preview lease expired", 409)
            receipt, replayed = self._db(self.store.admit_run, owner, preview_id, idempotency_key, payload)
            if not replayed:
                context.admission = False
                if context.cancel_event is not None:
                    context.cancel_event.set()
                context.wake.set()
        return receipt

    def cancel(self, preview_id, run_id, payload, *, owner):
        if not isinstance(payload, dict) or set(payload) != {"expected_owner_epoch"}:
            raise ServiceError("invalid_preview_request", "expected_owner_epoch is required", 400)
        self._get(preview_id, owner)
        context = self._context(preview_id)
        with context.condition:
            result = self._db(self.store.cancel_run, owner, preview_id, run_id, payload["expected_owner_epoch"])
            if result["state"] == "cancelling":
                context.admission = False
                context.interrupt_blocked = False  # An explicit retry may request a fresh interrupt.
                if context.run_id == run_id and context.cancel_event is not None:
                    context.cancel_event.set()
            context.wake.set()
        return result

    def renew(self, preview_id, payload, *, owner):
        if not isinstance(payload, dict) or set(payload) != {"expected_owner_epoch", "ttl_seconds"}:
            raise ServiceError("invalid_preview_request", "owner epoch and ttl_seconds are required", 400)
        ttl = payload["ttl_seconds"]
        if type(ttl) is not int or not 30 <= ttl <= 3600:
            raise ServiceError("invalid_preview_request", "ttl_seconds must be between 30 and 3600", 400)
        self._get(preview_id, owner)
        context = self._context(preview_id)
        # Serialize physical lease changes with their durable deadline and with
        # post-allocation alignment. Slow session persistence holds no input
        # admission lock, service-global lock or SQLite transaction.
        with context.renew_lock:
            with context.condition:
                if self._shutdown.is_set():
                    raise ServiceError("service_stopping", "Preview service is stopping", 503)
                preview = self._get(preview_id, owner)
                self._epoch(preview, payload["expected_owner_epoch"])
                if preview["state"] not in {"preparing", "ready"} or stamp(preview["expires_at"]) <= time.time():
                    raise ServiceError("preview_closing", "Preview lease cannot be renewed", 409)
                expiry = datetime.fromtimestamp(time.time() + ttl, timezone.utc).isoformat()
                session, handle = self._session(preview, context) if preview["session_id"] else (None, None)
            if session is not None:
                session.require_management_handle(handle)
                session.renew(ttl)
            with context.condition:
                if self._shutdown.is_set():
                    raise ServiceError("service_stopping", "Preview service is stopping", 503)
                latest = self._get(preview_id, owner)
                if latest["state"] not in {"preparing", "ready"} or stamp(latest["expires_at"]) <= time.time():
                    raise ServiceError("preview_closing", "Preview closed or expired during renewal", 409)
                self._mutate(preview_id, lambda state: state["preview"].update(expires_at=expiry))
                context.expires_at = stamp(expiry)
                context.wake.set()
        return self.get(preview_id, owner=owner)

    @staticmethod
    def _epoch(preview, epoch):
        if epoch != preview["owner_epoch"]:
            raise ServiceError("preview_owner_conflict", "Preview owner epoch differs", 409)

    @staticmethod
    def _closing(state):
        preview, runs = state["preview"], state["runs"]
        if preview["state"] == "closed":
            return
        preview["state"] = "closing"
        for run in runs.values():
            if run["state"] in TERMINAL:
                continue
            untouched = run["state"] == "queued" and run["run_id"] not in {preview["active_run_id"], preview["transition_run_id"]}
            run.update(cancel_intent=True, state="cancelled" if untouched else "cancelling")
            if untouched:
                run["interrupt_ack"] = "not-required"
        preview["desired_run_id"] = None

    def close(self, preview_id, payload, *, owner):
        if not isinstance(payload, dict) or set(payload) != {"expected_owner_epoch"}:
            raise ServiceError("invalid_preview_request", "expected_owner_epoch is required", 400)
        self._get(preview_id, owner)
        context = self._context(preview_id)
        with context.condition:
            preview = self._get(preview_id, owner)
            self._epoch(preview, payload["expected_owner_epoch"])
            self._mutate(preview_id, self._closing)
            context.admission = False
            if context.cancel_event is not None:
                context.cancel_event.set()
            context.wake.set()
        return self.get(preview_id, owner=owner)

    def shutdown(self):
        """Nonblocking: DeviceService retains responsibility for actual teardown."""
        self._shutdown.set()
        with self._lock:
            contexts = tuple(self._contexts.values())
        for context in contexts:
            if context.cancel_event is not None:
                context.cancel_event.set()
            context.wake.set()

    def _allocation_guard(self):
        # Retention integration supplies a short-delete barrier, never the
        # DeviceService global lock or a ledger transaction across composition.
        guard = getattr(self.service, "preview_allocation_guard", None)
        return guard() if guard is not None else nullcontext()

    def _session(self, preview, context):
        if not preview["session_id"]:
            raise ServiceError("preview_not_ready", "Preview has no verified session", 409)
        session = self.service.get_session(preview["session_id"])
        if context.handle is None:
            context.handle = self.service.recover_management_handle(
                preview["session_id"], preview_id=preview["preview_id"], owner_epoch=preview["owner_epoch"],
                expected_reference_sha256=preview["session_request"]["reference_sha256"],
            )
        session.require_management_handle(context.handle)
        identity = preview.get("session_identity")
        if identity and (session.id != identity["session_id"] or session.firmware_sha != identity["firmware_sha256"]):
            raise ServiceError("preview_session_changed", "Preview session identity differs", 409)
        return session, context.handle

    def _active(self, preview_id, run_id, owner):
        preview = self._get(preview_id, owner)
        run = self._db(self.store.get_run, owner, preview_id, run_id)
        if stamp(preview["expires_at"]) <= time.time():
            raise ServiceError("preview_closing", "Preview lease expired", 409)
        if preview["state"] != "ready" or preview["active_run_id"] != run_id:
            code, status = ("run_frame_unavailable", 410) if run["state"] in TERMINAL else ("preview_run_changed", 409)
            raise ServiceError(code, "Run has no current verified sample", status)
        if run["cancel_intent"] or run["state"] not in {"running", "completed"}:
            raise ServiceError("preview_run_changed", "Run is changing or unconfirmed", 409)
        return preview, run

    def frame(self, preview_id, run_id, *, owner, max_age_ms=0):
        if type(max_age_ms) is not int or not 0 <= max_age_ms <= 1000:
            raise ServiceError("invalid_frame_age", "max_age_ms must be between 0 and 1000", 400)
        self._get(preview_id, owner)
        context = self._context(preview_id)
        with context.condition:
            preview, run = self._active(preview_id, run_id, owner)
            session, _ = self._session(preview, context)
            before = session.program_status().get("program") or {}
            if before.get("execution_id") != run["execution_id"]:
                raise ServiceError("preview_run_changed", "Session execution differs", 409)
        sample = session.preview_frame(max_age_ms) if max_age_ms else session.frame_metrics(analyze=False)
        with context.condition:
            try:
                self._active(preview_id, run_id, owner)
            except ServiceError as error:
                if error.code in {"run_frame_unavailable", "preview_run_changed"}:
                    raise ServiceError("preview_run_changed", "Run changed during frame capture", 409) from error
                raise
            after = session.program_status().get("program") or {}
            if after.get("execution_id") != run["execution_id"] or sample.get("execution_id") != run["execution_id"] or sample.get("revision_id") != run["revision_id"]:
                raise ServiceError("preview_run_changed", "Run changed during frame capture", 409)
        digest = hashlib.sha256(sample["png"]).hexdigest()
        etag = hashlib.sha256(f"{preview_id}:{run_id}:{run['revision_id']}:{digest}".encode()).hexdigest()
        headers = {"X-Preview-ID": preview_id, "X-Run-ID": run_id,
                   "X-Frame-Execution-ID": run["execution_id"], "X-Frame-Revision-ID": run["revision_id"],
                   "X-Frame-Width": str(sample["width"]), "X-Frame-Height": str(sample["height"]),
                   "X-Frame-SHA256": digest, "ETag": '"' + etag + '"'}
        for field, header in (("captured_at", "X-Frame-Captured-At"), ("capture_seq", "X-Frame-Capture-Seq"),
                              ("source", "X-Frame-Source"), ("program_state", "X-Frame-Program-State")):
            if sample.get(field) is not None:
                headers[header] = str(sample[field])
        return {"png": sample["png"], "headers": headers}

    @staticmethod
    def _momentary(payload, unit=False):
        if not unit:
            if payload.get("kind") == "key" and payload.get("action") in {"down", "up"}:
                return "key:" + str(payload.get("key")), {**payload, "action": "up", "settle_seconds": 0}, payload["action"] == "down"
            return None
        values = payload.get("values", {})
        if not isinstance(values, dict):
            return None
        release, held = {}, False
        for field, value in values.items():
            if field != "pressed" and not field.endswith("-pressed"):
                continue
            if type(value) is bool:
                release[field], held = False, held or value
            elif isinstance(value, list) and value and all(type(item) is bool for item in value):
                release[field], held = [False] * len(value), held or any(value)
        if release:
            key = "unit:" + str(payload.get("id")) + ":" + ",".join(sorted(release))
            return key, {"id": payload.get("id"), "values": release}, held
        return None

    def input(self, preview_id, payload, *, owner):
        payload = plain(payload)
        fields = {"expected_owner_epoch", "expected_run_id", "input", "unit_input"}
        if not isinstance(payload, dict) or set(payload) - fields or not {"expected_owner_epoch", "expected_run_id"} <= payload.keys() or sum(name in payload for name in ("input", "unit_input")) != 1:
            raise ServiceError("invalid_preview_request", "owner epoch, expected_run_id and one input payload are required", 400)
        unit = "unit_input" in payload
        command = payload["unit_input" if unit else "input"]
        if not isinstance(command, dict):
            raise ServiceError("invalid_preview_request", "input must be an object", 400)
        self._get(preview_id, owner)
        context = self._context(preview_id)
        run_id = payload["expected_run_id"]
        with context.condition:
            if self._shutdown.is_set():
                raise ServiceError("service_stopping", "Preview service is stopping", 503)
            preview, run = self._active(preview_id, run_id, owner)
            self._epoch(preview, payload["expected_owner_epoch"])
            if not context.admission or run["state"] != "running" or preview["transition_run_id"] is not None:
                raise ServiceError("preview_run_changed", "Run is not accepting input", 409)
            session, handle = self._session(preview, context)
            session.require_management_handle(handle)
            # Reject deterministic host errors before recording a release
            # obligation. QMP failures after this point retain their intent.
            command = session.validate_unit_input(command) if unit else session.validate_input(command)
            momentary = self._momentary(command, unit)
            if not unit and any(command.get(field, 0) > 5 for field in ("settle_seconds", "hold_seconds")):
                raise ServiceError("invalid_input", "Preview input durations must not exceed 5 seconds", 400)
            context.inputs += 1
        try:
            # Keep physical application and its held-input receipt in the same
            # order. Permits are acquired first, so a waiting input still fences
            # a program replacement without occupying the admission/DB lock.
            with context.input_lock:
                if momentary and momentary[2]:
                    # Record immediately before this command's effect, in the
                    # same order as prior receipts. A queued press must not be
                    # erased by an earlier release that is still in flight.
                    def remember(state):
                        held = state["preview"].setdefault("held_inputs", {})
                        held[momentary[0]] = {"unit": unit, "payload": momentary[1], "run_id": run_id}
                    self._mutate(preview_id, remember)
                result = session.unit_input(command) if unit else session.inject(command)
                with context.condition:
                    if momentary:
                        def applied(state):
                            held = state["preview"].setdefault("held_inputs", {})
                            if momentary[2]:
                                held[momentary[0]] = {"unit": unit, "payload": momentary[1], "run_id": run_id}
                            else:
                                held.pop(momentary[0], None)
                        self._mutate(preview_id, applied)
                    try:
                        latest, latest_run = self._active(preview_id, run_id, owner)
                    except ServiceError as error:
                        if error.code in {"preview_run_changed", "run_frame_unavailable"}:
                            raise ServiceError("preview_run_changed", "Run changed while input was in flight", 409, effect_possible=True) from error
                        raise
                    if latest_run["state"] != "running" or latest["transition_run_id"] is not None:
                        raise ServiceError("preview_run_changed", "Run changed while input was in flight", 409, effect_possible=True)
            return {"preview_id": preview_id, "run_id": run_id, "execution_id": run["execution_id"],
                    "revision_id": run["revision_id"], "captured_at": now(), "result": result}
        finally:
            with context.condition:
                context.inputs -= 1
                context.condition.notify_all()
                context.wake.set()

    def _drained(self, preview_id, context):
        with context.condition:
            context.admission = False
            if context.inputs:
                self._mutate(preview_id, lambda state: state["preview"].update(blocked_reason="input_draining"))
                return False
        return True

    def _release_held(self, preview, session):
        # Inputs may have completed after the worker's earlier snapshot, before
        # its drain observed zero permits. Read the durable intents after drain.
        current = self._get(preview["preview_id"])
        if session.state != "running":
            if current.get("held_inputs"):
                self._mutate(preview["preview_id"], lambda state: state["preview"].update(held_inputs={}, held_release="session-not-running"))
            return
        for key, command in current.get("held_inputs", {}).items():
            if command["unit"]:
                session.unit_input(command["payload"])
            else:
                session.inject(command["payload"])
            self._mutate(preview["preview_id"], lambda state, key=key: state["preview"].setdefault("held_inputs", {}).pop(key, None))

    def _bind(self, preview, snapshot):
        session = self.service.get_session(snapshot["session_id"])
        frozen = preview["session_request"]
        if session.units != frozen["frozen_units"] or session.unit_contract != frozen["frozen_unit_contract"]:
            raise ServiceError("preview_target_changed", "Unit assembly or contract changed during allocation", 409)
        def bind(state):
            state["preview"].update(session_id=session.id, allocation_state="bound",
                                    session_identity={"session_id": session.id, "firmware_sha256": session.firmware_sha},
                                    blocked_reason=None)
        self._mutate(preview["preview_id"], bind)

    def _recover(self, preview):
        preview_id = preview["preview_id"]
        if preview["allocation_state"] == "pending":
            return
        if preview["allocation_state"] == "creating" and not preview["session_id"]:
            with self.service._lock:
                candidates = [session for session in self.service._sessions.values()
                              if (getattr(session, "management_binding", None) or {}).get("preview_id") == preview_id]
            if len(candidates) != 1:
                self._mutate(preview_id, lambda state: state["preview"].update(state="unknown", allocation_state="unknown", error={"code": "preview_allocation_unconfirmed", "message": "Allocation intent has no unique verifiable session; it will not be replayed"}))
                return
            self.service.recover_management_handle(candidates[0].id, preview_id=preview_id,
                                                   owner_epoch=preview["owner_epoch"], expected_reference_sha256=preview["session_request"]["reference_sha256"])
            self._bind(preview, candidates[0].snapshot())
        def recover_runs(state):
            p = state["preview"]
            for run in state["runs"].values():
                if run["state"] in {"preparing", "starting", "running"}:
                    run.update(state="unknown", error={"code": "preview_recovery_observation_required", "message": "Execution will be observed, never replayed"})
            p.update(active_run_id=None, transition_run_id=None, recovered_at=now())
        self._mutate(preview_id, recover_runs)

    def _allocate(self, preview, context):
        preview_id = preview["preview_id"]
        with self._allocation_guard():
            def begin(state):
                current = state["preview"]
                if self._shutdown.is_set() or current["state"] != "preparing" or current["allocation_state"] != "pending" or stamp(current["expires_at"]) <= time.time():
                    return False
                current["allocation_state"] = "creating"
                return True
            with context.condition:
                if not self._mutate(preview_id, begin):
                    return
            request = copy.deepcopy(preview["session_request"])
            reference = request.pop("reference_sha256")
            request.pop("frozen_units")
            request.pop("frozen_unit_contract")
            request.pop("preview_capabilities")
            request["idempotency_key"] = preview["allocation_key"]
            try:
                snapshot, context.handle = self.service.create_managed_session(
                    request, preview_id=preview_id, owner_epoch=preview["owner_epoch"], expected_reference_sha256=reference,
                )
                self._bind(preview, snapshot)
                # Renew may have arrived while this asynchronous allocation
                # was pending or composing. The immutable original request is
                # not the current lease; align before exposing ready.
                with context.renew_lock:
                    latest = self._get(preview_id)
                    session, handle = self._session(latest, context)
                    session.require_management_handle(handle)
                    session.renew(max(30, min(3600, math.ceil(stamp(latest["expires_at"]) - time.time()))))
            except Exception as error:
                # Find a persisted managed receipt before classifying failure.
                with self.service._lock:
                    candidates = [s for s in self.service._sessions.values() if (getattr(s, "management_binding", None) or {}).get("preview_id") == preview_id]
                if len(candidates) == 1:
                    self._mutate(preview_id, lambda state: state["preview"].update(session_id=candidates[0].id, allocation_state="bound", state="closing", error=error_info(error)))
                else:
                    self._mutate(preview_id, lambda state: state["preview"].update(allocation_state="failed" if isinstance(error, ServiceError) else "unknown", state="failed" if isinstance(error, ServiceError) else "unknown", error=error_info(error)))

    def _observe(self, preview_id, program):
        def observe(state):
            p = state["preview"]
            if self._shutdown.is_set() or stamp(p["expires_at"]) <= time.time():
                self._closing(state)
                return
            for run in state["runs"].values():
                if run["execution_id"] != program.get("execution_id"):
                    continue
                run["last_observation"] = plain(program)
                if run["state"] in TERMINAL or run["cancel_intent"] or p["state"] != "ready":
                    continue
                observed = program.get("state")
                if observed in {"running", "completed", "failed"}:
                    run.update(state=observed, observed_at=now())
                    p["active_run_id"] = run["run_id"] if observed in {"running", "completed"} else None
                    if p["transition_run_id"] == run["run_id"]:
                        p["transition_run_id"] = None
        self._mutate(preview_id, observe)

    def _interrupt(self, preview, context, session):
        if context.interrupt_blocked or not self._drained(preview["preview_id"], context):
            return
        try:
            self._release_held(preview, session)
            program = session.program_status().get("program")
            expected = program.get("execution_id") if program else None
            receipt = session.interrupt_program(expected_execution_id=expected, timeout_seconds=10, management_handle=context.handle)
            ack = receipt.get("interrupt_ack") or (receipt.get("program") or {}).get("interrupt_ack")
            if not isinstance(ack, dict) or ack.get("interruption_confirmed") is not True:
                raise ServiceError("preview_interrupt_unconfirmed", "Guest prompt was not confirmed", 409)
            def confirmed(state):
                p = state["preview"]
                for run in state["runs"].values():
                    if run["state"] == "cancelling":
                        run.update(state="cancelled", interrupt_ack="confirmed", interrupt_receipt=plain(ack),
                                   interrupt_observed_execution_id=expected, interrupted_at=now())
                        if p["active_run_id"] == run["run_id"]:
                            p["active_run_id"] = None
                        if p["transition_run_id"] == run["run_id"]:
                            p["transition_run_id"] = None
                p.update(blocked_reason=None, error=None)
            self._mutate(preview["preview_id"], confirmed)
        except Exception as error:
            context.interrupt_blocked = True
            self._mutate(preview["preview_id"], lambda state: state["preview"].update(blocked_reason="interrupt_unconfirmed", error=error_info(error)))

    def _transfer(self, preview, run, context, session):
        preview_id, run_id = preview["preview_id"], run["run_id"]
        if not self._drained(preview_id, context):
            return
        with context.condition:
            token = threading.Event()
            current = self._db(self.store.get_run, LOCAL_OWNER, preview_id, run_id)
            if current["cancel_intent"] or self._get(preview_id)["state"] != "ready":
                return
            context.cancel_event, context.run_id = token, run_id
        def synchronized():
            def update(state):
                p, current = state["preview"], state["runs"][run_id]
                p["active_run_id"] = None
                if not current["cancel_intent"]:
                    current.update(state="starting", synchronized_at=now())
            self._mutate(preview_id, update)
        try:
            self._release_held(preview, session)
            actual = session.program_status().get("program")
            expected = actual.get("execution_id") if actual else None
            result = session.run_revision(run["revision_id"], execution_id=run["execution_id"],
                                          expected_execution_id=expected, timeout_seconds=run["timeout_seconds"],
                                          cancelled=lambda: token.is_set() or self._shutdown.is_set() or (context.expires_at is not None and time.time() >= context.expires_at),
                                          on_synchronized=synchronized, management_handle=context.handle)
            program = result.get("program") or {}
            if program.get("execution_id") != run["execution_id"] or program.get("revision_id") != run["revision_id"]:
                raise ServiceError("preview_execution_changed", "Execution receipt differs from reserved identity", 409)
            self._observe(preview_id, program)
        except Exception as error:
            def failed(state):
                p, current = state["preview"], state["runs"][run_id]
                current["error"] = error_info(error)
                if current["cancel_intent"]:
                    current["state"] = "cancelling"
                else:
                    current["state"] = "unknown"
                p["blocked_reason"] = "execution_unconfirmed" if not current["cancel_intent"] else None
            self._mutate(preview_id, failed)
        finally:
            with context.condition:
                context.cancel_event, context.run_id = None, None
                current = self._get(preview_id)
                context.admission = current["state"] == "ready" and current["active_run_id"] == run_id and current["transition_run_id"] is None

    def _close_step(self, preview, context):
        if not self._drained(preview["preview_id"], context):
            return
        if preview["session_id"] is None:
            if preview["allocation_state"] in {"creating", "unknown"}:
                self._mutate(preview["preview_id"], lambda state: state["preview"].update(blocked_reason="allocation_unconfirmed"))
                return
            receipt = {"state": "stopped", "no_session_allocated": True}
        else:
            session, handle = self._session(preview, context)
            session.require_management_handle(handle)
            try:
                self._release_held(preview, session)
            except Exception as error:
                # An explicit close/expired lease must still tear down the
                # owned VM even when its controller cannot release an input.
                self._mutate(preview["preview_id"], lambda state: state["preview"].update(held_release_error=error_info(error)))
            if "close_evidence" not in preview:
                try:
                    bundle = session.evidence_bundle()
                    directory = self.service.state_dir / "previews" / preview["preview_id"]
                    directory.mkdir(parents=True, exist_ok=True)
                    path = directory / "before-close.zip"
                    temporary = directory / "before-close.zip.part"
                    temporary.write_bytes(bundle)
                    temporary.replace(path)
                    evidence = {"status": "captured", "captured_at": now(), "size": len(bundle),
                                "sha256": hashlib.sha256(bundle).hexdigest(), "path": str(path.relative_to(self.service.state_dir))}
                except Exception as error:
                    # Evidence failure must remain visible, but cannot strand
                    # a process/lease after an explicit close or lease expiry.
                    evidence = {"status": "unavailable", "captured_at": now(), "error": error_info(error)}
                self._mutate(preview["preview_id"], lambda state: state["preview"].update(close_evidence=evidence))
            receipt = session.stop(purge=False, retain_flash=False)
            if receipt.get("state") not in {"stopped", "failed"} or receipt.get("stop_pending") or getattr(session, "_worker_lease_active", False):
                return
        def closed(state):
            p = state["preview"]
            for run in state["runs"].values():
                if run["state"] not in TERMINAL:
                    run.update(state="interrupted", close_receipt=plain(receipt))
            p.update(state="closed", active_run_id=None, transition_run_id=None, desired_run_id=None,
                     completed_at=now(), cleanup=plain(receipt), blocked_reason=None)
        self._mutate(preview["preview_id"], closed)

    def _step(self, preview_id, context):
        with context.condition:
            preview = self._get(preview_id)
            context.expires_at = stamp(preview["expires_at"])
        if self._shutdown.is_set():
            return
        if preview["state"] == "closed":
            return
        if stamp(preview["expires_at"]) <= time.time() and preview["state"] != "closing":
            self._mutate(preview_id, self._closing)
            preview = self._get(preview_id)
        if preview["state"] == "closing":
            self._close_step(preview, context)
            return
        if preview["state"] in {"failed", "unknown"}:
            return
        if preview["allocation_state"] == "pending":
            self._allocate(preview, context)
            return
        session, _ = self._session(preview, context)
        if session.state != "running":
            if session.state in {"stopped", "failed"}:
                def lost(state):
                    state["preview"].update(state="failed", active_run_id=None, transition_run_id=None,
                                            error={"code": "preview_session_stopped", "message": "Bound session is no longer running"})
                    for run in state["runs"].values():
                        if run["state"] not in TERMINAL:
                            run["state"] = "interrupted"
                self._mutate(preview_id, lost)
            return
        if preview["state"] == "preparing":
            self._mutate(preview_id, lambda state: state["preview"].update(state="ready"))
            preview = self._get(preview_id)
        self._observe(preview_id, session.program_status().get("program") or {})
        state = self._mutate(preview_id, lambda value: value)
        preview, runs = state["preview"], state["runs"]
        if any(run["state"] == "cancelling" for run in runs.values()):
            self._interrupt(preview, context, session)
            return
        desired = runs.get(preview["desired_run_id"])
        if desired is None or desired["state"] not in {"queued", "preparing"}:
            with context.condition:
                active = runs.get(preview["active_run_id"])
                context.admission = bool(active and active["state"] == "running" and not active["cancel_intent"] and preview["transition_run_id"] is None)
            return
        def claim(state):
            p, current = state["preview"], state["runs"][desired["run_id"]]
            if p["state"] != "ready" or p["desired_run_id"] != desired["run_id"] or current["cancel_intent"] or current["state"] not in {"queued", "preparing"}:
                return False
            current["state"] = "preparing"
            p["transition_run_id"] = current["run_id"]
            return True
        if self._mutate(preview_id, claim):
            self._transfer(self._get(preview_id), desired, context, session)

    def _worker(self, preview_id, context):
        while not self._shutdown.is_set():
            context.wake.clear()
            try:
                self._step(preview_id, context)
                if self._get(preview_id)["state"] == "closed":
                    return
            except Exception as error:
                try:
                    self._mutate(preview_id, lambda state: state["preview"].update(error=error_info(error), blocked_reason="worker_unconfirmed"))
                except Exception:
                    pass
            context.wake.wait(0.1)
