"""Offline positive-input execution gates; no service, browser or guest runs."""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

import run_host_sensor_cases as runner


SAMPLES = {
    'color': ('SENSOR_COLOR 9000 6000 3000 42000', 'SENSOR_COLOR 21000 12000 6000 53000'),
    'tof': ('SENSOR_TOF 321 32.100', 'SENSOR_TOF 1456 145.600'),
    'ncir': ('SENSOR_NCIR 17.2900 37.0900', 'SENSOR_NCIR 31.4900 53.1900'),
    'heart': ('SENSOR_HEART 41000 36000', 'SENSOR_HEART 12000 9000'),
    'tvoc': ('SENSOR_TVOC 1250 230 26000 31000', 'SENSOR_TVOC 675 18 18300 24500'),
    'ultrasonic-i2c': ('SENSOR_ULTRASONIC 1234.500 123.450', 'SENSOR_ULTRASONIC 876.200 87.620'),
}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def fixture(case='color'):
    sid, firmware = 'offline-sensor-session', 'a' * 64
    record = {'unit_id': case, 'device_id': 'atoms3r', 'firmware_sha256': firmware, 'runtime': 'qemu'}
    values = runner.preparation.SENSOR_CASES[case]['changes']
    # An old identical value is deliberately present before the real UI offset.
    before = 'boot\r\n' + SAMPLES[case][0] + '\r\n' + SAMPLES[case][1] + '\r\n'
    prefixes = [before, before + SAMPLES[case][0] + '\r\n']
    serial = prefixes[1] + SAMPLES[case][1] + '\r\n'
    fresh, posts = [], []
    for index, vector in enumerate(values):
        start, end = 1 + index * 2, 2 + index * 2
        fresh.append({'requested': {'id': 'external1', 'values': deepcopy(vector)},
            'serial_offset_before_ui': len(prefixes[index]), 'before_serial_sha256': digest(prefixes[index]),
            'request_started_at': f'2026-10-26T00:00:0{start}.000+00:00',
            'request_returned_at': f'2026-10-26T00:00:0{end}.000+00:00'})
        for field, value in vector.items():
            posts.append({'at': f'2026-10-26T00:00:0{start}.500Z', 'method': 'POST', 'status': 200,
                'path': f'/api/v1/sessions/{sid}/unit-input',
                'request': {'id': 'external1', 'values': {field: value}},
                'response': {'session_id': sid, 'state': 'running', 'source': 'live', 'units': [
                    {'id': 'external1', 'unit_id': case, 'available': True, 'source': 'guest-qom',
                     'properties': {field: value}}]}})
    controller = {**record, 'session_id': sid, 'injections': [
        {'sequence': index, 'values': deepcopy(vector), 'guest_observed': True}
        for index, vector in enumerate(values, 1)]}
    web = {**record, 'session_id': sid, 'posts': posts}
    return record, fresh, web, serial, controller


class PositiveInputBindingTests(unittest.TestCase):
    def reject(self, items):
        with self.assertRaises((AssertionError, ValueError, TypeError)):
            runner.positive_input_binding(*items)

    def test_six_cases_bind_exact_posts_and_raw_crlf_serial_windows(self):
        for case in SAMPLES:
            with self.subTest(case=case):
                record, fresh, web, serial, controller = fixture(case)
                result = runner.positive_input_binding(record, fresh, web, serial, controller)
                self.assertEqual(result['status'], 'VERIFIED')
                self.assertEqual(result['full_serial_sha256'], digest(serial))
                self.assertEqual(result['post_count'], len(web['posts']))
                self.assertEqual(len(result['vectors']), 2)
                for index, row in enumerate(result['vectors']):
                    start, end = row['serial_offset_before_ui'], row['serial_end_offset']
                    self.assertEqual(row['before_serial_sha256'], digest(serial[:start]))
                    self.assertEqual(row['fresh_serial_sha256'], digest(serial[start:end]))
                    self.assertEqual(row['guest_marker_lines'], [SAMPLES[case][index]])
                    self.assertIs(row['guest_observed'], True)
                self.assertEqual(result['vectors'][0]['serial_end_offset'], result['vectors'][1]['serial_offset_before_ui'])

    def test_missing_extra_reordered_or_wrong_product_post_is_rejected(self):
        for mutation in ('missing', 'extra', 'order', 'wrong-value', 'wrong-field', 'bool-value', 'string-value'):
            with self.subTest(mutation=mutation):
                data = list(fixture())
                posts = data[2]['posts']
                if mutation == 'missing':
                    posts.pop()
                elif mutation == 'extra':
                    posts.append(deepcopy(posts[-1]))
                elif mutation == 'order':
                    posts[0], posts[1] = posts[1], posts[0]
                else:
                    field = next(iter(posts[0]['request']['values']))
                    posts[0]['request']['values'] = {
                        'wrong-field' if mutation == 'wrong-field' else field:
                        True if mutation == 'bool-value' else '42000' if mutation == 'string-value' else 1}
                self.reject(data)

    def test_product_method_status_session_instance_or_timestamp_must_match(self):
        for mutation in ('method', 'status', 'bool-status', 'path', 'instance', 'response-sid',
                         'response-state', 'response-source', 'response-instance', 'response-unit',
                         'available-integer', 'response-bool-value', 'old-time', 'late-time', 'missing-time', 'naive-time'):
            with self.subTest(mutation=mutation):
                data = list(fixture())
                post = data[2]['posts'][0]
                response, unit = post['response'], post['response']['units'][0]
                if mutation == 'method': post['method'] = 'GET'
                elif mutation == 'status': post['status'] = 500
                elif mutation == 'bool-status': post['status'] = True
                elif mutation == 'path': post['path'] = '/api/v1/sessions/other/unit-input'
                elif mutation == 'instance': post['request']['id'] = 'external2'
                elif mutation == 'response-sid': response['session_id'] = 'other'
                elif mutation == 'response-state': response['state'] = 'stopped'
                elif mutation == 'response-source': response['source'] = 'history'
                elif mutation == 'response-instance': unit['id'] = 'external2'
                elif mutation == 'response-unit': unit['unit_id'] = 'tof'
                elif mutation == 'available-integer': unit['available'] = 1
                elif mutation == 'response-bool-value': unit['properties']['clear-raw'] = True
                elif mutation == 'old-time': post['at'] = '2026-10-26T00:00:00.999Z'
                elif mutation == 'late-time': post['at'] = '2026-10-26T00:00:02.001Z'
                elif mutation == 'missing-time': post.pop('at')
                else: post['at'] = '2026-10-26T00:00:01.500'
                self.reject(data)

    def test_requested_and_original_controller_vectors_cannot_be_replaced(self):
        for mutation in ('missing-request', 'extra-request', 'request-instance', 'request-bool',
                         'missing-injection', 'false-injection', 'bool-sequence', 'changed-injection'):
            with self.subTest(mutation=mutation):
                data = list(fixture())
                fresh, controller = data[1], data[4]
                if mutation == 'missing-request': fresh.pop()
                elif mutation == 'extra-request': fresh.append(deepcopy(fresh[-1]))
                elif mutation == 'request-instance': fresh[0]['requested']['id'] = 'external2'
                elif mutation == 'request-bool': fresh[0]['requested']['values']['clear-raw'] = True
                elif mutation == 'missing-injection': controller['injections'].pop()
                elif mutation == 'false-injection': controller['injections'][0]['guest_observed'] = 1
                elif mutation == 'bool-sequence': controller['injections'][0]['sequence'] = True
                else: controller['injections'][0]['values']['clear-raw'] = 99
                self.reject(data)

    def test_wrong_firmware_device_runtime_or_session_cannot_share_posts(self):
        for key in ('firmware_sha256', 'device_id', 'runtime', 'session_id'):
            for target in ('web', 'controller'):
                with self.subTest(key=key, target=target):
                    data = list(fixture())
                    data[2 if target == 'web' else 4][key] = 'other'
                    self.reject(data)

    def test_stale_serial_wrong_units_swapped_fields_and_nonfinite_rows_are_rejected(self):
        for case, replacement in (('color', 'SENSOR_COLOR 42000 9000 6000 3000'),
                                  ('tof', 'SENSOR_TOF 321 321'),
                                  ('ultrasonic-i2c', 'SENSOR_ULTRASONIC 1234.500 1234.500'),
                                  ('heart', 'SENSOR_HEART 36000 41000'),
                                  ('ncir', 'SENSOR_NCIR nan 37.0900'),
                                  ('tvoc', 'SENSOR_TVOC 1250 230 26000 31000 extra'),
                                  ('color', 'unrelated new output')):
            with self.subTest(case=case, replacement=replacement):
                data = list(fixture(case))
                offset = data[1][0]['serial_offset_before_ui']
                data[3] = data[3][:offset] + data[3][offset:].replace(SAMPLES[case][0], replacement, 1)
                self.reject(data)

    def test_serial_reset_false_offset_or_overlapping_windows_cannot_pass(self):
        for mutation in ('reset', 'wrong-prefix-hash', 'false-offset', 'negative-offset', 'overlap'):
            with self.subTest(mutation=mutation):
                data = list(fixture())
                if mutation == 'reset': data[3] = data[3].replace('boot\r\n', 'reset\r\n', 1)
                elif mutation == 'wrong-prefix-hash': data[1][0]['before_serial_sha256'] = '0' * 64
                elif mutation == 'false-offset': data[1][0]['serial_offset_before_ui'] = False
                elif mutation == 'negative-offset': data[1][0]['serial_offset_before_ui'] = -1
                else: data[1][1]['serial_offset_before_ui'] = data[1][0]['serial_offset_before_ui'] - 1
                self.reject(data)


class HostClientInputCaptureTests(unittest.TestCase):
    def test_real_pre_ui_prefix_is_hashed_and_request_is_copied_without_network(self):
        client = object.__new__(runner.HostClient)
        client.fresh_inputs = []
        before = 'SENSOR_COLOR 1 2 3 4\r\n'
        payload = {'id': 'external1', 'values': {'clear-raw': 42000}}
        with patch.object(client, 'serial_now', return_value=before), patch.object(runner.Client, 'raw', return_value=b'{}'):
            self.assertEqual(client.raw('sessions/offline/unit-input', method='POST', payload=payload), b'{}')
        row = client.fresh_inputs[0]
        payload['values']['clear-raw'] = 1
        self.assertEqual(row['requested']['values']['clear-raw'], 42000)
        self.assertEqual(row['serial_offset_before_ui'], len(before))
        self.assertEqual(row['before_serial_sha256'], digest(before))
        self.assertLessEqual(runner.input_time(row['request_started_at']), runner.input_time(row['request_returned_at']))


if __name__ == '__main__':
    unittest.main()
