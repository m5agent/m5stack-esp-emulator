"""Publish complete files through the guest's real UART and filesystem.

The caller owns the session program lock. Nothing executes in host Python;
the generated finite commands use the guest's os, open, hashlib and importer.
Native callbacks/threads are outside the interrupt-only cleanup guarantee.
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid

from micropython_repl import RawREPL
from mpy_bytecode import MPYBytecodeError, validate_bytecode
from uiflow_runtime import UIFlowRuntimeError
from uiflow_main_loader import require_main_loader


GUEST_BASE = "/flash/.m5-live-packages"
MAX_GUEST_PACKAGES = 64
CHUNK_BYTES = 2048
# At most 64 files + 448 directories, each path <=192 UTF-8 bytes. Even
# conservatively escaping all Unicode uses at most 3x those path bytes
# (<288 KiB), leaving room for the file rows and JSON receipt envelope.
# Keep this finite and below GuestConsole's separate 1 MiB response bound.
INVENTORY_MAX_OUTPUT = 512 * 1024


def validate_mpy(files: dict[str, bytes], capabilities: dict) -> None:
    for path, data in files.items():
        if not path.lower().endswith(".mpy"):
            continue
        if len(data) < 4 or data[0] != ord("M"):
            raise UIFlowRuntimeError("program_mpy_invalid", "invalid .mpy header")
        mpy = capabilities.get("mpy")
        bits = capabilities.get("small_int_bits")
        if type(mpy) is not int or type(bits) is not int or bits != 31:
            raise UIFlowRuntimeError("program_mpy_capability_unknown", "guest .mpy capabilities are not an admitted S3/MPZ configuration")
        if data[1] != (mpy & 255) or data[3] > bits:
            raise UIFlowRuntimeError("program_mpy_incompatible", ".mpy version or small-int requirement differs from this guest")
        # Official bytecode-only mpy-cross emits zero feature/architecture byte.
        # Native code's subversion, arch and relocation semantics are not admitted.
        if data[2] != 0:
            raise UIFlowRuntimeError("program_mpy_native_unsupported", "only bytecode-only .mpy dependencies are admitted")
        try:
            validate_bytecode(data)
        except MPYBytecodeError as error:
            raise UIFlowRuntimeError("program_mpy_invalid", "invalid or unsupported bytecode-only .mpy container") from error


def _rpc(client, body, expression, *, max_output=65536):
    marker = "__M5_PKG_" + uuid.uuid4().hex + ":"
    result = client.execute(
        body + "\nprint(" + repr(marker) + " + json.dumps(" + expression + "))\n",
        max_output=max_output,
    )
    try:
        output = result["stdout"].decode("utf-8")
    except UnicodeError as error:
        raise UIFlowRuntimeError("program_package_receipt_invalid", "guest package receipt is not UTF-8") from error
    lines = [line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise UIFlowRuntimeError("program_package_receipt_invalid", "guest did not return one package receipt")
    try:
        return json.loads(lines[0])
    except (ValueError, TypeError) as error:
        raise UIFlowRuntimeError("program_package_receipt_invalid", "guest returned an invalid package receipt") from error


def _verify_inventory(files, snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {"files", "directories"}:
        raise UIFlowRuntimeError("program_package_integrity", "guest package snapshot is incomplete")
    inventory, directories = snapshot["files"], snapshot["directories"]
    expected_directories = set()
    for path in files:
        pieces = path.split("/")
        expected_directories.update("/".join(pieces[:index]) for index in range(1, len(pieces)))
    if not isinstance(directories, list) or any(not isinstance(path, str) for path in directories) or len(directories) != len(set(directories)) or set(directories) != expected_directories:
        raise UIFlowRuntimeError("program_package_integrity", "guest package directories differ from the snapshot")
    if not isinstance(inventory, dict) or set(inventory) != set(files):
        raise UIFlowRuntimeError("program_package_integrity", "guest package paths differ from the snapshot")
    for path, data in files.items():
        row = inventory[path]
        if not isinstance(row, dict) or type(row.get("size")) is not int or row["size"] != len(data) or row.get("sha256") != hashlib.sha256(data).hexdigest():
            raise UIFlowRuntimeError("program_package_integrity", "guest package bytes differ from the snapshot")
    return inventory


def deploy_package(console, files, metadata, *, timeout, cancelled, on_synchronized=None,
                   on_progress=None, loader_capabilities=None):
    """Verify, publish and activate one immutable package; do not start its entrypoint.

    A failed upload leaves only its unique staging directory. No partial package
    becomes the working directory. Quota exhaustion is explicit; old packages
    may still be referenced by native callbacks, so they are never auto-deleted.
    """
    if metadata.get("entrypoint", "main.py") == "main.mpy":
        # The service binds this observed proof to the same live session. A
        # boolean or caller-supplied firmware label never substitutes for it.
        require_main_loader(loader_capabilities)
    def progress(phase, **values):
        if on_progress is not None:
            on_progress({"phase": phase, **values})

    client = RawREPL(console, timeout=timeout, cancelled=cancelled)
    client.synchronize(on_synchronized)
    revision = metadata["revision_id"]
    final = GUEST_BASE + "/" + revision
    stage = GUEST_BASE + "/.stage-" + uuid.uuid4().hex
    progress("preflight", staging_path=stage, package_path=final)
    # This family is pinned to ESP32 OBJ_REPR_A + MPZ (31 bits). Count with
    # shifts: this actual UIFlow build does not implement int.bit_length().
    capabilities = _rpc(client, f'''import os, sys, json, hashlib, binascii
assert (os.stat('/flash')[0] & 0xf000) == 0x4000
try:
 os.mkdir({GUEST_BASE!r})
except OSError:
 assert (os.stat({GUEST_BASE!r})[0] & 0xf000) == 0x4000
_m5_pkg_names = os.listdir({GUEST_BASE!r})
_m5_pkg_exists = {revision!r} in _m5_pkg_names
_m5_pkg_fs = os.statvfs('/flash')
_m5_pkg_smallbits = 0
_m5_pkg_maxint = sys.maxsize
while _m5_pkg_maxint:
 _m5_pkg_smallbits += 1
 _m5_pkg_maxint >>= 1
''', "{'mpy': getattr(sys.implementation, '_mpy', None), 'small_int_bits': _m5_pkg_smallbits, 'existing': _m5_pkg_exists, 'directory_count': len(_m5_pkg_names), 'free_bytes': _m5_pkg_fs[0] * _m5_pkg_fs[3]}")
    if not isinstance(capabilities, dict) or type(capabilities.get("existing")) is not bool:
        raise UIFlowRuntimeError("program_package_receipt_invalid", "guest capabilities are invalid")
    validate_mpy(files, capabilities)
    if metadata.get("entrypoint", "main.py") == "main.mpy" and any(
        capabilities.get(key) != loader_capabilities.get(key) for key in ("mpy", "small_int_bits")
    ):
        raise UIFlowRuntimeError("program_mpy_capability_unknown", "guest bytecode ABI differs from its verified loader probe")
    progress("capabilities", capabilities=capabilities)

    # The walker rejects extra paths and nonregular entries. Its complete
    # inventory is re-read even on a cache hit: application code can mutate FS.
    _rpc(client, '''def _m5_pkg_inventory(root):
 result = {}
 directories = []
 pending = [('', root)]
 visited = 0
 while pending:
  relative, directory = pending.pop()
  assert (os.stat(directory)[0] & 0xf000) == 0x4000
  for name in os.listdir(directory):
   visited += 1
   assert visited <= 512
   child = relative + '/' + name if relative else name
   absolute = root + '/' + child
   kind = os.stat(absolute)[0] & 0xf000
   if kind == 0x4000:
    directories.append(child)
    pending.append((child, absolute))
   else:
    assert kind == 0x8000
    digest = hashlib.sha256()
    size = 0
    with open(absolute, 'rb') as stream:
     while True:
      chunk = stream.read(4096)
      if not chunk:
       break
      size += len(chunk)
      assert size <= 262144
      digest.update(chunk)
    result[child] = {'size': size, 'sha256': binascii.hexlify(digest.digest()).decode()}
 return {'files': result, 'directories': directories}
''', "True")
    reused = capabilities["existing"]
    if reused:
        inventory = _verify_inventory(files, _rpc(client, "", f"_m5_pkg_inventory({final!r})",
                                                max_output=INVENTORY_MAX_OUTPUT))
    else:
        if type(capabilities.get("directory_count")) is not int or capabilities["directory_count"] >= MAX_GUEST_PACKAGES:
            raise UIFlowRuntimeError("program_package_guest_quota", "guest package directory quota reached; create a new session explicitly")
        required = sum(len(data) for data in files.values()) + 4096 * (len(files) + 2)
        if type(capabilities.get("free_bytes")) is not int or capabilities["free_bytes"] < required:
            raise UIFlowRuntimeError("program_package_no_space", "guest filesystem has insufficient space")
        _rpc(client, f"os.mkdir({stage!r})", "True")
        directories = set()
        for path in files:
            pieces = path.split("/")
            directories.update("/".join(pieces[:index]) for index in range(1, len(pieces)))
        for directory in sorted(directories, key=lambda value: (value.count("/"), value)):
            _rpc(client, f"os.mkdir({stage + '/' + directory!r})", "True")
        written = 0
        for path, data in sorted(files.items()):
            target = stage + "/" + path
            _rpc(client, f"_m5_pkg_f = open({target!r}, 'wb')\n_m5_pkg_f.close()", "True")
            for offset in range(0, len(data), CHUNK_BYTES):
                chunk = data[offset:offset + CHUNK_BYTES]
                encoded = base64.b64encode(chunk).decode("ascii")
                count = _rpc(client, f"with open({target!r}, 'ab') as _m5_pkg_f:\n _m5_pkg_written = _m5_pkg_f.write(binascii.a2b_base64({encoded!r}))", "_m5_pkg_written")
                if type(count) is not int or count != len(chunk):
                    raise UIFlowRuntimeError("program_package_short_write", "guest file write was incomplete")
                written += len(chunk)
            progress("writing", path=path, written_bytes=written)
        inventory = _verify_inventory(files, _rpc(client, "", f"_m5_pkg_inventory({stage!r})",
                                                max_output=INVENTORY_MAX_OUTPUT))
        progress("verified", inventory=inventory)
        _rpc(client, f"os.sync()\nos.rename({stage!r}, {final!r})", "True")
    progress("published", inventory=inventory, reused=reused)

    # Remove only modules actually sourced from the managed tree, and matching
    # parent attributes, before the next complete application imports them.
    activated = _rpc(client, f'''_m5_pkg_removed = []
_m5_pkg_modules = list(sys.modules.items())
_m5_pkg_roots = []
for _m5_pkg_name, _m5_pkg_module in _m5_pkg_modules:
 _m5_pkg_file = getattr(_m5_pkg_module, '__file__', '')
 _m5_pkg_path = getattr(_m5_pkg_module, '__path__', '')
 _m5_pkg_locations = [_m5_pkg_file] + (list(_m5_pkg_path) if isinstance(_m5_pkg_path, (list, tuple)) else [_m5_pkg_path])
 if any(isinstance(p, str) and p.startswith({GUEST_BASE + '/'!r}) for p in _m5_pkg_locations):
  _m5_pkg_roots.append(_m5_pkg_name)
for _m5_pkg_name, _m5_pkg_module in sorted(_m5_pkg_modules, key=lambda item: -item[0].count('.')):
 if any(_m5_pkg_name == p or _m5_pkg_name.startswith(p + '.') for p in _m5_pkg_roots):
  del sys.modules[_m5_pkg_name]
  _m5_pkg_removed.append(_m5_pkg_name)
  if '.' in _m5_pkg_name:
   _m5_pkg_parent, _m5_pkg_attribute = _m5_pkg_name.rsplit('.', 1)
   _m5_pkg_parent_module = sys.modules.get(_m5_pkg_parent)
   if _m5_pkg_parent_module is not None and getattr(_m5_pkg_parent_module, _m5_pkg_attribute, None) is _m5_pkg_module:
    delattr(_m5_pkg_parent_module, _m5_pkg_attribute)
sys.path[:] = [p for p in sys.path if not (isinstance(p, str) and (p == {GUEST_BASE!r} or p.startswith({GUEST_BASE + '/'!r})))]
sys.path.insert(0, {final!r})
os.chdir({final!r})
''', "{'cwd': os.getcwd(), 'removed_modules': _m5_pkg_removed}")
    if not isinstance(activated, dict) or activated.get("cwd") != final:
        raise UIFlowRuntimeError("program_package_activation_unconfirmed", "guest package activation was not confirmed")
    receipt = {"phase": "activated", "package_path": final, "inventory": inventory,
               "reused": reused, "capabilities": capabilities,
               "removed_modules": activated["removed_modules"], "staging_path": stage}
    progress("activated", **{key: value for key, value in receipt.items() if key != "phase"})
    return receipt
