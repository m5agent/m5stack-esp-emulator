import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from types import SimpleNamespace
from unittest import mock

from device_service import DeviceService, DeviceSession, ServiceError
from runtime_acl import (
    OPERATIONS,
    RuntimeACL,
    RuntimeACLConfigError,
    RuntimeACLError,
)
from serve import Handler
from http.server import ThreadingHTTPServer


def policy_document() -> dict:
    return {
        "schema_version": 1,
        "devices": {
            "*": {
                "allow": ["serial.read", "program.read"],
            },
            "sticks3": {
                "allow": [
                    "serial.read",
                    "input.write",
                    "guest.reset",
                    "program.read",
                    "program.execute",
                    "program.interrupt",
                    "filesystem.write",
                    "flash.read",
                ],
                "execution_entrypoints": ["main.py"],
                "filesystem_write_allow": ["main.py", "lib/"],
                "filesystem_write_deny": ["lib/private/"],
            },
        },
    }


class RuntimeACLTests(unittest.TestCase):
    def test_unconfigured_policy_retains_legacy_permissions(self):
        policy = RuntimeACL.unconfigured()
        for operation in OPERATIONS:
            self.assertIsNone(policy.check("sticks3", operation))
        summary = policy.summary("sticks3")
        self.assertEqual(summary["status"], "NOT_CONFIGURED")
        self.assertIs(summary["configured"], False)
        self.assertEqual(summary["default_effect"], "allow")

    def test_configured_policy_is_device_specific_and_fail_closed(self):
        policy = RuntimeACL.from_document(policy_document())
        self.assertEqual(len(policy.policy_id), 64)
        self.assertIsNotNone(
            policy.check("sticks3", "program.execute", entrypoint="main.py")
        )
        self.assertIsNotNone(policy.allow_operation("sticks3", "program.execute"))
        with self.assertRaises(RuntimeACLError) as missing:
            policy.check("sticks3", "program.execute")
        self.assertEqual(missing.exception.reason, "entrypoint_required")
        self.assertIsNotNone(policy.check("cores3", "serial.read"))
        with self.assertRaises(RuntimeACLError) as error:
            policy.check("sticks3", "program.execute", entrypoint="main.mpy")
        self.assertEqual(error.exception.reason, "entrypoint_not_allowed")
        with self.assertRaises(RuntimeACLError):
            policy.check("unlisted-device", "program.execute", entrypoint="main.py")
        with self.assertRaises(RuntimeACLError):
            policy.check("cores3", "program.execute", entrypoint="main.py")

    def test_filesystem_rules_require_allow_and_apply_deny_first(self):
        policy = RuntimeACL.from_document(policy_document())
        self.assertIsNotNone(
            policy.check("sticks3", "filesystem.write", path="main.py")
        )
        self.assertIsNotNone(
            policy.check("sticks3", "filesystem.write", path="lib/driver.py")
        )
        for path in ("other.py", "lib/private/key.py", "lib"):
            with self.subTest(path=path):
                with self.assertRaises(RuntimeACLError):
                    policy.check("sticks3", "filesystem.write", path=path)

    def test_policy_hash_is_canonical_and_summary_is_auditable(self):
        first = RuntimeACL.from_document(policy_document())
        second_document = {
            "devices": {
                "sticks3": {
                    "filesystem_write_deny": ["lib/private/"],
                    "filesystem_write_allow": ["main.py", "lib/"],
                    "execution_entrypoints": ["main.py"],
                    "allow": [
                        "filesystem.write",
                        "program.interrupt",
                        "program.execute",
                        "program.read",
                        "guest.reset",
                        "input.write",
                        "serial.read",
                        "flash.read",
                    ],
                },
                "*": {"allow": ["program.read", "serial.read"]},
            },
            "schema_version": 1,
        }
        second = RuntimeACL.from_document(second_document)
        self.assertEqual(first.policy_id, second.policy_id)
        summary = first.summary("sticks3")
        self.assertEqual(summary["status"], "ENFORCED")
        self.assertEqual(summary["policy_id"], first.policy_id)
        self.assertEqual(summary["execution_entrypoints"], ["main.py"])
        self.assertEqual(first.summary("cores3")["allowed_operations"], ["program.read", "serial.read"])

    def test_policy_file_is_bounded_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy_path = root / "runtime-acl.json"
            policy_path.write_text(json.dumps(policy_document()), encoding="utf-8")
            loaded = RuntimeACL.from_file(policy_path)
            self.assertEqual(loaded.summary("sticks3")["status"], "ENFORCED")
            link = root / "runtime-acl-link.json"
            link.symlink_to(policy_path)
            with self.assertRaises(RuntimeACLConfigError):
                RuntimeACL.from_file(link)
            policy_path.write_bytes(b"{" + b" " * (64 * 1024) + b"}")
            with self.assertRaises(RuntimeACLConfigError):
                RuntimeACL.from_file(policy_path)

    def test_invalid_policies_fail_closed(self):
        cases = [
            {},
            {"schema_version": True, "devices": {"*": {"allow": []}}},
            {"schema_version": 2, "devices": {"*": {"allow": []}}},
            {"schema_version": 1, "devices": {}},
            {"schema_version": 1, "unexpected": True, "devices": {"*": {"allow": []}}},
            {"schema_version": 1, "devices": {"*": {"allow": ["unknown"]}}},
            {
                "schema_version": 1,
                "devices": {"*": {"allow": ["program.execute"]}},
            },
            {
                "schema_version": 1,
                "devices": {
                    "*": {
                        "allow": ["filesystem.write"],
                    }
                },
            },
            {
                "schema_version": 1,
                "devices": {
                    "*": {
                        "allow": ["program.read", "program.execute"],
                        "execution_entrypoints": ["other.py"],
                    }
                },
            },
        ]
        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(RuntimeACLConfigError):
                    RuntimeACL.from_document(document)

    def test_unknown_device_ids_are_rejected(self):
        policy = RuntimeACL.from_document(
            {
                "schema_version": 1,
                "devices": {
                    "*": {"allow": ["serial.read"]},
                    "missing-device": {"allow": ["serial.read"]},
                },
            }
        )
        with self.assertRaises(RuntimeACLConfigError):
            policy.validate_device_ids({"sticks3", "cores3"})


class RuntimeACLDeviceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.service = DeviceService(
            state_dir=Path(self.temporary.name),
            runtime_acl=RuntimeACL.from_document(
                {
                    "schema_version": 1,
                    "devices": {
                        "sticks3": {
                            "allow": ["program.read"],
                        }
                    },
                }
            ),
        )
        firmware_path = Path(self.temporary.name) / "firmware.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        self.session = DeviceSession(
            self.service,
            session_id="a" * 32,
            spec=self.service.specs["sticks3"],
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

    def tearDown(self):
        self.service.close_all()
        self.temporary.cleanup()

    def assert_denied(self, operation: str, call) -> ServiceError:
        with self.assertRaises(ServiceError) as caught:
            call()
        error = caught.exception
        self.assertEqual((error.code, error.status), ("runtime_acl_denied", 403))
        self.assertEqual(error.extra["operation"], operation)
        self.assertEqual(
            error.extra["policy_id"],
            self.service.runtime_acl.policy_id,
        )
        denied = [
            event
            for event in self.session.events
            if event.get("event") == "runtime_acl_denied"
            and event.get("operation") == operation
        ]
        self.assertTrue(denied)
        self.assertEqual(
            denied[-1]["policy_id"],
            self.service.runtime_acl.policy_id,
        )
        return error

    def test_guest_facing_operations_are_denied_before_runtime_io(self):
        self.assert_denied("serial.read", lambda: self.session.serial_read())
        self.assert_denied(
            "input.write",
            lambda: self.session.inject({"kind": "key", "key": "a"}),
        )
        self.assert_denied(
            "input.write",
            lambda: self.session.unit_input({"id": "missing", "values": {}}),
        )
        self.assert_denied("guest.reset", self.session.reset)
        self.assert_denied("flash.read", self.session.flash_get)
        self.assert_denied(
            "program.execute",
            lambda: self.session.run_program(
                {"source": "print(1)", "expected_execution_id": None}
            ),
        )

    def test_program_read_is_allowed_while_other_operations_remain_denied(self):
        result = self.session.program_status()
        self.assertIsNone(result["program"])
        self.assertEqual(
            self.session.snapshot()["runtime_acl"]["status"],
            "ENFORCED",
        )
        self.assertEqual(
            self.service.capacity()["runtime_acl"]["policy_id"],
            self.service.runtime_acl.policy_id,
        )
        self.assert_denied(
            "program.interrupt",
            lambda: self.session.interrupt_program(
                expected_execution_id=None
            ),
        )

    def test_repeated_denials_do_not_flood_audit_events(self):
        for _ in range(5):
            with self.assertRaises(ServiceError):
                self.session.serial_read()
        events = [
            event
            for event in self.session.events
            if event.get("event") == "runtime_acl_denied"
            and event.get("operation") == "serial.read"
        ]
        self.assertEqual(len(events), 1)

    def test_session_snapshot_hides_program_detail_without_read_permission(self):
        self.service.runtime_acl = RuntimeACL.from_document(
            {
                "schema_version": 1,
                "devices": {
                    "sticks3": {
                        "allow": ["serial.read"],
                    }
                },
            }
        )
        snapshot = self.session.snapshot()
        self.assertEqual(snapshot["program_transport"], "uart-repl")
        self.assertNotIn("program", snapshot)
        self.assertIn("program_capabilities", snapshot)
        self.session._record_event("program_submitted", execution_id="e" * 32)
        self.session._record_event("serial_marker", marker="PASS")
        visible = self.session.visible_events()
        self.assertNotIn("program_submitted", {event["event"] for event in visible})
        self.assertIn("serial_marker", {event["event"] for event in visible})
        self.assert_denied("program.read", self.session.program_status)

    def test_evidence_bundle_redacts_runtime_data_denied_by_acl(self):
        self.service.runtime_acl = RuntimeACL.from_document(
            {
                "schema_version": 1,
                "devices": {
                    "sticks3": {
                        "allow": [],
                    }
                },
            }
        )
        self.session.virtual_flash = self.session.firmware_path
        self.session.serial0.write_text("privileged serial\n")
        bundle = self.session.evidence_bundle(
            {"manifest", "serial", "logs", "flash"}
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        self.assertFalse(any(name.startswith("programs/") for name in names))
        self.assertNotIn("serial.log", names)
        self.assertNotIn("qemu.stdout", names)
        self.assertNotIn("flash/virtual-flash.bin", names)
        self.assertEqual(
            manifest["program_redaction"]["reason"],
            "runtime_acl_program_read_denied",
        )
        self.assertEqual(
            manifest["runtime_output_redaction"]["reason"],
            "runtime_acl_serial_read_denied",
        )
        self.assertEqual(
            manifest["flash"]["reason"],
            "runtime_acl_flash_read_denied",
        )

    def test_program_package_path_acl_denies_before_console_or_store(self):
        self.service.runtime_acl = RuntimeACL.from_document(
            {
                "schema_version": 1,
                "devices": {
                    "sticks3": {
                        "allow": [
                            "program.read",
                            "program.execute",
                            "filesystem.write",
                        ],
                        "execution_entrypoints": ["main.py"],
                        "filesystem_write_allow": ["main.py"],
                        "filesystem_write_deny": ["secret.env"],
                    }
                },
            }
        )
        self.assert_denied(
            "filesystem.write",
            lambda: self.session.run_program(
                {
                    "files": {
                        "main.py": {"encoding": "utf8", "data": "print(1)\n"},
                        "secret.env": {"encoding": "utf8", "data": "KEY=value\n"},
                    },
                    "entrypoint": "main.py",
                    "expected_execution_id": None,
                }
            ),
        )
        self.assertFalse((self.session.dir / "programs").exists())

    def test_unknown_policy_device_fails_service_construction(self):
        with self.assertRaises(RuntimeACLConfigError):
            DeviceService(
                state_dir=Path(self.temporary.name) / "invalid",
                runtime_acl=RuntimeACL.from_document(
                    {
                        "schema_version": 1,
                        "devices": {
                            "missing-device": {"allow": ["serial.read"]}
                        },
                    }
                ),
            )


class RuntimeACLHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.service = DeviceService(
            state_dir=Path(self.temporary.name),
            runtime_acl=RuntimeACL.from_document(
                {
                    "schema_version": 1,
                    "devices": {
                        "sticks3": {
                            "allow": ["program.read"],
                        }
                    },
                }
            ),
        )
        firmware_path = Path(self.temporary.name) / "firmware.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        self.session = DeviceSession(
            self.service,
            session_id="c" * 32,
            spec=self.service.specs["sticks3"],
            firmware_id="d" * 64,
            firmware_path=firmware_path,
            firmware_sha="d" * 64,
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
        service = SimpleNamespace(
            get_session=mock.Mock(return_value=self.session)
        )

        class RuntimeACLHandler(Handler):
            api_token = "runtime-acl-http-token"
            previous_api_token = None

            def log_message(self, *args):
                pass

        RuntimeACLHandler.service = service
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeACLHandler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.service.close_all()
        self.temporary.cleanup()

    def request(self, method: str, path: str, payload=None):
        headers = {"Authorization": "Bearer runtime-acl-http-token"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=2,
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_http_program_status_is_allowed_and_mutations_fail_closed(self):
        status, body = self.request(
            "GET",
            f"/api/v1/sessions/{self.session.id}/program",
        )
        self.assertEqual(status, 200)
        self.assertIsNone(body["program"])

        status, body = self.request(
            "POST",
            f"/api/v1/sessions/{self.session.id}/program",
            {"source": "print(1)", "expected_execution_id": None},
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "runtime_acl_denied")
        self.assertEqual(body["error"]["operation"], "program.execute")
        self.assertEqual(
            body["error"]["policy_id"],
            self.service.runtime_acl.policy_id,
        )

        status, body = self.request(
            "GET",
            f"/api/v1/sessions/{self.session.id}/serial",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["operation"], "serial.read")

        status, body = self.request(
            "POST",
            f"/api/v1/sessions/{self.session.id}/wait",
            {"ready_marker": "PASS", "timeout_seconds": 1},
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["operation"], "serial.read")

        status, body = self.request(
            "GET",
            f"/api/v1/sessions/{self.session.id}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["runtime_acl"]["status"], "ENFORCED")
        self.assertEqual(
            body["runtime_acl"]["policy_id"],
            self.service.runtime_acl.policy_id,
        )


if __name__ == "__main__":
    unittest.main()
