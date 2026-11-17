"""Contract checks for the native Dial encoder adapter."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call

from device_service_encoder import rotate_encoder
from device_service_errors import ServiceError


class DialEncoderTests(unittest.TestCase):
    def session(self, target=2, delivered=2, edges=8):
        return SimpleNamespace(
            spec=SimpleNamespace(id="dial", machine="m5dial"),
            runtime="qemu",
            _qmp_call=Mock(
                side_effect=[
                    {"return": target},
                    {"return": delivered},
                    {"return": edges},
                    {"return": {}},
                ]
            ),
        )

    def test_relative_target_and_prior_physical_evidence(self):
        session = self.session()
        self.assertEqual(
            rotate_encoder(session, -3),
            {
                "delta": -3,
                "target_detents": -1,
                "previous_detents": 2,
                "previous_gpio_edges": 8,
            },
        )
        path = "/machine/encoder"
        self.assertEqual(
            session._qmp_call.call_args_list,
            [
                call("qom-get", path=path, property=field)
                for field in ("detents", "delivered-detents", "gpio-edges")
            ]
            + [call("qom-set", path=path, property="detents", value=-1)],
        )

    def test_rejects_overlap_and_mid_detent_retarget(self):
        for target, delivered, edges in ((5, 2, 8), (2, 2, 9)):
            with self.subTest(target=target, delivered=delivered, edges=edges):
                session = self.session(target, delivered, edges)
                with self.assertRaises(ServiceError) as raised:
                    rotate_encoder(session, -1)
                self.assertEqual((raised.exception.code, raised.exception.status), ("input_busy", 409))
                self.assertEqual(session._qmp_call.call_count, 3)

    def test_rejects_invalid_deltas_before_qmp(self):
        for delta in (None, True, 0, "1", 1.0, -129, 129):
            with self.subTest(delta=delta):
                session = self.session()
                with self.assertRaises(ServiceError) as raised:
                    rotate_encoder(session, delta)
                self.assertEqual(raised.exception.code, "invalid_input")
                session._qmp_call.assert_not_called()

    def test_rejects_unsupported_machine_and_lane_before_qmp(self):
        for device_id, machine, runtime in (
            ("stickt2", "m5stickt2", "qemu"),
            ("dial", "m5cores3", "qemu"),
            ("dial", "m5dial", "network"),
        ):
            with self.subTest(device_id=device_id, machine=machine, runtime=runtime):
                session = self.session()
                session.spec.id = device_id
                session.spec.machine = machine
                session.runtime = runtime
                with self.assertRaises(ServiceError) as raised:
                    rotate_encoder(session, 1)
                self.assertEqual(raised.exception.code, "unsupported_input")
                session._qmp_call.assert_not_called()

    def test_rejects_target_outside_physical_bounds(self):
        for target, delta in ((4096, 1), (-4096, -1)):
            session = self.session(target=target, delivered=target)
            with self.assertRaises(ServiceError) as raised:
                rotate_encoder(session, delta)
            self.assertEqual(raised.exception.code, "invalid_input")
            self.assertEqual(session._qmp_call.call_count, 3)

    def test_rejects_unexpected_readback_without_a_write(self):
        for value in (True, None, "2"):
            session = self.session(target=value)
            with self.assertRaises(ServiceError) as raised:
                rotate_encoder(session, 1)
            self.assertEqual(raised.exception.code, "qmp_error")
            self.assertEqual(session._qmp_call.call_count, 1)
