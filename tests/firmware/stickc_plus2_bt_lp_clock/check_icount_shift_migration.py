"""Verify v2 icount wire compatibility and failed restore on a CPU-less machine."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import time

SUBSECTION = b"timer/icount/shift"
TAG = bytes((5, len(SUBSECTION))) + SUBSECTION + struct.pack(">I", 2)


class Qmp:
    def __init__(self, sock):
        self.reader = sock.makefile("r", encoding="utf-8")
        self.sock = sock
        assert "QMP" in json.loads(self.reader.readline())
        self.call("qmp_capabilities")

    def call(self, command, allow_error=False, **args):
        self.sock.sendall((json.dumps({"execute": command, "arguments": args}) + "\n").encode())
        while True:
            reply = json.loads(self.reader.readline())
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                if allow_error:
                    return reply
                raise RuntimeError(reply)


@contextmanager
def instance(binary, directory, label, cap, incoming=False):
    directory = Path(directory)
    qmp_socket = directory / (label + ".sock")
    log = directory / (label + ".log")
    mode = "shift=auto,align=off,sleep=on"
    if cap is not None:
        mode += f",max-shift={cap}"
    argv = [str(binary), "-M", "none,accel=tcg,usb=off", "-S", "-nodefaults",
            "-display", "none", "-serial", "none", "-monitor", "none",
            "-qmp", f"unix:{qmp_socket},server=on,wait=off", "-icount", mode]
    if incoming:
        argv.extend(["-incoming", "defer"])
    with log.open("wb") as output:
        process = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 5
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        sock.connect(str(qmp_socket))
                        break
                    except OSError:
                        time.sleep(0.02)
                else:
                    raise RuntimeError(log.read_text())
                yield Qmp(sock), log
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


def migration_wait(qmp, want):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        migration = qmp.call("query-migrate")
        if migration.get("status") in ("failed", "completed"):
            assert migration["status"] == want, migration
            return migration
        time.sleep(0.03)
    raise RuntimeError(migration)


def save(qmp, destination):
    qmp.call("migrate", uri=f"file:{destination}")
    migration_wait(qmp, "completed")
    return destination.read_bytes()


def tag_offset(data):
    assert data.count(TAG) == 1, data.count(TAG)
    return data.index(TAG) + len(TAG)


def stream_shift(data):
    return struct.unpack_from(">h", data, tag_offset(data))[0]


def load(qmp, source, want):
    qmp.call("migrate-incoming", uri=f"file:{source}", **{"exit-on-error": False})
    return migration_wait(qmp, want)


def job_wait(qmp, identity, want_error=False):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = next(row for row in qmp.call("query-jobs") if row["id"] == identity)
        if job["status"] == "concluded":
            assert ("error" in job) == want_error, job
            qmp.call("job-dismiss", id=identity)
            return job
        time.sleep(0.03)
    raise RuntimeError(job)


def add_disk(qmp, path):
    qmp.call("blockdev-add", driver="file", filename=str(path), **{"node-name": "storage"})
    qmp.call("blockdev-add", driver="qcow2", file="storage", **{"node-name": "image"})


def snapshot_fail_before_store(binary, out):
    disk = out / "snapshot.qcow2"
    with disk.open("wb") as stream:
        stream.truncate(1024 * 1024)
    with instance(binary, out, "snap-source", 5) as (qmp, _):
        qmp.call("blockdev-add", driver="file", filename=str(disk), **{"node-name": "storage"})
        qmp.call("blockdev-create", **{"job-id": "create", "options": {
            "driver": "qcow2", "file": "storage", "size": 1048576}})
        job_wait(qmp, "create")
        qmp.call("blockdev-add", driver="qcow2", file="storage", **{"node-name": "image"})
        qmp.call("snapshot-save", **{"job-id": "snapshot", "tag": "shift3", "vmstate": "image", "devices": ["image"]})
        job_wait(qmp, "snapshot")
    with instance(binary, out, "snap-load", 2) as (qmp, stderr):
        add_disk(qmp, disk)
        qmp.call("snapshot-load", **{"job-id": "restore", "tag": "shift3", "vmstate": "image", "devices": ["image"]})
        failed = job_wait(qmp, "restore", want_error=True)
        assert "incoming icount shift 3 is outside local max-shift 0..2" in stderr.read_text(), failed
        qmp.call("cont")
        qmp.call("stop")
        wire = save(qmp, out / "saved-after-failure")
        assert stream_shift(wire) == 2
        return {"snapshot_shift": 3, "local_cap": 2, "snapshot_load_failed": True,
                "cont_accepted": True, "local_shift_from_resaved_stream": 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=lambda name: Path(name).resolve(), required=True)
    parser.add_argument("--baseline", type=lambda name: Path(name).resolve(), required=True,
                        help="prior QEMU with adaptive icount and the original v2 reader")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="icount-wire-") as scratch:
        out = Path(scratch)
        original = out / "original"
        with instance(args.qemu, out, "source", 5) as (qmp, _):
            wire = save(qmp, original)
        assert stream_shift(wire) == 3
        at = tag_offset(wire)
        records = []
        for index, (label, binary, cap, shift, valid) in enumerate((
            ("same_cap", args.qemu, 5, 5, True),
            ("lower_cap", args.qemu, 4, 5, False),
            ("negative", args.qemu, 5, -1, False),
            ("above_global_limit", args.qemu, 5, 11, False),
            ("truncated", args.qemu, 5, None, False),
            ("previous_wire_reader", args.baseline, None, 5, True),
        )):
            src = out / f"wire-{index}"
            if shift is None:
                src.write_bytes(wire[:at+1])
            else:
                src.write_bytes(wire[:at] + struct.pack(">h", shift) + wire[at+2:])
            with instance(binary, out, str(index), cap, incoming=True) as (qmp, stderr):
                result = load(qmp, src, "completed" if valid else "failed")
                if not valid and shift is not None:
                    assert re.search(r"incoming icount shift -?\d+ is outside local max-shift",
                                     stderr.read_text()), (label, result, stderr.read_text())
                resume = qmp.call("cont", allow_error=True)
                qmp.call("stop", allow_error=True)
                migrated = qmp.call("migrate", uri=f"file:{out / f'next-{index}'}", allow_error=True)
                retained = None
                if "error" not in migrated:
                    migration_wait(qmp, "completed")
                    retained = stream_shift((out / f"next-{index}").read_bytes())
                    assert retained == (shift if valid else min(3, cap)), (label, retained)
                if valid:
                    assert retained == shift
                records.append({"case": label, "input_shift": shift, "cap": cap,
                                "completed": valid, "cont_accepted": "error" not in resume,
                                "local_shift_from_resaved_stream": retained,
                                "outgoing_migration_after_incoming_admitted": "error" not in migrated})
        snapshot = snapshot_fail_before_store(args.qemu, out)
        print(json.dumps({"wire": "timer/icount/shift v2 signed BE16", "cases": records,
                          "live_snapshot_fail_before_store": snapshot}, indent=2))


if __name__ == "__main__":
    main()
