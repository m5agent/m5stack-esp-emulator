#!/usr/bin/env python3
"""Exercise the shipped WASM32 TCI dispatcher against the real pinned libffi."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / "patches/qemu-wasm-probe/0025-wasm-tci-typed-helper-calls.patch"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_postimage():
    selected = False
    result = []
    for line in PATCH.read_text().splitlines():
        if line.startswith("diff --git "):
            selected = line.endswith(" b/tcg/tci-wasm-call.h")
        elif selected and line.startswith("+") and not line.startswith("+++"):
            result.append(line[1:])
    return "\n".join(result) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emcc", required=True)
    parser.add_argument("--ffi-prefix", type=Path, required=True,
                        help="target/ from the pinned browser source build")
    parser.add_argument("--node", default="node")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    if output.exists():
        parser.error("--out-dir must be new; preserve previous evidence")
    compiler = Path(args.emcc).resolve()
    sdk_config = compiler.parents[2] / ".emscripten"
    if not sdk_config.is_file():
        parser.error("--emcc must belong to the isolated, activated SDK")
    environment = os.environ.copy()
    for name in ("CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "EMCC_CFLAGS", "EMMAKEN_CFLAGS"):
        environment.pop(name, None)
    environment["EM_CONFIG"] = str(sdk_config)
    version = subprocess.check_output([str(compiler), "--version"], text=True, env=environment)
    if not re.search(r"\b3\.1\.50\b", version):
        parser.error("this ABI control requires Emscripten 3.1.50")
    prefix = args.ffi_prefix.resolve()
    library = prefix / "lib/libffi.a"
    if not library.is_file() or not (prefix / "include/ffi.h").is_file():
        parser.error("--ffi-prefix must contain the built libffi and headers")
    package = prefix / "lib/pkgconfig/libffi.pc"
    if not package.is_file() or not re.search(r"^Version:\s*3\.4\.7\s*$",
                                             package.read_text(), re.M):
        parser.error("this ABI control requires the pinned libffi 3.4.7")
    output.mkdir(parents=True)
    environment["EM_CACHE"] = str(output / "em-cache")
    header = output / "tci-wasm-call.h"
    header.write_text(header_postimage())
    lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
    if sha(header) != lock["patched_files"]["tcg/tci-wasm-call.h"]:
        parser.error("the tested header must match the locked QEMU postimage")
    source = Path(__file__).with_name("probe.c")
    target = output / "typed-helpers.cjs"
    command = [str(compiler), str(source), "-I" + str(output),
               "-I" + str(prefix / "include"), str(library), "-O3", "-pthread",
               "-sSINGLE_FILE=1", "-sENVIRONMENT=node", "-sWASM_BIGINT",
               "-sASYNCIFY=1", "-sASYNCIFY_IMPORTS=ffi_call_js", "-sEXIT_RUNTIME=1",
               "-sALLOW_TABLE_GROWTH=1", "-sASSERTIONS=1", "-sSTACK_SIZE=64KB",
               "-sDEFAULT_PTHREAD_STACK_SIZE=64KB", "-sSTACK_OVERFLOW_CHECK=2",
               "-o", str(target)]
    report = {"kind": "wasm32-tci-libffi-abi-control", "sdk": "3.1.50", "libffi": "3.4.7",
              "guest_execution": "NOT RUN", "status": "FAIL",
              "source_sha256": sha(source), "patch_sha256": sha(PATCH),
              "header_sha256": sha(header), "libffi_sha256": sha(library)}
    try:
        with (output / "build.log").open("wb") as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                           env=environment, check=True)
        result = subprocess.run([args.node, str(target)], capture_output=True,
                                text=True, timeout=30)
        (output / "run.log").write_text(result.stdout + result.stderr)
        result.check_returncode()
        marker = next(line for line in result.stdout.splitlines()
                      if line.startswith('{"status":"PASS"'))
        control = json.loads(marker)
        if (control.get("accepted_cases") != 66 or control.get("rejected_without_call") != 9
                or control.get("setjmp_fast") != 37 or control.get("setjmp_ffi") != 37):
            raise ValueError("the complete ABI, rejection and longjmp controls must pass")
        report.update(status="PASS", result=control,
                      artifact_sha256=sha(target), exit_code=result.returncode)
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
