"""Check real QMP key order and elapsed fixture time without a guest."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'uiflow2_profile_input', ROOT / 'tests/uiflow2/run_profile_ui_test.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FakeInput:
    def __init__(self):
        self.now = 0
        self.keys = []
        self.sleeps = []

    def cmd(self, name, *, events):
        assert name == 'input-send-event' and len(events) == 1
        event = events[0]
        assert event['type'] == 'key'
        self.keys.append((event['data']['key']['data'],
                          event['data']['down'], self.now))

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ProfileInputTests(unittest.TestCase):
    def test_keytap_holds_then_waits_full_release_settle(self):
        fake = FakeInput()
        with patch.object(RUNNER.time, 'sleep', side_effect=fake.sleep):
            RUNNER.send_input(fake, 'keytap:p,0.1', (320, 240), 1.25)
        self.assertEqual(fake.keys, [('p', True, 0), ('p', False, 0.1)])
        self.assertEqual(fake.sleeps, [0.1, 1.25])
        self.assertAlmostEqual(fake.now, 1.35)

    def test_legacy_key_keeps_450ms_hold_and_release_wait(self):
        fake = FakeInput()
        with patch.object(RUNNER.time, 'sleep', side_effect=fake.sleep):
            RUNNER.send_input(fake, 'key:p', (320, 240), 1.25)
        self.assertEqual(fake.keys, [('p', True, 0), ('p', False, 0.45)])
        self.assertEqual(fake.sleeps, [0.45, 0.45, 1.25])

    def test_invalid_keytap_never_presses_or_sleeps(self):
        for value in ('p,nan', 'p,NaN', 'p,inf', 'p,-inf', 'p,0',
                      'p,-0.1', 'p,10.01', 'p,1e309', 'p,no',
                      'p', 'p,1,2', ',0.1'):
            with self.subTest(value=value):
                fake = FakeInput()
                with patch.object(RUNNER.time, 'sleep', side_effect=fake.sleep):
                    with self.assertRaises(SystemExit):
                        RUNNER.send_input(fake, 'keytap:' + value, (1, 1), 1)
                self.assertEqual(fake.keys, [])
                self.assertEqual(fake.sleeps, [])

    def test_keytap_releases_after_interrupted_hold(self):
        fake = FakeInput()
        with patch.object(RUNNER.time, 'sleep', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                RUNNER.send_input(fake, 'keytap:p,0.1', (1, 1), 1)
        self.assertEqual(fake.keys, [('p', True, 0), ('p', False, 0)])


if __name__ == '__main__':
    unittest.main()
