# Exact Unit agent guide acceptance

This harness is prepared for root to execute after the five-probe API batch. The authoring agent has made no API call, launched no browser or guest, and never executed the extracted guest Python on the host. Offline preparation only reads text, parses AST/JSON data and writes under this directory.

`run_guide_acceptance.py` extracts the exact Button `main.py` heredoc and the exact HUB+ENV III+NCIR Python fence from `docs/unit-agent-api.md`. It records line spans, full guide SHA and snippet hashes. Button True→False comes from the guide's host-script AST literal; HUB topology and ENV 28.5/61.0/100800 plus NCIR 24.0/37.5 come from its JSON fences. No guest text is rewritten. The payload contains only `files={"main.py": exact_text}` plus the documented optional exact base SHA, so this run also validates automatic generated `boot.py`, caller-only CAS and effective source CAS separately.

Run both examples as separate visible sessions, using a fresh directory:

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-guide-live-20261026/run_guide_acceptance.py \
  --execute --api-url http://127.0.0.1:8787 \
  --out-dir .work/unit-guide-live-20261026/live-r1
```

`--case button` or `--case hub-env-ncir` selects one example. The default runtime SHA is `29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`; the CoreS3 base is pinned to `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`. Existing bridge Node/Chrome environment overrides are honored.

Offline preparation or replay:

```sh
/opt/miniconda3/bin/python3.12 -B \
  .work/unit-guide-live-20261026/run_guide_acceptance.py \
  --prepare-only --out-dir .work/unit-guide-live-20261026/new-preparation

PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-guide-live-20261026/run_guide_acceptance.py \
  --check --out-dir .work/unit-guide-live-20261026/live-r1
```

Each input is submitted by the real `Client`/`WebUIBridge` product DOM. It first records the actual serial `next_offset`, then saves all cursor-contiguous chunks and requires fresh guest values after that cursor. ENV tolerance is 0.2 °C/0.2 %/1.5 Pa; NCIR tolerance is 0.021 °C, consistent with the existing real-driver sensor tests. After NCIR injection, fresh ENV and NCIR values must both appear in the same guest stream. Each leaf requires its own nonzero transactions/read bytes/written bytes/input events, and injecting one leaf must leave the other leaf's physical input values unchanged. The passive HUB is never credited with a synthetic I2C address.

Artifacts bind exact source API request/response, canonical caller CAS, generated boot/effective CAS, mandatory startup source pin, direct runtime PID/executable hash/worker generation, real HTTP bodies/status, actual DOM/HTTP matching, frozen Unit source hashes, fresh guest serial/QOM and native PNGs. Native frames are checked for PNG geometry/nonempty colors; root should visually inspect the Button PRESSED/RELEASED frames if making a readable-UI claim.

The `finally` path always attempts ZIP before `DELETE ?purge=0`, retained metadata/frame/source identity, PID exit, mutable Flash release and health active count zero. A cleanup failure ends the batch. A browser failure still permits evidence/stop attempts. `--check` independently validates saved hashes, exact guide extraction, raw HTTP backing, cursor continuity/fresh readings, topology/leaf counters, DOM/HTTP, ZIP source provenance and retained cleanup. It requires distinct session IDs for the two examples.

`source_api_common.py` is a frozen copy of the prior host-side API harness, used only for transparent HTTP recording, canonical JSON hashing, native PNG inspection and read-only PID-existence checking. Its CLI and guest-preparation functions are never called by the guide harness. Existing product Client/Bridge files remain unchanged. No binary build/upload shim or fabricated Client response is used.

This prepares a virtual-device guide validation. Hardware, electrical behavior and full visual readability remain separate evidence categories.
