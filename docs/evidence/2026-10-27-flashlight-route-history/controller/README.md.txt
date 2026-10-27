UNIT-HOST-38 independent controller C evidence (2026-10-27)

This archive retains all 96 frozen input records from the independent audit:
86 files retain their exact original bytes; 10 Mach-O/DWARF executable bodies
retain only their original size and SHA256. No QEMU executable, firmware image,
ROM, MPY or ZIP is copied. Original and archived byte fingerprints are separate
fields. Original failures have not been overwritten or promoted to success.

Canonical comparison:
  originals/old-r3:       26 cases, 357 checks, 152 expected FAIL, exit 1.
  originals/candidate-r2: 26 cases, 357 checks,   0 FAIL,          exit 0.
Both use the same cases.c SHA256 recorded in index.json. They compile actual
read-only source fragments: GPIO register storage, W1TS/W1TC pad transition,
OUT_SEL MMIO commit, route query, AW3641 model, registry and route helper.
The harness never hand-calls the route helper or assigns a synthetic route
array. QOM, clock/timer delivery and IRQ types are shims. The unchanged LEDC
notification is a counting stub; this does not establish LEDC/RMT waveforms.

From any copied directory, with PYTHONPATH unset:
  python3 -I -B verify.py
  python3 -I -B verify.py --rebuild --out-dir /fresh/output/path
--rebuild alone also works and uses a temporary output directory. Rebuild
requires a C11 compiler at /usr/bin/clang. It compiles both frozen harness.c
files and matches exact stdout/stderr. It does not need the source worktrees,
the repository, Python packages, API access, network, guests or firmware.

originals/run.py is original extraction provenance, not the portable entrypoint.
It requires the original source tree when intentionally used to re-extract.
originals/verify.py is retained verbatim; the archive wrapper invokes it with
the explicit executable-omission option. Missing executable fingerprints are
not interpreted as missing text evidence or as rebuilt original binary bytes.

History kept separately:
- old-r1: compilation failed because the audit shim lacked a forward prototype.
- old-r2: 152 expected old-model failures, with unescaped quoted C expressions
  in stdout; this raw file is text, not valid JSONL.
- candidate-r1: 357 successful checks before the JSON formatting repair.
- permanent-tests-r1.log: wrong unittest module invocation failed to import.
- permanent-tests-r2.log: C suite passed; test scope helper had a path error.
- permanent-tests-r3.log: the final two permanent platform tests passed.

The permanent test source and its SHA256 are retained. That regression test
replays 0033/0038/0045/0046 with Git into an isolated temporary repository,
then compiles the actual current AW3641/registry/helper and GPIO commit hunk.
Its surrounding pad storage is a shim; the independent old-r3/candidate-r2
harness instead retains the full actual functional GPIO-controller fragments.

The source candidate's two C file hashes match the final source used by root
for runtime 3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1.
Build, guest, Web and matrix evidence is owned separately by the parent work.
This controller archive does not assign guest, Web or physical-hardware PASS.
Cold-route initialization, missing hard-reset observation, live S1 changes,
PWM/RMT waveforms and electrical/optical/thermal fidelity remain outside scope.

privacy-scan.json records UTF8, binary-extension, MAC and credential checks.
The local control token and its digest were compared in memory only; neither
was written into this archive or its scan receipt.
