from pathlib import Path
import argparse,contextlib,hashlib,io,json,subprocess,sys,types
from unittest import mock

parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out-dir',type=Path,required=True);args=parser.parse_args()
repo=Path.cwd();runner=repo/'tests/uiflow2/run_peripheral_matrix.py';raw=args.source.read_bytes();args.out_dir.mkdir(parents=True,exist_ok=True)
namespace={'__name__':'matrix_host_probe','__file__':str(runner)}
exec(compile(raw,str(runner),'exec'),namespace)
case=next(c for c in namespace['CASES'] if c['id']=='papercolor-rgb')
calls=[]
def fake_run(argv,**kwargs):
    argv=list(map(str,argv));callee=Path(argv[1]).name if len(argv)>1 else ''
    kind={'run_profile_ui_test.py':'profile-launch','check_rmt_ws2812.py':'ws2812-checker','check_frame_marker.py':'frame-checker'}.get(callee)
    assert kind is not None,argv
    calls.append({'kind':kind,'argv':argv,'check':kwargs.get('check'),'cwd':str(kwargs.get('cwd'))})
    if kind=='profile-launch':
        # This is a mock boundary: no runner, QEMU, firmware, or checkers are executed.
        kwargs['stdout'].write(b'HOST MOCK profile returncode zero\n')
        kwargs['stdout'].flush()
        assert kwargs['env']['M5SW_RMT_TX_FILE']==str(args.out_dir/'run/papercolor-rgb/rgb.rmt')
        return subprocess.CompletedProcess(argv,0)
    return subprocess.CompletedProcess(argv,0,stdout='PASS host mocked '+kind+'\n')
console=io.StringIO()
with mock.patch.object(sys,'argv',[str(runner),'--case','papercolor-rgb','--out-dir',str(args.out_dir/'run')]),mock.patch.object(namespace['subprocess'],'run',fake_run),contextlib.redirect_stdout(console):
    namespace['main']()
(args.out_dir/'main.stdout.txt').write_text(console.getvalue())
summary=json.loads((args.out_dir/'run/summary.json').read_text());result=summary['results']['papercolor-rgb']
launch=calls[0]['argv'];checker=calls[1]['argv']
checks={
 'actual_main_and_actual_papercolor_case_used':True,
 'subprocess_call_order_preserved':[c['kind'] for c in calls]==['profile-launch','ws2812-checker','frame-checker'],
 'ws2812_checker_received_expected_leds':checker[2:]==[str(args.out_dir/'run/papercolor-rgb/rgb.rmt'),'--led','0,255,0','--led','255,0,0'],
 'summary_command_is_actual_profile_launch_argv':result['command']==launch,
 'summary_command_is_ws2812_checker_argv':result['command']==checker,
 'mocked_returncodes_and_result_unchanged':all(c['check'] is False for c in calls) and result['status']=='PASS' and result['exit_code']==0 and result['attempts']==1,
 'summary_contains_both_checker_outputs':'PASS host mocked ws2812-checker' in result['validation'] and 'PASS host mocked frame-checker' in result['validation'],
}
record={'schema_version':1,'issue':'UNIT-HOST-22','status':'PASS' if checks['summary_command_is_actual_profile_launch_argv'] else 'FAIL','scope':'actual main/command_for/reference_layout/PaperColor RGB branch with only subprocess.run mocked; no guest, QEMU, profile runner, or checker process execution','runner_sha256':hashlib.sha256(raw).hexdigest(),'reference_layout':result['reference_layout'],'calls':calls,'checks':checks,'summary_command':result['command'],'actual_profile_launch_argv':launch,'ws2812_checker_argv':checker,'summary_sha256':hashlib.sha256((args.out_dir/'run/summary.json').read_bytes()).hexdigest()}
(args.out_dir/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
assert checks['subprocess_call_order_preserved'] and checks['ws2812_checker_received_expected_leds'] and checks['mocked_returncodes_and_result_unchanged'] and checks['summary_contains_both_checker_outputs']
print(json.dumps({'status':record['status'],'runner_sha256':record['runner_sha256'],'calls':[c['kind'] for c in calls],'launch_summary_matches':checks['summary_command_is_actual_profile_launch_argv'],'checker_summary_matches':checks['summary_command_is_ws2812_checker_argv']}))
