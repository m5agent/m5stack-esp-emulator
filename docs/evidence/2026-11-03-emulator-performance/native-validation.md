# Native Device Service UI performance — 2026-11-03

**Virtual-device validation.** Native runtime/controller models and exact firmware stay fixed. This covers public UI scheduling and the native SCS readback-to-model bridge, separate from browser-WASM CPU optimization and physical hardware.

Both sides use the current public.js. The before controller is from commit `3691870c27b028dde76202e42ecddba31d1547c1`; its missing native body bridge is reproduced as one static visual pose. The after controller independently reads frames, metadata and validated SCS state, then uses existing display-only interpolation.

| Device | Applied PNG updates/s before → after | PNG bytes per approximately 12 s before → after | Service CPU before → after |
| --- | ---: | ---: | ---: |
| StackChan | 1.25 → 27.17 | 30,974 → 590,587 | 0.92% → 13.63% |
| CoreS3 | 1.42 → 8.42 | 65,908 → 395,381 | 1.58% → 13.83% |

CPU 100% means one logical host core. These are actual applied PNG updates, including legitimate drawing in progress, rather than completed logical application frames or physical LCD refresh. Each steady sample lasts approximately 12 seconds on Chromium 156.0.8078.80 with the actual Apple M4 Metal model renderer.

## Functional and cleanup evidence

- Four real guest runs: 46/46 scoped checks PASS.
- StackChan after: 70 real QOM state changes, raw yaw [307, 613] and pitch [677, 850], with 47/32 distinct raw positions. Actual viewer render events produced 527 pose samples and 366 intermediate poses. DOM raw ticks, real joint targets, session and firmware identities match. Before: one static visual pose and zero native output callbacks.
- Both CoreS3 runs accept the actual controller longpress at (160,184), held 0.4 seconds, and produce the guest callback plus a readable Clicks:1 capture. StackChan touch is protocol acceptance only.
- All four evidence ZIPs precede purge=0 stop and pass contained-file hash/size verification. History and last frames remain readable; all four runtime processes exit.
- Capability/schema/firmware/session validation is mandatory for native SCS readback. Unsupported or failed readback stays unknown once; reset/new session retries. No host SCS values are generated.

## Limits and retained rounds

**REVIEW — complete-frame fidelity:** selected captures include partial guest redraws. Other retained same-runtime captures show complete expressions; the diagonal ambience is explicitly drawn by the exact hash-matched guest source. No atomic application-frame or pixel-fidelity oracle was run; this is not a controller-model image-fidelity fix.

**NOT RUN:** physical speed/torque/mechanics/electrical/RF/acoustic/optical behavior, long soak, multi-device capacity, other images or hosts. Startup speedup is deliberately excluded because before-side Flash preparation is cold and after-side cache is warm. Native UI evidence does not grant browser-WASM CPU/runtime PASS.

- r1 FAIL: UI harness SHA-field expansion error before guest allocation; preserved.
- r2 bounded PASS: LCD/input/cleanup, followed by diagnosis of the absent body bridge; preserved.
- r3 scoped PASS: display/readback/render/DOM/cleanup, including static-body before control; preserved.
- r4 scoped PASS: latest auto-route and WebCrypto UI, same exact native guest and controller/evidence checks; no browser runtime download.
- In r4, StackChan after uses auto with browser capability also enabled and correctly selects native. Both sides are asserted PublicSessionController; CoreS3 stays explicit service. No browser QEMU runtime is downloaded.

## Exact identities

- Native QEMU SHA256: `6d9af027e2f744208fc2503128f1772f436d7ca7358f9e53be597bc76800f39d`.
- StackChan firmware SHA256: `c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`.
- CoreS3 explicit LVGL candidate firmware SHA256: `e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554`.
- Before controller SHA256: `1b46cb4510e951a45a13ba57d9a596dfb4c928d2166aab007ca256bdf8eb52ba`.
- After controller SHA256: `8e845070de279746a3930adec7ca0a58c77bad308d2470f465494e7e1d15b250`.
- Common public.js SHA256: `a30b1125ef74e3539a3c64d16ff246cbc4ae67e0f9dda8936bc48477b7a22e31`.
- r4 raw report SHA256: `63b0c51cd86066ccba707fef59ea9598425c84b51afcd807c494789409b66b35`.

| Device / phase | Frame PNG SHA256 | Evidence ZIP SHA256 |
| --- | --- | --- |
| StackChan before | `16cd9fba9e34122d0ebe7711bba9555133ec95880b4d591e4978429a5c135f13` | `437325ff708d804446ab52456725a90d0000df4ca67263545567fb0e8139c6d7` |
| StackChan after | `e0943839fbed4a809f2f2cff2787d8f2dced86de711e563de6be956deaaa7304` | `b36d24507c885314dfcad71f0c1359ae5679d34314390cdc84f3b4f866085374` |
| CoreS3 before | `5b563aab77ec8218ac077f0c55aa7d273731a1047836af3c41237e2c54e319e9` | `eb8ecb2a7e0ae370f60d2a9f89edfd143f3bf62b53865b26bf817d77f236c56e` |
| CoreS3 after | `785e843c56c591ec9d960dcd5e9165803b294fd8c4b1d5ba1b19d8451b844a0d` | `bd83bef83e9221c6613ed732d48a1b174174b0f1430b52d81305bc07ec9f3501` |

The JSON companion lists all source, frame, retained-frame, workbench, observation, history, ZIP and round-report hashes. It excludes credentials, private endpoints, local paths and raw session identifiers; raw evidence remains outside source Git.

## Reproduction

Run `node platform/tests/test_public_native_performance.mjs --execute` with the required artifact environment listed in the JSON. Use an otherwise idle host and a fresh absent output directory; existing archives are rejected. The actual hardware renderer is checked before guest allocation. Host contract commands and coverage are listed separately in the JSON.
