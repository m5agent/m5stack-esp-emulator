# UNIT-HOST-20 raw PWM initialization A/B

Offline authoring only. No API, browser, guest, QEMU, compiler or firmware
binary has been executed/built/uploaded by this author. Only root may execute.

The exact five-file caller is `guest/{boot.py,main.py,probe_logging.py,
probe_config.py,pwm_route_program.py}`. On CoreS3 PORT.A it attaches one Buzzer
output endpoint, constructs `PWM(Pin(2), freq=2000, duty_u16=0)` exactly once,
emits `PWMR_READY`, and spends 60 guest seconds in a hold with only M5.update,
sleep, read-only PWM getters, serial heartbeats and screen drawing. There is
no post-constructor setter anywhere, no explicit zero workaround, no Unit
input, no GPIO/route mutation, and no BuzzerUnit/Haptic/SoftTimer/custom
callback patch. The diagnostic isolates initialization from the original
Buzzer.once timer-arity defect; it does not validate that driver or its timer.

The runtime or expected result is never embedded in the caller/config. Default
preparation reads the actual local CoreS3 reference hash and produces JSON only;
its expected base must still match the reviewed admitted reference. Host HTTP,
JSON/hash/PID and source-provenance helpers are a byte-exact copy of the accepted
source API common helper. Its unused execution/profile/runtime defaults are
not invoked; `run_acceptance.py` requires an exact runtime SHA on every live
execution and never fixes worker generation. The optional generation check
uses root's actual value.

`research-proof.json` re-verifies all 39 original raw QOM bodies at 0Hz/0% and
the first later 2000Hz/0% body against the original receipt SHA values. The
original probe and the explicit-zero workaround probe remain separate inputs.
Bundled official UIFlow2 Pin/Buzzer/Button docs and the existing fixed official
MicroPython/IDF source were read before authoring. Five getter functions are
extracted and hashed: machine PWM freq/get_u16 -> IDF ledc_get_freq/get_duty ->
HAL register get APIs; these functions contain no LEDC set/update/apply or GPIO
route calls. This is static source-path evidence, not a new dynamic native
MMIO trace or a claim about every firmware release. Existing C-fragment route
ordering evidence is preserved as text; no C code is compiled or executed.

Default offline prepare (fresh child output required):

```sh
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-pwm-route-acceptance-20261026/run_acceptance.py \
  --out-dir .work/unit-pwm-route-acceptance-20261026/prepared-r1
```

After independently verifying idle service, root runs the existing-runtime
baseline with its exact executable hash set in `PWM_BASELINE_RUNTIME_SHA256`:

```sh
M5_UNIT_WEB_BRIDGE=1 PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-pwm-route-acceptance-20261026/run_acceptance.py \
  --execute --expected-runtime-sha256 "${PWM_BASELINE_RUNTIME_SHA256}" \
  --expect-init-frequency 0 \
  --out-dir .work/unit-pwm-route-acceptance-20261026/baseline-r1
```

A collected zero-Hz baseline is `status=FAIL_REPRODUCED` and
`initialization_status=FAIL_REPRODUCED`, never initialization PASS.
`harness_check_status=PASS` only means the expected failure and its evidence
were collected/cleaned correctly. No observation is rewritten to 2000Hz.

After root installs/freezes the candidate runtime and again verifies idle
service, pass its exact executable hash via `PWM_CANDIDATE_RUNTIME_SHA256`:

```sh
M5_UNIT_WEB_BRIDGE=1 PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-pwm-route-acceptance-20261026/run_acceptance.py \
  --execute --expected-runtime-sha256 "${PWM_CANDIDATE_RUNTIME_SHA256}" \
  --expect-init-frequency 2000 \
  --peer-result .work/unit-pwm-route-acceptance-20261026/baseline-r1/result.json \
  --out-dir .work/unit-pwm-route-acceptance-20261026/candidate-r1
```

Candidate admission requires identical derived firmware SHA, caller/effective
CAS and complete source request, plus a different exact runtime binary. No
candidate-specific text, firmware rebuild behavior or config is inserted.
Candidate tolerance is 2000 +/- 1Hz, matching the existing audio observation
tolerance; duty must remain exactly zero (floating representation tolerance
1e-9). Eight serial-before -> actual controller/QOM -> fresh serial-after
windows must stay after READY and before HOLD_DONE, with a newer guest
heartbeat and unchanged serial prefix. Python does not generate guest markers.

The real product Web captures full screenshots and live DOM/HTTP readbacks;
output-only cases explicitly require zero Unit input POSTs/control actions.
A complete nonblank 320x240 native PNG is decoded and saved; decode does not
establish readability of every UI state. Direct PID/executable SHA, actual
worker/generation, source pin, frozen contract, serial and frame are bound in
the evidence ZIP before `DELETE ?purge=0`. Retained history/last frame, released
mutable Flash, owned PID exit and idle health are required even on failure.

Terminal replay is offline:

```sh
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-pwm-route-acceptance-20261026/run_acceptance.py \
  --check --out-dir .work/unit-pwm-route-acceptance-20261026/candidate-r1
```

`self_check.py self-check-r2` passed 38 offline checks under denied socket,
HTTP, Client, subprocess and legacy BIN builders. Explicit synthetic negative
cases reject post-init zero/frequency setters, extra constructors, injected
runtime config, callbacks, stale/unrelated UART, hold completion, wrong
frequency/duty/NaN, changed A/B firmware/CAS/runtime and missing CLI identity.
Its synthetic values are checker tests, never guest/controller PASS.

No route-mutation negative case or full LEDC period/fade semantics is claimed.
Those remain separate repository C tests/guest validations. Physical hardware,
acoustic behavior and full shared-runtime regression remain separate gates.
