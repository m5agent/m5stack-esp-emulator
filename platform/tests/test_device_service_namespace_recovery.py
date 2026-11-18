import os
from pathlib import Path
import select
import signal
import stat
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from device_service_errors import ServiceError
from device_service_namespace_recovery import (
    GATEWAY_HANDOFF_LOCK,
    claim_drained_gateway_handoff,
    namespace_runtime_scope,
    namespace_supervisor_identity,
    open_gateway_handoff_guard,
    stop_namespace_supervisor,
    verify_inherited_gateway_handoff_guard,
)


BOOT_ID = "12345678-1234-1234-1234-123456789abc"
PID = 42
PIDFD = 19
TOKEN = f"linux:{BOOT_ID}:123456"


class NamespaceSupervisorRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        boot_file = self.root / "sys/kernel/random/boot_id"
        boot_file.parent.mkdir(parents=True)
        boot_file.write_text(BOOT_ID + "\n")
        self.proc = self.root / str(PID)
        self.proc.mkdir()
        self.write_stat()
        self.config = self.root / "session with spaces/network-sandbox.json"
        self.script = self.root / "platform/tools/network_sandbox.py"
        self.write_argv(self.config)
        self.open_handle = self.enterContext(patch.object(os, "pidfd_open", return_value=PIDFD, create=True))
        self.send_signal = self.enterContext(patch.object(signal, "pidfd_send_signal", create=True))
        self.close_handle = self.enterContext(patch.object(os, "close"))
        self.poller = Mock()
        self.poller.poll.return_value = []
        self.enterContext(patch.object(select, "poll", return_value=self.poller))

    def write_stat(self, state="S", start=123456):
        fields = [state] + ["0"] * 18 + [str(start)]
        (self.proc / "stat").write_text(f"{PID} (python )\n worker) " + " ".join(fields))

    def write_argv(self, config, *, inner=False):
        arguments = ["/usr/bin/python3.12", self.script, *(["--inner"] if inner else []),
                     "--config", config, "--", "qemu-system-xtensa"]
        (self.proc / "cmdline").write_bytes(b"\0".join(map(os.fsencode, arguments)) + b"\0")

    def stop(self, *, token=TOKEN, **kwargs):
        return stop_namespace_supervisor(
            PID, start_token=token, config_path=self.config, sandbox_path=self.script, proc_root=self.root, **kwargs,
        )

    def assert_pending(self, message, **kwargs):
        with self.assertRaisesRegex(ServiceError, message) as raised:
            self.stop(**kwargs)
        self.assertEqual(raised.exception.code, "session_cleanup_pending")
        self.assertEqual(raised.exception.status, 503)

    def test_proc_identity_handles_parentheses_and_distinguishes_exit_from_unreadable(self):
        self.assertEqual(namespace_supervisor_identity(PID, proc_root=self.root), TOKEN)
        self.write_stat("Z")
        self.assertIsNone(namespace_supervisor_identity(PID, proc_root=self.root))
        (self.proc / "stat").unlink()
        self.assertIsNone(namespace_supervisor_identity(PID, proc_root=self.root))
        with patch.object(Path, "read_bytes", side_effect=PermissionError):
            with self.assertRaisesRegex(ServiceError, "cannot read"):
                namespace_supervisor_identity(PID, proc_root=self.root)

    def test_exact_identity_and_ordered_arguments_signal_only_owned_handle(self):
        self.poller.poll.side_effect = [[], [], [(PIDFD, select.POLLIN)]]
        self.stop()
        self.open_handle.assert_called_once_with(PID)
        self.send_signal.assert_called_once_with(PIDFD, signal.SIGTERM)
        self.assertEqual(self.poller.poll.call_args_list, [call(0), call(0), call(20000)])
        self.close_handle.assert_called_once_with(PIDFD)

    def test_observed_exit_does_not_signal_and_missing_identity_still_fails(self):
        self.open_handle.side_effect = ProcessLookupError
        self.stop()
        self.assert_pending("no saved process identity", token=None)
        self.open_handle.assert_called_once_with(PID)
        self.send_signal.assert_not_called()

    def test_live_handle_with_missing_procfs_record_is_not_a_confirmed_exit(self):
        (self.proc / "stat").unlink()
        self.assert_pending("identity is unreadable")
        self.send_signal.assert_not_called()

    def test_wrong_start_or_other_session_command_does_not_signal(self):
        self.write_stat(start=123457)
        self.assert_pending("start identity changed")
        self.write_stat()
        self.write_argv(self.config.with_suffix(".json.other"))
        self.assert_pending("does not match the saved launch")
        self.send_signal.assert_not_called()

    def test_legacy_token_requires_matching_callback_and_unchanged_proc_identity(self):
        legacy = "Wed Nov 18 12:00:00 2026"
        self.assert_pending("start identity changed", token=legacy)
        with patch(
            "device_service_namespace_recovery.namespace_supervisor_identity",
            side_effect=[TOKEN, f"linux:{BOOT_ID}:123457"],
        ):
            self.assert_pending("changed during verification", token=legacy, legacy_start_token=lambda _: legacy)
        self.send_signal.assert_not_called()
        self.poller.poll.side_effect = [[], [], [(PIDFD, select.POLLHUP)]]
        self.stop(token=legacy, legacy_start_token=lambda _: legacy)
        self.send_signal.assert_called_once_with(PIDFD, signal.SIGTERM)

    def test_timeout_retains_pending_and_never_forces_supervisor(self):
        self.assert_pending("did not finish cooperative stop", timeout=60)
        self.send_signal.assert_called_once_with(PIDFD, signal.SIGTERM)
        self.assertEqual(self.poller.poll.call_args_list[-1], call(20000))
        self.close_handle.assert_called_once_with(PIDFD)

    def test_inner_supervisor_requires_exact_namespace_and_argument_role(self):
        net = self.proc / "ns/net"
        net.parent.mkdir()
        net.touch()
        identity = net.stat()
        self.write_argv(self.config, inner=True)
        self.assert_pending("saved launch")
        self.assert_pending("left the original", inner_namespace=(identity.st_dev, identity.st_ino + 1))
        self.send_signal.assert_not_called()
        self.poller.poll.side_effect = [[], [], [(PIDFD, select.POLLIN)]]
        self.stop(inner_namespace=(identity.st_dev, identity.st_ino))
        self.send_signal.assert_called_once_with(PIDFD, signal.SIGTERM)

    def test_worker_scope_binds_boot_and_all_three_namespaces(self):
        expected = {"boot_id": BOOT_ID}
        namespaces = self.root / "self/ns"
        namespaces.mkdir(parents=True)
        for name in ("net", "mnt", "pid"):
            path = namespaces / name
            path.touch()
            identity = path.stat()
            expected[name] = [identity.st_dev, identity.st_ino]
        self.assertEqual(namespace_runtime_scope(proc_root=self.root), expected)
        (namespaces / "pid").unlink()
        with self.assertRaisesRegex(ServiceError, "original gateway worker context"):
            namespace_runtime_scope(proc_root=self.root)


class GatewayHandoffGuardTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.guard = root / GATEWAY_HANDOFF_LOCK

    def assert_blocked(self, identity, *, path=None):
        with self.assertRaises(ServiceError) as raised:
            with claim_drained_gateway_handoff(path or self.guard, identity):
                self.fail("an unverified handoff guard was accepted")
        self.assertEqual(raised.exception.code, "session_cleanup_pending")
        self.assertEqual(raised.exception.status, 503)

    def test_guard_is_private_exclusive_and_preserves_shared_lock_until_last_close(self):
        launcher, identity = open_gateway_handoff_guard(self.guard)
        try:
            self.assertFalse(os.get_inheritable(launcher))
            self.assertEqual(stat.S_IMODE(self.guard.stat().st_mode), 0o600)
            with self.assertRaises(ServiceError):
                open_gateway_handoff_guard(self.guard)
            inherited = os.dup(launcher)
            self.addCleanup(os.close, inherited)
        finally:
            os.close(launcher)
        verify_inherited_gateway_handoff_guard(inherited, self.guard, identity)
        self.assert_blocked(identity)

    def test_claim_holds_an_independent_lock_until_the_caller_exits(self):
        launcher, identity = open_gateway_handoff_guard(self.guard)
        duplicate = os.dup(launcher)
        os.close(launcher)
        try:
            self.assert_blocked(identity)
        finally:
            os.close(duplicate)
        with claim_drained_gateway_handoff(self.guard, identity):
            self.assert_blocked(identity)
        with self.assertRaisesRegex(OSError, "caller failure"):
            with claim_drained_gateway_handoff(self.guard, identity):
                raise OSError("caller failure")
        with claim_drained_gateway_handoff(self.guard, identity):
            pass

    def test_replaced_path_and_symlink_are_never_adopted(self):
        launcher, identity = open_gateway_handoff_guard(self.guard)
        self.addCleanup(os.close, launcher)
        original = self.guard.with_suffix(".original")
        self.guard.rename(original)
        self.assert_blocked(identity)
        self.guard.symlink_to(original)
        self.assert_blocked(identity)
        with self.assertRaises(ServiceError):
            open_gateway_handoff_guard(self.guard)
        self.guard.unlink()
        self.guard.write_bytes(original.read_bytes())
        self.guard.chmod(0o600)
        self.assert_blocked(identity)
        with self.assertRaisesRegex(ServiceError, "owned file"):
            verify_inherited_gateway_handoff_guard(launcher, self.guard, identity)
        verify_inherited_gateway_handoff_guard(launcher, original, identity)

    def test_rejects_truncated_untrusted_and_nonregular_guard_files(self):
        launcher, identity = open_gateway_handoff_guard(self.guard)
        os.close(launcher)
        for invalid in (None, (identity[0], identity[1]), [True, identity[1]], [identity[0], 0]):
            with self.subTest(invalid=invalid):
                self.assert_blocked(invalid)
        self.guard.chmod(0o644)
        self.assert_blocked(identity)
        self.guard.chmod(0o600)
        alias = self.guard.with_suffix(".alias")
        alias.hardlink_to(self.guard)
        self.assert_blocked(identity)
        alias.unlink()
        self.guard.write_bytes(b"")
        self.assert_blocked(identity)
        self.guard.unlink()
        os.mkfifo(self.guard, 0o600)
        pipe = self.guard.lstat()
        self.assert_blocked([pipe.st_dev, pipe.st_ino])


if __name__ == "__main__":
    unittest.main()
