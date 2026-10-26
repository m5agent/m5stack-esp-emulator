# FlashLight Web evidence, 2026-10-27

Mandatory controller / mounted material / current frame validation: PASS.
Optional browser response-body capture: PARTIAL (four observed empty HTTP 200
frame bodies). Archive byte integrity is a separate verification category.
Hardware execution: NOT RUN. No optical, photometric, thermal, current, power,
mechanical or physical electrical equivalence is established.

Run `python3 -B verify.py` from this directory or by absolute path. The verifier
uses only the Python standard library and performs no HTTP, browser or device
actions. `--check-originals` additionally checks the absolute original files on
the originating machine; it is optional and is not portable to another machine.

## Contents and original-byte identity

- `artifacts/` mirrors all 1,336 files originally present in the owned Web work
  folder, including plans, observer versions, coordination files, and all three
  independent live attempts. The final r3 directory preserves all 624 original
  files, including its original report and post-run verification.
- `regressions/` contains the five exact real reports present in the original
  seven-test verification index. `regression-map.json` maps their new locations.
  The FlashLight fixture and pure visual mapping checks originally printed only
  to tool stdout; no original report or stdout file was captured. This archive
  does not reconstruct those outputs or rerun tests to present new files as old.
- `artifact-manifest.json` records original and archived sizes and SHA256 for
  every copied file. Original paths are provenance, not portable dependencies.
  Generated archive instructions / assessment / verifier files are identified
  separately. The manifest excludes its own recursive hash.
- No credential file, firmware, ROM, ELF, native executable or MPY binary is
  included. Ordinary PNG screenshots/frame entities are explicitly admitted;
  HTTP `.response` files are classified by their actual bytes. No Markdown
  source is treated as an active repository document: this text uses `.md.txt`.

## Independent live attempts

1. `artifacts/live-cores3-torch-r1`: original FAIL retained. Its five mandatory
   on/off/unknown/recovery stages were observed, but the observer wrongly tried
   to read 185 HTTP 304 bodies and recorded errors. The observer source was not
   copied before this run. `observer-r1.reconstructed.mjs` is explicitly an
   after-run reconstruction by reversing the later 304-only fix; its exact SHA
   matches the original run's source hash. Its provenance file does not claim
   an original before-run capture.
2. `artifacts/live-cores3-torch-r2`: original FAIL retained. The observer source
   was actually saved before the first API request. Initial controller, mounted
   material and direct frame observations exist, with partial screenshots.
   The stage locator detached during screenshot capture. Its precise cause is
   UNCONFIRMED; a default 3D session-limit race was a hypothesis, not a proven
   diagnosis. No later result overwrites or promotes this run to PASS.
3. `artifacts/live-cores3-torch-r3`: independent final five-stage mandatory PASS,
   service generation 42. The actual observer source was saved before API use,
   and before/after source hashes agree. All five screenshots passed on their
   first attempt; the default session order stayed 0 and `allowThree` stayed
   true. No product 3D limit or input state was overridden.

The final run observes initial steady Torch on -> off -> on -> real slow EN
modulation classified unknown -> steady on recovery. Five distinct executions
retain the same QEMU PID and firmware. Brightness is [1, 0, 1, 0, 1], and output
known is [true, true, true, false, true]. FixedWhiteLed state and emissive material
are inspected on the actual mounted vendor component, with fixed white color
and no glow. Torch brightness is qualitative, not a light-output measurement.
The S1 mode fixture is creation-only; no visual detent mapping is asserted.

There are 72 mandatory direct GET observations and 318 actual browser response
observations. Each stage includes independent raw QOM properties, fresh guest
serial/execution identity, a valid nonempty current PNG and actual mounted
display center pixels / execution and revision metadata. All five actual Web
`/units` JSON observations are nonempty and are checked independently. The
25 final image artifacts are the five sets of direct frame, WebGL render,
Unit panel, viewport and stage screenshot. Their bytes/hashes and PNG structure
are checked; guest center pixels are independently decoded by the verifier.

The observer itself sends GET only. Program changes are performed by the root
runner through real same-VM UART execution after owned command-file requests.
The archived hold / command / observation / done files preserve that ownership
and sequence. No controller setter, fake API response, requested brightness,
LEDC duty, or synthetic mounted result supplies the validation values.

## Optional browser-body capture is PARTIAL

See `browser-capture-assessment.json` for all four affected response indices,
timestamps, URL/method, Content-Length, capture sequence, execution/revision and
frame header hashes, plus their mandatory nonempty-frame counterparts.

- 193 HTTP 304 observations correctly have protocol-level `body_absent`
  metadata. They have no `.response` body file and no empty-entity substitute.
- Of 125 HTTP 200 observations, 121 have nonempty captured bodies. Four frame
  observations (indices 4, 5, 82, 141) saved zero bytes despite advertised
  Content-Length 319, 319, 302, 319. These are original empty browser-body
  observations, not PNGs and not proof that the server entity was absent.
- Those four observations precede the corresponding mandatory phase capture
  windows. Their advertised frame hashes match the independent actual PNGs,
  but that does not make the optional bodies complete. Their precise cause
  remains UNCONFIRMED.
- Mandatory frame and mounted lamp evidence does not use those empty files.
  Actual display center pixels and execution/revision metadata are sampled
  separately against valid direct PNGs. Ordinary-session display SHA fields
  are response metadata, not an independent hash of all decoded texture pixels.
  The exact browser transfer that populated each display texture was not traced.

The original final-run report's observer error counter did not classify these
empty HTTP 200 bodies as incomplete. It remains unchanged as original evidence.
The supplemental assessment and this directory's verification explicitly state
PARTIAL for optional browser-body completeness; they do not convert it to PASS.

Earlier attempts also retain their actual empty HTTP 200 body observations
(three each in r1 and r2). None is rewritten or used as a 304 entity substitute.
