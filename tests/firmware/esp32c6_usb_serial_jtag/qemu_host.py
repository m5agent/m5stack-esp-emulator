#!/usr/bin/env python3
"""Attach an explicit serial host to the third C6 chardev for this regression."""
import os
from pathlib import Path
import sys


def main():
    real = Path(os.environ["M5_C6_USJ_REAL_QEMU"]).resolve(strict=True)
    assert real != Path(__file__).resolve()
    args = sys.argv[1:]
    if "-qmp" in args:
        qmp = args[args.index("-qmp") + 1]
        assert qmp.startswith("unix:")
        path = qmp[5:].split(",")[0]
        assert len(path.encode()) < 80
        serials = [index + 1 for index, arg in enumerate(args) if arg == "-serial"]
        assert len(serials) == 3
        original = args[serials[2]]
        assert original.startswith("file:")
        log = Path(original[5:])
        assert log.name == "usb-serial-jtag.log" and "," not in str(log)
        args[serials[2]] = "chardev:c6-usj-probe"
        args += ["-chardev", f"socket,id=c6-usj-probe,path={path}.usj,server=on,wait=off,logfile={log}",
                 "-S", "-monitor", f"unix:{path}.hmp,server=on,wait=off"]
    os.execv(str(real), [str(real), *args])


if __name__ == "__main__":
    main()
