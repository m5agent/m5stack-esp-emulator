"""Verify adaptive icount option admission without starting a guest CPU."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


CASES = (
    ("shift=auto,align=off,sleep=on,max-shift=0", None),
    ("shift=auto,align=off,sleep=on,max-shift=5", None),
    ("shift=auto,max-shift=10", None),
    ("shift=5,align=off,sleep=off", None),
    ("shift=auto,sleep=on", None),
    ("shift=auto,max-shift=-1", "must be 0..10"),
    ("shift=auto,max-shift=11", "must be 0..10"),
    ("shift=auto,max-shift=5foo", "must be 0..10"),
    ("shift=5,max-shift=5", "requires shift=auto"),
    ("max-shift=5", "requires shift=auto"),
    ("shift=auto,max-shift=5,sleep=off", "requires align=off, sleep=on"),
    ("shift=auto,max-shift=5,align=on", "requires align=off, sleep=on"),
    ("shift=auto,max-shift=5,rr=record", "cannot be combined with record/replay"),
    ("shift=auto,max-shift=5,rr=replay", "cannot be combined with record/replay"),
)
QMP_COMMANDS = (
    '{"execute":"qmp_capabilities"}\n'
    '{"execute":"query-status"}\n'
    '{"execute":"quit"}\n'
)
REPLAY_SENTINEL = b"existing replay sentinel\x00\xff"


def execute(binary, option, *, existing=True, split_replay=False):
    with tempfile.TemporaryDirectory(prefix="icount-admission-") as directory:
        replay = Path(directory) / "existing-replay.bin"
        if existing:
            replay.write_bytes(REPLAY_SENTINEL)
        icount_args = ["-icount", option]
        if ",rr=" in option:
            if split_replay:
                timing, replay_mode = option.rsplit(",rr=", 1)
                icount_args = ["-icount", timing, "-icount", f"rr={replay_mode},rrfile={replay}"]
            else:
                icount_args = ["-icount", f"{option},rrfile={replay}"]
        command = [
            str(binary.resolve()), "-machine", "none,accel=tcg,usb=off", "-S",
            "-nodefaults", "-display", "none", "-serial", "none",
            "-monitor", "none", "-qmp", "stdio", *icount_args,
        ]
        process = subprocess.run(command, input=QMP_COMMANDS, text=True,
                                 capture_output=True, timeout=8)
        unchanged = replay.read_bytes() == REPLAY_SENTINEL if existing else not replay.exists()
        return process, unchanged


def check(binary):
    observations = []
    for option, error in CASES:
        process, sentinel_preserved = execute(binary, option)
        if error:
            assert process.returncode != 0 and error in process.stderr, (option, process)
            assert sentinel_preserved, f"{option} modified an existing replay"
        else:
            assert process.returncode == 0, (option, process)
            messages = [json.loads(line) for line in process.stdout.splitlines()]
            assert any(
                isinstance(result := message.get("return"), dict) and result.get("running") is False
                for message in messages
            ), (option, messages)
        observations.append({"option": option, "accepted": error is None, "error_fragment": error})
    option = "shift=auto,max-shift=5,rr=record"
    for existing in (True, False):
        process, unchanged = execute(binary, option, existing=existing, split_replay=True)
        assert process.returncode != 0 and "cannot be combined with record/replay" in process.stderr, process
        assert unchanged, "split -icount unexpectedly changed the record path"
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"status": "PASS", "runtime_sha256": digest, "machine": "none",
            "existing_replay_bytes_preserved": True,
            "split_icount_does_not_create_or_modify_record_file": True, "cases": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--uncapped-qemu", type=Path)
    parser.add_argument("--unguarded-qemu", type=Path)
    args = parser.parse_args()
    result = check(args.qemu)
    if args.uncapped_qemu:
        process, _ = execute(args.uncapped_qemu, "shift=auto,sleep=on,max-shift=5")
        assert process.returncode != 0 and "max-shift" in process.stderr, process
        result["old_cli_rejected_new_option"] = True
    if args.unguarded_qemu:
        process, sentinel_preserved = execute(args.unguarded_qemu, "shift=auto,max-shift=5,rr=record")
        assert process.returncode != 0 and not sentinel_preserved, process
        result["unguarded_cli_modified_replay_before_rejecting"] = True
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
