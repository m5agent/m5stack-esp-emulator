Independent UNIT-HOST-38 C audit, 2026-10-27

Canonical same-suite comparison: old-r3 and candidate-r2. Both compile the actual
read-only source fragments using the same cases.c. Old: 26 cases, 357 checks,
152 expected failures, exit 1. Candidate: 26 cases, 357 checks, zero failures,
exit 0. Each route mutation enters the actual extracted esp32_gpio_write OUT_SEL
MMIO commit chain, rather than assigning a route array or hand-calling helper.
LEDC route callback is a counting stub; no LEDC waveform is claimed.

Run: python3 -B verify.py --rebuild-out /fresh/output/path
Add --check-sources only when the original exact source trees remain available.
If an archive intentionally excludes executable Mach-O harness files and retains
the receipt fingerprints only, add --allow-missing-executables. Rebuild compiles
both retained harness.c files and compares exact stdout/stderr with originals.

Do not overwrite old-r1, old-r2, candidate-r1 or any permanent-tests-r*.log.
Original failures remain distinct from final same-suite evidence. Old-r2 stdout
has unescaped C expression quotes and is raw text, not valid JSONL; old-r3 fixes
output encoding only. Canonical old-r3 and candidate-r2 are valid JSONL.

The permanent regression test source snapshot is retained separately. That test
replays 0033, 0038, 0045 and 0046 with Git in isolated temporary repositories,
then compiles actual Unit model/registry/helper and actual GPIO MMIO hunk.
Its surrounding pad storage is a shim. This is lower scope than the independent
full-controller extraction and is labeled accordingly.

This audit did not contact API, start guests or run a matrix. It cannot establish
guest, mounted Web or physical hardware PASS. See audit-summary.json for bounds.
