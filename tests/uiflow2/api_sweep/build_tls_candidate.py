#!/usr/bin/env python3
"""Relink one hash-pinned UIFlow main object without changing cached inputs."""
from __future__ import annotations
import argparse,hashlib,json,shlex,shutil,subprocess,time
from pathlib import Path
from build_rawbuf_candidate import ROOT,digest,segment
from firmware_analysis import parse_partition_table


def build(args):
    args.out_dir.mkdir(parents=True,exist_ok=False);out=args.out_dir.resolve()
    source=args.build_root/'uiflow';build=source/'m5stack'/('build-'+args.board)
    manifest=json.loads((ROOT/'patches/uiflow2-api/0010-mbedtls-epoch.json').read_text())
    original=source/manifest['path'];patch=ROOT/'patches/uiflow2-api/0010-mbedtls-epoch.patch'
    if digest(original)!=manifest['preimage_sha256']:raise ValueError('source preimage mismatch')
    copied=out/'source'/manifest['path'];copied.parent.mkdir(parents=True);copied.write_bytes(original.read_bytes())
    for command in (['git','apply','--check',str(patch)],['git','apply',str(patch)],['git','apply','--reverse','--check',str(patch)]):
        subprocess.run(command,cwd=out/'source',check=True,capture_output=True)
    if digest(copied)!=manifest['candidate_sha256']:raise ValueError('patched source mismatch')
    base=args.base_image.read_bytes();table=parse_partition_table(base,image_size=16<<20)
    apps=[entry for entry in table['partitions']if entry['type']==0]
    if not table['valid']or len(apps)!=1:raise ValueError('one valid application partition required')
    app=apps[0];old=(build/'micropython.bin').read_bytes();start=app['offset'];end=start+app['size']
    if base[start:start+len(old)]!=old:raise ValueError('preimage full-flash image does not match cached application')
    receipt={'status':'BUILDING','kind':'incremental-candidate-firmware','cold_build':False,
        'source_correction':manifest,'patch_sha256':digest(patch),'base_sha256':hashlib.sha256(base).hexdigest(),
        'cached_app_sha256':hashlib.sha256(old).hexdigest(),'cached_elf_sha256':digest(build/'micropython.elf'),
        'application_partition':app,'stages':[]}
    def save():(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    def run(label,argv):
        began=time.monotonic()
        with (out/(label+'.log')).open('wb')as log:
            result=subprocess.run(argv,cwd=build,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        receipt['stages'].append({'label':label,'argv':argv,'exit_code':result.returncode,'seconds':round(time.monotonic()-began,3)});save()
        if result.returncode:raise RuntimeError(label+' failed; inspect retained log')
    save();commands=json.loads((build/'compile_commands.json').read_text())
    entry=next(row for row in commands if row['file']==str(original));argv=shlex.split(entry['command'])
    obj=out/'main.c.obj';argv[argv.index('-o')+1]=str(obj);argv[argv.index('-c')+1]=str(copied)
    argv+=['-I',str(original.parent)];run('compile-main',argv)
    original_library=build/'esp-idf/main/libmain.a';library=out/'libmain.a';shutil.copy2(original_library,library)
    receipt['cached_library_sha256']=digest(original_library)
    compiler=Path(argv[0]);ar=compiler.with_name(compiler.name.removesuffix('gcc')+'ar')
    members=subprocess.check_output([str(ar),'t',str(library)],text=True).splitlines()
    if members.count(obj.name)!=1:raise ValueError('main archive member is ambiguous')
    run('archive',[str(ar),'r',str(library),str(obj)])
    ninja=args.build_root/'build-tools/ninja'
    lines=subprocess.check_output([str(ninja),'-C',str(build),'-t','commands','micropython.elf'],text=True).splitlines()
    argv=segment(next(row for row in reversed(lines)if ' -o micropython.elf 'in row),'-o')
    elf=out/'micropython.elf';argv[argv.index('-o')+1]=str(elf);direct=[]
    for index,word in enumerate(argv):
        if word=='esp-idf/main/libmain.a':argv[index]=str(library)
        elif word==entry['output']:argv[index]=str(obj);direct.append(word)
        elif word.startswith('-Wl,--Map='):argv[index]='-Wl,--Map='+str(out/'micropython.map')
        elif word.startswith('-Wl,--dependency-file='):argv[index]='-Wl,--dependency-file='+str(out/'micropython.d')
    receipt['direct_object_replacements']=direct;run('link',argv)
    lines=subprocess.check_output([str(ninja),'-C',str(build),'-t','commands','gen_project_binary'],text=True).splitlines()
    argv=segment(next(row for row in reversed(lines)if 'elf2image'in row),'elf2image')
    binary=out/'micropython.bin';argv[argv.index('-o')+1]=str(binary)
    argv=[str(elf)if word==str(build/'micropython.elf')else word for word in argv];run('elf2image',argv)
    raw=binary.read_bytes()
    if len(raw)>app['size']:raise ValueError('candidate exceeds application partition')
    merged=bytearray(base);merged[start:end]=b'\xff'*app['size'];merged[start:start+len(raw)]=raw
    if merged==base:raise ValueError('candidate is unchanged after correction')
    target=out/'candidate-full-flash.bin';target.write_bytes(merged)
    receipt.update(status='BUILT_NOT_EXECUTED',candidate_full_flash_sha256=digest(target),candidate_app_sha256=digest(binary),
        candidate_elf_sha256=digest(elf),outside_application_unchanged=merged[:start]==base[:start]and merged[end:]==base[end:],
        original_source_unchanged=digest(original)==manifest['preimage_sha256'],
        original_library_unchanged=digest(original_library)==receipt['cached_library_sha256'])
    save();print(json.dumps({key:receipt[key]for key in ('status','candidate_full_flash_sha256','outside_application_unchanged','original_source_unchanged','original_library_unchanged')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root',type=Path,required=True)
    parser.add_argument('--board',choices=('M5STACK_CoreS3','M5STACK_Cardputer_Adv'),default='M5STACK_CoreS3')
    parser.add_argument('--base-image',type=Path,required=True);parser.add_argument('--out-dir',type=Path,required=True)
    build(parser.parse_args())
