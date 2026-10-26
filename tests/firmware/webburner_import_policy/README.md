# WebBurner import policy probe

Last reviewed: `2026-10-26`.

This fixture verifies deterministic and fail-closed package selection:

- ZIP paths are normalized independently of the host filesystem;
- raw empty/`.`/`..` segments, Windows reserved names, case-only or Unicode
  normalization collisions, file/directory-prefix ambiguity and backslashes
  are rejected;
- symlink ZIP entries are rejected;
- multiple `manifest.json`/WebBurner manifests are rejected;
- multiple `sdkconfig`, `sdkconfig.defaults`, eFuse summary, `flasher_args.json`
  or SBOM resources are rejected instead of selecting the first sorted file;
- when both exist once, the effective `sdkconfig` takes explicit precedence
  over `sdkconfig.defaults`;
- a multi-build WebBurner package selects exactly one build matching the
  requested target SoC and otherwise fails closed.

Run:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/webburner_import_policy/run_test.py
```

This is static import validation. It does not flash, boot or otherwise execute
the selected image, and physical hardware remains `NOT RUN`.
