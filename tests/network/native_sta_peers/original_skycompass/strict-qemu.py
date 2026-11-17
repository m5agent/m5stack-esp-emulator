#!/usr/bin/env python3
"""Local native radio test with zero host IP egress."""
import json
import os
from pathlib import Path
import re
import socket
import sys

binary = os.environ["ORIGINAL_STA_QEMU"]
flags = sys.argv[1:]
if flags in (["-machine", "help"], ["-M", "help"], ["-netdev", "help"], ["--version"], ["-device", "misc.esp32s3.wifi,help"]):
    os.execv(binary, [binary, *flags])
assert flags.count("-M") == flags.count("-nic") == 1
assert flags[flags.index("-M") + 1] in ("m5cardputer", "m5cardputeradv", "m5sticks3")
assert not any(arg in {"-net", "-netdev", "-add-fd", "-monitor", "-gdb"} for arg in flags)
nic_index = flags.index("-nic") + 1
nic = flags[nic_index]
assert re.fullmatch(r"user,model=misc\.esp32s3\.wifi,mac=(?:[0-9a-f]{2}:){5}[0-9a-f]{2},id=wifi0", nic)
unix_path = os.environ["ORIGINAL_STA_UNIX"]
assert re.fullmatch(r"/tmp/m5staproof-[a-z0-9_]+/peer", unix_path)
endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
endpoint.connect(unix_path)
endpoint.set_inheritable(True)
flags[nic_index] = "socket," + nic.removeprefix("user,") + f",fd={endpoint.fileno()}"
Path(os.environ["ORIGINAL_STA_TOPOLOGY"]).write_text(json.dumps({
    "machine": flags[flags.index("-M") + 1],
    "native_sta_nics": 1,
    "backend": "one Unix stream",
    "ipv6": "off",
    "host_ip_egress": "denied by process sandbox",
    "guest_forwards": 0,
}))
sandbox = "/usr/bin/sandbox-exec"
profile = "(version 1) (allow default) (deny network-outbound (remote ip))"
os.execv(sandbox, [sandbox, "-p", profile, binary, *flags])
