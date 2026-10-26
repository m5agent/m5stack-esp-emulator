"""Source quota wiring with temporary stores; no network listener or guest."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import DeviceService
from program_revisions import RevisionError
import serve


class ProgramRevisionConfigTests(unittest.TestCase):
    def test_device_service_configures_real_store_and_preserves_package_quota(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {}, clear=True):
            service = DeviceService(state_dir=Path(temporary), max_program_revisions=2)
            try:
                self.assertEqual(service.program_revisions.max_count, 2)
                self.assertEqual(service.program_packages.max_count, 256)
                first = service.program_revisions.create({"files": {"main.py": "VALUE = 1\n"}})
                service.program_revisions.create({"files": {"main.py": "VALUE = 2\n"}})
                with self.assertRaises(RevisionError) as caught:
                    service.program_revisions.create({"files": {"main.py": "VALUE = 3\n"}})
                self.assertEqual((caught.exception.code, caught.exception.status), ("program_revision_quota_exceeded", 429))
                self.assertEqual(service.program_revisions.get(first["revision_id"]), first)
            finally:
                service.close_all()

    def test_device_service_rejects_invalid_configuration_without_coercion(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {}, clear=True):
            for value in (0, -1, 4097, True, False, 1.0, "257", None):
                with self.subTest(value=value), self.assertRaises(RevisionError) as caught:
                    DeviceService(state_dir=Path(temporary), max_program_revisions=value)
                self.assertEqual((caught.exception.code, caught.exception.status), ("invalid_revision_quota", 400))

    def test_service_reopen_uses_default_quota_without_reclaiming_existing_source(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {}, clear=True):
            root = Path(temporary)
            source = {"files": {"main.py": "print('保存历史')\n"}}
            configured = DeviceService(state_dir=root, max_program_revisions=1024)
            try:
                self.assertEqual(configured.program_revisions.max_count, 1024)
                metadata = configured.program_revisions.create(source)
                path = root / "program-revisions" / (metadata["revision_id"] + ".json")
                original = path.read_bytes()
            finally:
                configured.close_all()
            reopened = DeviceService(state_dir=root)
            try:
                self.assertEqual(reopened.program_revisions.max_count, 256)
                self.assertEqual(len(list(reopened.program_revisions.root.glob("*.json"))), 1)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(reopened.program_revisions.get(metadata["revision_id"]), metadata)
                self.assertEqual(reopened.program_revisions.source(metadata["revision_id"]), {**source, "entrypoint": "main.py"})
                self.assertEqual(reopened.program_revisions.create(source), metadata)
                self.assertEqual(path.read_bytes(), original)
            finally:
                reopened.close_all()

    def test_lazy_handler_passes_default_and_environment_quota(self):
        for environment, expected in (({}, 256), ({"M5_SERVICE_MAX_PROGRAM_REVISIONS": "1024"}, 1024)):
            with self.subTest(expected=expected), mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(serve.Handler, "service", None), mock.patch.object(serve, "DeviceService") as factory:
                handler = object.__new__(serve.Handler)
                self.assertIs(handler._get_service(), factory.return_value)
                self.assertIs(handler._get_service(), factory.return_value)
                factory.assert_called_once()
                self.assertEqual(factory.call_args.kwargs["max_program_revisions"], expected)

    def run_main(self, arguments, environment):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, environment, clear=True))
            stack.enter_context(mock.patch.object(sys, "argv", ["serve.py", *arguments]))
            stack.enter_context(mock.patch.object(serve.os, "chdir"))
            stack.enter_context(mock.patch.object(serve.signal, "signal"))
            stack.enter_context(mock.patch.object(serve.Handler, "service", None))
            stack.enter_context(mock.patch.object(serve.Handler, "api_token", None))
            stack.enter_context(mock.patch.object(serve.Handler, "previous_api_token", None))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            factory = stack.enter_context(mock.patch.object(serve, "DeviceService"))
            server = stack.enter_context(mock.patch.object(serve, "ServiceHTTPServer"))
            server.return_value.serve_forever.side_effect = KeyboardInterrupt
            try:
                serve.main()
            except SystemExit as error:
                return error.code, factory.call_args, server.call_args
            factory.return_value.close_all.assert_called_once()
            server.return_value.server_close.assert_called_once()
            return 0, factory.call_args, server.call_args

    def test_main_passes_default_environment_and_cli_override(self):
        for arguments, environment, expected in (
            ([], {}, 256),
            ([], {"M5_SERVICE_MAX_PROGRAM_REVISIONS": "1024"}, 1024),
            (["--max-program-revisions", "4096"], {"M5_SERVICE_MAX_PROGRAM_REVISIONS": "1024"}, 4096),
            (["--max-program-revisions", "1"], {}, 1),
        ):
            with self.subTest(arguments=arguments, environment=environment):
                code, service_call, server_call = self.run_main(arguments, environment)
                self.assertEqual(code, 0)
                self.assertEqual(service_call.kwargs["max_program_revisions"], expected)
                self.assertIsNotNone(server_call)

    def test_main_rejects_invalid_environment_and_cli_before_service_or_server(self):
        for value in ("0", "-1", "4097", "true", "1.5", ""):
            for arguments, environment in (
                ([], {"M5_SERVICE_MAX_PROGRAM_REVISIONS": value}),
                (["--max-program-revisions", value], {}),
            ):
                with self.subTest(arguments=arguments, environment=environment):
                    code, service_call, server_call = self.run_main(arguments, environment)
                    self.assertEqual(code, 2)
                    self.assertIsNone(service_call)
                    self.assertIsNone(server_call)


if __name__ == "__main__":
    unittest.main(verbosity=2)
