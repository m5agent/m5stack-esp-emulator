"""Bounded package quota wiring; temporary stores and mocked listener only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from device_service import DeviceService
from program_packages import ProgramPackageError
import test_program_revision_config as source_config
import serve


class ProgramPackageConfigTests(unittest.TestCase):
    def test_service_package_quota_is_independent_and_preserves_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = DeviceService(state_dir=Path(temporary), max_program_packages=2, max_program_revisions=1024)
            try:
                self.assertEqual(service.program_packages.max_count, 2)
                self.assertEqual(service.program_revisions.max_count, 1024)
                payload = lambda value: {"files": {"main.py": {"encoding": "utf8", "data": f"VALUE={value}\n"}}}
                first = service.program_packages.create(payload(1))
                service.program_packages.create(payload(2))
                with self.assertRaises(ProgramPackageError) as caught:
                    service.program_packages.create(payload(3))
                self.assertEqual((caught.exception.code, caught.exception.status), ("program_package_quota_exceeded", 429))
                self.assertEqual(service.program_packages.create(payload(1)), first)
            finally:
                service.close_all()

    def test_lazy_handler_passes_default_and_environment(self):
        for environment, expected in (({}, 256), ({"M5_SERVICE_MAX_PROGRAM_PACKAGES": "1024"}, 1024)):
            with self.subTest(expected=expected), mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(serve.Handler, "service", None), mock.patch.object(serve, "DeviceService") as factory:
                handler = object.__new__(serve.Handler)
                handler._get_service()
                factory.assert_called_once()
                self.assertEqual(factory.call_args.kwargs["max_program_packages"], expected)

    def test_cli_environment_precedence_and_invalid_values_fail_before_listener(self):
        run_main = lambda arguments, environment: source_config.ProgramRevisionConfigTests.run_main(self, arguments, environment)
        for arguments, environment, expected in (
            ([], {}, 256), ([], {"M5_SERVICE_MAX_PROGRAM_PACKAGES": "1024"}, 1024),
            (["--max-program-packages", "4096"], {"M5_SERVICE_MAX_PROGRAM_PACKAGES": "128"}, 4096),
        ):
            code, service, _ = run_main(arguments, environment)
            self.assertEqual(code, 0)
            self.assertEqual(service.kwargs["max_program_packages"], expected)
        for value in ("0", "-1", "4097", "true", "1.5", ""):
            for arguments, environment in ((["--max-program-packages", value], {}), ([], {"M5_SERVICE_MAX_PROGRAM_PACKAGES": value})):
                with self.subTest(value=value, arguments=arguments):
                    code, service, listener = run_main(arguments, environment)
                    self.assertEqual(code, 2)
                    self.assertIsNone(service)
                    self.assertIsNone(listener)


if __name__ == "__main__":
    unittest.main()
