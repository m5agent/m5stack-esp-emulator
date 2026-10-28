#!/usr/bin/env python3
"""Generate a finite stock-guest export audit for every system source owner."""
from pathlib import Path
import argparse
import json


BODY='''import sys,json,gc
DYNAMIC={"image.qrcode","image.QRCode","dl.DetectionResult","dl.RecognitionResult"}
def resolve(path):
 parts=path.split(".")
 for count in range(len(parts),0,-1):
  try:target=__import__(".".join(parts[:count]),None,None,["*"])
  except ImportError:continue
  for name in parts[count:]:
   try:target=getattr(target,name)
   except AttributeError as error:return None,"DYNAMIC_RETURN_TYPE"if path in DYNAMIC else"ABSENT",repr(error)
  return target,"PRESENT",None
 return None,"ABSENT","no importable module prefix"
for path in OWNERS:
 try:
  target,status,error=resolve(path)
  if status!="PRESENT":
   print("SYSTEM_EXPORT "+json.dumps({"path":path,"status":status,"error":error}))
  elif callable(target)and type(target).__name__!="type"and path.rsplit(".",1)[-1][0].isupper():
   print("SYSTEM_EXPORT "+json.dumps({"path":path,"status":"FACTORY_REQUIRES_INSTANCE","target_type":type(target).__name__}))
  else:
   names=set(dir(target));lazy=getattr(target,"_attrs",None)
   if isinstance(lazy,dict):names.update(lazy)
   members=[]
   for name in sorted(names):
    if name.startswith("_"):continue
    try:
     member=getattr(target,name)
     members.append([name,type(member).__name__,callable(member)])
    except Exception as error:members.append([name,"READ_ERROR",None])
   print("SYSTEM_EXPORT "+json.dumps({"path":path,"count":len(members),"members":members}))
  target=None
  gc.collect()
 except Exception as error:
  print("SYSTEM_EXPORT "+json.dumps({"path":path,"status":"REFLECTION_ERROR","error":repr(error)}))
print("SYSTEM_OWNER_REFLECTION_DONE")
'''


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory",type=Path,default=Path(__file__).with_name("inventory_system.source.json"))
    parser.add_argument("--owner",action="append",default=[])
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    inventory=json.loads(args.inventory.read_text())
    owners=sorted(set(args.owner)or {row["api"]if row["kind"]=="constructor"else row["api"].rsplit(".",1)[0]
        for row in inventory["entries"]if row["scope"]=="system-communication"})
    args.out.write_text("OWNERS="+repr(owners)+"\n"+BODY,encoding="utf-8")
    print(json.dumps({"owners":len(owners),"out":str(args.out)}))
