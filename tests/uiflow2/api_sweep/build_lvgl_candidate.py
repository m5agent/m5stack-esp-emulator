#!/usr/bin/env python3
"""Independently relink pinned LVGL source corrections without mutating the SDK.

This incremental fixture copies and hash-checks both original source files,
regenerates the binding from the cached preprocessed declaration, rebuilds two
objects in a cloned main archive, and changes only the application partition.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shlex,shutil,subprocess,time
from pathlib import Path
from build_rawbuf_candidate import ROOT,digest,segment
from firmware_analysis import parse_partition_table


def build(args):
    args.out_dir.mkdir(parents=True,exist_ok=False);out=args.out_dir.resolve()
    source=args.build_root/'uiflow';build=source/'m5stack/build-M5STACK_CoreS3'
    binding=source/'m5stack/cmodules/lv_binding_micropython'
    receipt={'kind':'incremental-candidate-firmware','cold_build':False,'status':'BUILDING','corrections':[],'stages':[]}
    def save(): (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    def run(label,argv,stdout=None,env=None):
        start=time.monotonic()
        with (out/(label+'.log')).open('wb') as log:
            r=subprocess.run(argv,cwd=build,env=env,stdout=stdout or log,stderr=log,timeout=300)
        receipt['stages'].append({'label':label,'argv':argv,'exit_code':r.returncode,'seconds':round(time.monotonic()-start,3)});save()
        if r.returncode:raise RuntimeError(label+' failed; inspect retained log')
    corrected={}
    manifests=[ROOT/'patches/uiflow2-api'/(name+'.json') for name in ['0005-lvgl-roller-final-option','0006-lvgl-python-event-identity']]+args.extra_manifest
    for manifest_path in manifests:
        manifest=json.loads(manifest_path.read_text());original=source/manifest['path']
        if digest(original)!=manifest['preimage_sha256']:raise ValueError('source preimage mismatch')
        copied=out/'source'/manifest['path']
        if original not in corrected:
            copied.parent.mkdir(parents=True,exist_ok=True);copied.write_bytes(original.read_bytes())
        current=digest(copied)
        expected=manifest['candidate_sha256'] if current==manifest['preimage_sha256'] else manifest.get('stack_candidate_sha256') if current==manifest.get('stack_preimage_sha256') else None
        if expected is None:raise ValueError('explicit patch stack preimage mismatch')
        patch=manifest_path.with_suffix('.patch').resolve()
        patch_env=dict(os.environ);patch_env['GIT_CEILING_DIRECTORIES']=str(out)
        for command in [['git','apply','--check',str(patch)],['git','apply',str(patch)],['git','apply','--reverse','--check',str(patch)]]:
            subprocess.run(command,cwd=out/'source',env=patch_env,check=True,capture_output=True)
        if digest(copied)!=expected:raise ValueError('patched source digest mismatch')
        receipt['corrections'].append({**manifest,'patch_sha256':digest(patch)});corrected[original]=copied
    receipt['cached_preprocessed_sha256']=digest(build/'lv_mp.c.pp')
    receipt['cached_binding_sha256']=digest(build/'lv_mp.c')
    ninja=args.build_root/'build-tools/ninja'
    lines=subprocess.check_output([str(ninja),'-C',str(build),'-t','commands','lv_mp.c'],text=True).splitlines()
    words=shlex.split(next(x for x in reversed(lines) if 'gen_mpy.py' in x))
    i=next(i for i,x in enumerate(words) if x.endswith('/idf-python-env/bin/python'));argv=words[i:words.index('>')]
    generator=binding/'gen/gen_mpy.py';argv[1]=str(corrected[generator]);argv[argv.index('-MD')+1]=str(out/'lv_mp.c.json')
    env=dict(os.environ);env['PYTHONPATH']=str(binding/'pycparser')
    generated=out/'lv_mp.c'
    with generated.open('wb') as f:run('generate-binding',argv,stdout=f,env=env)
    commands=json.loads((build/'compile_commands.json').read_text());objects=[]
    units=[(original.name,copied) for original,copied in corrected.items()
           if original.suffix=='.c' and original.is_relative_to(binding/'lvgl')]
    units.append(('lv_mp.c',generated))
    if len({name for name,_source in units})!=len(units):raise ValueError('corrected source basenames are ambiguous')
    for suffix,new_source in units:
        matching=[x for x in commands if x['file'].endswith('/'+suffix)]
        entry=next((x for x in matching if x['output'].startswith('CMakeFiles/micropython.elf.dir/')),matching[0]);original=Path(entry['file']);argv=shlex.split(entry['command']);obj=out/(suffix+'.obj')
        argv[argv.index('-o')+1]=str(obj);argv[argv.index('-c')+1]=str(new_source);argv+=['-I',str(original.parent)]
        run('compile-'+suffix,argv);objects.append(obj)
    original_library=build/'esp-idf/main/libmain.a';library=out/'libmain.a';shutil.copy2(original_library,library);receipt['cached_library_sha256']=digest(original_library)
    compiler=Path(shlex.split(next(x for x in commands if x['file'].endswith('/lv_roller.c'))['command'])[0]);ar=compiler.with_name(compiler.name.removesuffix('gcc')+'ar')
    members=subprocess.check_output([str(ar),'t',str(library)],text=True).splitlines()
    if any(members.count(obj.name)!=1 for obj in objects):raise ValueError('archive member is ambiguous')
    run('archive',[str(ar),'r',str(library),*[str(x) for x in objects]])
    lines=subprocess.check_output([str(ninja),'-C',str(build),'-t','commands','micropython.elf'],text=True).splitlines();argv=segment(next(x for x in reversed(lines) if ' -o micropython.elf ' in x),'-o')
    elf=out/'micropython.elf';argv[argv.index('-o')+1]=str(elf)
    direct_replacements=[]
    for i,w in enumerate(argv):
        if w=='esp-idf/main/libmain.a':argv[i]=str(library)
        elif any(w.endswith('/'+obj.name) for obj in objects):
            obj=next(obj for obj in objects if w.endswith('/'+obj.name));argv[i]=str(obj);direct_replacements.append(w)
        elif w.startswith('-Wl,--Map='):argv[i]='-Wl,--Map='+str(out/'micropython.map')
        elif w.startswith('-Wl,--dependency-file='):argv[i]='-Wl,--dependency-file='+str(out/'micropython.d')
    if len(direct_replacements)!=len(objects):raise ValueError('direct linked object coverage is ambiguous')
    receipt['direct_object_replacements']=direct_replacements
    run('link',argv)
    lines=subprocess.check_output([str(ninja),'-C',str(build),'-t','commands','gen_project_binary'],text=True).splitlines();argv=segment(next(x for x in reversed(lines) if 'elf2image' in x),'elf2image')
    binary=out/'micropython.bin';argv[argv.index('-o')+1]=str(binary);argv=[str(elf) if w==str(build/'micropython.elf') else w for w in argv];run('elf2image',argv)
    base=args.base_image.read_bytes();table=parse_partition_table(base,image_size=16<<20);apps=[x for x in table['partitions'] if x['type']==0]
    if not table['valid'] or len(apps)!=1:raise ValueError('one valid app partition required')
    app=apps[0];old=(build/'micropython.bin').read_bytes();start=app['offset'];end=start+app['size']
    if base[start:start+len(old)]!=old:raise ValueError('base is not bound to cached application')
    raw=binary.read_bytes()
    if len(raw)>app['size']:raise ValueError('candidate exceeds partition')
    image=bytearray(base);image[start:end]=b'\xff'*app['size'];image[start:start+len(raw)]=raw
    target=out/'candidate-full-flash.bin';target.write_bytes(image)
    if image==base:raise ValueError('candidate application is unchanged after corrections')
    receipt.update(status='BUILT_NOT_EXECUTED',base_sha256=hashlib.sha256(base).hexdigest(),candidate_full_flash_sha256=digest(target),candidate_app_sha256=digest(binary),candidate_binding_sha256=digest(generated),outside_application_unchanged=image[:start]==base[:start] and image[end:]==base[end:],original_sources_unchanged=all(digest(source/x['path'])==x['preimage_sha256'] for x in receipt['corrections']),original_library_unchanged=digest(original_library)==receipt['cached_library_sha256'],original_binding_unchanged=digest(build/'lv_mp.c')==receipt['cached_binding_sha256']);save()
    print(json.dumps({k:receipt[k] for k in ['status','candidate_full_flash_sha256','outside_application_unchanged','original_sources_unchanged','original_library_unchanged','original_binding_unchanged']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-root',type=Path,required=True);p.add_argument('--base-image',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--extra-manifest',type=Path,action='append',default=[]);build(p.parse_args())
