"""MicroPython source execution over the guest's actual UART raw REPL.

The socket is a QEMU chardev. It is not a host-side Python interpreter.
No reboot or firmware composition occurs here. Interrupting a program does
not promise to reset native modules, timers, IRQ handlers or other threads.
"""
from __future__ import annotations

import time
import re

from guest_console import GuestConsoleError, MAX_RESPONSE_BYTES

LIVE_PROGRAM_DEVICES = ("cores3", "atoms3r", "sticks3", "stopwatch")
LIVE_READY_MARKER = "M5EMU_UART_REPL_READY"


def live_bootstrap_files() -> dict[str, str]:
    """One-time filesystem initialization for admitted USB-console S3 builds.

    UART bytes still go through the emulated FIFO and the actual guest IRQ.
    These files are packaged by the existing source composer, never host-exec'd.
    Native UART-REPL boards require separate admission, not this bootstrap.
    """
    return {"boot.py": (
        "from machine import UART\nimport os\n"
        "_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)\n"
        "os.dupterm(_repl_uart, 0)\n"
        "_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)\n"
        "_uiflow_run_main = False\n"
        f"print({LIVE_READY_MARKER!r})\n"
    ), "main.py": "pass\n"}


class UIFlowRuntimeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def execution_markers(execution_id: str) -> dict[str, bytes]:
    prefix = f"__M5_EXEC_{execution_id}__:"
    return {state: (prefix + state).encode("ascii") for state in ("START", "DONE", "ERROR", "LOAD", "RESTORE_ERROR")}


def execution_state(data: bytes, execution_id: str) -> str | None:
    markers = execution_markers(execution_id)
    if markers["ERROR"] in data or markers["RESTORE_ERROR"] in data:
        return "failed"
    if markers["DONE"] in data:
        return "completed"
    if markers["START"] in data or markers["LOAD"] in data:
        return "running"
    return None


class ExecutionStateScanner:
    """Scan persistent serial bytes once, with bounded windows and overlap.

    Start at an execution's ``serial_offset`` so a DONE received alongside
    its initial START is still observed. ``state`` survives later noisy
    output; scanning each new window cannot downgrade a terminal result.
    """

    def __init__(self, execution_id: str, offset: int):
        self.execution_id = execution_id
        self.cursor = offset
        self.state = None
        self.restore_failed = False
        self.load_requested = False
        self._tail = b""
        self._overlap = max(map(len, execution_markers(execution_id).values())) - 1

    def scan(self, console) -> str | None:
        end = console.offset()
        count = min(MAX_RESPONSE_BYTES, max(0, end - self.cursor))
        if not count:
            return self.state
        data = console.read_from(self.cursor, count)
        if len(data) != count:
            raise GuestConsoleError("console_log_error", "console log lost committed bytes")
        window = self._tail + data
        if execution_markers(self.execution_id)["RESTORE_ERROR"] in window:
            self.restore_failed = True
        if execution_markers(self.execution_id)["LOAD"] in window:
            self.load_requested = True
        observed = execution_state(window, self.execution_id)
        ranks = {None: 0, "running": 1, "completed": 2, "failed": 3}
        if ranks[observed] > ranks[self.state]:
            self.state = observed
        self.cursor += len(data)
        self._tail = window[-self._overlap:]
        return self.state


def synchronize_raw_repl(console, *, timeout: float, cancelled) -> dict:
    """Confirm an actual raw prompt without submitting source or resetting VM."""
    deadline = time.monotonic() + timeout

    def remaining():
        if cancelled():
            raise UIFlowRuntimeError("program_cancelled", "session is stopping")
        left = deadline - time.monotonic()
        if left <= 0:
            raise UIFlowRuntimeError("program_timeout", "guest execution acknowledgement timed out")
        return left

    offset = console.offset()
    console.write(b"\r\x03", timeout=remaining())
    # This only separates control characters. Prompt/OK/START, rather than
    # this delay, establish synchronization and actual guest execution.
    until = time.monotonic() + 0.1
    while time.monotonic() < until:
        remaining()
        time.sleep(0.01)
    console.write(b"\r\x01", timeout=remaining())
    _, prompt_end = console.wait_for(
        b"raw REPL; CTRL-B to exit\r\n>", offset, remaining(), cancelled,
    )
    remaining()
    return {"serial_offset": offset, "prompt_end": prompt_end,
            "interruption_confirmed": True, "cleanup_mode": "interrupt-only"}


def run_source(console, source: str, execution_id: str, *, timeout: float, cancelled,
               on_synchronized=None, source_path: str | None = None) -> dict:
    """Interrupt, synchronize raw REPL, then compile and execute source in guest.

    MicroPython raw REPL uses Ctrl-A to enter, Ctrl-D to submit and an OK
    acknowledgement. This intentionally does not issue Ctrl-D at an empty
    prompt (a VM soft reset); console routing must remain installed.
    """
    markers = execution_markers(execution_id)
    prepare_source = (
        f" with open({source_path!r}, 'r') as _m5_input:\n  _m5_text = _m5_input.read()\n"
        if source_path is not None else ""
    )
    expression = "_m5_text" if source_path is not None else repr(source)
    wrapper = (
        "try:\n"
        + prepare_source
        + f" _m5_compiled = compile({expression}, '<m5-{execution_id}>', 'exec')\n"
        f" print({markers['START'].decode()!r})\n"
        " exec(_m5_compiled, {'__name__': '__main__', '__file__': 'main.py'})\n"
        "except BaseException as _m5_error:\n"
        " import sys\n"
        " sys.print_exception(_m5_error)\n"
        f" print({markers['ERROR'].decode()!r})\n"
        "else:\n"
        f" print({markers['DONE'].decode()!r})\n"
    ).encode("utf-8")
    return _run_wrapper(console, wrapper, execution_id, timeout=timeout, cancelled=cancelled,
                        on_synchronized=on_synchronized)


def run_mpy(console, execution_id: str, *, package_path: str, entrypoint_sha256: str,
            loader_capabilities: dict, timeout: float, cancelled, on_synchronized=None) -> dict:
    """Dispatch untouched bytecode through the real importer; LOAD is not START.

    The official API loads and executes in one call. A generic binary has no
    injectable body-entry hook, so application_started/ready stay unknown.
    Native callbacks/threads remain outside interrupt-only restoration.
    """
    from uiflow_main_loader import require_main_loader
    capabilities = require_main_loader(loader_capabilities)
    if not isinstance(package_path, str) or re.fullmatch(r"/flash/\.m5-live-packages/[0-9a-f]{64}", package_path) is None:
        raise UIFlowRuntimeError("program_package_integrity", "binary entrypoint requires a managed immutable package path")
    if not isinstance(entrypoint_sha256, str) or re.fullmatch("[0-9a-f]{64}", entrypoint_sha256) is None:
        raise UIFlowRuntimeError("program_package_integrity", "binary entrypoint requires its exact lowercase SHA256")
    markers = execution_markers(execution_id)
    target = package_path + "/main.mpy"
    owner_id = capabilities["probe"]["owner_before_id"]
    wrapper = f'''import sys,os,hashlib,binascii
_m5_binary_owner=__import__('__main__')
_m5_binary_cwd=os.getcwd()
_m5_binary_path=sys.path[:]
_m5_binary_saved={{}}
for _m5_binary_name in ('main','__main__'):
 _m5_binary_saved[_m5_binary_name]=(_m5_binary_name in sys.modules,sys.modules.get(_m5_binary_name))
_m5_binary_error=False
_m5_binary_restored=False
try:
 assert id(_m5_binary_owner)=={owner_id}, 'REPL owner differs from the verified loader probe'
 assert 'main.py' not in os.listdir({package_path!r}) and 'main' not in os.listdir({package_path!r}), 'entrypoint shadowing'
 assert (os.stat({target!r})[0] & 0xf000)==0x8000, 'entrypoint is not a regular file'
 _m5_binary_digest=hashlib.sha256()
 _m5_binary_size=0
 _m5_binary_header=b''
 with open({target!r},'rb') as _m5_binary_file:
  while True:
   _m5_binary_chunk=_m5_binary_file.read(4096)
   if not _m5_binary_chunk:
    break
   if not _m5_binary_size:
    _m5_binary_header=_m5_binary_chunk[:4]
   _m5_binary_size+=len(_m5_binary_chunk)
   assert _m5_binary_size<=262144, 'entrypoint too large'
   _m5_binary_digest.update(_m5_binary_chunk)
 assert binascii.hexlify(_m5_binary_digest.digest()).decode()=={entrypoint_sha256!r}, 'entrypoint bytes changed'
 assert len(_m5_binary_header)==4 and _m5_binary_header[0]==77, 'invalid .mpy magic'
 sys.modules.pop('main',None)
 os.chdir({package_path!r})
 sys.path[:]=[{package_path!r}]+[p for p in _m5_binary_path if p!={package_path!r}]
 print({markers['LOAD'].decode()!r})
 _m5_binary_module=__import__('main',None,None,False,0)
 assert sys.modules.get('main') is _m5_binary_module and sys.modules.get('__main__') is _m5_binary_module and __import__('__main__') is _m5_binary_module, 'application module identity differs'
 assert _m5_binary_module.__name__=='__main__' and _m5_binary_module.__file__=={target!r}, 'application entrypoint differs'
except BaseException as _m5_binary_exception:
 _m5_binary_error=True
 sys.print_exception(_m5_binary_exception)
finally:
 try:
  os.chdir(_m5_binary_cwd)
  sys.path[:]=_m5_binary_path
  for _m5_binary_name,_m5_binary_pair in _m5_binary_saved.items():
   if _m5_binary_pair[0]:
    sys.modules[_m5_binary_name]=_m5_binary_pair[1]
   else:
    sys.modules.pop(_m5_binary_name,None)
  _m5_binary_restored=id(__import__('__main__'))=={owner_id} and __import__('__main__') is _m5_binary_owner and os.getcwd()==_m5_binary_cwd and sys.path==_m5_binary_path and all((_m5_binary_name in sys.modules)==_m5_binary_pair[0] and (not _m5_binary_pair[0] or sys.modules[_m5_binary_name] is _m5_binary_pair[1]) for _m5_binary_name,_m5_binary_pair in _m5_binary_saved.items())
 except BaseException as _m5_binary_restore_exception:
  sys.print_exception(_m5_binary_restore_exception)
 if not _m5_binary_restored:
  print({markers['RESTORE_ERROR'].decode()!r})
 elif _m5_binary_error:
  print({markers['ERROR'].decode()!r})
 else:
  print({markers['DONE'].decode()!r})
'''.encode("utf-8")
    result = _run_wrapper(console, wrapper, execution_id, timeout=timeout, cancelled=cancelled,
                          on_synchronized=on_synchronized)
    if result.pop("loader_restore_failed", False):
        raise UIFlowRuntimeError("program_main_loader_restore_failed", "binary execution did not restore its verified REPL owner")
    requested = result.pop("loader_import_requested", False)
    result.update(entrypoint="main.mpy", execution_phase={"running": "import-requested", "completed": "import-returned", "failed": "load-or-execute-failed" if requested else "preflight-failed"}[result["state"]],
                  start_semantics="import-request-only", application_started=None, application_ready=None,
                  owner_restored=True if result["state"] in {"completed", "failed"} else None)
    return result


def _run_wrapper(console, wrapper: bytes, execution_id: str, *, timeout: float, cancelled,
                 on_synchronized=None) -> dict:
    """Shared bounded raw-paste transport; wrapper owns its truthful markers."""
    deadline = time.monotonic() + timeout

    def remaining():
        if cancelled():
            raise UIFlowRuntimeError("program_cancelled", "session is stopping")
        left = deadline - time.monotonic()
        if left <= 0:
            raise UIFlowRuntimeError("program_timeout", "guest execution acknowledgement timed out")
        return left

    prompt_end = synchronize_raw_repl(console, timeout=remaining(), cancelled=cancelled)["prompt_end"]
    if on_synchronized is not None:
        on_synchronized()
    cursor = prompt_end

    def read_exact(size):
        nonlocal cursor
        try:
            data = console.read_exact(cursor, size, remaining(), cancelled)
        except GuestConsoleError as error:
            if error.code == "console_timeout":
                raise UIFlowRuntimeError(
                    "program_timeout", "guest execution acknowledgement timed out"
                ) from error
            if error.code == "console_cancelled":
                raise UIFlowRuntimeError("program_cancelled", "session is stopping") from error
            raise
        cursor += size
        return data

    # Upstream MicroPython tools/pyboard.py raw-paste negotiation and credit
    # protocol. Guest stdin buffers are small; an unpaced bulk write can lose
    # source even though the socket itself accepted every byte.
    console.write(b"\x05A\x01", timeout=remaining())
    response = read_exact(2)
    if response == b"R\x01":
        window = int.from_bytes(read_exact(2), "little")
        if not 0 < window <= 65535:
            raise UIFlowRuntimeError("program_protocol_error", "invalid raw-paste window")
        credit = window
        sent = 0
        while sent < len(wrapper):
            while credit == 0 or console.offset() > cursor:
                control = read_exact(1)
                if control == b"\x01":
                    credit += window
                elif control == b"\x04":
                    console.write(b"\x04", timeout=remaining())
                    raise UIFlowRuntimeError("program_protocol_error", "guest ended source transfer early")
                else:
                    raise UIFlowRuntimeError("program_protocol_error", "unexpected raw-paste control byte")
            count = min(credit, 128, len(wrapper) - sent)
            console.write(wrapper[sent:sent + count], timeout=remaining())
            credit -= count
            sent += count
        console.write(b"\x04", timeout=remaining())
        control = read_exact(1)
        while control == b"\x01":
            control = read_exact(1)
        if control != b"\x04":
            raise UIFlowRuntimeError("program_protocol_error", "raw-paste EOF was not acknowledged")
        transfer = "raw-paste"
    elif response == b"R\x00":
        for start in range(0, len(wrapper), 128):
            console.write(wrapper[start:start + 128], timeout=remaining())
            time.sleep(min(0.01, remaining()))
        console.write(b"\x04", timeout=remaining())
        if read_exact(2) != b"OK":
            raise UIFlowRuntimeError("program_protocol_error", "raw REPL did not acknowledge source")
        transfer = "raw-repl-paced"
    else:
        raise UIFlowRuntimeError("program_protocol_error", "guest did not recognize raw-paste negotiation")
    scanner = ExecutionStateScanner(execution_id, prompt_end)
    while True:
        remaining()
        state = scanner.scan(console)
        if state is not None:
            return {"state": state, "serial_offset": prompt_end,
                    "next_offset": scanner.cursor,
                    "acknowledged": True, "transfer_mode": transfer,
                    "cleanup_mode": "interrupt-only",
                    **({"loader_restore_failed": True} if scanner.restore_failed else {}),
                    **({"loader_import_requested": True} if scanner.load_requested else {})}
        if scanner.cursor < console.offset():
            continue
        # Wait on the live reader rather than polling historical read_from:
        # a disconnected console must fail immediately, even after source ACK.
        cursor = scanner.cursor
        read_exact(1)
