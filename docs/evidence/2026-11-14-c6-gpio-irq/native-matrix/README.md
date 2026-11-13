# Full native peripheral regression after C6 GPIO IRQ repair

Reviewed: `2026-11-14`. **Virtual-device validation: 70/70 PASS**, one attempt
per case, no automatic retries. This is a new complete native matrix run; it
does not replace the earlier old-runtime failures or targeted service evidence.

[Summary and source binding](summary.json) links one bounded case file per
machine. Each case records the original and VFS-composed firmware hashes, case
specification hash, runtime selection, serial/output/frame hashes, input and QOM
step counts from the frozen executed case, mutable Flash hash and executable
partition preservation. Every case preserved the original application partitions.
The matrix's ordinary serial, controller, audio/RMT/disk and framebuffer checks
passed according to each checked-in case's declared acceptance.

Execution was pinned to source commit
`0e00cdcbc99a8210af6485df1bcfd04a514bc8a1`, C6 runtime
`69493c4edccaab5bc24961982ddb9097dda11c9b3418f9cdc0aaa2b27ae865a4`, and unchanged
Xtensa runtime `5ce7d9f5ce397ce87935626c0284955714e0ed286fcce0cd91ca47f4f326040c`.
All required ROMs and 11 original firmware inputs were independently hashed
before execution and remained unchanged afterward. The six C6 cases explicitly
used the Nesso board profile; no runtime or fixture source was edited during
the run. Final inspection found zero owned guests remaining.

The final integration candidate at the time of comparison was
`014841a8fe082cf8aaaa57de898e0ac0f665aedf`. These are different source commits:
523 runtime recipe, patch, probe, fixture and runner files have identical Git
blobs and match the actual execution SHA256 inventory. The service's identity
implementation and generated API inventory differ outside this native matrix
path. Device Service acceptance on the final deployment remains a separate
gate; the comparison does not relabel execution as the later commit.

Reproduce with the fixed input files and explicit runtime paths described by
the [native regression guide](../../../../tests/AGENTS.md):

```sh
M5_QEMU_RISCV32="$c6_binary" M5_QEMU_RISCV32_ROM_DIR="$c6_rom_directory" \
  M5_QEMU_XTENSA="$xtensa_binary" M5_QEMU_XTENSA_ROM_DIR="$xtensa_rom_directory" \
  M5SW_C6_BOARD=nesso-n1 PYTHONPATH=.work/py \
  python3 tests/uiflow2/run_peripheral_matrix.py --out-dir "$private_evidence_directory"
```

The original raw run summary SHA256 is
`86e6654904be9b63ac0198db2861620d9bea7e1f3a0266ca6fef59a14ed8de4b`.
Full raw artifacts stay outside Git. This directory contains only bounded
observations, hashes and reproduction instructions.

Meshtastic, Bruce and Honeypot are not cases in this UIFlow VFS-probe matrix;
their original-BIN service nonregression is recorded separately. This run does
not establish browser-WASM, physical electrical behavior, NMI/source 31,
GPIO sleep/wake/filter timing, BMI270 IRQ generation or FT6336 trigger pulses.
