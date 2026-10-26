"""Observe a real guest's main-MPY importer; never infer it from host metadata.

The caller owns the console and admits the probe only during controlled boot.
The fixed passive canary is ordinary official-compiler bytecode. Caller
bytecode is never rewritten or instrumented. This is observed compatibility,
not cryptographic firmware attestation or a hardware measurement.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid

from micropython_repl import RawREPL
from guest_console import GuestConsoleError
from uiflow_runtime import UIFlowRuntimeError

LOADER = "micropython-override-main-v1"
PROBE_KIND = "uiflow-main-mpy-canary-v1"
PROBE_ROOT = "/flash/.m5-loader-probe-"
CANARY_SOURCE = """import sys
_state = sys.modules['__m5_main_loader_canary_state__']
_module = sys.modules.get('main')
_state['observed'] = {'if_main': __name__ == '__main__', 'name': __name__, 'file': getattr(_module, '__file__', None), 'real_main_name': getattr(_module, '__main__', None), 'main_id': id(_module), 'sys_main_id': id(sys.modules.get('__main__')), 'import_main_id': id(__import__('__main__')), 'nonce': _state['nonce']}
_state['entered'] += 1
"""
CANARY_BYTES = base64.b64decode(
    "TQYAHxUEMG01LW1haW4tbG9hZGVyLWNhbmFyeS5weQAPBnN5cwAObW9kdWxlcwCBLYFjKw5pZl9tYWluAAhuYW1lABBfX2ZpbGVfXwAIZmlsZQAObWFpbl9pZAAKbm9uY2UAEG9ic2VydmVkAA5lbnRlcmVkAAxfc3RhdGUADl9tb2R1bGUAL4EvgTcUX19pbXBvcnRfXwAFH19fbTVfbWFpbl9sb2FkZXJfY2FuYXJ5X3N0YXRlX18ABQ5yZWFsX21haW5fbmFtZQAFC3N5c19tYWluX2lkAAUOaW1wb3J0X21haW5faWQAiFggDgEmKSwfHz2AURsCFgIRAhMDIwBVFg8RAhMDFAQQBTYBFhAsCBEREAbZEAdiEREQCGIREhEQEAlRNAMQCmIREhEQEAZRNAMjAWIRExEQNAEQC2IRExECEwMUBBAGNgE0ASMCYhETERQQBjQBNAEjA2IRDxAMVRAMYhEPEA1WEQ8QDlhVgeVbVlFj"
)
CANARY_SHA256 = "0713a25c1bdfb35a2ba0ebf431ec1ccccaa32846eb0dd74f3ebb230ffeac9420"
CANARY_SOURCE_SHA256 = "e21b73a791266cea38d5c2050e0d4ae48180f4e3908bf748db4b10995908ed78"
CANARY_COMPILER_SHA256 = "c8646ebb97047c1c56a9d164474729a1bf13508e49d4cd3b1e5c6f00c509911b"
CANARY_RECIPE = {
    "micropython_commit": "78ff170de9e32c79db6e64d3e33d2bd60002bdcd",
    "compiler_sha256": CANARY_COMPILER_SHA256,
    "argv": ["mpy-cross", "-s", "m5-main-loader-canary.py", "-o", "canary.mpy", "canary.py"],
    "emitter": "official default pure bytecode; no native/viper or instrumentation",
    "source_sha256": CANARY_SOURCE_SHA256, "bytecode_sha256": CANARY_SHA256,
}


def main_loader_verified(record) -> bool:
    """Validate the core observed proof; session identity is the caller's gate."""
    if not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        return False
    if record.get("status") != "verified" or record.get("mpy_entrypoint") is not True or record.get("loader") != LOADER:
        return False
    if type(record.get("mpy")) is not int or record["mpy"] < 0 or record["mpy"] & 255 != CANARY_BYTES[1] or type(record.get("small_int_bits")) is not int or record["small_int_bits"] != 31:
        return False
    probe = record.get("probe")
    if not isinstance(probe, dict):
        return False
    if probe.get("error") is not None:
        return False
    nonce = probe.get("nonce")
    if not isinstance(nonce, str) or re.fullmatch("[0-9a-f]{32}", nonce) is None:
        return False
    if any(probe.get(key) != value for key, value in {
        "kind": PROBE_KIND, "status": "PASS", "canary_sha256": CANARY_SHA256,
        "source_sha256": CANARY_SOURCE_SHA256, "compiler_sha256": CANARY_COMPILER_SHA256,
        "file_sha256": CANARY_SHA256,
    }.items()) or any(probe.get(key) is not True for key in ("owner_restored", "cleanup_complete", "body_entered")):
        return False
    if type(probe.get("file_bytes")) is not int or probe["file_bytes"] != len(CANARY_BYTES):
        return False
    owner = probe.get("owner_before_id")
    if type(owner) is not int or owner <= 0 or type(probe.get("owner_after_id")) is not int or probe["owner_after_id"] != owner:
        return False
    actual = probe.get("actual_identity")
    if not isinstance(actual, dict) or actual.get("if_main") is not True:
        return False
    if any(actual.get(key) != value for key, value in {
        "name": "__main__", "file": PROBE_ROOT + nonce + "/main.mpy", "real_main_name": "main", "nonce": nonce,
    }.items()):
        return False
    module_id = actual.get("main_id")
    return (type(module_id) is int and module_id > 0 and module_id != owner
            and all(type(actual.get(key)) is int and actual[key] == module_id for key in ("sys_main_id", "import_main_id")))


def require_main_loader(record) -> dict:
    if not main_loader_verified(record):
        raise UIFlowRuntimeError("program_mpy_entrypoint_unsupported", "main.mpy requires a verified same-guest run-as-main loader capability")
    return record


def _probe_source(nonce: str, marker: str) -> str:
    directory = PROBE_ROOT + nonce
    encoded = base64.b64encode(CANARY_BYTES).decode("ascii")
    return f'''import sys,os,json,hashlib,binascii
_m5_cap_owner=__import__('__main__')
_m5_cap_cwd=os.getcwd()
_m5_cap_path=sys.path[:]
_m5_cap_saved={{}}
for _m5_cap_name in ('main','__main__','__m5_main_loader_canary_state__'):
 _m5_cap_saved[_m5_cap_name]=(_m5_cap_name in sys.modules,sys.modules.get(_m5_cap_name))
_m5_cap_state={{'nonce':{nonce!r},'entered':0,'observed':None}}
_m5_cap_result={{'owner_before_id':id(_m5_cap_owner),'mpy':getattr(sys.implementation,'_mpy',None),'small_int_bits':0,'error':None,'file_sha256':None,'file_bytes':None}}
_m5_cap_maxint=sys.maxsize
while _m5_cap_maxint:
 _m5_cap_result['small_int_bits']+=1
 _m5_cap_maxint >>= 1
_m5_cap_created=False
try:
 if type(_m5_cap_result['mpy']) is int and _m5_cap_result['mpy'] & 255 == {CANARY_BYTES[1]} and _m5_cap_result['small_int_bits']==31:
  os.mkdir({directory!r})
  _m5_cap_created=True
  with open({directory + '/main.mpy'!r},'wb') as _m5_cap_file:
   assert _m5_cap_file.write(binascii.a2b_base64({encoded!r}))=={len(CANARY_BYTES)}
  os.sync()
  with open({directory + '/main.mpy'!r},'rb') as _m5_cap_file:
   _m5_cap_data=_m5_cap_file.read({len(CANARY_BYTES) + 1})
  _m5_cap_result['file_bytes']=len(_m5_cap_data)
  _m5_cap_result['file_sha256']=binascii.hexlify(hashlib.sha256(_m5_cap_data).digest()).decode()
  assert _m5_cap_result['file_bytes']=={len(CANARY_BYTES)} and _m5_cap_result['file_sha256']=={CANARY_SHA256!r}
  sys.modules['__m5_main_loader_canary_state__']=_m5_cap_state
  sys.modules.pop('main',None)
  os.chdir({directory!r})
  sys.path[:]=[{directory!r}]+[p for p in _m5_cap_path if p!={directory!r}]
  _m5_cap_module=__import__('main',None,None,False,0)
except BaseException as _m5_cap_error:
 _m5_cap_result['error']={{'type':type(_m5_cap_error).__name__,'message':str(_m5_cap_error)}}
finally:
 _m5_cap_result['body_entered']=_m5_cap_state['entered']==1
 _m5_cap_result['actual_identity']=_m5_cap_state['observed']
 _m5_cap_result['cleanup_complete']=False
 try:
  os.chdir(_m5_cap_cwd)
  sys.path[:]=_m5_cap_path
  for _m5_cap_name,_m5_cap_pair in _m5_cap_saved.items():
   if _m5_cap_pair[0]:
    sys.modules[_m5_cap_name]=_m5_cap_pair[1]
   else:
    sys.modules.pop(_m5_cap_name,None)
  _m5_cap_result['owner_after_id']=id(__import__('__main__'))
  _m5_cap_result['owner_restored']=__import__('__main__') is _m5_cap_owner and os.getcwd()==_m5_cap_cwd and sys.path==_m5_cap_path and all((_m5_cap_name in sys.modules)==_m5_cap_pair[0] and (not _m5_cap_pair[0] or sys.modules[_m5_cap_name] is _m5_cap_pair[1]) for _m5_cap_name,_m5_cap_pair in _m5_cap_saved.items())
  if _m5_cap_created:
   os.remove({directory + '/main.mpy'!r})
   os.rmdir({directory!r})
  _m5_cap_result['cleanup_complete']=True
 except BaseException as _m5_cap_restore_error:
  _m5_cap_result['restore_error']={{'type':type(_m5_cap_restore_error).__name__,'message':str(_m5_cap_restore_error)}}
print({marker!r}+json.dumps(_m5_cap_result))
'''


def probe_main_loader(console, *, timeout: float, cancelled, on_synchronized=None) -> dict:
    """Finite controlled-boot probe. False semantics is safe; lost control is not."""
    if hashlib.sha256(CANARY_BYTES).hexdigest() != CANARY_SHA256 or hashlib.sha256(CANARY_SOURCE.encode()).hexdigest() != CANARY_SOURCE_SHA256:
        raise UIFlowRuntimeError("program_main_loader_probe_failed", "fixed canary provenance differs")
    nonce = uuid.uuid4().hex
    marker = "__M5_LOADER_" + nonce + ":"
    client = RawREPL(console, timeout=timeout, cancelled=cancelled)
    try:
        client.synchronize(on_synchronized)
        response = client.execute(_probe_source(nonce, marker), max_output=16384)
    except GuestConsoleError as error:
        raise UIFlowRuntimeError("program_cancelled" if error.code == "console_cancelled" else "program_main_loader_probe_failed", "guest console lost control during the loader probe") from error
    try:
        if not isinstance(response["stdout"], (bytes, bytearray)):
            raise ValueError("canary receipt is not bytes")
        lines = [line[len(marker):] for line in response["stdout"].decode("utf-8").splitlines() if line.startswith(marker)]
        if len(lines) != 1:
            raise ValueError("not one canary receipt")
        observed = json.loads(lines[0])
        if not isinstance(observed, dict):
            raise ValueError("invalid canary receipt")
    except (UnicodeError, ValueError, TypeError, KeyError) as error:
        raise UIFlowRuntimeError("program_main_loader_probe_failed", "guest did not return one valid canary receipt") from error
    owner = observed.get("owner_before_id")
    if observed.get("owner_restored") is not True or observed.get("cleanup_complete") is not True or observed.get("restore_error") is not None or type(owner) is not int or owner <= 0 or type(observed.get("owner_after_id")) is not int or observed["owner_after_id"] != owner:
        raise UIFlowRuntimeError("program_main_loader_restore_failed", "canary did not confirm REPL owner and fixture cleanup")
    error = observed.get("error")
    if error is not None and (not isinstance(error, dict) or error.get("type") not in {"ImportError", "ValueError"}):
        raise UIFlowRuntimeError("program_main_loader_probe_failed", "canary failed before compatibility could be established")
    record = {"schema_version": 1, "status": "verified", "mpy_entrypoint": True, "loader": LOADER,
        "mpy": observed.get("mpy"), "small_int_bits": observed.get("small_int_bits"),
        "probe": {"kind": PROBE_KIND, "nonce": nonce, "status": "PASS", **observed,
                  "canary_sha256": CANARY_SHA256, "source_sha256": CANARY_SOURCE_SHA256,
                  "compiler_sha256": CANARY_COMPILER_SHA256}}
    if not main_loader_verified(record):
        record.update(status="unsupported", mpy_entrypoint=False)
        record["probe"]["status"] = "FAIL"
    return record
