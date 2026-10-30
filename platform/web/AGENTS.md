# Browser and model integration

The [root guidance](../../AGENTS.md) applies. This directory contains the public
workbench, service-backed session UI, browser QEMU adapter and model/Unit bridges.
Read [Pages deployment](../../docs/pages-deployment.md) for the static execution
contract and [the code map](../../docs/code-map.md) for service UI entry points.

## Keep execution lanes distinct

- Browser admission comes from `qemu-browser-profiles.json` intersected with the
  actual runtime's compiled profiles. A 3D shell, a compiled machine or native
  PASS does not admit browser firmware execution.
- `public-qemu-runtime.js` manages validated assets and the run; the instance
  iframe transfers one private port; `public-qemu-engine.js` owns QEMU/MEMFS,
  QMP, UART and nested pthreads. Preserve origin/owner checks, generation and
  cancellation fences, transfer ownership, bounded requests and disposal.
- Normal guest exit, iframe removal, owner notifications and actual CDP Worker
  disappearance are separate observations. Never count forced termination or
  context closure as a successful normal-exit fence.
- Preserve reference firmware/profile SHA binding, ROM/eFuse checks, explicit
  clock profiles and source/build provenance. Do not silently enable an SDK
  candidate, fallback runtime or unsupported feature for an uploaded image.

## Inputs, frames and models

- Route Web inputs through the guest controller and board wiring. Visual press
  feedback is not guest acceptance. Map physical keys/modifiers and transformed
  screen coordinates correctly; release must retain its original owner/source,
  including overlapping holds, pointer cancel and teardown.
- Display textures and actuator/Unit state must derive from the same guest's
  framebuffer/controller observations. Do not use input echoes or requested
  target values as device output. Keep freshness, unknown/unbound state and
  render/transport frame identity explicit.
- Keep `vendor/` imports pinned and reviewed. Use `sync_visual_models.py` for a
  model update, retain licenses/provenance and reviewed runtime patch hashes;
  do not edit generated vendor files or import a dirty upstream worktree as a
  new source baseline. A visual-only device stays visual-only.

## Verification and export

Start with the affected Node contracts in `platform/tests/`; the shared set is:

```sh
npm run --prefix platform/tests test:contracts
```

Use an affected model case rather than the full model sweep for a local mapping
change, for example:

```sh
node platform/tests/test_model_shell.mjs --case controller:cardputer-adv
```

These host/model checks are not firmware tests. Browser guest validation follows
the root isolated-site rule; record actual runtime/firmware/manifest identity,
input, serial/frame/data-plane results and Worker cleanup. Native results cannot
be spliced in. Do not run concurrent heavy builds or guests while measuring a
short input pulse or performance.

Export with `platform/tools/build_public_site.py` and follow the documented
admission/publication gate. Verify project-relative URLs, the asset closed set,
hashes, corresponding source/licenses and the absence of firmware/ROM, credentials
or private service endpoints. HTTP byte checks prove deployment integrity, not a
new guest run. Screenshot updates must show an actual identified UI/run and must
not imply wider firmware or hardware coverage.
