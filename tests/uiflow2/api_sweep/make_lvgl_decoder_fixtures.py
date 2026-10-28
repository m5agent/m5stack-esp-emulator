#!/usr/bin/env python3
"""Create owned tiny decoder inputs and pin the official FS adapter source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fs-driver',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    expected='a65fcacf64fc8bcbd3201bbf9a3ae31239d0091349205f7a4752149601521b58'
    if hashlib.sha256(args.fs_driver.read_bytes()).hexdigest()!=expected:
        raise ValueError('official fs_driver.py must match the pinned UIFlow2 source')
    from PIL import Image
    args.out_dir.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(args.fs_driver,args.out_dir/'fs_driver.py')
    pixels=[(255,0,0),(0,255,0),(0,0,255),(255,255,255)]
    image=Image.new('RGB',(2,2));image.putdata(pixels)
    image.save(args.out_dir/'owned-2x2.bmp')
    image.convert('RGBA').save(args.out_dir/'owned-2x2.png')
    # One complete JPEG MCU avoids partial edge or chroma-subsampling ambiguity.
    Image.new('RGB',(8,8),(255,0,0)).save(args.out_dir/'owned-red-8x8.jpg',quality=100,subsampling=0,optimize=False,progressive=False)
    provenance={'source_commit':'3a86d8f611b3639cca755a933e01a5a829771ef1',
        'fs_driver_sha256':expected,'owned_inputs':{'bmp_png':{'size':[2,2],'pixels_rgb':pixels},
        'jpeg':{'size':[8,8],'source_rgb':[255,0,0],'quality':100,'subsampling':0,'progressive':False}},
        'pillow_version':Image.__version__}
    provenance['sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(args.out_dir.iterdir())if p.is_file()and p.name!='provenance.json'}
    (args.out_dir/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(provenance))


if __name__=='__main__':main()
