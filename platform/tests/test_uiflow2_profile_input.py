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


class InputStepTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from types import SimpleNamespace
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.serial = Path(self.tmp.name) / 'serial.log'
        self.evidence = Path(self.tmp.name) / 'input-steps.jsonl'
        self.proc = SimpleNamespace(poll=lambda: None)
        self.fake = FakeInput()

    def events(self):
        import json
        return [json.loads(line) for line in self.evidence.read_text().splitlines()]

    def run_steps(self, steps, **options):
        with patch.object(RUNNER.time, 'sleep', side_effect=self.fake.sleep), \
                patch.object(RUNNER.time, 'monotonic', side_effect=lambda: self.fake.now):
            RUNNER.run_input_steps(self.fake, steps, self.serial, self.proc,
                                   (320, 240), 0, self.evidence, **options)

    def test_waits_then_delays_and_sends_each_real_key_in_order(self):
        original_sleep = self.fake.sleep
        def advance(seconds):
            original_sleep(seconds)
            if self.fake.now >= .1:
                self.serial.write_text('FIRST\nSECOND\n')
        self.fake.sleep = advance
        self.run_steps([(0.2, 'keydown:a', 'FIRST'), (0.3, 'keyup:a', 'SECOND')])
        self.assertEqual([(k, d) for k, d, _ in self.fake.keys], [('a', True), ('a', False)])
        self.assertAlmostEqual(self.fake.keys[0][2], .3)
        self.assertAlmostEqual(self.fake.keys[1][2], .6)
        events = self.events()
        self.assertEqual([e['event'] for e in events],
                         ['wait-marker', 'marker-observed', 'input-start', 'qmp-send',
                          'qmp-complete', 'input-complete'] * 2)
        self.assertEqual(events[3]['arguments']['events'][0]['data']['down'], True)
        self.assertAlmostEqual(events[-1]['elapsed_seconds'], .6)
        self.assertEqual([e['step'] for e in events], [0]*6 + [1]*6)

    def test_missing_marker_times_out_without_any_input_or_later_step(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.run_steps([(0, 'keydown:a', 'MISSING'), (0, 'keyup:a', 'LATER')])
        self.assertEqual(self.fake.keys, [])
        self.assertGreaterEqual(self.fake.now, 30)
        self.assertLess(self.fake.now, 30.1)
        self.assertEqual([e['event'] for e in self.events()], ['wait-marker', 'step-failed'])
        self.assertEqual(self.events()[-1]['phase'], 'marker')

    def test_guest_exit_blocks_even_an_already_present_marker(self):
        self.serial.write_text('READY')
        self.proc.poll = lambda: 1
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            self.run_steps([(0, 'keydown:a', 'READY')])
        self.assertEqual(self.fake.keys, [])

    def test_guest_exit_during_delay_blocks_input(self):
        self.serial.write_text('READY')
        self.proc.poll = lambda: 1 if self.fake.now >= 1 else None
        with self.assertRaisesRegex(RuntimeError, 'during input-step delay'):
            self.run_steps([(1, 'keydown:a', 'READY')])
        self.assertEqual(self.fake.keys, [])
        self.assertEqual(self.events()[-1]['phase'], 'delay')

    def test_qmp_failure_is_retained_and_does_not_send_later_input(self):
        self.serial.write_text('ONE\nTWO')
        with patch.object(self.fake, 'cmd', side_effect=RUNNER.QMPCommandError('failed')) as cmd:
            with self.assertRaises(RUNNER.QMPCommandError):
                self.run_steps([(0, 'keydown:a', 'ONE'), (0, 'keyup:a', 'TWO')])
        self.assertEqual(cmd.call_count, 1)
        self.assertNotIn('input-complete', [e['event'] for e in self.events()])
        self.assertEqual(self.events()[-1]['error_type'], 'QMPCommandError')

    def test_actual_pointer_events_and_hold_timing_are_retained(self):
        self.serial.write_text('TOUCH')
        calls = []
        self.fake.cmd = lambda name, **kw: calls.append((self.fake.now, name, kw))
        self.run_steps([(0, 'longpress:67,160,0.5', 'TOUCH')])
        self.assertEqual([c[0] for c in calls], [0, .5])
        self.assertEqual(calls[0][2]['events'], RUNNER.pointer_events(67, 160, (320, 240), True))
        self.assertEqual(calls[1][2]['events'], RUNNER.pointer_events(67, 160, (320, 240), False))
        self.assertEqual([e['elapsed_seconds'] for e in self.events() if e['event']=='qmp-send'], [0, .5])

    def test_capture_failure_stops_following_steps_but_keeps_completed_input(self):
        self.serial.write_text('ONE\nTWO')
        def failed_capture(index):
            raise RuntimeError('blank frame')
        with self.assertRaisesRegex(RuntimeError, 'blank frame'):
            self.run_steps([(0, 'keydown:a', 'ONE'), (0, 'keyup:a', 'TWO')],
                           after_input=failed_capture)
        self.assertEqual(len(self.fake.keys), 1)
        self.assertEqual(self.events()[-2]['event'], 'input-complete')
        self.assertEqual(self.events()[-1]['phase'], 'capture')

    def test_empty_sequence_does_not_create_evidence_or_change_input(self):
        self.run_steps([])
        self.assertFalse(self.evidence.exists())
        self.assertEqual(self.fake.keys, [])
        self.assertEqual(self.fake.sleeps, [])

    def test_invalid_steps_are_rejected_before_execution(self):
        for steps in ([['0', 'keydown:a']], [['-1', 'keydown:a', 'M']],
                      [['nan', 'keydown:a', 'M']], [['inf', 'keydown:a', 'M']],
                      [['no', 'keydown:a', 'M']], [['0', '', 'M']],
                      [['0', 'keydown:a', '  ']], [['0', 'missing-colon', 'M']]):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                RUNNER.parse_input_steps(steps)
        self.assertEqual(RUNNER.parse_input_steps([['0.25', 'keyup:a', 'M']]),
                         [(0.25, 'keyup:a', 'M')])

    def test_main_preserves_qom_pre_frame_legacy_step_post_frame_order(self):
        import contextlib
        import io
        from types import SimpleNamespace
        trace = []
        process = SimpleNamespace(poll=lambda: None,
                                  terminate=lambda: trace.append('terminate'),
                                  wait=lambda timeout: trace.append('reaped'))
        class Qmp:
            def cmd(self, command, **arguments):
                if command == 'screendump':
                    trace.append(Path(arguments['filename']).name)
                else:
                    trace.append(command)
                return {'return': {}}
            def close(self):
                trace.append('qmp-close')
        out = Path(self.tmp.name)
        (out/'serial.log').write_text('QOM')
        (out/'serial1.log').write_text('')
        argv = ['runner', '--base', 'unused', '--prebuilt-image', 'unused',
                '--machine', 'test', '--files-dir', 'unused', '--vfs-offset', '0',
                '--vfs-size', '1', '--flash-size', '1', '--expected-size', '2x2',
                '--out-dir', str(out), '--wait', '0', '--allow-static-frame',
                '--qom-step', '0', '/machine', 'value', 'true', 'QOM',
                '--pre-input-marker', 'PRE', '--post-input-marker', 'POST',
                '--input', 'keydown:b', '--input-step', '0', 'keyup:a', 'STEP',
                '--capture-each-input', '--min-nonblack-pixels', '1']
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(RUNNER.sys, 'argv', argv))
            stack.enter_context(patch.object(RUNNER.subprocess, 'Popen', return_value=process))
            stack.enter_context(patch.object(RUNNER, 'efuse_image', return_value=b''))
            stack.enter_context(patch.object(RUNNER, 'wait_qmp', return_value=Qmp()))
            stack.enter_context(patch.object(RUNNER.time, 'sleep'))
            stack.enter_context(patch.object(RUNNER, 'wait_serial_marker', side_effect=lambda p,m,proc: trace.append(m)))
            stack.enter_context(patch.object(RUNNER, 'capture_before_frame', side_effect=lambda *a,**kw: trace.append('before') or (2,2)))
            stack.enter_context(patch.object(RUNNER, 'send_input', side_effect=lambda q,s,*a: trace.append(s)))
            stack.enter_context(patch.object(RUNNER, 'canonicalize_screendump', return_value=(2,2,b'pixels')))
            stack.enter_context(patch.object(RUNNER, 'frame_stats', return_value=(4,2)))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            RUNNER.main()
        self.assertEqual(trace, ['qom-set', 'PRE', 'before', 'keydown:b', 'input-000.ppm',
                                 'STEP', 'keyup:a', 'input-001.ppm', 'POST', 'after.ppm',
                                 'qmp-close', 'terminate', 'reaped'])


class ConsoleCaptureTests(unittest.TestCase):
    def argv(self, folder, *extra):
        return ['runner', '--base', 'unused', '--prebuilt-image', 'unused',
                '--machine', 'esp32c6', '--files-dir', 'unused', '--vfs-offset', '0',
                '--vfs-size', '1', '--flash-size', '1', '--expected-size', '2x2',
                '--out-dir', str(folder), *extra]

    def test_exact_qemu_serial_arguments_and_metadata_for_default_and_usb(self):
        import contextlib
        import json
        import tempfile
        for extra, expected in (([], ['serial.log', 'serial1.log']),
                                (['--console-index', '2'], ['uart0.log', 'serial1.log', 'serial.log'])):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                with patch.object(RUNNER.sys, 'argv', self.argv(folder, *extra)), \
                        patch.object(RUNNER.subprocess, 'Popen', side_effect=RuntimeError('host prelaunch stop')) as launch:
                    with self.assertRaisesRegex(RuntimeError, 'host prelaunch stop'):
                        RUNNER.main()
                command = launch.call_args.args[0]
                actual = [command[i+1] for i,value in enumerate(command) if value == '-serial']
                self.assertEqual(actual, ['file:' + str(folder/name) for name in expected])
                metadata = json.loads((folder/'console-capture.json').read_text())
                self.assertEqual([row['file'] for row in metadata['backends']], expected)
                self.assertEqual([row['index'] for row in metadata['backends']], list(range(len(expected))))
                self.assertEqual(metadata['backends'][-1]['channel'], 'usb-serial-jtag' if extra else 'uart1')
                self.assertEqual(metadata['primary_console_index'], 2 if extra else 0)

    def test_illegal_console_or_machine_is_rejected_before_build_or_launch(self):
        import contextlib
        import io
        import tempfile
        for extra in (['--console-index', '1'], ['--console-index', '-1'],
                      ['--console-index', '3'], ['--console-index', '2', '--machine', 'm5cores3']):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                with patch.object(RUNNER.sys, 'argv', self.argv(tmp, *extra)), \
                        patch.object(RUNNER, 'build_image') as build, \
                        patch.object(RUNNER.subprocess, 'Popen') as launch, \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        RUNNER.main()
                build.assert_not_called()
                launch.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_default_uart_mapping_is_identical_for_existing_machine_profiles(self):
        expected = [{'index': 0, 'channel': 'uart0', 'file': 'serial.log'},
                    {'index': 1, 'channel': 'uart1', 'file': 'serial1.log'}]
        for machine in ('esp32c6', 'm5cores3', 'm5core2', 'm5cardputer'):
            with self.subTest(machine=machine):
                self.assertEqual(RUNNER.serial_capture_backends(machine, 0), expected)


if __name__ == '__main__':
    unittest.main()
