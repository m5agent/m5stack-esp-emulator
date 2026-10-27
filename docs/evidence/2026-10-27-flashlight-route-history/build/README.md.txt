UNIT-HOST-38 source build and source replay (2026-10-27)

This archive proves the source/build layer only. It is not a firmware, guest,
Web, or physical-hardware PASS. The sibling controller archive retains the
original independent C failure and the corrected result without rewriting them.

The fresh QEMU source and object build produced runtime SHA256
3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1.
The prior 7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e
runtime remains unchanged. Twelve ordered patches cover 106 source files, and
the three 0046 implementation files match the final build source exactly.

A temporary GIT_INDEX_FILE loaded HEAD and added only the explicit 106-file
whitelist. Reversing the twelve patches with --cached produced HEAD tree
ddde372fbcc1b22e99f24372e14dee425be3193b. Applying them forward restored the exact
postimage tree ce1b71562a4f87bcdd0344cc8dd8304b661fff6f. The real QEMU index,
106 working files and runtime bytes were unchanged before/after replay. All
77 command records and raw stdout/stderr are retained. No source worktree was
reset or rewritten, and the running regression assets were untouched.

The QEMU objects are newly built. Forty-three regular pinned static dependency
cache files and three download archives were reused; their bytes are excluded
and their current SHA256 checks are recorded. The fresh build venv was created
by bootstrap. Existing pkg-config files can refer to their original owned
prefix. This is not a claim that the dependencies were rebuilt from scratch.

original-bytes records preserve exact original UTF-8 bytes and equal source /
archive SHA256, including CR progress output and build warnings. generated
records identify explanatory metadata. fingerprint-only records retain path,
length and SHA256 without copying QEMU C sources, historical patches, dependency
or executable bytes. No firmware, ROM, MPY, runtime, object or credentials are
included. The outer bootstrap argv is a root-provided actual-launch attestation
captured after execution, not an independent pre-saved ps/exec trace. Tool and
bootstrap-source captures are also post-build observations.

Portable verification needs only Python 3.10+ and this directory:
  python3 -B verify.py

Optional current-original comparison:
  python3 -B verify.py --check-originals --repo-root /path/to/repository

Optional exact isolated-index source replay needs matching external QEMU source
at the pinned commit and the matching repository patch files; it runs no guest:
  python3 -B verify.py --repo-root /path/to/repository \
    --qemu-source /path/to/prepared/qemu

The index excludes itself and covers every other archive file, including the
verifier and this README. Hashes verify consistency, not an external signature.
