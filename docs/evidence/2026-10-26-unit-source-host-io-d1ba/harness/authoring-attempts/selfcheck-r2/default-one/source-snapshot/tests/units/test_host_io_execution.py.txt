"""IO execution gates against fabricated offline fixtures, never a guest/API."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import run_host_io_cases as run


MARKERS = {
    'pir': ['IO_PIR_CALLBACK 1 1','IO_PIR_CALLBACK 0 1','IO_PIR 1 1 1 1','IO_PIR_DISABLED_DONE 1 1','IO_PIR_CALLBACK 1 2','IO_PIR_CALLBACK 0 2'],
    'dual-button': ['IO_DUAL 0 1 0 0','IO_DUAL_CLICK 1 0','IO_DUAL 1 0 1 0','IO_DUAL_CLICK 1 1'],
    'limit': ['IO_LIMIT 0 0','IO_LIMIT 1 1','IO_LIMIT 0 2','IO_LIMIT 1 3'],
    'key': ['IO_KEY_RAW 0','IO_KEY_RAW 1'],
    'ir': ['IO_IR_RX 52 18 0 1','IO_IR_HEARTBEAT 1\r\nIO_IR_HEARTBEAT 1','IO_IR_RX 52 18 -1 2','IO_IR_RX 120 86 0 3'],
    'rs485': ['IO_RS485_RX '+b'peer-to-guest\x00\x7f\xff'.hex()],
}


def fixture(case='pir', noop=None):
    record={'unit_id':case,'device_id':'atoms3r','runtime':'qemu','firmware_sha256':'a'*64,
            'attachments':run.preparation.original.attachments(case,'custom')}
    controller={**record,'session_id':'offline-host-io','injections':[]}
    web={**record,'session_id':controller['session_id'],'posts':[],'actions':[]}
    serial='boot\r\n'
    rows=[]
    for index,(instance,values) in enumerate(run.INPUTS[case]):
        prefix=serial
        start,end=1+index*2,2+index*2
        row={'requested':{'id':instance,'values':deepcopy(values)},'serial_offset_before_ui':len(prefix),
             'before_serial_sha256':run.sha(prefix.encode()),
             'before_live_state':{'session_id':controller['session_id'],'source':'live','units':[{
                 'id':instance,'unit_id':next(a['unit_id'] for a in record['attachments'] if a['id']==instance),
                 'available':True,'source':'guest-qom','properties':{**deepcopy(values),'adc-samples':index*10}}]},
             'request_started_at':f'2026-10-26T00:00:{start:02d}+00:00','request_returned_at':f'2026-10-26T00:00:{end:02d}+00:00'}
        rows.append(row)
        controller['injections'].append({'id':instance,'values':deepcopy(values)})
        for field,value in values.items():
            at=f'2026-10-26T00:00:{start:02d}.500Z'
            if noop==(index,field):
                web['actions'].append({'at':at,'kind':'already-equal-noop','instance':instance,'field':field,'value':deepcopy(value)})
                continue
            web['posts'].append({'at':at,'method':'POST','status':200,
                'path':f"/api/v1/sessions/{controller['session_id']}/unit-input",'request':{'id':instance,'values':{field:deepcopy(value)}},
                'response':{'session_id':controller['session_id'],'state':'running','source':'live','units':[{
                    'id':instance,'unit_id':next(a['unit_id'] for a in record['attachments'] if a['id']==instance),
                    'available':True,'source':'guest-qom','properties':{field:deepcopy(value)}}]}})
        if case in MARKERS: marker=MARKERS[case][index]
        elif case in {'angle','light'}:
            voltage=values['voltage-mv' if case=='angle' else 'analog-mv']
            expected=run.preparation.original.expected_ideal_input(voltage,attenuation=3,adc_unit=1)
            marker=('IO_ANGLE %d %.6f %d'%(expected['read_u16'],expected['read_uv']/1000000,expected['read_uv'])
                    if case=='angle' else 'IO_LIGHT %d %d'%(expected['read_u16'],values['digital-level']))
        elif case=='hub':
            state=deepcopy(run.preparation.original.HUB_INITIAL)
            for key,vector in run.INPUTS['hub'][:index+1]: state[key].update(vector)
            marker='IO_HUB '+' '.join(str(x) for x in [*state['env'].values(),*state['ncir'].values(),*state['tvoc'].values()])
        serial += marker+'\r\n'
    if case in {'angle','light'}:
        controller['unit_state']={'units':[{'id':'external1','properties':{'adc-samples':len(rows)*10}}]}
    return record,rows,web,serial,controller


class PositiveInputTests(unittest.TestCase):
    def reject(self,data):
        with self.assertRaises((AssertionError,ValueError,TypeError,KeyError,StopIteration)):
            run.positive_input_binding(*data)

    def test_all_twelve_cases_keep_original_vector_count_and_raw_crlf_windows(self):
        for case in run.CASES:
            with self.subTest(case=case):
                data=fixture(case)
                result=run.positive_input_binding(*data)
                self.assertEqual(len(result['vectors']),len(run.INPUTS[case]))
                self.assertEqual(result['post_count'],sum(len(v) for _,v in run.INPUTS[case]))
                self.assertEqual(result['full_serial_sha256'],run.sha(data[3].encode()))
                for row in result['vectors']:
                    self.assertEqual(row['fresh_serial_sha256'],run.sha(data[3][row['serial_offset_before_ui']:row['serial_end_offset']].encode()))
                if not run.INPUTS[case]: self.assertEqual(result['status'],'VERIFIED_OUTPUT_ONLY_ZERO_POSTS')

    def test_old_identical_markers_do_not_satisfy_fresh_observation(self):
        data=list(fixture('key'))
        data[3]=data[3].replace('IO_KEY_RAW 0\r\n','old\r\n',1)
        # Keep the first prefix untouched so the failure is fresh observation,
        # not only a prefix digest mismatch.
        data[1]=data[1][:1]
        data[4]['injections']=data[4]['injections'][:1]
        self.reject(data)
        record,rows,web,serial,controller=fixture('rs485')
        start=rows[0]['serial_offset_before_ui']
        serial=serial[:start]+'not the incoming value\r\n'
        self.reject([record,rows,web,serial,controller])

    def test_missing_extra_wrong_type_order_status_or_identity_post_is_rejected(self):
        for mutation in ('missing','extra','bool-status','method','path','value-type','wrong-unit','wrong-session','old-time','wrong-input'):
            with self.subTest(mutation=mutation):
                data=list(fixture('dual-button'));posts=data[2]['posts'];post=posts[0]
                if mutation=='missing':posts.pop(0)
                elif mutation=='extra':posts.append(deepcopy(post))
                elif mutation=='bool-status':post['status']=True
                elif mutation=='method':post['method']='GET'
                elif mutation=='path':post['path']='/api/v1/sessions/other/unit-input'
                elif mutation=='value-type':post['request']['values']['blue-pressed']=1
                elif mutation=='wrong-unit':post['response']['units'][0]['unit_id']='pir'
                elif mutation=='wrong-session':post['response']['session_id']='other'
                elif mutation=='old-time':post['at']='2026-10-25T00:00:00Z'
                elif mutation=='wrong-input':data[4]['injections'][0]['values']['blue-pressed']=False
                self.reject(data)

    def test_explicit_equal_noop_requires_action_and_real_preinput_live_value(self):
        data=fixture('light',noop=(0,'digital-level'))
        result=run.positive_input_binding(*data)
        self.assertEqual(result['verified_noop_fields'],1)
        self.assertEqual(result['vectors'][0]['already_equal_noop_fields'],['digital-level'])
        for mutation in ('no-action','wrong-prevalue','stale-state','duplicate-action'):
            items=deepcopy(list(data))
            if mutation=='no-action':items[2]['actions']=[]
            elif mutation=='wrong-prevalue':items[1][0]['before_live_state']['units'][0]['properties']['digital-level']=True
            elif mutation=='stale-state':items[1][0]['before_live_state']['source']='persisted'
            else:items[2]['actions'].append(deepcopy(items[2]['actions'][0]))
            self.reject(items)

    def test_adc_requires_nonzero_fresh_vectors_and_perwindow_sample_delta(self):
        for case in ('angle','light'):
            data=list(fixture(case));run.positive_input_binding(*data)
            data[4]['unit_state']['units'][0]['properties']['adc-samples']=20
            self.reject(data)
            data=list(fixture(case));data[3]=data[3].splitlines(keepends=True)[0]+('IO_ANGLE 0 0.000000 0\r\n' if case=='angle' else 'IO_LIGHT 0 0\r\n')*3
            self.reject(data)

    def test_consumed_rmt_queue_still_requires_exact_post_and_fresh_decoder_or_negative(self):
        data=list(fixture('ir'))
        for post in data[2]['posts']: post['response']['units'][0]['properties']['rx-pulses-us']=[]
        self.assertEqual(run.positive_input_binding(*data)['post_count'],4)
        data[3]=data[3].replace('IO_IR_HEARTBEAT 1\r\nIO_IR_HEARTBEAT 1','IO_IR_RX 1 2 0 99')
        self.reject(data)

    def test_output_only_never_claims_input_post_and_hub_ids_remain_distinct(self):
        for case in ('rgb','fan','buzzer'):
            data=list(fixture(case));self.assertEqual(run.positive_input_binding(*data)['post_count'],0)
            data[2]['posts']=[fixture('pir')[2]['posts'][0]];self.reject(data)
        data=list(fixture('hub'));run.positive_input_binding(*data)
        data[2]['posts'][-1]['request']['id']='ncir';self.reject(data)

    def test_zero_post_claim_requires_retained_browser_records(self):
        for key in ('posts','actions'):
            data=list(fixture('rgb'));del data[2][key];self.reject(data)


class PreApiTests(unittest.TestCase):
    def readiness(self):
        rows=[{'device_id':host,'unit_id':case,'status':'PREPARED_NOT_EXECUTED','runtime':'qemu',
               'custom_flags':{'ir_callback_root_patch':False,'buzzer_callback_arity_patch':False}}
              for host in run.DEVICES for case in run.CASES]
        return {'schema_version':1,'status':'PREPARED_NOT_EXECUTED','case_count':len(rows),
                'selection':{'devices':list(run.DEVICES),'cases':list(run.CASES)},'custom_flags':rows[0]['custom_flags'],'cases':rows}

    def test_selection_rejects_missing_duplicate_and_mixed_custom_rows(self):
        good=self.readiness();self.assertEqual(len(run.select_cases(good)),36)
        for mutation in ('missing','duplicate','mixed-custom','integer-custom'):
            bad=deepcopy(good)
            if mutation=='missing':bad['cases'].pop();bad['case_count']-=1
            elif mutation=='duplicate':bad['cases'][-1]=deepcopy(bad['cases'][0])
            elif mutation=='mixed-custom':bad['cases'][0]['custom_flags']['ir_callback_root_patch']=True
            else:bad['custom_flags']['ir_callback_root_patch']=1
            with self.assertRaises(AssertionError):run.select_cases(bad)

    def test_blocked_execute_rejects_before_client_or_output_creation(self):
        readiness=self.readiness()
        with patch.object(sys,'argv',['run_host_io_cases.py','--prepared-dir','/offline-prepared','--execute',
                    '--out-dir',str(run.ROOT/'.work/never-create-host-io-test'),'--expected-runtime-sha256','a'*64]), \
             patch.object(Path,'read_bytes',return_value=json.dumps(readiness).encode()), \
             patch.object(run,'source_continuity'), patch.object(run,'UnitRegistry'), \
             patch.object(run,'validate_case',return_value=(None,{'blockers':[{'code':'runtime_model_gap'}]})), \
             patch.object(run,'Client',side_effect=AssertionError('API contacted')) as client:
            with self.assertRaisesRegex(AssertionError,'no API contacted'):run.main()
            client.assert_not_called()

    def test_original_run_case_and_validate_io_are_not_monkeypatched(self):
        original=run.preparation.original
        before=(original.prepare,original.run_case,original.validate_io,original.Observations)
        module=run.io_adapter(Path('/not-executed'),{},Path('/not-executed'))
        self.assertEqual(before,(original.prepare,original.run_case,original.validate_io,original.Observations))
        self.assertEqual(module.validate_io.__code__.co_code,original.validate_io.__code__.co_code)
        self.assertEqual(module.run_case.__code__.co_code,original.run_case.__code__.co_code)


if __name__=='__main__':unittest.main()
