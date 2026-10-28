#!/usr/bin/env python3
"""Opt-in Emscripten 3.1.50 Fiber/SjLj reproducer; never runs a guest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emcc', default='emcc')
    parser.add_argument('--ffi-include', type=Path, required=True)
    parser.add_argument('--ffi-library', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    if out.exists():
        parser.error('--out-dir must be a new directory; prior results are immutable')
    version = subprocess.check_output([args.emcc, '--version'], text=True)
    if not re.search(r'\b3\.1\.50\b', version):
        parser.error('this reproducer pins Emscripten 3.1.50')
    library = args.ffi_library.resolve()
    include = args.ffi_include.resolve()
    source = Path(__file__).resolve().with_name('repro.c')
    if not library.is_file() or not (include / 'ffi.h').is_file():
        parser.error('provide the unmodified libffi 3.4.7 wasm32-pthread archive and headers')
    out.mkdir(parents=True)
    receipt = {'schema_version': 1, 'status': 'BUILDING', 'sdk': '3.1.50',
               'category': 'no-guest-fiber-sjlj-reproducer',
               'build_script_sha256': sha(Path(__file__).resolve()),
               'sdk_version_output': version,
               'libffi_contract': 'unmodified 3.4.7 wasm32 pthread, supplied by caller',
               'source_sha256': sha(source), 'libffi_sha256': sha(library),
               'profiles': {}, 'commands': {}, 'artifacts': {}}
    try:
        for name, restore, stack in [('baseline-2m', 0, '2MB'),
                                     ('compat-2m', 1, '2MB'),
                                     ('compat-64k', 1, '64KB')]:
            target = out / 'site' / name
            target.mkdir(parents=True)
            receipt['profiles'][name] = {
                'restore_after_longjmp': restore,
                'stack_size': stack,
                'pthread_stack_size': stack,
            }
            command = [args.emcc, str(source), '-I' + str(include), str(library),
                       '-O2', '-pthread', '-DWASM_BIGINT', '-fexceptions',
                       '-sWASM_BIGINT=1', '-sASYNCIFY=1',
                       '-sASYNCIFY_IMPORTS=ffi_call_js', '-sPROXY_TO_PTHREAD=1',
                       '-sEXIT_RUNTIME=1', '-sSTACK_SIZE=' + stack,
                       '-sDEFAULT_PTHREAD_STACK_SIZE=' + stack,
                       '-sSTACK_OVERFLOW_CHECK=2', '-sASSERTIONS=2',
                       '-sINITIAL_MEMORY=32MB',
                       '-DM5_RESTORE_AFTER_LONGJMP=' + str(restore),
                       '-o', str(target / 'repro.js')]
            receipt['commands'][name] = command
            with (out / (name + '-build.log')).open('wb') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'{name} compilation failed; see its build log')
            (target / 'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Fiber/SjLj C reproducer</title><script>
globalThis.probe={output:[],errors:[],exitCode:null,initial:{isolated:crossOriginIsolated,sab:typeof SharedArrayBuffer}};
var Module={print(text){probe.output.push(text);},printErr(text){probe.errors.push(text);},onAbort(text){probe.abort=String(text);},onExit(code){probe.exitCode=code;}};
</script><script src="repro.js"></script>''')
            receipt['artifacts'][name] = {
                filename: {'size': (target / filename).stat().st_size,
                           'sha256': sha(target / filename)}
                for filename in ['index.html', 'repro.js', 'repro.wasm', 'repro.worker.js']}
        if sha(library) != receipt['libffi_sha256']:
            raise RuntimeError('libffi input changed during build')
        if sha(source) != receipt['source_sha256']:
            raise RuntimeError('reproducer source changed during build')
        receipt['status'] = 'PASS'
    except BaseException as error:
        receipt['status'] = 'FAIL'
        receipt['error'] = str(error)
        raise
    finally:
        (out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        (out / 'commands.sh').write_text('#!/bin/sh\nset -eu\n' + '\n'.join(
            shlex.join(command) for command in receipt['commands'].values()) + '\n')
    print(json.dumps({'status': receipt['status'], 'out_dir': str(out)}))


if __name__ == '__main__':
    main()
