"""Host IO preparation boundaries; never starts a guest or contacts a service."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import prepare_host_io as prep


class Admit:
    def attachments(self, *_args):
        return []


def host_inputs(host):
    hosts = json.loads((prep.ROOT / 'platform/units/host-ports.json').read_bytes())['hosts']
    port = next(x for x in hosts if x['device_id'] == host)['ports'][0]
    profile = {**prep.HOSTS[host], 'log_tx':43, 'log_rx':44, 'internal_controller':1, 'external_controller':0}
    return port, profile


class OriginalProtocolTests(unittest.TestCase):
    def test_all_twelve_original_cases_and_protocol_segments_are_preserved(self):
        audit, _, _ = prep.protocol_audit()
        self.assertEqual(len(prep.CASES), 12)
        self.assertEqual(set(prep.CONTROLLER_PATHS), set(prep.CASES))
        self.assertEqual(set(audit['original_runner_segments']), {'validate_io','run_case','Observations','validate_evidence'})
        self.assertIn('wait_ms', audit['guest_protocol_sha256'])
        self.assertIn('original_io_loop', audit['guest_protocol_sha256'])
        self.assertEqual(audit['official_drivers'], prep.original.driver_manifest())

    def test_timing_initialization_callbacks_and_output_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / 'guest'
            shutil.copytree(prep.GUEST, candidate)
            path = candidate / 'io_program.py'
            original = path.read_text()
            for old,new in [('wait_ms(4000)','wait_ms(3999)'), ('unit.enable_irq()','unit.disable_irq()'),
                            ('pir_callbacks[1] += 1','pir_callbacks[1] += 2'), ('unit.tx(0x12, 0x34)','unit.tx(0x12, 0x35)')]:
                with self.subTest(mutation=old), patch.object(prep,'GUEST',candidate):
                    self.assertIn(old,original)
                    path.write_text(original.replace(old,new,1))
                    with self.assertRaises(AssertionError): prep.protocol_audit()

    def test_source_inventory_includes_every_new_and_direct_dependency(self):
        paths, _ = prep.source_paths()
        names = {p.relative_to(prep.ROOT).as_posix() for p in paths}
        self.assertTrue({'tests/units/run_host_io_cases.py','tests/units/prepare_host_io.py',
            'tests/units/test_host_io_execution.py','tests/units/io_probe/io_drivers/source-manifest.json',
            'tests/units/host_io_probe/io_program.py','tests/units/host_io_probe/host_io_layout.py',
            'tests/units/host_io_probe/font-source.json','tests/uiflow2/lib/rtc_probe.py',
            'platform/tools/device_service.py','platform/web/unit-panel.js',
            'scripts/bootstrap-unit-runtime.py',
            'patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch',
            'platform/tests/test_unit_ledc_readback_patch.py'} <= names)


class CustomCopyTests(unittest.TestCase):
    def test_explicit_patch_changes_generated_copy_and_preserves_vendor(self):
        manifest = prep.original.driver_manifest()
        for case,name,patch_path in [('ir','ir.py',prep.original.IR_CALLBACK_PATCH),('buzzer','buzzer.py',prep.original.BUZZER_CALLBACK_PATCH)]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                files = Path(temporary)
                shutil.copytree(prep.original.PROBE/'io_drivers', files/'io_drivers')
                before = (prep.original.PROBE/'io_drivers'/name).read_bytes()
                self.assertIsNone(prep.custom_driver(files,case))
                self.assertEqual((files/'io_drivers'/name).read_bytes(),before)
                result = prep.custom_driver(files,case,True,True)
                self.assertEqual(result['original_driver_sha256'],manifest[name]['sha256'])
                self.assertNotEqual(result['patched_driver_sha256'],result['original_driver_sha256'])
                self.assertEqual((prep.original.PROBE/'io_drivers'/name).read_bytes(),before)
                with self.assertRaises(AssertionError): prep.strict_patch(b'wrong\n',patch_path.read_bytes(),'io_drivers/'+name)

    def test_custom_flavors_do_not_affect_other_cases(self):
        flags={'ir_callback_root_patch':True,'buzzer_callback_arity_patch':True}
        self.assertEqual(prep.flavor('ir',flags),'custom-guest-ir-callback-root-patch')
        self.assertEqual(prep.flavor('buzzer',flags),'custom-guest-buzzer-callback-arity-patch')
        self.assertEqual(prep.flavor('pir',flags),'reference-app-with-original-unit-drivers-host-io-probe')
        self.assertNotEqual(prep.flavor('ir',flags),prep.flavor('ir',dict.fromkeys(flags,False)))


class ResourceTests(unittest.TestCase):
    def test_default_ir_buzzer_risks_do_not_inherit_another_hosts_failure(self):
        for host in prep.HOSTS:
            port,profile=host_inputs(host)
            for case in ('ir','buzzer'):
                row=prep.resource_preflight(host,case,port,profile,b'',Admit())
                self.assertEqual(row['status'],'ADMITTED_NOT_EXECUTED')
                self.assertEqual(row['blockers'],[])
                self.assertTrue(row['known_risks'])

    def test_adc_fixture_boundary_and_stopwatch_adc2_are_explicit(self):
        for host in prep.HOSTS:
            port,profile=host_inputs(host)
            for case in ('angle','light'):
                with patch.object(prep,'verify_firmware',side_effect=ValueError('application mismatch')):
                    row=prep.resource_preflight(host,case,port,profile,b'',Admit())
                codes={x['code'] for x in row['blockers']}
                self.assertIn('adc_fixture_application_mismatch',codes)
                self.assertEqual('adc_oracle_unit_mismatch' in codes,host=='stopwatch')
                self.assertEqual(row['adc_unit'],2 if host=='stopwatch' else 1)
                self.assertIn('Light raw/digital data plane is not inferred unsupported',row['blockers'][0]['reason'])

    def test_registry_blocker_is_kept_and_pin_overlap_is_rejected(self):
        port,profile=host_inputs('atoms3r')
        blocked=unittest.mock.Mock()
        blocked.attachments.side_effect=prep.UnitError('runtime_model_gap','not admitted',409)
        row=prep.resource_preflight('atoms3r','pir',port,profile,b'',blocked)
        self.assertEqual(row['blockers'][0]['kind'],'admission')
        profile['log_tx']=port['pins']['white']
        with self.assertRaises(AssertionError): prep.resource_preflight('atoms3r','pir',port,profile,b'',Admit())

    def test_uart0_log_and_grove_are_disjoint_for_every_host(self):
        for host in prep.HOSTS:
            port,profile=host_inputs(host)
            row=prep.resource_preflight(host,'rs485',port,profile,b'',Admit())
            self.assertEqual(row['uart0_log'],[43,44])
            self.assertTrue(row['uart1_for_rs485'] and row['pin_sets_disjoint'])
            config=prep.config_bytes(host,'rs485',port,profile,{'ir_callback_root_patch':False,'buzzer_callback_arity_patch':False})
            self.assertIn(b'LOG_TX = 43\nLOG_RX = 44\n',config)


class LayoutTests(unittest.TestCase):
    def test_all_layouts_fit_native_frame_and_stopwatch_circle(self):
        module=prep.layout_module()
        for host in prep.HOSTS:
            for case in prep.CASES:
                layout=module.planned_layout(host,case)
                self.assertLessEqual(layout['bottom'],module.PROFILES[host]['native'][1])
                self.assertEqual(layout['body_rows'],8)

    def test_wrap_uses_measured_width_and_never_silently_truncates(self):
        module=prep.layout_module()
        screen=unittest.mock.Mock()
        screen.textWidth.side_effect=lambda text:len(text)*5
        text='GRB: 112233/445566/778899'
        lines=module.wrap_text(screen,text,40,8)
        self.assertEqual(''.join(lines),text)
        self.assertTrue(all(len(line)<=8 for line in lines))
        with self.assertRaises(RuntimeError): module.wrap_text(screen,text,40,1)
        with self.assertRaises(RuntimeError): module.wrap_text(screen,'X',1,8)


if __name__=='__main__': unittest.main()
