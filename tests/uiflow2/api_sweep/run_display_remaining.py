#!/usr/bin/env python3
"""Observe intermediate frames while a finite Display fixture owns the guest."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from check_ui_frame import check_frame
import run_guest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api', required=True)
    p.add_argument('--token-file', type=Path)
    p.add_argument('--device', choices=('cores3', 'cardputer-adv'), required=True)
    p.add_argument('--canvas', action='store_true')
    p.add_argument('--uiflow-root', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    prepare = a.out_dir.with_name(a.out_dir.name + '-source')
    prepare.mkdir(exist_ok=False)
    font_path = Path('m5stack/fs/system/common/font/Montserrat-Medium-18.vlw')
    asset = a.uiflow_root / font_path
    expected_font = '5779c663b395a6e9d2ce29d2261c08df52a6a1f2bf8ba73bf72075ea4d2766cd'
    if hashlib.sha256(asset.read_bytes()).hexdigest() != expected_font:
        raise ValueError('the official font fixture differs from the pinned upstream blob')
    (prepare / 'fixtures').mkdir()
    shutil.copyfile(asset, prepare / 'fixtures/contract-font.vlw')
    source = Path(__file__).with_name('probe_display_remaining.py').read_text()
    source = 'DISPLAY_CONTRACT_CANVAS = ' + repr(a.canvas) + '\n' + source
    (prepare / 'main.py').write_text(source)
    run_guest.save(prepare / 'provenance.json', {'source': 'https://github.com/m5stack/uiflow-micropython',
                   'commit': '3a86d8f611b3639cca755a933e01a5a829771ef1', 'font': str(font_path),
                   'font_sha256': hashlib.sha256(asset.read_bytes()).hexdigest()})
    observed, results = set(), []
    class FrameApi(run_guest.Api):
        sid = None
        transcript = ''
        def json(self, path, method='GET', payload=None, **kwargs):
            r = super().json(path, method, payload, **kwargs)
            if path == 'sessions' and method == 'POST':
                self.sid = r['session_id']
            if method == 'GET' and self.sid and path.startswith('sessions/' + self.sid + '/serial?'):
                self.transcript += r['data']
                for line in self.transcript.splitlines():
                    if not line.startswith('M5EMU_DISPLAY_FRAME ') or line in observed:
                        continue
                    observed.add(line)
                    item = json.loads(line.split(' ', 1)[1])
                    raw = self.raw('sessions/' + self.sid + '/frame.png')
                    name = item['method'] + '.png'
                    (a.out_dir / name).write_bytes(raw)
                    results.append(dict(item, frame=name, frame_sha256=hashlib.sha256(raw).hexdigest(),
                                        result=check_frame(raw, item['oracle'])))
                    run_guest.save(a.out_dir / 'intermediate-frame-oracles.json', results)
            return r
    run_guest.Api = FrameApi
    args = argparse.Namespace(api=a.api, token_file=a.token_file, device=a.device, runtime='qemu',
             source=prepare / 'main.py', fixture_dir=prepare / 'fixtures', out_dir=a.out_dir,
             done_marker='DISPLAY_REMAINING_DONE', timeout=240, prepare_timeout=600)
    return run_guest.run(args)

if __name__ == '__main__':
    raise SystemExit(main())
