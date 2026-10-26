"""Independent host tests for binary-entrypoint admission and base selection.

Real Session persistence, immutable stores, source composition and management
fences are exercised. Guest UART, process launch and entrypoint execution are
mocked or forbidden. A synthetic verified receipt tests host binding checks;
it is not new firmware, canary or physical-hardware execution evidence.
"""
from __future__ import annotations

import base64
import copy
from dataclasses import replace
import hashlib
import unittest
from unittest import mock

import device_service as service_module
import uiflow_main_loader as loader
from test_device_program_packages import _PackageFixture
from test_mpy_bytecode import HELPER, NATIVE
from test_uiflow_service import ServiceFixture, canonical, store_explicit_base
from uiflow_runtime import execution_markers, live_bootstrap_files


def verified_core():
    """The fixed, compiler-pinned canary receipt; never run by these tests."""
    nonce = "a" * 32
    return {
        "schema_version": 1, "status": "verified", "mpy_entrypoint": True,
        "loader": loader.LOADER, "mpy": 11014,
        "small_int_bits": 31,
        "probe": {
            "kind": loader.PROBE_KIND, "nonce": nonce,
            "status": "PASS", "owner_restored": True, "cleanup_complete": True,
            "owner_before_id": 123, "owner_after_id": 123,
            "canary_sha256": loader.CANARY_SHA256, "file_sha256": loader.CANARY_SHA256,
            "source_sha256": loader.CANARY_SOURCE_SHA256,
            "compiler_sha256": loader.CANARY_COMPILER_SHA256,
            "file_bytes": len(loader.CANARY_BYTES), "body_entered": True,
            "actual_identity": {
                "if_main": True, "name": "__main__",
                "file": loader.PROBE_ROOT + nonce + "/main.mpy",
                "real_main_name": "main", "main_id": 456,
                "sys_main_id": 456, "import_main_id": 456, "nonce": nonce,
            },
        },
    }


def session_identity(session):
    return {
        "session_id": session.id, "device_id": session.spec.id,
        "pid": session.pid, "firmware_sha256": session.firmware_sha,
        "runtime": session.runtime, "worker_generation": session.worker_generation,
        "process_start_token": session.process_start_token,
    }


class MainLoaderAdmissionTests(_PackageFixture):
    def target(self, **kwargs):
        session = self.session(**kwargs)
        self.console(session)
        session.pid = 424242
        session.process_start_token = "fixture-owned-process-start"
        return session

    def admit(self, session):
        session._program_capabilities = {
            **verified_core(), "identity": session_identity(session),
        }
        self.assertTrue(session.program_capabilities()["mpy_entrypoint"])

    @staticmethod
    def binary_payload(**changes):
        return {
            "source_kind": "uiflow2-package", "entrypoint": "main.mpy",
            "files": {"main.mpy": {
                "encoding": "base64", "data": base64.b64encode(HELPER).decode("ascii"),
            }},
            **changes,
        }

    def state_bytes(self, session):
        return {
            "program": copy.deepcopy(session._program),
            "events": copy.deepcopy(session.events),
            "files": {
                str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()
            },
        }

    def active_source(self, session):
        self.execute.return_value["state"] = "running"
        previous = session.run_program({"source": "print('old program')\n", "expected_execution_id": None})["program"]
        self.execute.reset_mock()
        self.deploy.reset_mock()
        return previous

    def active_binary(self, session):
        self.admit(session)

        def deployed(console, files, revision, *, on_synchronized, on_progress, **kwargs):
            package_path = "/flash/.m5-live-packages/" + revision["revision_id"]
            progress = lambda values: on_progress({**values, **({"package_path": package_path} if "package_path" in values else {})})
            receipt = self.deploy_success(console, files, revision, on_synchronized=on_synchronized, on_progress=progress, **kwargs)
            return {**receipt, "package_path": package_path}

        self.deploy.side_effect = deployed
        runner = self.stack.enter_context(mock.patch.object(service_module, "run_mpy", return_value={
            "state": "running", "acknowledged": True, "serial_offset": 0,
            "next_offset": 0, "entrypoint": "main.mpy", "execution_phase": "import-requested",
            "application_started": None, "application_ready": None,
            "start_semantics": "import-request-only", "cleanup_mode": "interrupt-only",
        }))
        program = session.run_program(self.binary_payload(expected_execution_id=None))["program"]
        return program, runner

    def assert_early_rejection(self, session, payload, *, code=None):
        before = self.state_bytes(session)
        error = self.assert_service_error(lambda: session.run_program(payload), code=code, status=409)
        self.assertEqual(self.state_bytes(session), before, "rejected binary must preserve the old execution, evidence and stores")
        self.deploy.assert_not_called()
        self.execute.assert_not_called()
        return error

    def test_default_and_manual_uart_sessions_are_unknown_without_guest_probe(self):
        session = self.target()
        before = self.state_bytes(session)
        self.assertFalse(session.program_capabilities()["mpy_entrypoint"])
        self.assertEqual(session.program_capabilities()["status"], "unknown")
        self.assertEqual(self.state_bytes(session), before, "capability reads must not probe or mutate UART/history")
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_verified_receipt_is_bound_to_every_current_guest_identity_field(self):
        session = self.target()
        self.admit(session)
        saved = copy.deepcopy(session._program_capabilities)
        for field in session_identity(session):
            session._program_capabilities = copy.deepcopy(saved)
            value = saved["identity"][field]
            session._program_capabilities["identity"][field] = value + 1 if type(value) is int else str(value) + "-changed"
            with self.subTest(field=field):
                self.assertFalse(session.program_capabilities()["mpy_entrypoint"])
                self.assertEqual(session.program_capabilities()["status"], "unknown")
        session._program_capabilities = saved
        self.assertTrue(session.program_capabilities()["mpy_entrypoint"])

    def test_nonrunning_state_never_grants_recorded_loader_admission(self):
        session = self.target()
        self.admit(session)
        for state in ("provisioning", "flashing", "booting", "failed", "stopped"):
            session.state = state
            with self.subTest(state=state):
                self.assertFalse(session.program_capabilities()["mpy_entrypoint"])
        session.state = "running"

    def test_missing_concrete_process_identity_stays_unknown_even_if_record_matches(self):
        session = self.target()
        for pid, token in ((None, "start"), (0, "start"), (True, "start"), (424242, None), (424242, "")):
            session.pid, session.process_start_token = pid, token
            session._program_capabilities = {**verified_core(), "identity": session_identity(session)}
            with self.subTest(pid=pid, token_present=bool(token)):
                self.assertFalse(session.program_capabilities()["mpy_entrypoint"])

    def test_reset_revokes_old_loader_proof_without_reprobing_during_the_mutation(self):
        session = self.target()
        self.admit(session)
        with mock.patch.object(session, "_qmp_call") as qmp:
            session.reset()
        qmp.assert_called_once_with("system_reset")
        self.assertFalse(session.program_capabilities()["mpy_entrypoint"])
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_restored_session_does_not_inherit_a_persisted_true_receipt(self):
        session = self.target()
        self.admit(session)
        session._persist_session()
        restored = self.target(sid=session.id, restored=True)
        self.assertEqual(session_identity(restored), session_identity(session))
        self.assertFalse(restored.program_capabilities()["mpy_entrypoint"])

    def test_semantic_or_restoration_evidence_cannot_be_replaced_by_a_true_flag(self):
        session = self.target()
        self.admit(session)
        saved = copy.deepcopy(session._program_capabilities)
        mutations = (
            lambda row: row.update(status="unknown"),
            lambda row: row.update(loader="caller-declared-loader"),
            lambda row: row.update(small_int_bits=32),
            lambda row: row["probe"].update(owner_restored=False),
            lambda row: row["probe"].update(cleanup_complete=False),
            lambda row: row["probe"].update(file_sha256="0" * 64),
            lambda row: row["probe"].update(body_entered=False),
            lambda row: row["probe"]["actual_identity"].update(if_main=False),
            lambda row: row["probe"]["actual_identity"].update(import_main_id=789),
        )
        for index, mutate in enumerate(mutations):
            session._program_capabilities = copy.deepcopy(saved)
            mutate(session._program_capabilities)
            with self.subTest(mutation=index):
                self.assertFalse(session.program_capabilities()["mpy_entrypoint"])

    def test_capability_result_is_detached_from_internal_admission(self):
        session = self.target()
        self.admit(session)
        view = session.program_capabilities()
        view["identity"]["session_id"] = "unrelated-session"
        view["probe"]["owner_restored"] = False
        self.assertTrue(session.program_capabilities()["mpy_entrypoint"])

    def test_stock_unknown_and_identity_mismatch_inline_binary_preserve_old_program_and_package_slots(self):
        for status in ("stock", "unknown", "wrong-session"):
            session = self.target()
            old = self.active_source(session)
            if status == "stock":
                session._program_capabilities = {"status": "unsupported", "mpy_entrypoint": False}
            elif status == "wrong-session":
                self.admit(session)
                session._program_capabilities["identity"]["session_id"] = "b" * 32
            with self.subTest(status=status):
                self.assert_early_rejection(session, self.binary_payload(expected_execution_id=old["execution_id"]))
                self.assertEqual(list(self.service.program_packages.root.glob("*.json")), [])

    def test_saved_binary_checkpoint_unknown_loader_rejects_before_old_program_interruption(self):
        session = self.target()
        old = self.active_source(session)
        revision = self.service.program_packages.create(self.binary_payload())
        self.assert_early_rejection(session, {"revision_id": revision["revision_id"], "expected_execution_id": old["execution_id"]})
        self.assertEqual(self.service.program_packages.get(revision["revision_id"]), revision)

    def test_loader_revoked_during_store_read_rejects_before_execution_allocation(self):
        for by_reference in (False, True):
            session = self.target()
            self.admit(session)
            old = self.active_source(session)
            package = self.binary_payload()
            if by_reference:
                revision = self.service.program_packages.create(package)
                payload = {"revision_id": revision["revision_id"], "expected_execution_id": old["execution_id"]}
            else:
                payload = {**package, "expected_execution_id": old["execution_id"]}
            before = copy.deepcopy(session._program)
            program_files = {path.name: path.read_bytes() for path in (session.dir / "programs").glob("*.json")}
            current_record = session.program_path.read_bytes()
            read_files = self.service.program_packages.read_files

            def revoked_after_read(revision_id):
                files = read_files(revision_id)
                session._invalidate_program_loader("independent-store-read-race")
                return files

            with self.subTest(by_reference=by_reference), mock.patch.object(self.service.program_packages, "read_files", side_effect=revoked_after_read):
                error = self.assert_service_error(lambda: session.run_program(payload), status=409)
                self.assertIn(error.code, ("program_mpy_entrypoint_unsupported", "program_mpy_capability_unknown"))
            self.assertEqual(session._program, before)
            self.assertEqual(session.program_path.read_bytes(), current_record)
            self.assertEqual({path.name: path.read_bytes() for path in (session.dir / "programs").glob("*.json")}, program_files)
            self.deploy.assert_not_called()
            self.execute.assert_not_called()

    def test_verified_session_dispatches_unchanged_binary_to_the_mpy_runner(self):
        session = self.target()
        program, runner = self.active_binary(session)
        self.assertEqual(program["entrypoint"], "main.mpy")
        self.assertEqual(program["source_bytes"], len(HELPER))
        self.assertEqual(program["execution_phase"], "import-requested")
        self.assertIsNone(program["application_started"])
        self.assertEqual(self.service.program_packages.read_files(program["revision_id"])["main.mpy"], HELPER)
        runner.assert_called_once()
        self.assertIs(runner.call_args.args[0], session._console)
        self.assertEqual(runner.call_args.args[1], program["execution_id"])
        self.assertEqual(runner.call_args.kwargs["entrypoint_sha256"], hashlib.sha256(HELPER).hexdigest())
        self.assertEqual(runner.call_args.kwargs["loader_capabilities"]["identity"], session_identity(session))
        self.execute.assert_not_called()

    def test_verified_loader_still_rejects_native_and_bad_bytecode_before_cancelling_or_saving(self):
        session = self.target()
        self.admit(session)
        old = self.active_source(session)
        for data, code in ((NATIVE, "program_mpy_native_unsupported"), (HELPER[:-1], "program_mpy_invalid")):
            payload = self.binary_payload(expected_execution_id=old["execution_id"])
            payload["files"]["main.mpy"]["data"] = base64.b64encode(data).decode("ascii")
            with self.subTest(code=code):
                self.assert_early_rejection(session, payload, code=code)
                self.assertEqual(list(self.service.program_packages.root.glob("*.json")), [])

    def test_status_observation_of_restore_error_revokes_admission_and_preserves_the_failure(self):
        session = self.target()
        program, runner = self.active_binary(session)
        self.deploy.reset_mock()
        session._console.append(execution_markers(program["execution_id"])["RESTORE_ERROR"] + b"\r\n")
        observed = session.program_status()
        self.assertFalse(observed["program_capabilities"]["mpy_entrypoint"])
        self.assertTrue(observed["program"]["loader_restore_failed"])
        self.assertIs(observed["program"]["owner_restored"], False)
        self.assertEqual(observed["program"]["error"]["code"], "program_main_loader_restore_failed")
        self.assert_early_rejection(session, self.binary_payload(expected_execution_id=program["execution_id"]))
        self.assertEqual(runner.call_count, 1)

    def test_ctrl_c_prompt_receipt_cannot_hide_an_old_binary_restore_error(self):
        session = self.target()
        program, runner = self.active_binary(session)
        self.deploy.reset_mock()

        def synchronize(*args, **kwargs):
            session._console.append(execution_markers(program["execution_id"])["RESTORE_ERROR"] + b"\r\n")
            return {"interruption_confirmed": True, "serial_offset": 0, "prompt_end": session._console.offset()}

        with mock.patch.object(service_module, "synchronize_raw_repl", side_effect=synchronize):
            stopped = session.interrupt_program(expected_execution_id=program["execution_id"])
        self.assertTrue(stopped["interrupt_ack"]["interruption_confirmed"])
        self.assertIs(stopped["interrupt_ack"]["owner_restored"], False)
        self.assertFalse(session.program_capabilities()["mpy_entrypoint"])
        self.assertEqual(stopped["program"]["error"]["code"], "program_main_loader_restore_failed")
        self.assert_early_rejection(session, self.binary_payload(expected_execution_id=program["execution_id"]))
        self.assertEqual(runner.call_count, 1)

    def test_running_binary_load_without_terminal_marker_does_not_revoke_proof(self):
        session = self.target()
        program, _ = self.active_binary(session)
        session._console.append(execution_markers(program["execution_id"])["LOAD"] + b"\r\n")
        observed = session.program_status()
        self.assertEqual(observed["program"]["state"], "running")
        self.assertTrue(observed["program_capabilities"]["mpy_entrypoint"])
        self.assertNotIn("loader_restore_failed", observed["program"])

    def test_cancel_after_load_requires_terminal_owner_proof_even_with_a_fresh_prompt(self):
        session = self.target()
        program, runner = self.active_binary(session)
        self.deploy.reset_mock()
        session._console.append(execution_markers(program["execution_id"])["LOAD"] + b"\r\n")
        self.assertTrue(session.program_status()["program_capabilities"]["mpy_entrypoint"])
        with mock.patch.object(service_module, "synchronize_raw_repl", return_value={
            "interruption_confirmed": True, "serial_offset": session._console.offset(),
            "prompt_end": session._console.offset() + 30,
        }):
            stopped = session.interrupt_program(expected_execution_id=program["execution_id"])
        self.assertTrue(stopped["interrupt_ack"]["interruption_confirmed"])
        self.assertIs(stopped["interrupt_ack"]["owner_restored"], False)
        self.assertFalse(stopped["program_capabilities"]["mpy_entrypoint"])
        self.assertEqual(stopped["program"]["error"]["code"], "program_main_loader_restore_failed")
        self.assert_early_rejection(session, self.binary_payload(expected_execution_id=program["execution_id"]))
        self.assertEqual(runner.call_count, 1)

    def test_source_replacement_rechecks_loaded_binary_owner_at_its_sync_boundary(self):
        session = self.target()
        program, runner = self.active_binary(session)
        session._console.append(execution_markers(program["execution_id"])["LOAD"] + b"\r\n")
        observed = session.run_program({
            "files": {"main.py": {"encoding": "utf8", "data": "print('source recovery')\n"}},
            "expected_execution_id": program["execution_id"],
        })
        self.assertEqual(observed["program"]["state"], "completed")
        self.assertFalse(observed["program_capabilities"]["mpy_entrypoint"])
        previous = self.record(session, program["execution_id"])
        self.assertEqual(previous["state"], "unknown")
        self.assertIs(previous["owner_restored"], False)
        self.assertEqual(previous["error"]["code"], "program_main_loader_restore_failed")
        self.assertEqual(runner.call_count, 1)

    def test_cancel_during_deployment_before_load_keeps_verified_loader_proof(self):
        session = self.target()
        program, _ = self.active_binary(session)
        session._program.update(state="unknown", execution_phase="preparing", cancel_requested=True,
                                deployment={"phase": "writing"})
        session._console.append(b"package deployment was interrupted before import\r\n")
        with mock.patch.object(service_module, "synchronize_raw_repl", return_value={
            "interruption_confirmed": True, "serial_offset": session._console.offset(),
            "prompt_end": session._console.offset() + 30,
        }):
            stopped = session.interrupt_program(expected_execution_id=program["execution_id"])
        self.assertTrue(stopped["program_capabilities"]["mpy_entrypoint"])
        self.assertNotIn("loader_restore_failed", stopped["program"])
        self.assertNotIn("error", stopped["program"])

    def test_loaded_binary_done_or_error_is_positive_owner_proof_after_prompt(self):
        for terminal in ("DONE", "ERROR"):
            session = self.target()
            program, _ = self.active_binary(session)
            markers = execution_markers(program["execution_id"])
            session._console.append(markers["LOAD"] + b"\r\n" + markers[terminal] + b"\r\n")
            with self.subTest(terminal=terminal), mock.patch.object(service_module, "synchronize_raw_repl", return_value={
                "interruption_confirmed": True, "serial_offset": session._console.offset(),
                "prompt_end": session._console.offset() + 30,
            }):
                stopped = session.interrupt_program(expected_execution_id=program["execution_id"])
                self.assertTrue(stopped["program_capabilities"]["mpy_entrypoint"])
                self.assertNotIn("loader_restore_failed", stopped["program"])
                self.assertNotIn("error", stopped["program"])

    def test_caller_capability_fields_cannot_authorize_an_inline_run(self):
        session = self.target()
        old = self.active_source(session)
        for field in ("loader_capabilities", "program_capabilities", "mpy_entrypoint"):
            payload = self.binary_payload(expected_execution_id=old["execution_id"], **{field: True})
            before = self.state_bytes(session)
            with self.subTest(field=field):
                self.assert_service_error(lambda: session.run_program(payload), code="invalid_program", status=400)
                self.assertEqual(self.state_bytes(session), before)
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_verified_loader_does_not_bypass_preview_management_handle(self):
        binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": "c" * 64}
        session = self.target(management_binding=binding)
        self.admit(session)
        before = self.state_bytes(session)
        self.assert_service_error(lambda: session.run_program(self.binary_payload(expected_execution_id=None)), code="session_managed_by_preview", status=409)
        revision = self.service.program_packages.create(self.binary_payload())
        for handle in (None, binding, object()):
            with self.subTest(handle_type=type(handle).__name__):
                self.assert_service_error(lambda: session.run_revision(revision["revision_id"], execution_id="e" * 32, expected_execution_id=None, management_handle=handle), code="session_managed_by_preview", status=409)
        self.assertEqual(session._program, before["program"])
        self.assertEqual(session.events, before["events"])
        self.deploy.assert_not_called()
        self.execute.assert_not_called()


class ExplicitMainLoaderBaseSelectionTests(ServiceFixture, unittest.TestCase):
    def request(self, base, **changes):
        return {
            "device_id": "cores3", "program_mode": "uiflow-live",
            "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"],
            **changes,
        }

    def test_program_mode_composes_selected_base_with_server_bootstrap_and_source_binding(self):
        base = store_explicit_base(self.service)
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            created = self.service.create_session(self.request(base))
        start.assert_called_once()
        firmware = self.service.firmware.get(created["firmware_id"])
        source = firmware["source"]
        self.assertEqual(source["metadata"]["base_firmware_id"], base["firmware_id"])
        self.assertEqual(source["metadata"]["base_sha256"], base["sha256"])
        self.assertEqual(firmware["base_manifest"], base["manifest"])
        self.assertEqual(created["firmware_provenance"], source)
        self.assertEqual(created["program_transport"], "uart-repl")
        self.assertEqual(self.service.artifacts.read(source["artifact_id"]), canonical(live_bootstrap_files()))
        self.assertFalse(self.service.get_session(created["session_id"]).program_capabilities()["mpy_entrypoint"])

    def test_base_selection_requires_both_fields_and_live_program_mode(self):
        base = store_explicit_base(self.service)
        full = self.request(base)
        for omitted in ("base_firmware_id", "expected_base_sha256", "program_mode"):
            request = {key: value for key, value in full.items() if key != omitted}
            before = self.stores()
            with self.subTest(omitted=omitted), mock.patch.object(service_module.DeviceSession, "start") as start:
                with self.assertRaises(service_module.ServiceError) as caught:
                    self.service.create_session(request)
                self.assertIn(caught.exception.status, (400, 409))
                start.assert_not_called()
                self.assertFalse(self.service._sessions)
                self.assertEqual(self.stores(), before)
                self.assertEqual(self.service.worker.snapshot()["active_lease_count"], 0)

    def test_wrong_explicit_base_pin_rejects_without_session_lease_or_new_source(self):
        base = store_explicit_base(self.service)
        before = self.stores()
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            with self.assertRaises(service_module.ServiceError) as caught:
                self.service.create_session(self.request(base, expected_base_sha256="0" * 64))
        self.assertEqual((caught.exception.code, caught.exception.status), ("uiflow_base_hash_mismatch", 409))
        start.assert_not_called()
        self.assertFalse(self.service._sessions)
        self.assertEqual(self.stores(), before)
        self.assertEqual(self.service.worker.snapshot()["active_lease_count"], 0)

    def test_program_mode_does_not_erase_the_selected_base_psram_requirement(self):
        base = store_explicit_base(self.service, psram_size=8 << 20)
        self.service.specs["cores3"] = replace(self.service.specs["cores3"], memory="4")
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            with self.assertRaises(service_module.ServiceError) as caught:
                self.service.create_session(self.request(base))
        self.assertEqual((caught.exception.code, caught.exception.status), ("unsupported_firmware_capability", 409))
        self.assertEqual(caught.exception.extra["issues"][0]["code"], "runtime_psram_mismatch")
        start.assert_not_called()
        self.assertFalse(self.service._sessions)
        self.assertEqual(self.service.worker.snapshot()["active_lease_count"], 0)

    def test_management_pin_cannot_select_a_different_explicit_base(self):
        base = store_explicit_base(self.service)
        binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": "c" * 64}
        before = self.stores()
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            with self.assertRaises(service_module.ServiceError) as caught:
                self.service.create_managed_session(self.request(base), **binding)
        self.assertEqual(caught.exception.status, 409)
        start.assert_not_called()
        self.assertFalse(self.service._sessions)
        self.assertEqual(self.stores(), before)
        self.assertEqual(self.service.worker.snapshot()["active_lease_count"], 0)

    def test_matching_management_base_pin_freezes_source_and_replays_same_handle(self):
        base = store_explicit_base(self.service)
        request = self.request(base, idempotency_key="explicit-base-managed-admission")
        binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": base["sha256"]}
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            created, handle = self.service.create_managed_session(request, **binding)
            replayed, repeated = self.service.create_managed_session(request, **binding)
        self.assertEqual(created["session_id"], replayed["session_id"])
        self.assertIs(handle, repeated)
        start.assert_called_once()
        self.assertEqual(created["management_binding"], binding)
        session = self.service.get_session(created["session_id"])
        session.require_management_handle(handle)
        with self.assertRaises(service_module.ServiceError) as caught:
            session.run_program({"source": "pass\n", "expected_execution_id": None})
        self.assertEqual(caught.exception.code, "session_managed_by_preview")
        self.assertFalse(session.program_capabilities()["mpy_entrypoint"])


if __name__ == "__main__":
    unittest.main()
