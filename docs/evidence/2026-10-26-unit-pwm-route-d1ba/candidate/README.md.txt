# UNIT-HOST-20 GPIO-route candidate

Candidate cold build `d1ba0063…`; firmware/guest validation is pending root. UNIT-HOST-20 remains OPEN.

New 0038 refreshes actual LEDC register observations after a changed GPIO OUT_SEL signal field. Same-layout realized instances are notified; unrealize removes them. Endpoint observers filter SoC layout. No register write or LED intensity action is replayed. Existing unroute getter gating, zero-duty configured frequency, sigout/timer masks and DUTY/DUTY_R readback remain.

Exact candidate/baseline C functions were compiled in a host-only stub. Candidate covers route establishment, removal, rebind with current state, channel reuse, both layouts, masks, readback and lifecycle (18 grouped scenarios). Frozen baseline independently reproduces route-after-init 0Hz, manual observer 2000Hz and cross-layout endpoint write; candidate rejects the latter. This is offline C evidence, not dynamic guest MMIO tracing or physical behavior.

Eight-patch source reverse-to-clean-base and forward replay PASS; cold QEMU compilation used entirely new source/build objects with hash-verified existing dependencies. Frozen 29d8 source, receipt, seven patches and binary remain byte-identical. No service, browser, API, firmware runner or guest was invoked by this candidate work.

Related 8 contracts PASS. First complete platform suite: 652 ran, 628 passed, 22 skipped, two expected docs-count/snapshot failures. Runtime/peripheral/profile validators PASS; project_snapshot is STALE until root updates authority docs and regenerates it. Raw first-run logs are preserved; no full-suite rerun was performed. Root owns subsequent Device Service A/B and shared-controller/full regression.

The issue is not FIXED by this report. Full PWM cycles, fade, clocks, inversion and physical equivalence remain separate questions. See receipt.json, source-replay.json, actual-c-fragments.json and cold-build.log.
