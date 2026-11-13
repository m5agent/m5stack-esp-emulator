#!/usr/bin/env python3
"""Portable checked-in ESP-IDF GPIO ISR regression runner. No guest without --execute.

Only actual UART commands and existing QMP board inputs are used. The probe's
registered public ESP-IDF GPIO handler is the sole writer of the guest count.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests/uiflow2'))
from run_profile_ui_test import QMP, pointer_events

ROW=re.compile(r'C6_GPIO_IRQ stage=(\w+) pin=(\d+) hits=(\d+) level=(\d+) raw=([0-9a-fA-F]+) cpu=([0-9a-fA-F]+)')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--board',choices=['nano','nesso'],required=True)
    parser.add_argument('--runtime',choices=['baseline','candidate'],required=True)
    parser.add_argument('--qemu',type=Path,required=True)
    parser.add_argument('--rom-dir',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--build-receipt',type=Path,required=True)
    parser.add_argument('--runtime-sha256',required=True,help='Expected SHA256 of the independently built runtime')
    parser.add_argument('--out-dir',type=Path,required=True,help='New private evidence directory; must not exist')
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}',args.runtime_sha256):parser.error('runtime SHA256 must be 64 lowercase hexadecimal characters')
    if not args.execute:
        print(json.dumps({'status':'PREPARED','guest':'NOT RUN','board':args.board,'runtime':args.runtime}))
        return
    assert sha(args.qemu)==args.runtime_sha256, 'Runtime bytes differ'
    assert sha(args.rom_dir/'esp32c6-rom.bin')=='91db14c2419391308b108bac0b15fe3442a9c411cdd7f3fb088767c9fbc4b713', 'Exact C6 ROM differs'
    build=json.loads(args.build_receipt.read_text())
    assert build['build_status']=='PASS', 'Probe build has not passed'
    assert sha(args.image)==build['artifacts'][args.board]['merged.bin'], 'Firmware differs from frozen build receipt'
    probe_sha=sha(ROOT/'tests/firmware/esp32c6_gpio_irq/main/main.c')
    assert probe_sha==build['probe_files_sha256']['main/main.c'], 'Probe source changed since compilation'
    assert args.image.stat().st_size==(16 if args.board=='nesso' else 4)*1024*1024, 'Board flash size differs'
    out=args.out_dir.resolve()
    out.mkdir(parents=True,mode=0o700)
    shutil.copyfile(args.image,out/'flash.bin')
    (out/'driver.py').write_bytes(Path(__file__).read_bytes())
    report={'schema_version':1,'validation':'virtual-device validation','device':'nesso-n1' if args.board=='nesso' else 'nanoc6',
            'lane':'checked-in IDF regression; direct QEMU','service_idf_lane':'NOT RUN','status':'FAIL',
            'runtime_sha256':sha(args.qemu),'firmware_sha256':sha(args.image),'driver_sha256':sha(Path(__file__)),
            'build_receipt_sha256':sha(args.build_receipt),'sdk_commit':build['sdk_git_metadata']['head'],
            'probe_source_sha256':probe_sha,'rom_sha256':sha(args.rom_dir/'esp32c6-rom.bin'),
            'runtime_env':{'M5SW_C6_BOARD':'nesso-n1' if args.board=='nesso' else 'nanoc6'},
            'board_selection_source':'hw/riscv/esp32c6.c reads M5SW_C6_BOARD; not inferred from flash size',
            'checks':[],'observations':[],'cleanup':{}}
    proc=None;qmp=None;uart=None;drain=None;failure=None
    timeline=[]
    serial=out/'serial.log'
    def trace(kind,**data):
        timeline.append({'monotonic':time.monotonic(),'kind':kind,**data})
    def row_after(offset,stage,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            text=serial.read_bytes()[offset:].decode(errors='replace') if serial.exists() else ''
            for match in ROW.finditer(text):
                if match[1]==stage:
                    row={'stage':match[1],'pin':int(match[2]),'hits':int(match[3]),'level':int(match[4]),'raw':int(match[5],16),'cpu':int(match[6],16)}
                    report['observations'].append(row)
                    assert row['pin']==(3 if args.board=='nesso' else 9), 'Guest probe pin differs from selected board'
                    return row
            if proc.poll() is not None:raise RuntimeError('Guest exited before marker '+stage)
            time.sleep(.02)
        raise RuntimeError('Guest marker timeout '+stage)
    def command(value,stage=None):
        offset=serial.stat().st_size if serial.exists() else 0
        trace('uart-command',command=value)
        uart.sendall((value+'\n').encode())
        return row_after(offset,stage or {'snap':'SNAPSHOT','disable':'DISABLED','ack':'ACK','reset':'READY'}.get(value,'ARMED'),timeout=45 if value=='reset' else 20)
    def qmp_command(name,**values):
        result=qmp.cmd(name,**values);trace('qmp',command=name,arguments=values,result=result);return result
    def button(down):
        if args.board=='nano':qmp_command('qom-set',path='/machine',property='button-gpio9',value=down)
        else:qmp_command('input-send-event',events=[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':'a'}}}])
        time.sleep(.10)
    def touch(down):
        assert args.board=='nesso'
        qmp_command('input-send-event',events=pointer_events(67,160,(135,240),down))
        time.sleep(.10)
    def clear():
        button(False)
        command('ack')
        # ACK may create a rising/active-high IRQ. Observe it after one fixed,
        # recorded settle window, not by assuming printf races the CPU ISR.
        started=time.monotonic();time.sleep(.10)
        trace('ack-settle',requested_seconds=.10,actual_seconds=time.monotonic()-started)
        return command('snap')
    def check(name,row,*,hits=None,level=None,delta=None,before=None):
        passed=(hits is None or row['hits']==hits) and (level is None or row['level']==level)
        if delta is not None:passed=passed and row['hits']-before['hits']==delta
        report['checks'].append({'name':name,'pass':passed,'observed':row,
                                 'expected_hits':hits,'expected_level':level,'expected_delta':delta,
                                 'before_hits':before['hits'] if before else None})
        return row
    try:
        with tempfile.TemporaryDirectory(prefix='m5-c6-irq-') as socket_dir:
            qmp_path=Path(socket_dir)/'qmp.sock';uart_path=Path(socket_dir)/'uart.sock'
            argv=[str(args.qemu),'-M','esp32c6','-drive',f'file={out}/flash.bin,if=mtd,format=raw',
                  '-L',str(args.rom_dir),'-display','none','-no-shutdown',
                  '-chardev',f'socket,id=irq_uart,path={uart_path},server=on,wait=off,logfile={serial}',
                  '-serial','chardev:irq_uart','-serial',f'file:{out}/serial1.log',
                  '-qmp',f'unix:{qmp_path},server=on,wait=off']
            (out/'command-private.json').write_text(json.dumps(argv,indent=2)+'\n')
            log=(out/'qemu.log').open('wb')
            env={key:value for key,value in os.environ.items() if not key.startswith('M5SW_')}
            env.update(report['runtime_env'])
            proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and not uart_path.exists():
                if proc.poll() is not None:raise RuntimeError('Guest exited during startup')
                time.sleep(.02)
            uart=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);uart.connect(str(uart_path))
            def drain_uart():
                try:
                    while uart.recv(65536):pass
                except OSError:pass
            drain=threading.Thread(target=drain_uart,daemon=True);drain.start()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                try:qmp=QMP(qmp_path);break
                except OSError:time.sleep(.02)
            assert qmp is not None,'QMP unavailable'
            ready=row_after(0,'READY',45)
            check('cold-boot-ready',ready,hits=0,level=1)
            children=qmp_command('qom-list',path='/machine')['return']
            board_names={row['name'] for row in children if row['name'].startswith('nesso-')}
            report['actual_board_children']=sorted(board_names)
            assert ({'nesso-panel','nesso-pi4ioe1','nesso-pi4ioe2','nesso-bmi270'}<=board_names if args.board=='nesso' else not board_names), 'Actual QOM wiring does not match selected board'
            # Read-only source30 route evidence. Official C6 register base is
            # 0x60010000 and GPIO_PRO mapping register offset is 0x78.
            report['intmatrix_source30_route']=qmp_command('human-monitor-command',**{'command-line':'xp /1wx 0x60010078'})
            disabled=command('disable');button(True)
            check('disabled-source-pad',command('snap'),before=disabled,delta=0,level=0)
            button(True);check('disabled-held-quiet',command('snap'),before=disabled,delta=0,level=0)
            check('disabled-release-ack',clear(),before=disabled,delta=0,level=1)
            for mode,label in [(2,'falling'),(1,'rising'),(3,'both')]:
                clear();armed=command('arm '+str(mode));button(True)
                pressed=check(label+'-press',command('snap'),before=armed,delta=0 if mode==1 else 1,level=0)
                button(True);check(label+'-held-quiet',command('snap'),before=pressed,delta=0,level=0)
                released=clear()
                check(label+'-release-ack',released,before=pressed,delta=1 if mode in (1,3) else 0,level=1)
                command('disable')
            # The public ISR masks a held level; acknowledgement/source release
            # and a later public driver re-arm permit exactly one new callback.
            clear();armed=command('arm 4');button(True)
            low=check('low-level-isr',command('snap'),before=armed,delta=1,level=0)
            button(True);check('low-level-isr-mask',command('snap'),before=low,delta=0,level=0)
            clear();rearmed=command('arm 4');button(True)
            check('low-level-rearm',command('snap'),before=rearmed,delta=1,level=0)
            command('disable');clear();button(True);armed=command('arm 5')
            high=check('high-level-isr',clear(),before=armed,delta=1,level=1)
            check('high-level-isr-mask',command('snap'),before=high,delta=0,level=1)
            button(True);rearmed=command('arm 5')
            check('high-level-rearm',clear(),before=rearmed,delta=1,level=1)
            command('disable')
            if args.board=='nesso':
                clear();touch(False);armed=command('arm 3');button(True)
                pressed=check('shared-button-isr',command('snap'),before=armed,delta=1,level=0)
                touch(True);check('shared-touch-no-second-edge',command('snap'),before=pressed,delta=0,level=0)
                acked=command('ack');check('shared-button-ack-keeps-touch-low',acked,before=pressed,delta=0,level=0)
                button(False);touch(False)
                released=check('shared-final-release-isr',command('snap'),before=acked,delta=1,level=1)
                touch(True);check('touch-source-isr',command('snap'),before=released,delta=1,level=0)
                touch(False);command('disable');clear()
            restarted=command('reset');check('software-reset-ready',restarted,hits=0,level=1)
            armed=command('arm 2');button(True)
            check('software-reset-fresh-isr',command('snap'),before=armed,delta=1,level=0)
            command('disable');clear()
            if args.board=='nesso':
                qmp_command('screendump',filename=str(out/'frame-private.ppm'))
            report['functional_result']='PASS' if all(row['pass'] for row in report['checks']) else 'FAIL'
            report['status']=report['functional_result']
            if args.runtime=='baseline':
                negative_ok=all(row['pass'] for row in report['checks'] if row['expected_delta'] in (None,0))
                source_levels_ok=all(row['expected_level'] is None or row['observed']['level']==row['expected_level'] for row in report['checks'])
                report['baseline_missing_irq_reproduced']=report['functional_result']=='FAIL' and negative_ok and source_levels_ok and all(row['hits']==0 for row in report['observations'])
            # Graceful owned shutdown; full finally fencing still runs on error.
            qmp_command('quit');proc.wait(timeout=10)
    except Exception as error:
        failure=error;report['error']=str(error)
    finally:
        if proc and proc.poll() is None:
            try:
                if qmp:qmp.cmd('quit')
                proc.wait(timeout=10)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        if uart:
            try:uart.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            uart.close()
        if drain:drain.join(timeout=2)
        if qmp:
            try:qmp.sock.close()
            except OSError:pass
        report['cleanup']={'owned_process_reaped':proc is not None and proc.poll() is not None,'returncode':proc.returncode if proc else None,'uart_thread_stopped':not drain or not drain.is_alive()}
        cleanup_ok=report['cleanup']['owned_process_reaped'] and report['cleanup']['uart_thread_stopped']
        serial_text=serial.read_text(errors='replace') if serial.exists() else ''
        fatal_markers=re.findall(r'Guru Meditation|assert failed|abort\(\) was called|panic.ed|Interrupt wdt timeout|Task watchdog got triggered',serial_text,re.IGNORECASE)
        ready_count=sum(match[1]=='READY' for match in ROW.finditer(serial_text))
        reset_count=serial_text.count('C6_GPIO_IRQ_RESET_REQUEST')
        report['boot_integrity']={'ready_markers':ready_count,'requested_reset_markers':reset_count,'fatal_marker_count':len(fatal_markers)}
        boot_ok=ready_count==2 and reset_count==1 and not fatal_markers
        report['harness_status']='PASS' if failure is None and cleanup_ok and boot_ok else 'FAIL'
        if report['harness_status']!='PASS':
            report['status']='FAIL'
            if args.runtime=='baseline':report['baseline_missing_irq_reproduced']=False
        (out/'timeline-private.json').write_text(json.dumps(timeline,indent=2)+'\n')
        report['artifacts']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='flash.bin'}
        (out/'summary-safe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'board':args.board,'runtime':args.runtime,
                      'checks':len(report['checks']),'passed':sum(row['pass'] for row in report['checks']),
                      'baseline_missing_irq_reproduced':report.get('baseline_missing_irq_reproduced'),
                      'cleanup':report['cleanup'],'output_folder':out.name}))
    if report['harness_status']!='PASS' or args.runtime=='candidate' and report['status']!='PASS' or args.runtime=='baseline' and not report.get('baseline_missing_irq_reproduced'):raise SystemExit(1)

if __name__=='__main__':
    os.umask(0o077);main()
