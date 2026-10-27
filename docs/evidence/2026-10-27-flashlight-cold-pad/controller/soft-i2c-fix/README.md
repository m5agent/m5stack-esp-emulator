# Soft-I2C pull-up regression and minimal fix

This archive covers source and host C logic only. It grants no guest, display,
stock-firmware or physical-hardware PASS. The first 825fd698 candidate remained
unaccepted after the shared S3 regression; its original evidence is retained
separately. Final runtime acceptance belongs to the parent validation record.

The new GPIO resolver exposed an existing implicit assumption: software-I2C
buses had default-high compatibility input but no owned board pull-up sources.
M5GFX first drives both lines low, then enables internal pull-downs and expects
the external I2C pull-ups to keep the released lines high before address probes.
The old bridge made SCL a known low and produced probe reads 0x1 instead of 0x3.

Only the actual software-I2C bridge initialization changed: each SDA/SCL gets an
independent owned weak pull-up handle. ACK/data input, IE, the GPIO resolver and
board callers stay unchanged. Opposing board/internal pulls remain explicitly
conflict/unknown; compatibility CPU reads recover the prior high level. This
does not claim that a resistance/voltage solver proved a known high. CoreS3
R20/R32 are independently documented as 2.2 kOhm/1 percent to 3V3 in the sibling
[official evidence](../../research/cores3-pullups/README.md); other bridges are
not assigned those resistance values.

`originals/bias-check/` retains the original before/after entire bridge C plus
actual GPIO fragments, compiler output, UBSan runs and full-TU syntax result.
Four S3 pin groups change from probe 0x1 to 0x3; SCL keeps IE=1, external=0 and
becomes known=0/conflict=1/board_up=1. The Core2 legacy line behavior stays the
same. Both old/new harnesses exit zero because they assert their respective
observed states: the old probe result is the reproduced regression, not PASS
of the device behavior. I2C endpoint methods, host clock/IRQ/QOM and aux blockers
are shims. The harness does not run a guest or establish protocol/hardware PASS.

`test-snapshots/` stores the two permanent tests and the existing pure-C replay
module/fixture they reuse. Those tests replay the actual current GPIO patch
stack and separately the pre-fix/fixed bridge; no `.work`, generated QEMU config,
glib or network is required. The archived repeat ran exactly two tests, both OK.
They cover CoreS3/StopWatch detector behavior, real bias ownership, reset and
hardware hand-off retention, unknown/conflict preservation, and unchanged
Core2 high/drive-low/release reads. Host-only handle removal checks ownership;
the product bridge and legacy listeners still have process lifetime, with no
dynamic hot-unplug API claimed.

Index records distinguish exact original bytes from path-redacted copies and
record source/archive SHA256, byte counts and each transformation. Only absolute
repository/home paths are replaced by `<REPO>`/`<HOME>`; the original path values
are intentionally not published. Source paths in the index are repository
relative. Original files and prior evidence were not rewritten. Executables
are fingerprint-only; no executable/object/firmware/ROM or `.git` is copied.
Hashes check consistency, not an external signature.

Portable verification (Python 3.10+, from any working directory):

```sh
python3 -B /path/to/soft-i2c-fix/verify.py
```

Optional offline recompilation of both archived standard-C harnesses (a C
compiler and its UBSan runtime are required; temporary outputs stay outside
the archive):

```sh
python3 -B /path/to/soft-i2c-fix/verify.py --replay-c
```
