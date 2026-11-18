"""Test managed Linux worker staging without starting a service or a VM."""

from argparse import Namespace
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import socket
import stat
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from macos_linux_worker import install, launchd_role  # noqa: E402


DEVICE_SOURCE = "a" * 40
DEVICE_API_SHA = "b" * 64
OLD_TOKEN = b"c" * 64 + b"\n"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class MacOSLinuxWorkerInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="m5-worker-install-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.pinned, self.scenario = self.root / "pinned", self.root / "scenario"
        self.output = self.root / "installed"
        self.manifest = self.root / "payload.json"
        self.runner = self.write_file(self.root / "runner", b"fixture runner\n", 0o700)
        self.relay = self.write_file(self.root / "relay-python", b"fixture interpreter\n", 0o700)
        self.input_files = {
            "pinned/cloud-kernel": self.write_file(self.pinned / "cloud-kernel", b"fixture kernel\n"),
            "pinned/readonly-share/trixie-rootfs.tar.gz": self.write_file(
                self.pinned / "readonly-share/trixie-rootfs.tar.gz", b"fixture rootfs\n"
            ),
            "scenario/vsock-initrd.img": self.write_file(self.scenario / "vsock-initrd.img", b"fixture initrd\n"),
            "scenario/host-relay.py": self.write_file(self.scenario / "host-relay.py", b"# fixture relay\n"),
            "scenario/scenarios/guest.py": self.write_file(self.scenario / "scenarios/guest.py", b"# fixture guest\n"),
            "scenario/scenarios/guest-action.sh": self.write_file(
                self.scenario / "scenarios/guest-action.sh", b"# fixture guest action\n", 0o700
            ),
            "scenario/scenarios/service/app.py": self.write_file(
                self.scenario / "scenarios/service/app.py", b"# fixture guest helper\n"
            ),
        }
        self.payload = {
            "schema_version": 1,
            "files": {name: self.file_record(path) for name, path in self.input_files.items()},
            "device_source": DEVICE_SOURCE,
            "device_openapi_sha256": DEVICE_API_SHA,
        }
        self.args = Namespace(
            package=self.output,
            instance="worker-lab",
            pinned=self.pinned,
            scenario=self.scenario,
            payload_manifest=self.manifest,
            payload_manifest_sha256=self.write_manifest(),
            runner=self.runner,
            runner_sha256=digest(self.runner),
            relay_python=self.relay,
            relay_python_sha256=digest(self.relay),
            port=28194,
        )
        layout_check = patch.object(install, "check_layout", return_value={"status": "SOURCE_AND_DURABLE_LAYOUT_OK"})
        self.check_layout = layout_check.start()
        self.addCleanup(layout_check.stop)
        self.available = SimpleNamespace(free=install.HOST_FLOOR)
        disk_usage = patch.object(install.shutil, "disk_usage", return_value=self.available)
        disk_usage.start()
        self.addCleanup(disk_usage.stop)

    @staticmethod
    def write_file(path, contents, mode=0o600):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(contents)
        path.chmod(mode)
        return path

    @staticmethod
    def file_record(path):
        return {
            "size": path.stat().st_size,
            "mode": oct(stat.S_IMODE(path.stat().st_mode)),
            "sha256": digest(path),
        }

    def write_manifest(self):
        self.write_file(self.manifest, (json.dumps(self.payload, sort_keys=True) + "\n").encode())
        return digest(self.manifest)

    def stage(self):
        old_umask = os.umask(0o077)
        try:
            return install.stage(self.args)
        finally:
            os.umask(old_umask)

    def assert_stage_rejected(self, error=ValueError):
        with self.assertRaises(error):
            self.stage()
        self.check_layout.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_payload_is_pinned_to_exact_manifest_bytes(self):
        self.assertEqual(install.read_payload(self.manifest, self.args.payload_manifest_sha256), self.payload)
        with self.assertRaises(ValueError):
            install.read_payload(self.manifest, "0" * 64)

    def test_payload_rejects_traversal_unsafe_modes_and_incomplete_digest(self):
        record = self.payload["files"]["pinned/cloud-kernel"]
        for name, metadata in (
            ("scenario/../pinned/cloud-kernel", record),
            ("/scenario/scenarios/guest.py", record),
            ("scenario/scenarios/control-token", record),
            ("scenario/results/worker.json", record),
            ("pinned/cloud-kernel", {**record, "mode": "0o666"}),
            ("pinned/cloud-kernel", {**record, "sha256": "0" * 63}),
        ):
            with self.subTest(name=name, metadata=metadata):
                original = self.payload["files"].copy()
                try:
                    self.payload["files"][name] = metadata
                    with self.assertRaises(ValueError):
                        install.read_payload(self.manifest, self.write_manifest())
                finally:
                    self.payload["files"] = original

    def test_stage_ignores_old_state_and_seals_the_installed_assets(self):
        future_old_paths = {
            "scenarios/control-token": OLD_TOKEN,
            "scenarios/controller/lifecycle-command.json": b"old intent\n",
            "endpoint.private.json": b"old endpoint\n",
            "results/worker/worker.json": b"old worker\n",
            "results/.supervisor/ready-1.json": b"old receipt\n",
        }
        for name, content in future_old_paths.items():
            self.write_file(self.scenario / name, content)

        result = self.stage()

        self.check_layout.assert_called_once()
        receipt_path = self.output / "install-receipt.private.json"
        receipt = json.loads(receipt_path.read_bytes())
        plan, = self.output.glob("*.plist")
        launch = plistlib.loads(plan.read_bytes())
        self.assertEqual(launch["Label"], plan.stem)
        self.assertEqual(launch["ProgramArguments"][0], "/usr/bin/python3")
        self.assertFalse(launch.get("KeepAlive", False))
        self.assertFalse(launch.get("RunAtLoad", False))
        self.assertNotIn(OLD_TOKEN.strip().decode(), str(launch))
        manifest_path = self.output / "immutable-assets.private.json"
        manifest_sha = digest(manifest_path)
        self.assertEqual(result["asset_manifest_sha256"], manifest_sha)
        self.assertEqual(receipt["asset_manifest_sha256"], manifest_sha)
        self.assertEqual(receipt["plist_sha256"], digest(plan))
        self.assertEqual(receipt["payload_sha256"], self.args.payload_manifest_sha256)
        argv = launch["ProgramArguments"]
        self.assertEqual(argv[argv.index("--asset-manifest-sha256") + 1], manifest_sha)
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["device_source"], DEVICE_SOURCE)
        self.assertEqual(manifest["device_openapi_sha256"], DEVICE_API_SHA)
        self.assertEqual(manifest["relay_python_sha256"], digest(self.relay))
        files = manifest["files"]
        instance = self.output / self.args.instance
        self.assertTrue(instance.is_dir())
        token = instance / "scenarios/control-token"
        self.assertRegex(token.read_text(), r"\A[0-9a-f]{64}\n\Z")
        self.assertEqual(stat.S_IMODE(token.stat().st_mode), 0o600)
        for name, original in self.input_files.items():
            if name.startswith("scenario/"):
                installed_name = f"{self.args.instance}/{name.removeprefix('scenario/')}"
            else:
                installed_name = name
            installed = self.output / installed_name
            self.assertEqual(installed.read_bytes(), original.read_bytes(), installed_name)
            self.assertEqual(self.file_record(installed), files[installed_name], installed_name)
        for name, metadata in files.items():
            with self.subTest(asset=name):
                path = self.output / name
                self.assertEqual(path.resolve(strict=True), path)
                self.assertTrue(path.is_relative_to(self.output))
                self.assertEqual(self.file_record(path), metadata)
        for name, prior_contents in future_old_paths.items():
            destination = instance / name
            if name.startswith("results/"):
                self.assertFalse(destination.exists(), name)
            if destination.exists():
                self.assertNotEqual(destination.read_bytes(), prior_contents, name)
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode) & 0o077, 0, name)
            self.assertEqual((self.scenario / name).read_bytes(), prior_contents, name)
            self.assertNotIn(f"{self.args.instance}/{name}", files)

    def test_stage_refuses_existing_directory_without_modifying_it(self):
        marker = self.write_file(self.output / "owner-marker", b"first owner\n")
        identity = self.output.stat().st_ino
        with self.assertRaises((FileExistsError, ValueError)):
            self.stage()
        self.check_layout.assert_not_called()
        self.assertEqual(self.output.stat().st_ino, identity)
        self.assertEqual(list(self.output.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b"first owner\n")

    def test_stage_rejects_unpinned_asset_bytes_before_layout(self):
        # Same size ensures this exercises the digest check as well as inventory shape.
        path = self.input_files["pinned/cloud-kernel"]
        path.write_bytes(b"x" * path.stat().st_size)
        self.assert_stage_rejected()

    def test_stage_rejects_asset_mode_drift_before_layout(self):
        self.input_files["scenario/scenarios/guest.py"].chmod(0o644)
        self.assert_stage_rejected()

    def test_stage_rejects_symlink_even_when_target_bytes_match(self):
        path = self.input_files["scenario/scenarios/guest.py"]
        alias = self.write_file(self.root / "matching.py", path.read_bytes())
        path.unlink()
        path.symlink_to(alias)
        self.assert_stage_rejected((OSError, ValueError))
        self.assertEqual(alias.read_bytes(), b"# fixture guest\n")

    def test_stage_rejects_a_symlinked_parent_of_an_asset(self):
        nested = self.pinned / "readonly-share"
        relocated = self.root / "outside-source"
        nested.rename(relocated)
        nested.symlink_to(relocated, target_is_directory=True)
        self.assert_stage_rejected((OSError, ValueError))
        self.assertEqual((relocated / "trixie-rootfs.tar.gz").read_bytes(), b"fixture rootfs\n")

    def test_stage_rejects_unpinned_runner_or_python_before_layout(self):
        for attribute in ("runner_sha256", "relay_python_sha256"):
            with self.subTest(attribute=attribute):
                with patch.object(self.args, attribute, "0" * 64):
                    self.assert_stage_rejected()

    def test_stage_rejects_reserved_and_invalid_ports_before_layout(self):
        for port in (8787, 8830, 0, 65536):
            with self.subTest(port=port):
                with patch.object(self.args, "port", port):
                    self.assert_stage_rejected()

    def test_stage_rejects_insufficient_disk_before_layout(self):
        self.available.free = install.HOST_FLOOR - 1
        self.assert_stage_rejected()

    def test_layout_failure_removes_only_the_new_disposable_package(self):
        self.check_layout.side_effect = RuntimeError("fixture layout refusal")
        with self.assertRaisesRegex(RuntimeError, "fixture layout refusal"):
            self.stage()
        self.assertFalse(self.output.exists())
        self.assertEqual(digest(self.manifest), self.args.payload_manifest_sha256)
        for name, path in self.input_files.items():
            self.assertEqual(self.file_record(path), self.payload["files"][name])

    def test_controller_rejects_a_changed_manifest_or_installed_file(self):
        result = self.stage()
        instance = self.output / self.args.instance
        pinned = self.output / "pinned"
        runner = self.output / "bin/vz-managed-runner"
        manifest_sha = result["asset_manifest_sha256"]
        with patch.object(launchd_role, "SERVICE", self.output / "controller"):
            checked = launchd_role.check_manifest(instance, pinned, runner, manifest_sha)
            self.assertEqual(checked.device_source, DEVICE_SOURCE)
            self.assertEqual(checked.openapi_sha256, DEVICE_API_SHA)
            self.assertEqual(checked.runner_sha256, digest(self.runner))
            with self.assertRaisesRegex(RuntimeError, "manifest digest"):
                launchd_role.check_manifest(instance, pinned, runner, "0" * 64)
            path = pinned / "cloud-kernel"
            path.write_bytes(b"!" * path.stat().st_size)
            with self.assertRaisesRegex(RuntimeError, "asset digest"):
                launchd_role.check_manifest(instance, pinned, runner, manifest_sha)

    def test_control_status_checks_only_the_recorded_worker_when_loaded(self):
        self.stage()
        args = Namespace(package=self.output, action="status")
        instance = self.output / self.args.instance
        plan, = self.output.glob("*.plist")
        loaded = SimpleNamespace(returncode=0, stdout=f"path = {plan}\nstate = running")
        missing = SimpleNamespace(returncode=113, stdout="")
        foreign = SimpleNamespace(returncode=0, stdout="path = /foreign/worker.plist\nstate = running")
        with patch.object(install, "launchctl", side_effect=[missing, foreign, loaded]) as launchctl:
            with patch.object(install, "worker_ready", return_value=True) as ready:
                self.assertEqual(install.control(args), {"status": "staged", "loaded": False, "worker_ready": False})
                with self.assertRaisesRegex(ValueError, "Registered launch definition"):
                    install.control(args)
                ready.assert_not_called()
                self.write_file(instance / "launchd-status.private.json", b'{"phase": "running"}')
                self.assertEqual(install.control(args), {"status": "running", "loaded": True, "worker_ready": True})
                ready.assert_called_once_with(instance, DEVICE_API_SHA, self.args.port)
        expected = call("print", f"gui/{os.getuid()}/{plan.stem}", check=False)
        self.assertEqual(launchctl.call_args_list, [expected] * 3)

    def test_stopped_status_waits_for_the_launchd_process(self):
        self.stage()
        instance = self.output / self.args.instance
        self.write_file(instance / "launchd-status.private.json", b'{"phase": "stopped"}')
        plan, = self.output.glob("*.plist")
        running = SimpleNamespace(returncode=0, stdout=f"path = {plan}\nstate = running")
        inactive = SimpleNamespace(returncode=0, stdout=f"path = {plan}\nstate = not running")
        unloaded = SimpleNamespace(returncode=113, stdout="")
        args = Namespace(package=self.output, action="status")
        with patch.object(install, "launchctl", side_effect=[running, inactive, unloaded]):
            with patch.object(install, "worker_ready", return_value=True):
                self.assertEqual(install.control(args), {"status": "draining", "loaded": True, "worker_ready": False})
                self.assertEqual(install.control(args), {"status": "stopped", "loaded": True, "worker_ready": False})
                self.assertEqual(install.control(args), {"status": "stopped", "loaded": False, "worker_ready": False})

    def test_restart_admits_time_wait_without_an_active_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, socket.socket() as client:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.settimeout(2)
            client.settimeout(2)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            address = listener.getsockname()
            client.connect(address)
            accepted, _ = listener.accept()
            with accepted:
                accepted.settimeout(2)
                # The old worker side closes first and retains TIME_WAIT on its port.
                accepted.shutdown(socket.SHUT_WR)
                self.assertEqual(client.recv(1), b"")
                client.shutdown(socket.SHUT_WR)
                self.assertEqual(accepted.recv(1), b"")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as plain:
            with self.assertRaises(OSError) as old_preflight:
                plain.bind(address)
            self.assertEqual(old_preflight.exception.errno, errno.EADDRINUSE)

        self.args.port = address[1]
        self.stage()
        instance = self.output / self.args.instance
        self.write_file(instance / "launchd-status.private.json", b'{"phase": "running"}')
        missing = SimpleNamespace(returncode=113, stdout="")
        ok = SimpleNamespace(returncode=0, stdout="")
        args = Namespace(package=self.output, action="start")
        with patch.object(install, "launchctl", side_effect=[missing, ok, ok]) as launchctl:
            with patch.object(install, "worker_ready", return_value=True):
                self.assertEqual(install.control(args), {"status": "running", "worker_ready": True})
        self.assertEqual([item.args[0] for item in launchctl.call_args_list], ["print", "bootstrap", "kickstart"])

    def test_restart_still_refuses_a_live_listener_before_bootstrap(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            self.args.port = listener.getsockname()[1]
            self.stage()
            args = Namespace(package=self.output, action="start")
            plan, = self.output.glob("*.plist")
            missing = SimpleNamespace(returncode=113, stdout="")
            with patch.object(install, "launchctl", side_effect=[missing]) as launchctl:
                with self.assertRaises(OSError) as occupied:
                    install.control(args)
                self.assertEqual(occupied.exception.errno, errno.EADDRINUSE)
            launchctl.assert_called_once_with("print", f"gui/{os.getuid()}/{plan.stem}", check=False)

    def test_readiness_requires_authenticated_current_linux_worker_and_exact_api(self):
        self.stage()
        instance = self.output / self.args.instance
        token = (instance / "scenarios/control-token").read_text().strip()
        endpoint = instance / "endpoint.private.json"
        self.write_file(endpoint, b'{"phase": "running", "ready": true, "worker_id": "fixture", "worker_generation": 3}')
        worker = {"platform": "linux", "worker_id": "fixture", "generation": 3,
                  "accepting_leases": True, "stale": False, "session_create_recovery": "review-v1"}
        api = b"fixture API schema"
        api_sha = sha256(api).hexdigest()
        for identity, schema, acceptable in (
            (worker, api, True),
            ({**worker, "generation": 2}, api, False),
            (worker, b"wrong schema", False),
        ):
            with self.subTest(identity=identity, schema=schema):
                first, second = Mock(status=200), Mock(status=200)
                first.read.return_value, second.read.return_value = json.dumps(identity).encode(), schema
                with patch.object(install, "HTTPConnection") as http:
                    http.return_value.getresponse.side_effect = [first, second]
                    self.assertIs(install.worker_ready(instance, api_sha, self.args.port), acceptable)
                    self.assertEqual(http.return_value.request.call_args_list, [
                        call("GET", "/api/v1/" + name, headers={"Authorization": "Bearer " + token})
                        for name in ("worker", "openapi.yaml")
                    ])
        endpoint.write_bytes(b"invalid JSON")
        with patch.object(install, "HTTPConnection") as http:
            self.assertFalse(install.worker_ready(instance, api_sha, self.args.port))
            http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
