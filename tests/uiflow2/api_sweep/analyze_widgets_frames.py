"""Supplement warm Widgets calls with geometry and disappearance frame oracles.

Glyph scaling compares identical text and font in the constructor/control frame.
This supplements the report; it never changes state results or stock failures.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from check_ui_frame import check_frame


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(root, target):
    directory=root/('Widgets-'+target)
    report=json.loads((directory/'report.json').read_text())
    return report,{case.get('method'): (directory/case['label'],case) for case in report['cases']}


def bounds(path, box):
    image=Image.open(path).convert('RGB')
    expected=(243,247,248)
    points=[(x,y) for y in range(box[1],box[3]) for x in range(box[0],box[2])
            if max(abs(a-b) for a,b in zip(image.getpixel((x,y)),expected))<=8]
    return ([min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1] if points else None)


def analyze(root, targets):
    rows=[]
    for target in targets:
        report,group=cases(root,target)
        for method in ({'Label':['setSize'],'Title':['setSize','setTextCursor'],'QRCode':['setVisible']}[target]):
            directory,case=group[method]
            source=(directory/'main.py').read_text()
            row={'api_target':'M5.Widgets.'+target,'method':method,'argument_domain':None,
                 'session_id':report['session_id'],'firmware_sha256':report['firmware_sha256'],
                 'runtime_binary_sha256':report['runtime_binary_sha256'],'execution_id':case['execution_id'],
                 'source_sha256':case['source_sha256'],'frame_sha256':digest(directory/'frame.png'),
                 'report':str(directory.parent/'report.json')}
            image=Image.open(directory/'frame.png')
            width,height=image.size
            if target=='Label':
                assert "obj.setSize(1.5)" in source
                baseline=group[None][0]/'frame.png'
                before=bounds(baseline,[20,55,width,min(150,height)])
                after=bounds(directory/'frame.png',[20,55,width,min(150,height)])
                ratios=([float(after[2]-after[0])/(before[2]-before[0]),float(after[3]-after[1])/(before[3]-before[1])] if before and after else [])
                row.update(argument_domain='text-size-1.5-geometry',status='FRAME_PASS' if len(ratios)==2 and all(1.35<=r<=1.65 for r in ratios) else 'FAIL',
                           oracle='same glyph/font foreground width and height scale by 1.5 within raster tolerance',before_bounds=before,after_bounds=after,ratios=ratios,control_frame_sha256=digest(baseline))
            elif target=='Title' and method=='setSize':
                assert 'obj.setSize(40)' in source
                oracle={'kind':'pixels','points':[[2,35,0x304850],[2,41,0x0B1014]]}
                row.update(argument_domain='integer-height-40',oracle=oracle,**check_frame((directory/'frame.png').read_bytes(),oracle,8))
            elif target=='Title':
                assert 'obj.setTextCursor(28)' in source
                baseline=group[None][0]/'frame.png'
                before=bounds(baseline,[0,0,width,30]);after=bounds(directory/'frame.png',[0,0,width,30])
                ok=bool(before and after and after[0]-before[0]==20 and after[2]-before[2]==20 and after[1]==before[1] and after[3]==before[3])
                row.update(argument_domain='text-x-8-to-28',status='FRAME_PASS' if ok else 'FAIL',oracle='same text shifts 20 pixels horizontally with identical extent and vertical position',before_bounds=before,after_bounds=after,control_frame_sha256=digest(baseline))
            else:
                assert 'obj.setVisible(False)' in source
                x,y,size=(40,60,120) if height>=200 else (40,30,80)
                oracle={'kind':'color_region','rgb':0x0B1014,'box':[x,y,x+size,y+size],'minimum':size*size}
                row.update(argument_domain='hidden-entire-original-region',oracle=oracle,**check_frame((directory/'frame.png').read_bytes(),oracle,8))
            rows.append(row)
    return {'schema_version':1,'validation':'virtual-device validation','hardware_validation':'NOT RUN','root':str(root),'results':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--target',action='append',choices=('Label','Title','QRCode'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=analyze(args.root,args.target or ['Label','Title','QRCode'])
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([(row['api_target'],row['method'],row['status']) for row in result['results']]))
