# Core2 IMU matched A/B diagnostic

Both single attempts PASS; the original full-run frame-marker failure was not reproduced. Intermittence observed; cause not established or fixed.

The original full matrix remains 66 PASS / 1 FAIL and was not modified. This is virtual-device repository regression only; hardware NOT RUN.

Same firmware, source, wait/input/QOM values and validators; each variant ran once without retries.

| Variant | Runtime SHA256 | Status | (4,4) RGB | Expected serial accel/gyro |
| --- | --- | --- | --- | --- |
| old | d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff | PASS | [0, 255, 0] | False |
| new | b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2 | PASS | [0, 255, 0] | True |

Initial composed firmware SHA256: `04ba1e4c5a9b9a286bfd7c66b4693e75a508167d4f0a7ba794a0cdfbf85b8a4b`.

Source inputs, tooling, runtime binaries, source manifests, ROMs and all original full-run evidence retain identical before/after hashes. Exact commands, timestamp freshness and real PPM pixel/serial analysis are in report.json; frozen hashes are in source-freeze-before.json and source-freeze-after.json.

The original full-run initial composed firmware hash also equals the two A/B hashes. Both fresh serial logs satisfy the unchanged probe acceptance predicate (accel x/y and gyro x/y). The old run exits with last printed gyro-z=0.0; its all-six-target-values serial observation is false. New and original logs contain gyro-z=30.0. The probe already exits after the x/y predicate, while the runner applies QOM fields sequentially. This distinction is recorded in supplemental-analysis.json; no additional run or weaker validator was used.
