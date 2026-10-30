# Capabilities and evidence boundaries

Read current device/Unit metadata and the operator-provided or deployed
OpenAPI contract before selecting a path. This standalone skill does not
carry a frozen list of supported products or inherit a historical firmware's
PASS. The service may report a modeled product that is unavailable on this
host because a runtime, ROM, flasher, firmware reference or peer dependency
is missing. Diagnose `missing_runtime_files`; do not hide unavailable targets
or change capabilities merely to enable a picker.

## What each result proves

| Observation | Permitted conclusion |
| --- | --- |
| Device/Unit in a catalog or visual picker | It is described; examine admission and limitations separately. |
| `backend_ready` / `creatable` | This deployment has the required runtime files and can admit that path, subject to request checks. |
| `runtime.status=implemented` / `host_admission.admitted` | A model/controller route is available for this host/configuration; functional behavior still needs execution. |
| Firmware upload/hash match | The server stored the submitted bytes. |
| Import/compose/static validation success | The image passed those compatibility/structure checks, not application execution. |
| Session `running` | The process/control channel is alive. |
| UIFlow START / binary LOAD | Source execution began / an import was dispatched; neither proves application readiness. |
| Valid application READY plus fresh expected behavior | That asserted behavior ran in the identified guest/window. |
| Unit injection accepted | The model accepted a fixture; confirm delivery through the actual guest driver. |
| Frame captured | Those pixels were observed; open the image before claiming visual quality. |
| Network/pcap control succeeded | The selected action/capture occurred; verify the expected guest/network exchange. |
| Owned session stopped and lease released | The observed owned runtime cleanup completed within its documented scope. |

Use a result vocabulary that separates causes:

- **Virtual PASS:** the explicit user path/assertions passed for the recorded
  firmware SHA, device, runtime/profile, assembly and fixtures.
- **Firmware/code FAIL:** the actual guest showed the relevant exception or
  incorrect behavior, with a reproducible current input/output window.
- **Model gap / PARTIAL:** a required controller, instruction, driver route,
  firmware feature or peripheral behavior is missing or incomplete.
- **Fixture gap:** required NVS/SD/user data, peer/account/device or test input
  was unavailable; do not classify absent provisioning as firmware failure.
- **Infrastructure/transport failure:** startup, capacity, credentials,
  dependency or API communication failed; application result is unconfirmed.
- **UNKNOWN / NOT RUN:** the needed execution or observation was not obtained.
  A failed query is not an empty result and a timeout is not proof of no effect.

## Compatibility is specific

Before an uploaded merged or segmented image runs, establish its chip, exact
board/profile, flash and effective PSRAM, partition/offset layout, required
controller coverage and eFuse/security mode. A product's advertised PSRAM
capacity is not the effective virtual-memory model. Manifest declarations and
static security checks do not authenticate firmware, perform live eFuse reads
or validate real production keys. Preserve contradictory/unknown evidence;
never downgrade required features or security claims to bypass rejection.

Unit support is device-local. Select confirmed wiring and admitted ports from
that host's metadata, and freeze it in the session. A PASS on another board,
firmware SHA or driver/controller path does not transfer. Attachments require
the firmware's real constructor/driver using the returned pins; Python-level
fake sensor values are not peripheral simulation. Units with partial models
may be useful within an explicitly tested subset, but retain their blockers.
PIR, touch, image, audio and other fixtures are synthetic virtual inputs, not
physical measurements. A read-only output must never become an injection input.

QEMU board/radio profiles can establish same-guest serial, frame, input, QOM
and selected network data planes. A separate `runtime=network` session cannot
be spliced together with another board session to claim one-device success.
Select profiles with their real firmware/ELF prerequisites; a matching symbol
name does not make an ELF from another build safe for hooks.

Tab5 is a partial backend: missing dynamic/controller-level paths remain
blockers where relevant. CardputerZero uses an independent Linux backend and
is outside this Device Service contract. Do not silently substitute another
board/backend. Discovery determines what this deployment actually exposes.

## Minimum evidence for a useful report

Keep a compact, redacted summary and put raw evidence in the operator's ignored
artifact area. Record:

1. Exact target, chip, runtime/profile and firmware SHA; original artifact SHA
   and normalized image SHA separately. Include known runtime/tool identity.
2. Owned session ID, creation/expiry, assembly with frozen pins, firmware/code
   revision and explicit fixtures. Do not publish real physical identifiers.
3. Expected assertions and fresh input/action order; serial offset windows and
   actual exception/output. Keep original failure evidence before fixing code.
4. Frame PNG/hash/dimensions where relevant, plus actual visual inspection
   status; Unit/controller outputs, network evidence or pcap when required.
5. Evidence ZIP/hash and validation, then terminal cleanup/lease/Flash retention
   state. Identify an unavailable export or cleanup uncertainty explicitly.

State/frame/serial/network calls are separate observations, not an atomic
snapshot. A PNG hash cannot establish layout, readability or interaction.
Read the actual image after meaningful UI changes. If the active model cannot
inspect images, provide the artifact and say that visual review was not done.
Do not promise a fixed FPS, first-frame latency, indefinite lease or automatic
renewal merely because polling is available.

## Physical and service boundaries

Virtual-device PASS is distinct from hardware PASS. It does not establish RF,
antenna/range/channel/roaming behavior, power, physical cache/PSRAM timing,
electrical limits, acoustics, optics or mechanics. Functional WPA2 pairwise
delivery does not establish every security mode, multicast/group-key behavior
or physical-link security. A launch flag or QOM property is not a physical
measurement.

Loopback forwards, restricted user networking, a shared Bearer token and the
current namespace runner are not an untrusted-firmware or multi-tenant sandbox.
Do not expose the service publicly, widen networking, invent isolation policy,
flash hardware or contact external accounts as part of a local simulation.
Stop only owned sessions; do not restart/drain shared services or workers.

Worker-local process cleanup, companion/pcap finalization and guest/controller
state are different evidence layers. Observe the selected runtime's actual
teardown; a stopped worker process does not prove termination of external
side effects. Same-VM UIFlow replacement only interrupts the previous program
and does not guarantee full native/IRQ/timer/thread cleanup. Unknown execution
after restart is observed and reconciled, never blindly replayed.

Current workstreams retain open firmware-family, controller, lifecycle,
isolation and physical-equivalence gaps. Do not present a successful subcase as
completion of an entire product/family. User confirmation of a preview and
authorization of an actual physical target remain separate from simulation.
