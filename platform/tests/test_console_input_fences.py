"""Guest completion fences must not replay input or accept stale UART text."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/uiflow2'))
import run_device_matrix as matrix
profile = importlib.import_module('run_profile_ui_test')


class ConsoleInputFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.serial = Path(self.temp.name) / 'serial.log'
        self.serial.write_text('READY\n')
        self.qmp = mock.Mock()

    def events(self, qmp, spec, frame, settle):
        for down in (True, False):
            qmp.cmd('input-send-event', events=[{'type': 'key', 'data': {
                'down': down, 'key': {'type': 'qcode', 'data': spec.split(':')[1]}}}])

    def test_waits_for_new_draw_before_next_unmodified_input(self):
        sent = []

        def send(qmp, spec, frame, settle):
            self.assertEqual(frame, (320, 240))
            self.assertEqual(settle, 0.5)
            sent.append(spec)
            self.events(qmp, spec, frame, settle)
            if spec == 'key:b':
                self.assertIn('FRAME 2', self.serial.read_text())
                with self.serial.open('a') as out:
                    out.write('FRAME 4\n')

        def finish_draw(_):
            with self.serial.open('a') as out:
                out.write('FRAME 2\n')

        with mock.patch.object(profile, 'send_input', side_effect=send), \
                mock.patch.object(matrix.time, 'sleep', side_effect=finish_draw):
            rows, error = matrix.send_console_inputs(
                self.qmp, ['key:a', 'key:b'], (320, 240), 0.5,
                self.serial, time.time()+1, ['FRAME 2', 'FRAME 4'])
        self.assertIsNone(error)
        self.assertEqual(sent, ['key:a', 'key:b'])
        self.assertTrue(all(row['after_marker_observed'] for row in rows))
        self.assertEqual([event['events'][0]['data']['down']
                          for row in rows for event in row['events']],
                         [True, False, True, False])

    def test_stale_marker_cannot_release_a_later_input(self):
        self.serial.write_text('FRAME 2\n')
        with mock.patch.object(profile, 'send_input', side_effect=self.events) as send, \
                mock.patch.object(matrix.time, 'time', side_effect=[0, 2]), \
                mock.patch.object(matrix.time, 'sleep'):
            rows, error = matrix.send_console_inputs(
                self.qmp, ['key:a', 'key:b'], (320, 240), 0.5,
                self.serial, 1, ['FRAME 2', 'FRAME 4'])
        self.assertIn('FRAME 2', error)
        self.assertEqual(send.call_count, 1)
        self.assertFalse(rows[0]['after_marker_observed'])

    def test_invalid_fence_contract_rejects_before_input(self):
        for markers in (['ONE'], 'AB', ['', 'TWO']):
            with self.subTest(markers=markers), \
                    mock.patch.object(profile, 'send_input') as send:
                with self.assertRaises(ValueError):
                    matrix.send_console_inputs(self.qmp, ['key:a', 'key:b'],
                        (320, 240), 0.5, self.serial, time.time()+1, markers)
                send.assert_not_called()
