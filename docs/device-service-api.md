# Device Service API v1

Last reviewed: `2026-10-26`.

Status: local MVP with unified-device runtime contract `1.35.0` and bounded
storage retention implemented on `2026-10-24`.

The service creates an on-demand virtual M5Stack device, flashes an exact
firmware artifact into an isolated virtual-flash copy, and exposes serial,
frame, input and QOM operations through HTTP.

Current scope:

- external Unit protocol inventory and confirmed host-port wiring are available
  through `/units`; attachment execution is enabled per model/controller, not
  inferred from a visual model or a documented chip;

- enabled: 12 QEMU-backed ESP32 devices;
- Tab5: enabled through esp-emu, with `peripheral_status=partial` and explicit
  warnings;
- excluded: CardputerZero;
- single-device runtime: `qemu-unified` is the canonical runtime for one
  board + radio evidence bundle when the selected profile supplies the
  requested surfaces. `qemu-wifi` is a WiFi-only variant of the same QEMU
  guest, `qemu-ble` remains a compatibility alias, and `runtime=network` is a
  diagnostic lane rather than a complete-device test;
- network emulation: `runtime=network` remains available for diagnosis on
  S3/C6; StickS3 also supports a Wi-Fi-only board lease through
  `uiflow2-sticks3-wifi`, while StickS3, CoreS3, Cardputer ADV, StopWatch,
  AtomS3R, PaperColor, PaperMono, StackChan and StamPLC use one combined
  WiFi+BLE+board QEMU lease through their unified profiles; environment-gated
  Core2 adds `core2-unified` through the classic ESP32 OpenMAC/HCI QEMU path
  and `core2-native-hci` as the canonical no-GDB stock-firmware native-HCI
  path. `core2-native-vhci` remains an explicit GDB diagnostic/compatibility
  profile;
- NanoC6 adds `nanoc6-hci-ble`: board peripherals, RMT WS2812/IR, QEMU C6
  WiFi DHCP/HTTP and UART1 HCI BLE run in one C6 guest;
- Nesso N1 adds `nesso-unified`: display/touch, PI4IOE, power telemetry,
  BMI270, SX1262, IR, buzzer, QEMU C6 WiFi DHCP/HTTP and UART1 HCI BLE run in
  one C6 guest;
- sessions: active leases are process-local and reserved in a persistent
  worker registry; stopped/failed metadata, events and last-known evidence are
  restored from each session directory after a service restart. A running
  local QEMU can be re-attached only after PID start-time, session QMP
  ownership and `query-status=running` checks;
- evidence: serial/QEMU logs remain under the configured state directory.
  QEMU radio sessions add pcap summaries, network policy evidence and a
  link-fault control for reconnect tests; versioned firmware manifests add
  capability/security preflight.
- storage: stopped/failed history is bounded by age, count and bytes; session
  Flash files are released after stop unless explicitly retained, and
  unreferenced artifact/firmware/prepared-flash caches and abandoned upload
  staging are garbage-collected.

The architecture and future pooling direction are documented in
[`simulator-service-architecture.md`](simulator-service-architecture.md).
The machine-readable contract is
[`device-service.openapi.yaml`](device-service.openapi.yaml) and is also
served at `/api/v1/openapi.yaml`.

## External Units

`GET /units?device_id=cores3` returns the fixed Unit protocol inventory, runtime
implementation status and confirmed host wiring. `implemented` means the C
controller model is available for validation; it does not imply a guest or Web
functional PASS. `runtime.hosts` is explicit admission; a host does not inherit
another host's validation. `runtime.guest_validation` binds a recorded device,
firmware, runtime and Web report; additional hosts have separate
`runtime.host_validation` records. Unsupported combinations fail with
`409 runtime_model_gap`.

`runtime-profiles.json` owns current runtime status. The compatibility aliases
`model_status` and `blocker` follow that profile (or its session-frozen copy).
`research_snapshot` preserves the original protocol-research status and notes;
it is not current capability or admission evidence.

`POST /sessions` accepts optional `units` with stable `id`, `unit_id`,
`port_id` and `initial` fields. Pins and QOM paths are selected by the service.
For a passive HUB, children additionally supply `parent_id` and select one of
`grove-1`, `grove-2`, `grove-3` as `port_id`. Children inherit the real upstream
pins; a HUB has no I2C address or switching register. Cycles, occupied slots,
duplicate I2C addresses and unmodeled parallel GPIO drive contention fail
closed. Multiple parallel leaves currently require I2C. This is a functional
bus model; aggregate current, voltage and physical electrical limits are not
validated.

`GET /sessions/{id}/units` queries the live QOM model and returns `properties`,
per-property `errors`, `definitions` and `contract_hashes`. The definitions and
QOM mapping are frozen when the session is created. Editing the catalog cannot
change the input meaning of an active session or its retained history.
Stopped sessions return their last snapshot with `source=persisted`.
`contract_status=frozen` identifies a recorded contract. Legacy history without
one is `unrecorded`; a malformed contract is `invalid`. Such history retains its
old values, has no reconstructed definitions or current-catalog hashes, and
rejects Unit writes with `409 unit_contract_unavailable`.

`POST /sessions/{id}/unit-input` accepts exactly `{id, values}`. Values are
validated against the session's input schema before QOM writes; unknown fields,
outputs, invalid array lengths, malformed hex and nonfinite values are rejected.
Successful injection establishes model acceptance; guest serial/bus observations
are still required to prove firmware consumption. The evidence ZIP includes
`units/runtime.json`, `units/state.json` and `units/contract.json` alongside
serial and framebuffer evidence. Request it before stop and retain history with
`purge=0`.
A copyable source-to-session workflow, including a Button input and a passive
HUB with multiple I2C Units, is in [External Agent Unit API](unit-agent-api.md).
Attachments are configured before the guest starts; changing the topology
requires a new session. The guest must initialize the corresponding drivers.

Controller-side rejection, such as a full UART FIFO, returns
`409 unit_input_rejected` while preserving the healthy QMP connection. A broken
transport remains `503`; a command timeout remains `504`.

## Start the service

```bash
python3 platform/tools/serve.py 8787 \
  --state-dir platform/.cache/service \
  --max-sessions 12 \
  --max-per-device 8 \
  --session-ttl 1800
```

For HTTPS or mTLS:

```bash
python3 platform/tools/serve.py 8787 \
  --bind 0.0.0.0 \
  --api-token-file /secure/service.token \
  --tls-cert /secure/server.crt \
  --tls-key /secure/server.key \
  --tls-client-ca /secure/worker-ca.crt \
  --security-reload-drain-timeout 30
```

The defaults can also be overridden without changing the command line:

```bash
M5_SERVICE_MAX_SESSIONS=12 \
M5_SERVICE_MAX_PER_DEVICE=8 \
./start.sh
```

Storage retention defaults can be changed with:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `M5_SERVICE_HISTORY_TTL` | 604800 | seconds before stopped/failed history is pruned; `0` disables age pruning |
| `M5_SERVICE_MAX_HISTORY_SESSIONS` | 100 | maximum retained stopped/failed sessions; `0` disables the count limit |
| `M5_SERVICE_MAX_HISTORY_BYTES` | 2147483648 | maximum retained history bytes; `0` disables the byte limit |
| `M5_SERVICE_MAX_CACHE_BYTES` | 4294967296 | target maximum for artifact/firmware/flash-cache data |
| `M5_SERVICE_CACHE_GRACE` | 86400 | seconds before an unreferenced cache entry becomes eligible for GC |
| `M5_SERVICE_MIN_FREE_BYTES` | 2147483648 | free-space reserve required before writes or new leases |
| `M5_SERVICE_RETAIN_SESSION_FLASH` | false | retain every stopped session's full mutable Flash |
| `M5_SERVICE_STORAGE_PRUNE_INTERVAL` | 30 | janitor storage-prune interval in seconds |

Local worker identity and heartbeat can be controlled with:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `M5_WORKER_ID` | generated | stable worker identity persisted across process generations |
| `M5_WORKER_STATE_PATH` | `<state-dir>/worker.json` | worker lifecycle and lease record |
| `M5_WORKER_HEARTBEAT_INTERVAL` | 5 | heartbeat write interval in seconds |
| `M5_WORKER_STALE_AFTER` | 15 | age at which a heartbeat is marked stale |
| `M5_JOB_LEASE_SECONDS` | 60 | remote job lease renewal/expiry interval; clamped to 5–3600 seconds |
| `M5_SERVICE_API_TOKEN_FILE` | unset | file-backed service/worker token; mutually exclusive with the in-memory token option |
| `M5_SERVICE_API_TOKEN_PREVIOUS_FILE` | unset | optional token accepted only during a bounded overlap; remove it and send `SIGHUP` to finalize |
| `M5_SECURITY_RELOAD_DRAIN_TIMEOUT` | 30 | seconds to wait for active requests before a `SIGHUP` reload is canceled |
| `M5_SERVICE_TLS_CERT` | unset | server certificate chain; requires `M5_SERVICE_TLS_KEY` |
| `M5_SERVICE_TLS_KEY` | unset | server private key; requires `M5_SERVICE_TLS_CERT` |
| `M5_SERVICE_TLS_CLIENT_CA` | unset | client CA; when set, HTTPS requires a trusted client certificate |
| `M5_SERVICE_TLS_CLIENT_CA_PREVIOUS` | unset | optional previous client CA trusted only during overlap; remove it and send `SIGHUP` to finalize |
| `M5_WORKER_TLS_CA` | system trust | custom CA bundle used by `worker_agent.py` |
| `M5_WORKER_TLS_CLIENT_CERT` | unset | worker client certificate; requires `M5_WORKER_TLS_CLIENT_KEY` |
| `M5_WORKER_TLS_CLIENT_KEY` | unset | worker client private key; requires `M5_WORKER_TLS_CLIENT_CERT` |

Only one live service process may own a worker state directory. A second
process fails closed with `409 worker_state_locked`.

The janitor never deletes provisioning, flashing, booting or running sessions.
Manual inspection and pruning are available through:

```bash
curl -sS http://127.0.0.1:8787/api/v1/storage
curl -sS -X POST \
  'http://127.0.0.1:8787/api/v1/storage/prune?include_cache=1'
```

`POST /storage/prune` applies the same retention pass as the background janitor.
Use `include_cache=0` to prune only session history.

### Local worker lifecycle

`GET /worker` returns the stable worker ID, process instance ID, generation,
heartbeat, stale state, active lease IDs, abandoned leases and bounded recent
results. `POST /worker/drain` stops new lease admission while allowing active
sessions to finish; the state becomes `drained` when the last active lease is
released. `POST /worker/resume` restores admission.

Each session records the worker ID and generation that owned it. When a new
service generation finds active leases in the previous `worker.json`, those
leases are recorded under `abandoned_leases`. A QEMU session can be re-adopted
only when its persisted PID start time still matches, its command line owns the
session-specific QMP socket, QMP responds, and `query-status` reports
`running`. The new service generation then reserves a fresh local lease and
sets `reattached_process=true`. `recovery_scope=qemu-control-plane` means only
QEMU/QMP was restored. For trusted-host unified sessions,
`recovery_scope=qemu-control-plane+companions` additionally means the HTTP
fixture was recreated on its profile port with durable request history and a
surviving BLE peer was adopted only after PID, exact start-time and complete
command-SHA256 checks. Companion ownership failure rejects the re-attach.
Unverified, expired or incompatible sessions become interrupted `failed`
history. Stopped/failed sessions and their last-known evidence remain readable.

`POST /sessions` accepts an optional non-secret `owner` label of at most 128
printable characters. The label is stored with the worker lease and does not
grant access or identity.

It also accepts a caller-stable `idempotency_key` of 1–128 printable
characters. The service persists only SHA256(key), the canonical request hash
and the resulting session ID under `session-idempotency.json`. An identical
retry returns the original session with `idempotent_replay=true`; reusing the
key for different request content returns HTTP `409`
`session_idempotency_conflict`. The mapping survives service restart. Raw keys
and request bodies are not written to the mapping file.

This section describes local worker lifecycle control. The separate durable
job queue below provides remote enqueue/claim/lease supervision, but it does
not execute jobs, transfer an evidence bundle or place work across a production
multi-host scheduler. Local QEMU/QMP control-plane re-attach and trusted-host
unified HTTP/BLE companion continuity are implemented. Namespace-managed,
Tab5 and cross-host companion recovery plus a continuous external evidence
stream remain `NOT RUN`.

### Remote worker directory MVP

The service persists remote-worker enrollment under
`<state-dir>/workers.json`. This directory records stable worker identity,
instance/generation, heartbeat, drain/stop state, endpoint, bounded
capabilities, active lease IDs and up to 32 recent result records. It does not
launch a worker, assign a session, transfer evidence files or recover a live
QEMU process.

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/workers \
  -H 'Content-Type: application/json' \
  -d '{
    "worker_id": "linux-east-1",
    "instance_id": "boot-20261024-a",
    "generation": 1,
    "stale_after_seconds": 30,
    "endpoint": "https://worker.example:8787",
    "capabilities": {"qemu": true, "network_namespace": true},
    "active_lease_ids": []
  }'

curl -sS http://127.0.0.1:8787/api/v1/workers
```

Registration is idempotent only for the same `worker_id`, `instance_id` and
`generation` while that instance is live. A live worker cannot be replaced by
another instance. A stale or stopped worker must be replaced with a strictly
higher `generation`; a stopped identity cannot heartbeat back into service.
Endpoint URLs must use HTTP(S), contain no credentials, query or fragment, and
the serialized capability object is limited to 16 KiB. The directory is
bounded to 128 workers, 128 active lease IDs per worker and 32 recent results
per worker.

Heartbeats update `ready`, `draining` or `drained`, active lease IDs and
capabilities. `drain` becomes `drained` only when the reported active lease
list is empty. `stop` is terminal for the current generation. A result record
contains only `lease_id`, result `state`, optional `evidence_sha256` and
`completed_at`; it is an index to external evidence, not the evidence bundle.

### Durable remote job queue

`<state-dir>/jobs.json` persists jobs, idempotency keys, capability
requirements, worker leases, retry counts and terminal results. The queue is
pull-based: a ready registered worker claims the oldest compatible job, then
heartbeats and reports a result. A request is limited to 64 KiB; the queue is
bounded to 1024 jobs and 10 attempts per job.

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "label": "sticks3-network-review",
    "request": {
      "device_id": "sticks3",
      "runtime": "qemu-unified",
      "profile": "uiflow2-sticks3-unified"
    },
    "required_capabilities": {"qemu": true, "pcap": true},
    "max_attempts": 3,
    "idempotency_key": "review-20261024-sticks3-a"
  }'

curl -sS -X POST http://127.0.0.1:8787/api/v1/jobs/claim \
  -H 'Content-Type: application/json' \
  -d '{
    "worker_id": "linux-east-1",
    "instance_id": "boot-20261024-a",
    "generation": 1
  }'
```

The claim response includes a `lease_id` and lease expiry. The worker must
heartbeat with the same identity and lease before expiry, then submit
`PASS`, `PARTIAL`, `FAIL` or `REVIEW` to `/jobs/{id}/result`.
`FAIL` is terminal for that attempt and marks the job failed; lease expiry,
worker staleness, worker stop, a missing worker or a generation replacement
requeues the job while attempts remain, otherwise marks it failed. Operator
cancel is terminal. These transitions are persisted across service restart.
The terminal job result stores the originating `lease_id` and worker identity,
so evidence can be tied back to the exact claim after the lease itself is
closed.

Lease ownership also fences stale side effects. After expiry, staleness,
worker stop, generation replacement or operator recovery causes a job to be
requeued, the next claim receives a new `lease_id`. Heartbeat or result
requests using the previous lease return `409 job_lease_mismatch` and cannot
overwrite the new claim. `WorkerAgent` treats a non-transient ownership error,
or exhausted transient recovery for job heartbeat, as a local fence: it
interrupts session readiness/evidence waits, stops its worker-local runtime
session, writes a local `FAIL` result with `lease_fenced=true`, and does not
report the stale result to the central queue. This fences the queue result and
the worker-owned process it can still reach. It does not prove remote process
termination on a physically disconnected host; cross-host external side-effect
fencing remains open in `NET-04`.

After a job is claimed, `WorkerAgent` retries transient control-plane network
failures and HTTP 429/5xx for up to `--control-reconnect-timeout` (default 30
seconds). If the central service restarts, the agent idempotently re-registers
its unchanged identity/generation, retries heartbeat/result and keeps the
worker-local runtime session/evidence path unchanged. Claim itself is not
blindly retried because the job queue has no stable claim-request dedup token;
a future claim-recovery protocol must add one. This does not restart the
worker-local runtime.

After a concrete runtime `session_id` exists, `WorkerAgent` also retries
transient runtime status/evidence/stop requests for
`--runtime-reconnect-timeout`. A runtime Device Service can restart on the same
port/state directory and re-attach the surviving QEMU only after PID
start-time, session QMP ownership and `query-status=running` all agree.
WorkerAgent derives a stable session-create `idempotency_key` from job and
lease. Session creation can therefore be retried safely; identical retries
return the same session and different request content returns 409.
The request is intended for non-secret job parameters; credentials, tokens
and firmware payloads must remain in their dedicated stores.

This queue is not a worker executor and does not make a lost QEMU process
truthful. The separate `platform/tools/worker_agent.py` executor registers a
persistent generation, claims one or more jobs, creates the requested session,
waits for `running` while heartbeating both worker and job, downloads the
evidence ZIP, stops with `purge=0`, and reports SHA256 plus terminal state.
`--runtime-service-url` now separates the central claim/heartbeat/result API
from the Device Service that creates and owns the QEMU session. If omitted,
both planes use one URL for compatibility. The split has unit coverage and a
real Linux worker-local StickS3 QEMU fixture with the peer services in two
veth-connected network namespaces: the worker namespace owns the runtime
Device Service, real QEMU session, artifact/firmware preparation,
serial/frame/QOM evidence and cleanup, while the central service handles
registration, claim, heartbeat and terminal result. Source/normalized firmware
and QEMU SHA256 are bound, the token is absent from retained logs, and QEMU
plus both namespaces are reaped. This is still one host with separate network
namespaces; the real cross-host QEMU executor, automatic discovery and
cross-host re-attach remain `NOT RUN`. A separate real-process
loopback run verifies HTTPS/mTLS: TLS 1.2 is the configured minimum, TLS 1.3
was negotiated, the server certificate was verified, clients without a
certificate were rejected, trusted clients passed, Bearer/HMAC remained
required, unsigned claim returned `401`, and `worker_agent.py` completed
signed registration/heartbeat/claim/stop over mTLS. The same fixture also
uploads and composes a complete StickS3 flash over mTLS, runs a durable job
through a real QEMU session, downloads evidence, verifies SHA256 and reports
terminal `completed/PASS`. A second job uses the unified StickS3 image and
requires its board/WiFi/BLE markers, network evidence, pcap and PNG frame in
the same evidence ZIP. A third real-process run atomically rotates the server
certificate, client CA, worker client identity and master token through
`SIGHUP`; the service drains an active old-token request before committing
the new configuration, the retired TLS identity and token then return `401`,
the new credentials complete a signed QEMU job, and evidence SHA256 matches.
A fourth run stages `--api-token-previous-file` and
`--tls-client-ca-previous`: both old/new client CAs and tokens are accepted
during the overlap window. The worker moves to the new identity, the previous
files are removed, and a final `SIGHUP` rejects the retired CA/token before
the real QEMU job. A fifth run starts two workers from immutable credential
generations. They first load an `A+B` server-trust bridge, continue through
the service A-to-B overlap, then atomically replace one generation pointer;
each worker reloads on its next request and writes a secret-free receipt
without receiving `SIGHUP`. A separate Linux fixture covers both the no-QEMU
control-plane compatibility path and a worker-local real StickS3 QEMU
execution path. A worker can discover the control URL from an active-token
IPv4 multicast beacon within one multicast domain. A worker outside that
domain can instead verify the same signed beacon fetched from a routable
unicast discovery seed. Two routed/masqueraded subnets, wrong/old-token
rejection, rotation and cleanup pass 3/3. Cross-host QEMU jobs, arbitrary NAT
traversal without a reachable seed, cross-host re-attach and
namespace-managed/Tab5/cross-host companion recovery remain open.

Control-plane reconnect is also time-bounded at the request level: the
remaining reconnect budget caps each registration/heartbeat socket timeout.
A worker-to-control blackhole therefore fences ownership, deletes its
reachable runtime session, reaps a process side effect and suppresses the
stale result instead of waiting for a full default HTTP timeout. The central
job lease then expires and is requeued after `M5_JOB_LEASE_SECONDS`; a new
worker attempt can complete the job after connectivity returns. The committed
Linux fixtures cover both an authenticated OS-process runtime and a real
worker-local Device Service plus StickS3 QEMU process. The QEMU lane proves
the old QEMU PID is reaped and attempt 2 boots a new instance; guest/device
controller effects and externally owned network side effects remain separate
boundaries.

`worker_agent.py --advertise-endpoint` stores an externally reachable HTTP(S)
worker endpoint in the registration record. The worker directory rejects
credential-bearing, query-bearing or fragment-bearing URLs. Advertising an
endpoint is static registration, not automatic discovery or connectivity proof.

When a service API token is configured, worker-only mutation endpoints
(`/jobs/claim`, job heartbeat/result and worker heartbeat/drain/stop/results)
also require an HMAC signature derived from:

```text
HMAC-SHA256(master-token, worker-id:instance-id:generation)
```

The request binds method, path, UTC timestamp, one-time nonce and body SHA256.
The signature window is 90 seconds, nonces are replay-cached, and the signed
identity must match both the path worker ID and JSON body. Missing/invalid
signatures return `401`; replay and identity mismatch return `409`.

### Capacity sizing

The default of `12` global sessions and `8` sessions per model is a
workstation profile, not a protocol limit. It was measured on the current
Apple M4 host with 10 CPU cores and 32 GB RAM:

Twelve concurrent StickS3 sessions used about 227% of one CPU core in total
(about 2.27 of the host's 10 cores), 1.46 GiB aggregate RSS and 1.12 GiB
physical footprint. All 12 reached a non-black frame; 12 concurrent frame
captures completed in 18-39 ms.

- eight running StickS3 QEMU sessions used about 1.68 CPU cores and 983 MiB
  aggregate RSS;
- twelve running StickS3 QEMU sessions used about 2.27 CPU cores, 1.46 GiB
  aggregate RSS and 1.12 GiB physical footprint;
- all twelve sessions reached a non-black frame;
- twelve concurrent frame captures completed in 18-39 ms wall time;
- `/capacity` remained below 1 ms and the next request returned `429`.

Per-device resource use varies with firmware activity and device backend. Use
the environment variables or CLI flags to tune the limits for the host and
workload. Capacity exhaustion for immediate `/sessions` creation still returns
`429` with `Retry-After`. Remote batch jobs can wait in the durable queue, but
the current service does not auto-launch a worker or reserve capacity when a
job is enqueued.

For LAN access with a shared token:

```bash
export M5_SERVICE_API_TOKEN='<private-token>'
python3 platform/tools/serve.py 8787 --bind 0.0.0.0
```

When a token is configured, every `/api/v1` endpoint except health requires:

```http
Authorization: Bearer <private-token>
```

The legacy catalog endpoints `/api/devices`, `/api/peripherals` and
`/api/peripheral-interfaces` use the same token when one is configured.

The service is intended for a trusted workstation or an isolated worker. Do not
expose it directly to the public internet.

### HTTPS and mTLS

`--tls-cert` and `--tls-key` enable a TLS 1.2+ HTTPS listener. When
`--tls-client-ca` is provided, every new connection must present a client
certificate signed by that CA.

The service can read its master token from `--api-token-file` or
`M5_SERVICE_API_TOKEN_FILE`. The token file must be UTF-8, contain 1–4096
bytes, and have no NUL; trailing CR/LF is ignored. The CLI token and token-file
options are mutually exclusive.

Send `SIGHUP` after atomically replacing the token and TLS files. The service
validates all configured files before committing the new token and TLS
context. The new TLS context applies to subsequent handshakes; an established
socket retains its negotiated TLS session. Before committing the reload, the
service stops admitting handlers, waits for already-active requests to finish,
and then activates the new token for subsequent protected requests. New
connections wait in the listener/backlog during this bounded drain. The
default timeout is 30 seconds and can be changed with
`--security-reload-drain-timeout` or
`M5_SECURITY_RELOAD_DRAIN_TIMEOUT`. On timeout the reload is canceled and the
old configuration stays active. Invalid reload input also leaves the previous
configuration active.

This closes active-request draining. For a bounded overlap, add
`--api-token-previous-file` and/or `--tls-client-ca-previous`:

```bash
python3 platform/tools/serve.py 8787 \
  --api-token-file /secure/service.token \
  --api-token-previous-file /secure/previous-token \
  --tls-cert /secure/server.crt \
  --tls-key /secure/server.key \
  --tls-client-ca /secure/worker-ca.crt \
  --tls-client-ca-previous /secure/previous-worker-ca.crt
```

The bearer/API check accepts either token and worker HMAC verification tries
both tokens. The TLS listener trusts both client CAs. A missing previous file
disables that side of the overlap. To finalize, remove both previous files,
then send another `SIGHUP`. The final service state trusts only the active
CA/token.

For automated worker migration, keep complete credential sets in immutable
generation directories and publish one pointer by atomic rename:

```json
{
  "schema_version": 1,
  "generation": "B",
  "token_file": "generations/b/token",
  "ca_file": "generations/b/ca.crt",
  "client_cert": "generations/b/client.crt",
  "client_key": "generations/b/client.key"
}
```

Relative paths resolve from the pointer file. Workers using
`--credential-generation-file` compare the pointer before every API request;
an atomic pointer replacement commits the complete credential set, while a
failed load keeps the previous set active. Workers should first move to an
`A+B` server-trust generation, then the service can switch its active server
certificate and client CA with A retained as previous. After service overlap
is active, publish the B worker generation. `--credential-receipt-dir` writes
one `0600` secret-free receipt per worker containing identity, generation,
timestamp and a file-generation fingerprint.

The retained same-host fixture moves two workers through A, A+B and B, verifies
both receipts and new-identity heartbeats, then removes the server previous
files and verifies old credentials fail. Worker `SIGHUP` is not required in
this path. Automatic discovery of worker hosts, cross-host migration,
secret-manager distribution and final cutover orchestration remain `NOT RUN`.

The worker uses verified TLS by default for `https://` URLs. `--ca-file`
selects a private CA bundle, while `--client-cert` + `--client-key` enable an
mTLS client identity. The worker can load the token from `--token-file` or
`M5_SERVICE_API_TOKEN_FILE`; `--token` and `--token-file` are mutually
exclusive. Direct file options still use `SIGHUP` for reload. For automatic
fleet migration, use `--credential-generation-file` and
`--credential-receipt-dir`:

```bash
python3 platform/tools/worker_agent.py \
  --service-url https://device-service.example \
  --credential-generation-file /secure/worker-generation.json \
  --credential-receipt-dir /secure/worker-receipts
```

There is no hostname-verification bypass. TLS options are rejected for
plaintext `http://` URLs. The transport is defense in depth, not a replacement
for worker HMAC.

## Base URL

```text
http://127.0.0.1:8787/api/v1       # local default
https://device-service.example/api/v1  # TLS/mTLS deployment
```

Every JSON response includes `X-Request-ID`. Errors use:

```json
{
  "error": {
    "code": "device_capacity_exhausted",
    "message": "maximum active sessions for sticks3 is 2"
  }
}
```

## Objects

### Device

`GET /api/v1/devices` returns all registered devices. `supported=false` rows
are visible but cannot be leased.

Important fields:

- `device_id`
- `supported`
- `creatable`
- `reference_available`
- `backend_ready`
- `missing_runtime_files`: repo-relative backend paths that prevent a session;
  empty when `backend_ready=true`.
- `flash_size`
- `display`
- `features.flash/serial/screenshot/input/qom`
- `network_status` separates simulator capability from test evidence:
  `validated`, `unverified`, `board-init-blocked`, or `not-supported`.
- `features.network` is `true` only for a `validated` device-level path.
  `network_profiles` still lists scenarios that can be used for diagnostics on
  an `unverified` or `board-init-blocked` chip; a profile being listed is not a
  PASS claim. The generic `features.network` flag remains false for Tab5 and
  Core2 because their usable paths are backend- or environment-gated. For
  Core2, the explicit `qemu-wifi`, `qemu-unified` and `core2-native-hci`
  profiles are the current network paths; this flag is not a statement that
  those profiles are absent.
- `network_console` reports the generic-firmware console default declared by
  the device matrix, such as `usb-jtag` for C6 UIFlow2.
- Tab5 `features.qom` is `false`; its touch path uses the GDB mailbox currently
  used by the validated Tab5 runtime.

`backend_ready=false` is a deployment state, not evidence that the device model
is broken. A fresh source clone has no ignored `.work/` runtime assets; see
[Deployment and runtime assets](deployment.md).

### Artifact

An artifact is an immutable content-addressed byte blob. Upload the bootloader,
partition table, application or a complete merged image separately.
The per-artifact limit is 96 MiB so a matching UIFlow2 ELF with debug/symbol
data can accompany BLE tests; stripped ELFs are not interchangeable when the
emulator needs the full symbol data for HCI interception.

```http
POST /api/v1/artifacts
Content-Type: application/octet-stream
X-Artifact-Name: firmware.bin
```

Response:

```json
{
  "artifact_id": "<sha256>",
  "sha256": "<sha256>",
  "size": 123456,
  "name": "firmware.bin",
  "content_type": "application/octet-stream",
  "created_at": "..."
}
```

Large WebBurner/browser uploads can use a resumable chunk path so the complete
artifact is not buffered as one request:

```http
POST /api/v1/artifact-uploads
Content-Type: application/json
```

```json
{
  "expected_size": 8388608,
  "expected_sha256": "<final-sha256>",
  "name": "web-burner.bin",
  "content_type": "application/octet-stream"
}
```

Then append contiguous raw chunks, at most 8 MiB each:

```http
POST /api/v1/artifact-uploads/<upload-id>/chunks
Content-Type: application/octet-stream
X-Chunk-Offset: 0
X-Chunk-SHA256: <chunk-sha256>
```

The response includes `received_bytes` and `next_offset`. Upload state remains
available through `GET /api/v1/artifact-uploads/<upload-id>` so a client can
resume after a dropped connection:

```http
POST /api/v1/artifact-uploads/<upload-id>/complete
```

Completion verifies the full size and SHA256, atomically publishes the normal
content-addressed artifact, and returns the same metadata shape as direct
upload. `DELETE /api/v1/artifact-uploads/<upload-id>` aborts an incomplete
upload. Chunks must be contiguous and non-overlapping; a wrong offset or chunk
hash fails with `409` and leaves the accepted prefix intact.

An append is committed only after the staging write and atomic metadata replace
both succeed. A write, `fsync` or metadata failure truncates the staging file
back to the last acknowledged offset and returns `500 upload_write_failed`;
clients can query the upload and retry from `next_offset`. Upload metadata
contains no artifact body. The cache janitor removes interrupted staging data
and expired completed upload records after `M5_SERVICE_CACHE_GRACE`, while a
completed artifact follows normal content-addressed artifact retention.

### Import a browser-uploaded firmware package

The WebBurner page uploads the package artifact and then asks the service to
run the same FirmwareManifest importer used by the CLI:

```http
POST /api/v1/firmware/import
Content-Type: application/json
```

```json
{
  "device_id": "sticks3",
  "artifact_id": "<uploaded-package-sha256>"
}
```

The uploaded artifact name selects the importer path:

- `.bin`: merged flash;
- `.zip`, `.m5burner` or `.webburner`: WebBurner/M5Burner/ESP-IDF package.

The endpoint performs archive-safe extraction, segment composition, padding,
static/security review, filesystem inventory and target capability checks. It
always publishes a normalized merged-flash artifact to the firmware store and
preserves the original source format and normalized segment hashes in the
manifest. `409 unsupported_firmware_capability` includes structured
`issues[]`; an invalid package returns `400 invalid_firmware_package`.
An unknown required capability also fails closed through this response because
the service cannot verify that the target profile supports it. Unknown optional
capabilities remain warnings. The manifest identity is content-stable across
different output/package filenames; `artifact.file` is not part of
`manifest_id`.

Security preflight also inspects every supplied evidence layer. A caller cannot
hide secure boot or Flash Encryption by setting only the aggregate security
fields to `unknown`: enabled sdkconfig, a signed/invalid Secure Boot v2 image
claim, or a package-provided eFuse claim is rejected when the target runtime
does not model that chain. These checks remain compatibility decisions; they
do not authenticate the package summary or perform a live eFuse read.

The browser page is `/platform/web/firmware.html`. It streams the complete
SHA256 calculation and 4 MiB chunks, retries transient failures, exposes
progress/cancel, and restores the upload checkpoint from browser storage.
After a refresh, an incomplete upload requires reselecting the same file for
content verification; a completed artifact can continue directly to manifest
import without uploading again.

### Firmware

A firmware manifest composes one or more artifacts into a flash-sized image
for a specific device. The resulting file is padded with `0xff`.

Complete merged image:

```json
{
  "device_id": "sticks3",
  "kind": "merged",
  "artifact_id": "<sha256>"
}
```

Segmented image:

```json
{
  "device_id": "sticks3",
  "kind": "segmented",
  "segments": [
    {"offset": "0x0", "artifact_id": "<bootloader-sha256>"},
    {"offset": "0x8000", "artifact_id": "<partition-sha256>"},
    {"offset": "0x10000", "artifact_id": "<app-sha256>"},
    {"offset": "0x210000", "artifact_id": "<filesystem-sha256>"}
  ]
}
```

Offsets may be integers or `0x` strings. Segments cannot overlap or exceed the
target device flash size.

Versioned manifest:

```json
{
  "device_id": "sticks3",
  "kind": "manifest",
  "manifest": {
    "schema_version": 1,
    "kind": "m5stack-firmware-manifest",
    "artifact": {
      "kind": "merged-flash",
      "file": "firmware-flash.bin",
      "artifact_id": "<normalized-image-sha256>",
      "size": 8388608,
      "sha256": "<normalized-image-sha256>"
    },
    "target": {"soc": "esp32s3", "flash_size": 8388608},
    "security": {
      "secure_boot": "unknown",
      "flash_encryption": "unknown",
      "efuse": "not-included"
    },
    "provenance": {
      "importer": "m5stack-firmware-manifest/1",
      "source_format": "merged-bin"
    },
    "validation": {"status": "PASS", "errors": [], "warnings": []}
  }
}
```

Use the manifest importer to normalize an M5Burner `.bin`/sidecar, a
WebBurner `manifest.json` part list, a `.zip`, or an ESP-IDF
`flasher_args.json` package:

```bash
python3 platform/tools/firmware_manifest.py /path/to/package \
  --out-dir /tmp/m5-firmware-manifest --print summary
```

The schema is
[`platform/tools/firmware_manifest.schema.json`](../platform/tools/firmware_manifest.schema.json).
The importer pads sparse images to the complete virtual flash, prohibits
archive path traversal, records hashes/provenance and keeps unknown security
state as `unknown` rather than claiming it disabled. When a target device is
known, required capabilities, chip, flash and PSRAM are checked. The service
returns HTTP `409 unsupported_firmware_capability` with `issues[]`; a model gap
must not be reported as a firmware crash.

`POST /api/v1/firmware/import` accepts up to 64 canonicalized
`required_capabilities` and 64 `optional_capabilities`. Aliases such as
`screen` become `display`; malformed, non-string, empty or overlong entries
return HTTP `400 invalid_capability_requirements`. WebBurner exposes the same
two comma/space-separated fields before upload, so a package declaring
`camera` for a device without a camera is rejected before session creation
instead of producing an empty capabilities object.

When the package includes `sdkconfig`, the manifest also reports
`capabilities.detected` for high-confidence WiFi/Bluetooth/PSRAM build flags.
Detected values are review warnings when the target profile lacks a capability;
only `required_capabilities` rejects the import. This avoids treating a build
flag as proof that an application code path actually uses the peripheral.
When sdkconfig is absent, the normalized image is scanned with an allowlisted
token set and emits separate `capabilities.observed` entries with
`source=image-signature` and `confidence=low`. Observed-but-undeclared,
required-but-not-observed and observed-but-unsupported values are warnings;
they never weaken a required capability mismatch. The scan records
`SCANNED`/`TRUNCATED`, total/scanned bytes and cannot prove runtime use.

QEMU memory is rechecked at session creation against the selected profile.
For example, a manifest requiring more PSRAM than the effective runtime memory
receives `issues[].code=runtime_psram_mismatch`, even if the physical board
inventory declares more PSRAM. This preflight prevents a known memory-model
mismatch from being misreported later as a firmware crash.

```http
POST /api/v1/firmware
Content-Type: application/json
```

The response includes `firmware_id`, `sha256`, `device_id`, `flash_size`,
`kind`, `source` and `header_magic`.

`artifact_sha256` identifies the uploaded source artifact. `firmware_id` and
`firmware.sha256` identify the composed, flash-sized image after padding and
segment composition. They intentionally do not have to be equal.

### UIFlow2 Python source

`POST /api/v1/firmware` also accepts `kind=uiflow`:

```json
{
  "kind": "uiflow",
  "device_id": "cores3",
  "files": {
    "main.py": "import M5\nM5.begin()\n",
    "pkg/__init__.py": "",
    "pkg/example.py": "VALUE = 1\n"
  }
}
```

The convenience endpoint `POST /api/v1/firmware/uiflow` accepts the same object
**without `kind`**. Supplying `kind` there, or unknown source-request fields on
either endpoint, returns `400 invalid_uiflow_request`. Optional
`expected_base_sha256` pins the cached reference image to a lowercase SHA256;
a mismatch returns `409 uiflow_base_hash_mismatch`.

Source intake currently admits only `cores3`, `atoms3r`, `sticks3` and
`stopwatch`, using each device's known, locally cached UIFlow2 reference.
An enabled device outside that set returns `409 unsupported_uiflow_device`;
a missing cached reference returns `409 reference_firmware_missing`. This is
not a generic MicroPython, signed/encrypted image or arbitrary base importer.
Existing merged, segmented and FirmwareManifest paths keep their own capability
and security preflight.

`files` is a path-to-source-string object with a root `main.py`. Nested Python
packages are supported. Paths must be canonical relative UTF-8 POSIX `.py`
paths: no absolute paths, traversal, empty components, backslashes, control
characters or case/Unicode-normalization collisions. There are at most 128
caller files, 256 KiB UTF-8 bytes per file and 1 MiB UTF-8 bytes total; these
are byte limits, not JSON character limits. Independently, the existing HTTP
JSON-body limit is 1 MiB (1,048,576 bytes) for both source endpoints. The
serialized body includes field names, paths, JSON punctuation/whitespace and
escaping; it can exceed the HTTP limit even when decoded caller-source bytes
fit the helper's 1 MiB limit. Both limits apply; an HTTP body over the limit
returns `413 body_too_large` before composition. Source strings cannot contain NUL.
The current path limits are 512 UTF-8 bytes, 32 components and 255 UTF-8 bytes
per component. Existing VFS file/directory collisions fail closed.

The service mounts the real reference LittleFS `vfs` partition without
formatting, overlays submitted paths, then remounts it to verify persisted
bytes and preserved files. It preserves image bytes outside that partition
and pads the final image to the device's flash size. It never executes caller
Python on the host. An omitted `boot.py` produces
`_uiflow_run_main = True\n` with `origin=generated`; a caller-supplied `boot.py`
is retained unchanged and must arrange its own entrypoint execution.
`main.py` source validity, imports and behavior are checked by running the
resulting firmware in a Device Service session, not by a successful compose.

The response is the normal Firmware object with `kind=uiflow` and:

```json
{
  "source": {
    "kind": "uiflow",
    "artifact_id": "<canonical-caller-files-json-sha256>",
    "metadata": {
      "schema_version": 1,
      "kind": "uiflow2-source-composition",
      "status": "COMPOSED_NOT_EXECUTED",
      "entrypoint": "main.py",
      "base_sha256": "<cached-reference-sha256>",
      "source_sha256": "<canonical-caller-files-json-sha256>",
      "effective_source_sha256": "<caller-plus-generated-files-json-sha256>",
      "firmware_sha256": "<derived-full-image-sha256>",
      "source_hash_format": "canonical-json-utf8-path-to-source/v1",
      "files": [
        {"path": "main.py", "size": 21, "sha256": "<file-sha256>", "origin": "caller"},
        {"path": "boot.py", "size": 24, "sha256": "<file-sha256>", "origin": "generated"}
      ]
    }
  }
}
```

This abbreviated metadata example illustrates the shape; sizes and hashes must
be taken from the real response. Canonical source JSON uses UTF-8,
`ensure_ascii=False`, sorted keys and separators `(',', ':')`. Its artifact
contains exactly the caller's `files` object, including code; a generated
`boot.py` appears in the effective hash and file metadata, not in that artifact.
`GET /artifacts/{artifact_id}` returns artifact metadata only.

The complete composition metadata also records `base_size`, `flash_size`,
`firmware_family_precondition`, `caller_file_count`, `caller_source_bytes`,
`generated_files`, the actual partition layout and LittleFS hashes/versions in
`vfs`, preservation/readback flags in `preservation`, and builder, Python,
LittleFS versions and filesystem config in `toolchain`. Its status remains
`COMPOSED_NOT_EXECUTED` even after a separate runtime test; runtime evidence
belongs to the session and validation report.

When creating a session for `kind=uiflow`, also supply
`uiflow_source_sha256=source.metadata.source_sha256` from the compose response.
The image ID alone cannot distinguish different caller-source declarations
that produce identical image bytes. A missing source pin returns
`400 uiflow_source_binding_required`; a mismatched pin, or a pin supplied for
non-UIFlow firmware, returns `409 uiflow_source_binding_mismatch` before launch.
An overwrite/race can therefore require re-composition and a fresh source pin;
it must not silently select another source's provenance.

For sessions created from this firmware, `firmware_provenance` contains the
same `source` object and survives history restoration. The evidence ZIP adds
`firmware/uiflow-source.json` with that hash-only provenance, not source code.
`artifact_sha256` and `source_artifacts[0]` identify the caller-source JSON;
`firmware_id`, `firmware_sha256` and `source.metadata.firmware_sha256` identify
the derived complete image. Record both identities; do not compare them as if
they were the same artifact. The mutable session Flash has its own lifecycle
and hashes.

Common source failures:

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_uiflow_request` | Unknown request fields, or `kind` on the convenience endpoint |
| 400 | `invalid_uiflow_source` / `invalid_uiflow_source_path` | Missing `main.py`, invalid source values or unsafe paths |
| 409 | `uiflow_source_path_conflict` | Caller or existing VFS path collision |
| 409 | `unsupported_uiflow_device` / `reference_firmware_missing` | Target or cached base is unavailable for source intake |
| 409 | `uiflow_base_hash_mismatch` | Optional expected base hash does not match |
| 409 | `unsupported_uiflow_vfs` / `uiflow_vfs_unmountable` | Unsupported layout or unmountable existing LittleFS; no format fallback |
| 413 | `body_too_large` | Entire serialized HTTP JSON body exceeds 1 MiB, including escaping and keys |
| 413 | `uiflow_source_too_large` / `uiflow_vfs_full` | Source limits or available filesystem capacity exceeded |
| 503 | `uiflow_source_dependency_unavailable` / `reference_firmware_unreadable` | Required LittleFS dependency or cached base cannot be read |

Composition alone proves filesystem packaging and readback. It does not prove
that a driver imported, a Unit transaction occurred, an application displayed,
or physical hardware worked. The workflow's current execution evidence and
remaining gates are recorded in [the Agent guide](unit-agent-api.md) and the
project authority pages.

### Session

A session is one exclusive emulator lease. It has one device profile, one
immutable source firmware, one private flash copy, one QEMU process and one
serial log set.

`runtime` is `qemu` by default. Use `qemu-unified` for the canonical complete
virtual-device path and pair it with one of the `*-unified` profiles. It starts
one QEMU guest containing the board model, WiFi path and (where applicable) the
HCI/BLE path, then returns frame, serial, input, device-state, audio and radio
evidence from that same session.

The legacy `qemu-ble` runtime remains accepted for compatibility and for
radio-specific profiles such as `core2-ble-advertise`,
`core2-hci-gatt` and `nanoc6-hci-ble`. Do not infer full-device coverage from a
runtime name alone; use the profile matrix below.

| Runtime | Intended use | Whole-device evidence |
| --- | --- | --- |
| `qemu-unified` | Canonical board + radio profile ending in `-unified` | Yes, when the profile passes |
| `qemu-wifi` | Board + WiFi firmware without external BLE | Board and WiFi only |
| `qemu-ble` | Legacy alias for unified profiles and radio-specific diagnostics | Depends on profile |
| `network` | Separate `esp-emu` network/BLE diagnostic lane | No framebuffer, input, QOM or same-instance board state |

`runtime=network` runs S3/C6 firmware through the separate `esp-emu` lane. It
does not expose framebuffer, input, QOM or same-instance board state, so its
result cannot be combined with another session to claim a complete-device
PASS. It also rejects `capture_pcap=true`: `esp-emu` user networking has no
Ethernet capture interface. Use a QEMU radio runtime for pcap evidence.

QEMU radio sessions capture Ethernet traffic by default through QEMU
`filter-dump`. After stop, `GET /sessions/{id}/network` contains
`packet_capture` with flow endpoints, DNS names, DHCP/ARP counts, egress scope
and payload SHA256 values; raw payloads are not copied into the summary.
Evidence ZIPs include `network/capture.pcap` and
`network/pcap-summary.json`.

DHCP summaries include message-type counts, bounded transaction records,
selecting/renewal request counts, renewal ACK correlation, lease/T1/T2 values
when advertised, and the assigned address. This distinguishes initial
`DISCOVER/OFFER/REQUEST/ACK` from a later unicast `REQUEST/ACK` renewal.

`network.policy` provides a fail-closed isolation envelope:

```json
{
  "policy": {
    "isolation": "namespace",
    "egress": "allowlist",
    "dns": "controlled",
    "allowed_hosts": ["allowed.lab.test"],
    "allowed_domains": ["fixture.test"],
    "allowed_endpoints": [
      {
        "protocol": "tcp",
        "address": "10.0.2.2",
        "port": 18443
      }
    ]
  }
}
```

`isolation=namespace` is Linux-only. For `lab-only`, the service creates a
private namespace with no external route and starts controlled HTTP/BLE peers
inside it. For `allowlist`, nftables input/output chains default to `drop`;
only exact IPv4 or IPv6 `protocol + address + port` endpoints,
established/related flows, IPv6 neighbor discovery, and required loopback
control ports are accepted.

`allowed_endpoints` accepts at most 64 IPv4/IPv6 address-or-CIDR endpoints.
IPv4 CIDRs must be `/16` or narrower and IPv6 CIDRs `/48` or narrower. The
parser rejects broad prefixes, unspecified/loopback/link-local/multicast
space, IPv4-mapped IPv6 CIDRs and CIDRs covering the QEMU SLiRP synthetic
networks. Exact loopback and link-local endpoints are also rejected;
callers cannot grant arbitrary host-loopback services. A guest-visible exact
`10.0.2.2` or `fec0::2` endpoint is enforced against the corresponding SLiRP
host-loopback socket; other destinations use a per-session dual-stack veth
and temporary worker-side NAT table. Loopback allowances are derived
internally from controlled DNS, HTTP/TLS fixtures and HCI/GDB control ports.

`egress=allowlist` requires at least one of `allowed_hosts`,
`allowed_domains` or `allowed_endpoints`. Profiles with a controlled HTTP
fixture add their exact HTTP endpoint automatically. Profiles without one
require an explicit endpoint that covers every managed DNS answer; otherwise
the request fails with `allowlist_not_supported`.
`dns=controlled` requires namespace isolation and `egress=allowlist`. The
sandbox creates a private mount namespace, binds a temporary resolver
configuration only into the QEMU process tree, and serves explicitly bound
names or domain suffixes while returning NXDOMAIN for other names.
`allowed_hosts` is an exact Host/DNS allowlist with strict ASCII DNS labels,
lowercase normalization and at most one trailing root dot. It rejects empty
labels, leading/trailing hyphens, ports, userinfo and wildcard syntax.
`dns=controlled` requires at least one allowed endpoint. `allowed_domains` is
a suffix allowlist with DNS-label boundaries: `allowy.test` also matches
`api.allowy.test`, but not `evilallowy.test`; exact records win and the
longest suffix wins. Every suffix must have explicit resolver answers covered
by an allowed endpoint. Exact A/AAAA records and CNAME terminal answers use
the same endpoint check; IPv4-mapped IPv6 DNS records are rejected. Managed
profiles bind Host/domain grants to
`10.0.2.2` and therefore require a controlled HTTP profile or an exact
`10.0.2.2` endpoint. A domain suffix never authorizes arbitrary addresses
from an outside resolver. The sandbox core accepts exact A/AAAA records and
can bind an IPv6 `ControlledHttp`; the Device Service's managed controlled
HTTP fixture still exposes its existing IPv4 path.
A standalone UIFlow2 test build in a Linux private network namespace has
completed controlled AAAA, allowed IPv6 HTTP, denied-port blocking, pcap,
namespace cleanup and QEMU reap in one guest lifecycle. That closes `NET-06`
for the accepted virtual-device scope; it does not claim that every managed
profile defaults to IPv6 or that stock UIFlow2 enables an IPv6 link-local.

`network.cname_records` is an optional exact-name CNAME map for controlled
DNS. Every alias must be covered by `allowed_hosts` or `allowed_domains`;
every chain is limited to eight links and must terminate at a non-alias exact
host or at a domain suffix with explicit resolver answers. Cycles, aliases
outside the policy, uncontrolled terminals and CNAME owners that also have
exact or domain-suffix address data are rejected with `invalid_network`.
Matching A/AAAA responses include the CNAME chain followed by the terminal
address record, while a CNAME query returns the chain without inventing an
address. The resolver test covers A/AAAA CNAME-chain encoding, CNAME-query
encoding, NXDOMAIN and invalid graphs. The `cname_guest_lifecycle` fixture
also validates the same-guest path: one `qemu-wifi/uiflow2-sticks3-wifi`
lease resolves the controlled alias, follows its terminal A record to
`10.0.2.2`, completes HTTP/1.0 200 on the allowed port, rejects an unlisted
name and rejects an unlisted port. Three independent leases PASS with
identical probe/QEMU/service/sandbox hashes. CNAME resolution never bypasses
endpoint IP/CIDR/port egress rules.

Controlled HTTP evaluates exactly one Host header with an optional numeric
port and an origin-form request target. Userinfo, comma-separated or
multi-colon authorities, invalid/out-of-range ports, duplicate Host headers
and absolute-form request targets are denied. A Linux namespace StickS3 lease
on `2026-10-26` completed controlled DNS allow/NXDOMAIN, strict Host
allow/deny, TLS 200/403, DHCP, pcap and cleanup under the same evidence
bundle.

For namespaced QEMU radio sessions, `GET /sessions/{id}/network` also returns
the sandbox `isolation` state plus bounded `dns_requests` and
`http_fixture_requests` logs. The session evidence ZIP includes
`network/dns-requests.json`, `network/http-fixture.json` and
`network/isolation.json` when those files exist. Namespace sessions receive a
20-second termination grace so the sandbox can finish QEMU reap, fixture
closure and cleanup evidence before Device Service escalates.

The Linux worker must provide root or equivalent `NET_ADMIN`/`SYS_ADMIN`
capabilities, `nftables`, and `iproute2`. External IPv4 endpoints require
`net.ipv4.ip_forward=1`; external IPv6 endpoints additionally require
`net.ipv6.conf.all.forwarding=1`. Preflight failure returns
`egress_policy_unavailable`; readiness/rule installation failure remains
fail-closed. Every temporary namespace, veth pair and NAT table is removed when
the session stops.

Use `runtime=qemu-wifi` with `network.profile=uiflow2-sticks3-wifi` for a
StickS3 application that needs the board framebuffer, input and public
internet without an external BLE controller. This lane starts the QEMU
`misc.esp32s3.wifi` NIC and does not start the HCI/Bumble peer.

ESP32-S3 `qemu-wifi/generic-observe` accepts `wifi_auth=open` or
`wifi_auth=wpa2-psk`. WPA2-PSK validates the SSID/password, completes the
RSN four-way exchange, installs PTK/GTK and supplies hardware-decrypted CCMP
RX to the guest. The service derives a locally-administered synthetic MAC from
the session id, writes it into the ESP32-S3 eFuse fixture and passes the same
address to QEMU, so supplicant, DHCP and QEMU NIC no longer disagree about the
station address. Correct credentials have reached DHCP, DNS and TCP/443;
wrong credentials are rejected at M2 MIC and retried without DHCP. WPA3-SAE
returns `unsupported_wifi_security`; WPA2 group-key multicast and RF behavior
remain outside the current claim.

Core2 retains `qemu-wifi` and `qemu-ble` as compatibility runtimes when the
service starts with `M5_CORE2_RADIO_QEMU` pointing at a QEMU build containing
the classic ESP32 WiFi and Bluetooth models. The canonical combined paths are
`runtime=qemu-unified` with `profile=core2-unified` or
`profile=core2-native-hci`. The latter is the preferred stock-firmware path.
`profile=core2-native-vhci` is retained for GDB diagnosis and compatibility.
`M5_CORE2_WIFI_QEMU` remains a compatibility alias for existing deployments.

```json
{
  "device_id": "core2",
  "runtime": "qemu-wifi",
  "network": {
    "profile": "core2-openmac",
    "expected_markers": ["CORE2_WIFI_RESULT: PASSED"],
    "attempts": 5
  }
}
```

This is the same QEMU instance as the Core2 board lane, so framebuffer, serial,
QMP and QOM remain available while the stock WiFi driver runs. The model uses
the fixed test AP `myssid` and QEMU user networking. Core2 radio QEMU uses
deterministic `tcg,thread=single,tb-size=128` plus `icount` scheduling; `attempts` remains
a diagnostic retry setting, but retries are not used as evidence that a failed
first attempt was repaired.
The input must already be a complete, flash-sized merged image. The service
validates its SHA256, bootloader, partition table, app partitions and ESP32 chip
ID, then mounts that exact copy as the QEMU MTD drive without invoking esptool.
A partial image is rejected instead of being silently padded in this lane.
This runtime remains environment-gated and is not enabled without the
environment-selected patched QEMU.

The BLE controller bootstrap uses the same QEMU instance and guest UART/frame/
QOM paths:

```json
{
  "device_id": "core2",
  "runtime": "qemu-ble",
  "network": {
    "profile": "core2-ble-advertise",
    "expected_markers": [
      "CORE2_BLE_ACTIVE True",
      "CORE2_BLE_RESULT: PASSED"
    ],
    "attempts": 5
  }
}
```

This service profile proves stock UIFlow2 NimBLE activation, GAP configuration,
controller reset and advertising enable. Separate standalone runners now
bridge the same stock firmware's VHCI boundary to Bumble; the BLE-only runner
passes external NUS GATT 5/5 and the same-guest board+WiFi+public-network
variant passes 3/3. The canonical stock-firmware service path is
`qemu-unified/profile=core2-native-hci`; it requires a matching ELF, resolves
API/HLI hook addresses, and does not launch GDB. The legacy GDB-based path is
still available as `qemu-unified/profile=core2-native-vhci` for diagnosis and
compatibility.

The `core2-hci-gatt` profile exercises the separate HCI-offload lane:

```json
{
  "device_id": "core2",
  "runtime": "qemu-ble",
  "network": {
    "profile": "core2-hci-gatt",
    "attempts": 3
  }
}
```

The uploaded firmware must use the UIFlow2 HCI-UART test configuration with
the internal controller disabled. The service starts Bumble as an external
controller, connects QEMU's UART1 chardev to it, and uses a second peer to
scan, connect, discover NUS, subscribe, write and validate the guest notify.
The session remains one QEMU instance, so serial, frame, QOM and BLE evidence
are captured together. `/network` returns
`kind=m5stack-qemu-ble-hci-gatt-proof` and the evidence ZIP contains both
serial and `ble-probe.log`.

This is HCI offload. It does not claim a native ESP32 radio/controller model,
RF behavior, pairing/security or production throughput.

NanoC6 uses the same one-guest contract for board peripherals, QEMU C6 WiFi
and HCI-offload BLE:

```json
{
  "device_id": "nanoc6",
  "runtime": "qemu-ble",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "nanoc6-hci-ble",
    "attempts": 3
  }
}
```

The firmware is built with the C6 internal controller disabled and HCI UART1
on GPIO16/17. The USB-Serial-JTAG console remains on QEMU serial2; UART0 is
unused and UART1 is attached to Bumble. One QEMU C6 guest runs the
`misc.esp32c6.wifi` NIC, obtains DHCP through SLiRP, reaches the controlled
HTTP fixture, and completes the external Bumble NUS exchange. The service
injects GPIO9 press/release through QOM and captures WS2812/IR symbols.
`/network` returns
`kind=m5stack-nanoc6-board-hci-ble-qemu-proof` with unified WiFi and BLE checks.

Nesso N1 extends the same C6 unified lane to its full board peripheral set:

```json
{
  "device_id": "nesso-n1",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 120,
  "network": {
    "profile": "nesso-unified",
    "attempts": 3
  }
}
```

The service waits for the PI4IOE rail setup, injects BQ27220/AW32001 and
BMI270 QOM values, sends touch and key input, captures a nonblank/touch-redrawn
135x240 frame, checks SX1262 loopback, RMT IR and buzzer PCM, and waits for an
external Bumble peer to complete NUS scan/connect/subscribe/write/notify.
The same guest obtains DHCP, reaches the controlled HTTP fixture and keeps the
WiFi path active while the external peer completes the NUS exchange.
`/network` returns
`kind=m5stack-nesso-board-hci-ble-qemu-proof` with unified WiFi and BLE checks.

Core2 also has a combined WiFi and BLE profile through the same board/QMP/
UART1 instance:

```json
{
  "device_id": "core2",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 90,
  "network": {
    "profile": "core2-unified",
    "attempts": 3
  }
}
```

The image uses the Core2 HCI-UART build, QEMU `-m 0`, the OpenMAC
`misc.esp32_wifi` device, UART1 H4, a Bumble controller/peer and a controlled
HTTP endpoint on port `18089`. QOM is written while the guest runs.
The profile exercises display/touch, AXP2101, INA3221, MPU6886, PCF8563,
NS4168 speaker, SPM1423 microphone, WiFi DHCP/HTTP, public IPv4 DNS/HTTP and
external HCI-offload BLE NUS in one guest. Ten independent first attempts
passed 10/10 with no retry under deterministic TCG/icount scheduling. This is
simulation-only evidence and is not equivalent to physical cache/PSRAM timing.
The `core2-unified` service profile still uses HCI-offload. Stock VHCI runners
also pass external NUS GATT 5/5 and same-guest unified 3/3 without rebuilding
for UART HCI; they execute Bumble in place of the bit-exact Espressif BT
baseband/controller.

The preferred stock-firmware path is `core2-native-hci`:

```json
{
  "device_id": "core2",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 120,
  "network": {
    "profile": "core2-native-hci",
    "elf_artifact_id": "<matching-xtensa-elf-sha256>",
    "attempts": 1,
    "capture_pcap": true
  }
}
```

`elf_artifact_id` is mandatory and must point to the matching symbol ELF.
The service starts one `m5core2` guest with CLI `-m 0`, the OpenMAC WiFi NIC
and the QEMU `esp32-native-hci` device. QOM reports the resolved machine
memory as 8 MiB with `has_psram=true`; evidence keeps the CLI request and
effective value separate. Before launch it strictly resolves every
API-boundary, HLI queue, ATT trace and task-recycle address required by the
device arguments. No QEMU GDB endpoint is created. Event and ACL delivery use
the firmware HLI queue/IRQ; H2C ownership is isolated at
`API_vhci_host_send_packet`. A second Bumble peer performs NUS discovery,
subscription, write and notification readback.

The network evidence `runtime.memory` object records the requested CLI and
QOM-effective QEMU PSRAM size, the selected policy, and
`physical_cache_psram_timing=NOT RUN`. Native-controller profiles report
`cli_requested_psram_mib=0`; for Core2 the resolved
`effective_psram_mib=8` comes from the current `m5core2` QOM. The normal
ESP32 DRAM1 heap remains the architectural 4 MiB mapped window; the upper
4 MiB requires the modelled MMU bank switch. Other profiles report the CLI
model unless another board-specific resolution is documented.
This makes memory policy auditable without claiming physical PSRAM or cache
timing.

`/network` returns `kind=m5stack-core2-unified-qemu-proof`,
`profile=core2-native-hci`, and
`hci_transport=ESP32 native HCI device + HLI to Bumble`. The evidence ZIP
contains serial, peer log, frame, audio source PCM, QOM snapshot, pcap and
manifest. `HCI-4` passed five independent leases with
`gdb_bridge=false`; each lease also passed frame, QOM, WiFi DHCP/HTTP,
public DNS/HTTP and external NUS GATT:
[`hci4-service-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json).
For two simultaneous cold starts, `0008` keeps two real guest HCI-event
buffers and two ACL mbufs preallocated while CPU0 is idle. Two independent
`4×120s` gates pass `8/8`; every lease records 36 events and 9 ACLs on the
fast path, HLI `45/45`, `hli-errors=0`, no scheduler reset and no panic.
The observed Command Status receive-to-HLI delay falls from about `3.660s`
to `0.328s`. Two additional three-instance `3×120s` gates pass `6/6`.
The first four-instance `4×120s` batch is explicitly `1 PASS / 3 FAIL`: one
lease reports `hli-errors=1` and `hli-prealloc-failures=2`, while two leases
panic before READY in NimBLE `ble_hs_hci_process_ack` at `0x402630cc`.
After retaining that failure, `0009` expands the real guest reserve from two
event/two ACL objects to eight event/four ACL objects. Two independent
four-instance `4×120s` batches then pass `4/4` each (`8/8`), ending with QOM
spare depth `8/4`, HLI `45/45`, 36 events/9 ACLs and zero
errors/reset/panic. One passing first-batch lease records two transient refill
failures before recovery; the confirmation batch records none.
For unified profiles, the external BLE peer scan window follows the session
readiness budget within `40–120s`; the former fixed `40s` window expired
before guest BLE initialization under three-instance startup load.
This remains functional virtual-device evidence, not a bit-exact Espressif BT
controller/baseband or hardware/RF result. The API/HLI/trace hook offsets are
pinned to the validated UIFlow2 v2.5.3 build; `elf_artifact_id` must come from
that exact firmware build. Another Core2 firmware build is `NOT RUN` even when
the ELF exposes the same symbol names.

Use the reconnect fields when the same peer process must prove more than one
GATT lifecycle:

```json
{
  "device_id": "core2",
  "runtime": "qemu-unified",
  "network": {
    "profile": "core2-native-hci",
    "elf_artifact_id": "<matching-xtensa-elf-sha256>",
    "ble_reconnect_cycles": 121,
    "ble_reconnect_delay_seconds": 2
  }
}
```

The stock Core2 guest passes 121 cycles in each of three independent
artifact-bound leases. Earlier 20, 30, 60 and 120-cycle gates each passed
`3/3`. The former failure was a stale ACK caused by the Bumble compatibility
layer returning Command Status for the no-response
`HCI_Host_Number_of_Completed_Packets (0x0c35)` command. The fields still
describe the peer workload and must be verified per firmware/runtime.

The legacy `core2-native-vhci` profile remains available for diagnosis:

```json
{
  "device_id": "core2",
  "runtime": "qemu-unified",
  "network": {
    "profile": "core2-native-vhci",
    "elf_artifact_id": "<matching-xtensa-elf-sha256>",
    "attempts": 1,
    "capture_pcap": true
  }
}
```

It starts a QEMU GDB endpoint and uses the supervised bridge for pause,
callback injection and synthetic return. That path passed one service lease
but only `1/2` repeated leases, so it must be labeled diagnostic/compatibility
and is not the preferred production profile.

The StickS3 unified profile closes WiFi and BLE in that same instance:

```json
{
  "device_id": "sticks3",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-sticks3-unified",
    "attempts": 2
  }
}
```

The uploaded image must contain the repository's unified StickS3 probe and the
UIFlow2 HCI-UART test configuration. The service starts one QEMU `m5sticks3`
guest with the ESP32-S3 WiFi MAC/DMA NIC, routes UART1 H4 to Bumble, and starts
a controlled HTTP endpoint on port 18080. `/network` returns
`kind=m5stack-sticks3-unified-qemu-proof`; the evidence ZIP includes the frame,
audio PCM, QOM snapshot, serial, BLE peer log, HTTP request record and network
evidence.

This profile proves a functional open virtual AP on one fixed channel and an
HCI-offload BLE controller. It does not claim WPA2/WPA3, native S3 RF/PHY,
RF-range/security behavior or a native ESP32-S3 Bluetooth controller model.

CoreS3 uses the same one-guest contract:

```json
{
  "device_id": "cores3",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-cores3-unified",
    "attempts": 2
  }
}
```

The CoreS3 image exercises the 320x240 display, touch redraw, AXP2101 power
state, BMI270 IMU, AW88298 speaker PCM, WiFi scan/association/DHCP and a
controlled HTTP request on port `18081`, plus HCI-UART BLE
NUS discovery/subscription/write and notification. `/network` returns
`kind=m5stack-cores3-unified-qemu-proof`; the evidence ZIP includes the frame,
audio PCM, QOM snapshot, serial, BLE peer log, HTTP request record and network
evidence.

Cardputer ADV uses the same one-guest contract:

```json
{
  "device_id": "cardputer-adv",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-cardputer-adv-unified",
    "attempts": 2
  }
}
```

The Cardputer image exercises the 240x135 display, TCA8418 keyboard redraw,
BMI270 IMU, ES8311/NS4150B speaker PCM, WiFi scan/association/DHCP and a
controlled HTTP request on port `18082`, plus HCI-UART BLE NUS
discovery/subscription/write and notification. UART1 uses GPIO15/16 because
GPIO33-38 drive the display; BLE payloads stay within the default attribute
length.

StopWatch uses the same one-guest contract:

```json
{
  "device_id": "stopwatch",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-stopwatch-unified",
    "attempts": 2
  }
}
```

The StopWatch image exercises the 466x466 CO5300 display, CST820 touch,
M5PM1 power telemetry, M5IOE1 G10/AW8737A amplifier state, BMI270 IMU,
ES8311 I2S speaker PCM, WiFi scan/association/DHCP and a controlled HTTP
request on port `18083`, plus HCI-UART BLE NUS discovery/subscription/write
and notification. StopWatch routes PA enable through M5IOE1, not M5PM1; the
device-state expander probe reads the real G10 output state.

AtomS3R uses the same one-guest contract:

```json
{
  "device_id": "atoms3r",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-atoms3r-unified",
    "attempts": 2
  }
}
```

The AtomS3R image exercises the 128x128 display, GPIO41 button, BMI270,
BMM150, LP5562 RGB PWM, WiFi scan/association/DHCP and a controlled HTTP
request on port `18084`, plus HCI-UART BLE NUS discovery/subscription/write
and notification.

PaperColor uses the same one-guest contract:

```json
{
  "device_id": "papercolor",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-papercolor-unified",
    "attempts": 2
  }
}
```

The PaperColor image exercises the 400x600 Spectra 6 display, GPIO buttons,
M5PM1 power, SHT40, ES8311/AW8737A audio, WiFi scan/association/DHCP and a
controlled HTTP request on port `18085`, plus HCI-UART BLE NUS
discovery/subscription/write and notification. GPIO43 is the e-paper DC pin,
so the probe routes its audit UART output through GPIO44/45.

PaperMono uses the same one-guest contract:

```json
{
  "device_id": "papermono",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-papermono-unified",
    "attempts": 2
  }
}
```

The PaperMono image exercises the 480x800 four-gray SSD1677 display, FT6336
touch, GPIO keys, M5PM1/IP2315 power and charging state, BMI270, RX8130,
RGB LED, GPIO42 speaker, WiFi scan/association/DHCP and a controlled HTTP
request on port `18086`, plus HCI-UART BLE NUS discovery/subscription/write
and notification.

StackChan uses the same one-guest contract:

```json
{
  "device_id": "stackchan",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-stackchan-unified",
    "attempts": 2
  }
}
```

The StackChan image exercises the 320x240 ILI9342 display, FT6336 and Si12T
touch, GC0308 camera, BMI270/BMM150, AXP2101/AW9523/M5IOE1, INA226, LTR553,
PCF8563, two SCS servos, ES7210/AW88298 audio, ST25R3916 NFC and RMT IR,
together with WiFi DHCP/HTTP on port `18087` and UART2 HCI BLE NUS. UART1
remains the servo bus; UART2 uses GPIO31/32 to avoid the camera, audio and
servo pins. The service pauses the guest at the post-driver IMU setup marker,
injects the configured peripheral state, and resumes it before readiness.
Its evidence ZIP also retains microphone source PCM and NEC IR capture.

StamPLC uses the same one-guest contract:

```json
{
  "device_id": "stamplc",
  "runtime": "qemu-unified",
  "ready_timeout_seconds": 60,
  "network": {
    "profile": "uiflow2-stamplc-unified",
    "attempts": 2
  }
}
```

The StamPLC image exercises the 240x135 ST7789 display, keys/RGB,
AW9523 relay/input banks, INA226, LM75, RX8130, TWAI CAN, PWR-485 and the
G44 buzzer together with WiFi DHCP/HTTP on port `18088` and UART1 HCI BLE.
UART2 remains the PWR-485 bus on G0/G39/G46; UART1 HCI uses the documented
custom G40/G41 pins.

State machine:

```text
provisioning -> flashing -> booting -> running
                                  \-> failed
running -> stopping -> stopped
```

`POST /api/v1/sessions` is asynchronous and returns `202 Accepted` while the
session is provisioning. Poll the session or call `wait`.

`running` means the QEMU process and QMP control channel are alive. It does
not guarantee that the application reached its first frame or a serial marker.
For application-level readiness, provide `ready_marker` in the create request
or call `/wait`, then inspect serial and/or `/frame.png`.

Audio data-plane tests can provide a narrow, trusted-local `runtime_env`
object when creating a session:

```json
{
  "device_id": "cores3",
  "firmware_id": "<firmware-id>",
  "runtime_env": {
    "M5SW_I2S_DMA_IRQ": "1",
    "M5SW_I2S_PCM_FILE": "/private/tmp/session/speaker.pcm",
    "M5SW_I2S_RX_PCM_FILE": "/private/tmp/session/microphone.pcm"
  }
}
```

Core2 board-revision probes may additionally set
`M5SW_CORE2_PMIC=axp192` or `M5SW_CORE2_PMIC=axp2101`. Only
`M5SW_CORE2_PMIC`, `M5SW_I2S_DMA_IRQ`, `M5SW_I2S_PCM_FILE`,
`M5SW_I2S_RX_PCM_FILE`, and `M5SW_I2S_TRACE` are accepted. This is a
trusted-workstation control surface; do not expose it to untrusted tenants.

Devices whose `features.storage` is true accept a content-addressed raw SD
image through `storage.sd_image_artifact_id` in the session request:

```json
{
  "device_id": "papermono",
  "firmware_id": "<firmware-id>",
  "storage": {
    "sd_image_artifact_id": "<sha256-artifact-id>"
  }
}
```

The service validates that the target device has a modeled SDMMC card, copies
the artifact into the session directory, re-hashes the isolated copy, and
attaches it with `-drive if=sd,format=raw`. The source artifact is never
mounted writable. Session snapshots, persisted records and evidence bundles
expose the artifact SHA, size, interface and session-isolated copy boundary.
`platform/tools/sd_image.py` creates deterministic FAT32+MBR or FAT16
superfloppy fixtures for reproducible storage-dependent firmware tests.

Firmware that expects first-boot or provisioned NVS data can attach a complete
NVS partition without changing the firmware artifact:

```json
{
  "device_id": "atoms3r",
  "firmware_id": "<firmware-id>",
  "nvs": {
    "partition_label": "nvs",
    "image_artifact_id": "<sha256-artifact-id>"
  }
}
```

The service parses the firmware partition table, requires an NVS partition
(type `data`, subtype `nvs`) with the requested label, and requires the
artifact size to equal the partition size. It then copies the source firmware
to the session, writes the NVS bytes only into that isolated copy, and records
both the base firmware SHA and effective Flash SHA. The source firmware and
NVS artifacts are never modified. Session snapshots and evidence include the
partition label/offset/size, NVS fixture SHA and overlay boundary. A QEMU
retry restores the clean firmware copy and reapplies the same NVS fixture.
The request field is `nvs.image_artifact_id`; `partition_label` defaults to
`nvs`. NVS fixtures are accepted only by QEMU guest runtimes: `qemu`,
`qemu-wifi`, `qemu-ble` and `qemu-unified`. The separate `runtime=network`
diagnostic lane and the Tab5 backend reject `nvs` with `409
nvs_not_supported`, because neither executes the requested session-isolated
guest Flash path.

`platform/tools/nvs_image.py` creates deterministic NVSv2 fixtures containing
namespace and string values. Its encoder is checked byte-for-byte against
`esp-idf-nvs-partition-gen 0.3.0`. NVS provisioning data is a runtime fixture,
not a firmware-quality PASS; tests must still distinguish missing user data,
WiFi security behavior, cloud credentials and headless/application behavior.
The OpenAI comparison reaches DNS/TCP with both Open and WPA2-PSK fixtures.
Its third control uses a wrong WPA2 password and verifies M2 MIC rejection,
deauthentication, retry and no DHCP. This closes the former `RUNTIME-05`
WPA2 model gap for the validated pairwise/unicast path.

Network sessions use a validated scenario:

```json
{
  "device_id": "sticks3",
  "firmware_id": "<firmware-id>",
  "runtime": "network",
  "network": {
    "profile": "esp-idf-http",
    "timeout_seconds": 45
  }
}
```

Profiles are:

- `esp-idf-http`: WiFi, DHCP and a controlled complete HTTP/TCP download;
- `esp-idf-smoke`: WiFi, DHCP and the upstream comprehensive smoke suite;
- `idf-dns-udp`: WiFi, DHCP, host-forwarder DNS and a controlled UDP round
  trip against a disposable host peer;
- `esp-idf-coex`: the upstream NimBLE/WiFi coexistence application plus an
  external Bumble GATT connect/write/readback while WiFi remains active;
- `uiflow2-sticks3`: UIFlow2 network/BLE probe. BLE requires a matching ELF
  uploaded as an artifact and referenced by `elf_artifact_id`.
- `generic-observe`: runs an arbitrary compatible image for the requested
  timeout window. With no `expected_markers` the result is `PARTIAL` and
  proves only that the process/serial path ran; add up to 16 marker strings to
  obtain an application-level PASS/FAIL assertion. Add
  `net_mode=user,restrict=yes` for untrusted firmware. When `ble=true`, the
  profile runs an external Bumble observer and requires
  `elf_artifact_id`; successful BLE requires GATT discovery, subscription,
  write, and guest-side delivery.

#### Firmware-created SoftAP and provisioning portal

`generic-observe` can join a SoftAP created by the firmware and expose selected
TCP/UDP guest ports on loopback for provisioning review:

```json
{
  "device_id": "sticks3",
  "firmware_id": "<firmware-id>",
  "runtime": "network",
  "network": {
    "profile": "generic-observe",
    "timeout_seconds": 120,
    "expected_markers": ["PROVISIONING_READY"],
    "firmware_ap_password": "<firmware-ap-password>",
    "hostfwd": [
      {
        "protocol": "tcp",
        "host_port": 18080,
        "guest_port": 80
      }
    ]
  }
}
```

While the session is running, the reviewer can open
`http://127.0.0.1:18080/` or drive the portal from an automated HTTP client.
The host address is fixed to `127.0.0.1`; callers cannot bind a forward to the
workstation LAN. Host ports must be in `1024-65535`, guest ports in `1-65535`,
and duplicate `protocol`/`host_port` pairs are rejected. A session accepts at
most eight forwards.

`firmware_ap_password` is optional. When omitted, esp-emu uses
`wifi_password`; an explicit empty string selects an open AP. Both passwords
are redacted from persisted session JSON, command evidence and serial logs.
The engine supports open and WPA2-PSK firmware APs. WPA3-SAE-only and hidden
SSIDs are `NOT RUN`. TCP `hostfwd` reaches the firmware AP while that path is
up and otherwise uses the station path; UDP `hostfwd` reaches only the station
path.

This path drives the real guest portal and can prove its HTTP behavior. It does
not emulate a physical phone OS, captive-portal detection, mDNS discovery or
RF behavior, and it does not provide framebuffer/input from the same guest.
Keep those boundaries explicit in firmware-review evidence.

For `qemu-wifi`, `qemu-unified` and legacy `qemu-ble` sessions,
`GET /sessions/{id}/network` recomputes evidence from the current serial and
peer logs. Live session snapshots refresh non-PASS network evidence, and stop
captures the final evidence before terminating the guest. A stopping session
therefore retains the markers observed at the end of its run instead of the
initial empty-serial `PARTIAL` result. For a unified session this endpoint
describes the radio slice of the same guest; frame, input, device-state and
audio evidence remain attached to the same session and evidence ZIP.

`network.net_mode` accepts `user` or `user,restrict=yes`. Validated test
profiles default to `user`; callers may explicitly select restricted mode.
Use `user` for unrecognized firmware only inside a disposable VM.

`network.console_mode` accepts `auto`, `uart0` and `usb-jtag`.
`generic-observe` uses the device's matrix `network_console` value when one is
declared; ESP32-C6 UIFlow2 entries currently use `usb-jtag`. Other generic
devices default to `auto`. Validated lane profiles default to `uart0`.

`network.i2c_devices` accepts at most 32 canonical endpoint definitions such as
`0:0x34,fill=0x00,reg=0x03=0x4A`. They are served by the emulated SoC I2C
controller and exist to help a board driver pass identity/bootstrap reads.
This is not full keyboard, PMIC, touch or sensor simulation; a firmware test
must still record those board data planes separately as `PARTIAL` or `NOT RUN`.

For StickS3 BLE-only, use
`{"profile":"uiflow2-sticks3","wifi":false,"ble":true,"elf_artifact_id":"..."}`.
The same guest also supports `wifi=true,ble=true`; the runner stages REPL input
around UIFlow2's WebREPL startup and has passed simultaneous association/DHCP
and BLE GATT.

The service stores the latest captured framebuffer as `last-frame.png` and
`last-frame.json`. When a session stops, `frame.png` returns this last-known
frame instead of failing. Session snapshots expose `last_frame_available` and
`last_frame_captured_at`. QEMU sessions also expose `runtime_memory` with the
CLI request, effective memory, resolution source and physical-timing
`NOT RUN` boundary; `runtime=network` sessions set it to `null`.

Devices with a normalized runtime-state probe also expose
`GET /sessions/{id}/device-state`. StickS3 currently reports M5PM1 power state
and BMI270 IMU values through the same QMP instance. Live sampling is persisted
to the session directory and remains readable as a last-known snapshot after
the session stops. This endpoint does not expose arbitrary QOM internals.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Service health and capacity |
| GET | `/api/v1/devices` | Device catalog; add `?include_unsupported=0` to hide disabled rows |
| GET | `/api/v1/devices/{device_id}` | One device profile |
| GET | `/api/v1/capacity` | Global and per-device active lease counts |
| GET | `/api/v1/worker` | Local worker identity, heartbeat, state, leases and restart classification |
| POST | `/api/v1/worker/drain` | Stop new lease admission; active sessions continue |
| POST | `/api/v1/worker/resume` | Resume admission after a drain |
| GET | `/api/v1/workers` | List remote worker registrations, freshness and aggregate capacity |
| POST | `/api/v1/workers` | Register or idempotently retry a remote worker identity |
| POST | `/api/v1/workers/{worker_id}/heartbeat` | Update identity-bound heartbeat, state, capabilities and active leases |
| POST | `/api/v1/workers/{worker_id}/drain` | Stop accepting new remote leases and report draining/drained |
| POST | `/api/v1/workers/{worker_id}/stop` | Mark the current remote generation stopped |
| POST | `/api/v1/workers/{worker_id}/results` | Append bounded result metadata and optional evidence SHA256 |
| GET | `/api/v1/jobs` | List durable jobs, status counts and optional status filter |
| POST | `/api/v1/jobs` | Submit an idempotent capability-constrained job |
| GET | `/api/v1/jobs/{job_id}` | Read one durable job |
| POST | `/api/v1/jobs/claim` | Claim the oldest compatible job for a ready registered worker |
| POST | `/api/v1/jobs/{job_id}/heartbeat` | Extend the identity-bound worker lease |
| POST | `/api/v1/jobs/{job_id}/result` | Record a terminal result and optional evidence SHA256 |
| POST | `/api/v1/jobs/{job_id}/cancel` | Cancel a queued or leased job |
| GET | `/api/v1/storage` | Session/cache/disk usage and retention limits |
| POST | `/api/v1/storage/prune` | Apply retention; `include_cache=0` skips cache GC |
| POST | `/api/v1/artifacts` | Upload a binary artifact |
| GET | `/api/v1/artifacts/{artifact_id}` | Artifact metadata |
| DELETE | `/api/v1/artifacts/{artifact_id}` | Delete an artifact |
| POST | `/api/v1/artifact-uploads` | Start a resumable artifact upload |
| GET | `/api/v1/artifact-uploads/{upload_id}` | Read resumable upload progress |
| POST | `/api/v1/artifact-uploads/{upload_id}/chunks` | Append one contiguous chunk |
| POST | `/api/v1/artifact-uploads/{upload_id}/complete` | Verify and publish the artifact |
| DELETE | `/api/v1/artifact-uploads/{upload_id}` | Abort and clean staging |
| POST | `/api/v1/firmware` | Compose a merged or segmented firmware |
| POST | `/api/v1/firmware/import` | Normalize an uploaded `.bin`/WebBurner/ESP-IDF package |
| GET | `/api/v1/firmware/{firmware_id}` | Firmware metadata |
| POST | `/api/v1/firmware/analyze` | Validate image, chip ID, partition table and app descriptor |
| GET | `/api/v1/firmware/{firmware_id}/analysis` | Read stored static analysis |
| GET | `/api/v1/sessions` | List sessions; history is included by default, `include_stopped=0` shows active leases only |
| POST | `/api/v1/sessions` | Create a session |
| DELETE | `/api/v1/sessions?state=stopped&purge=1` | Clear stopped/failed history |
| GET | `/api/v1/sessions/{id}` | Session status |
| GET | `/api/v1/sessions/{id}/events` | Lifecycle event timeline |
| GET | `/api/v1/sessions/{id}/network` | Machine-readable network/BLE evidence |
| POST | `/api/v1/sessions/{id}/network-fault` | Set `wifi0` link state or toggle the WiFi model's `radio-enabled` QOM property |
| GET | `/api/v1/sessions/{id}/device-state` | Live or last-known normalized device state |
| POST | `/api/v1/sessions/{id}/wait` | Wait for serial/frame readiness; `wait_for_completion=true` waits for a one-shot network session to finish |
| GET | `/api/v1/sessions/{id}/evidence` | Download a hashed evidence ZIP |
| GET | `/api/v1/sessions/{id}/serial?offset=0&limit=65536` | Incremental serial read |
| GET | `/api/v1/sessions/{id}/logs?offset=0&limit=65536` | Serial plus runtime stdout/stderr tail |
| GET | `/api/v1/sessions/{id}/frame.png` | Live or last-known framebuffer as PNG |
| POST | `/api/v1/sessions/{id}/input` | Key, touch, long press or drag |
| POST | `/api/v1/sessions/{id}/qom` | Set a QOM property |
| GET | `/api/v1/sessions/{id}/qom?path=...&property=...` | Read a QOM property |
| GET | `/api/v1/sessions/{id}/qom/list?path=/machine` | List QOM properties |
| POST | `/api/v1/sessions/{id}/qom-snapshot` | Store a recursive QOM snapshot |
| GET | `/api/v1/sessions/{id}/qom/diff?before=...&after=...` | Diff stored QOM snapshots |
| GET | `/api/v1/sessions/{id}/flash?format=sha256\|bin` | Read virtual flash hash or bytes |
| POST | `/api/v1/sessions/{id}/flash-snapshot` | Store a virtual flash snapshot |
| GET | `/api/v1/sessions/{id}/flash/diff?before=...&after=...` | Diff flash snapshots |
| POST | `/api/v1/sessions/{id}/reset` | Reset the guest |
| POST | `/api/v1/sessions/{id}/renew` | Extend the lease |
| POST | `/api/v1/sessions/{id}/stop` | Stop; full Flash is released unless `retain_flash=true` |
| DELETE | `/api/v1/sessions/{id}` | Stop and optionally purge session files; supports `retain_flash=1` |

## Quick examples

### Create a reference UIFlow2 device

If the reference firmware is cached for the device, `firmware_id` can be
omitted:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"sticks3","ttl_seconds":600}' \
  http://127.0.0.1:8787/api/v1/sessions
```

The first run prepares and verifies a virtual flash through the backend's
flashing path. Core2 and Tab5 use an exact host-image copy: Core2 avoids the
intermittent LX6 ROM download handshake, while the esp-emu 0.50.0 Tab5 esptool
path does not support upper flash regions. Later sessions with the same device
and firmware hash copy the prepared flash cache into a new per-session flash
file.

Core2 board inventory and the QEMU machine both expose 8 MiB PSRAM.
Native-controller profiles request CLI `-m 0`, and the current `m5core2`
machine resolves this to an 8 MiB QOM memory with `has_psram=true`; the
evidence records both values. The normal heap is limited to the ESP32 4 MiB
DRAM1 mapping window, while `tests/firmware/core2_psram_himem/` covers the
upper bank through MMU remapping. Always read the session evidence memory
fields before comparing runs. This is not physical cache/PSRAM timing
validation. Tab5 sessions attach the board's
PI4IOE, INA226, RX8130 and BMI270 register devices to I2C1 before boot, so
application firmware sees the documented addresses rather than an empty bus.

### Wait for boot

```bash
SID='<session-id>'
curl -sS -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":60,"ready":{"frame_nonblank":true,"frame_min_bytes":1024,"frame_min_nonblack_pixels":16}}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/wait
```

For firmware with known serial markers:

```json
{
  "timeout_seconds": 60,
  "ready": {
    "serial_markers": ["APP_READY", "UIFLOW_READY"],
    "frame_nonblank": true,
    "frame_min_bytes": 1024,
    "frame_min_nonblack_pixels": 16,
    "require_all": true
  }
}
```

The response includes `ready`, `ready_reason`, matched serial markers,
`first_serial_at`, `first_frame_at` and frame metrics without embedding the
PNG bytes.

### Evidence bundle

```bash
curl -sS \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>/evidence?include=manifest,serial,frames,logs,qom' \
  -o /tmp/m5-evidence.zip
```

### Wait for a network session

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":90,"wait_for_completion":true}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/wait
```

`GET /sessions/{id}/network` returns the final `evidence.json`, including
checks, artifact hashes, log hashes and explicit simulation-only limits.

Add `flash` to include the full isolated virtual flash while it is still
available. A stopped session releases it by default, so request the evidence
ZIP before stop or stop with `retain_flash=1`. The ZIP always contains
`manifest.json` with session timeline, file hashes, device warnings and flash
metadata; released images remain represented by their firmware hash.

### QOM and flash snapshots

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"path":"/machine","depth":2,"max_nodes":500}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/qom-snapshot

curl -sS -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/flash-snapshot
```

Use the returned `snapshot_id` values with the corresponding `diff` endpoint.
Flash snapshot diff reports changed byte count and contiguous ranges, not a
second full-size image.

### Network fault and reconnect evidence

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"action":"down","target":"radio"}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/network-fault

sleep 2

curl -sS -H 'Content-Type: application/json' \
  -d '{"action":"up","target":"radio"}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/network-fault
```

`target=link` (the compatibility default) invokes QMP `set_link` on `wifi0`.
`target=radio` locates the QEMU WiFi device's `radio-enabled` QOM property,
stops/starts beacon and management replies, and records the QOM path in the
timeline event. The radio action requires a model exposing that property; an
unsupported model returns `radio_fault_not_supported`.

A reconnect PASS needs guest-side failure/recovery and DHCP/data-plane
evidence after radio restoration; the control command alone is not a PASS.
The retained StickS3 probe also performs HTTP `/before` and `/after` requests,
yielding a pcap with the full before/after exchange.

### Read serial incrementally

```bash
curl -sS \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>/serial?offset=0&limit=65536'
```

Use `next_offset` on the next request. Serial content is decoded as UTF-8 with
replacement characters; the underlying file remains the authoritative evidence.

### Get a screenshot

```bash
curl -sS \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/frame.png \
  -o /tmp/device.png
```

The response headers include `X-Frame-Width`, `X-Frame-Height` and
`X-Frame-SHA256`. The Live Sessions page polls active framebuffers independently
from session metadata, targets about 8 FPS, and skips texture updates when the
frame hash is unchanged. For a recently stopped session it returns the persisted
last-known frame.

### Inject input

Key:

```json
{"kind":"key","key":"a","settle_seconds":0.3}
```

Physical hold uses separate key-down and key-up requests. The Live Sessions 3D
shells use this form so a model button is down only while the pointer is held:

```json
{"kind":"key","key":"a","action":"down","settle_seconds":0.02}
{"kind":"key","key":"a","action":"up","settle_seconds":0.02}
```

Touch:

```json
{"kind":"touch","x":67,"y":160,"settle_seconds":0.3}
```

Long press:

```json
{"kind":"longpress","x":67,"y":160,"hold_seconds":1.0}
```

Drag:

```json
{"kind":"drag","x1":20,"y1":200,"x2":100,"y2":200}
```

### Set a QOM value

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"path":"/machine/bmi270","property":"accel-x","value":0.25}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/qom
```

QOM is a trusted-local control surface. Do not expose arbitrary QOM access to
untrusted tenants.

### Upload and boot an arbitrary merged image

```bash
curl -sS -X POST \
  -H 'Content-Type: application/octet-stream' \
  -H 'X-Artifact-Name: webburner.bin' \
  --data-binary @webburner.bin \
  http://127.0.0.1:8787/api/v1/artifacts
```

Then create firmware:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","kind":"merged","artifact_id":"<sha256>"}' \
  http://127.0.0.1:8787/api/v1/firmware
```

Then create the session with the returned `firmware_id`:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","firmware_id":"<firmware-id>","ttl_seconds":900}' \
  http://127.0.0.1:8787/api/v1/sessions
```

This accepts a merged image or segmented image. It does not prove that a vendor
artifact is complete; if the source provides only an app image, the caller must
upload the bootloader, partition table and filesystem segments as well.

### Renew or delete

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"ttl_seconds":900}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/renew

curl -sS -X DELETE \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>?purge=0&retain_flash=0'
```

Without `purge=1`, `session.json`, the event timeline, serial/QEMU logs, the
last frame and device state remain under the state directory. The mutable
`virtual-flash.bin` is deleted by default because it is the largest per-session
artifact and is usually not needed after the evidence bundle and frame are
collected. Pass `retain_flash=1` when a stopped session must continue to support
flash reads, snapshots or before/after diffs. The session is removed from the
active capacity count immediately and is restored as history after a service
restart.

## Concurrency and lifecycle rules

- one session owns one flash copy and one QEMU process;
- a session cannot be shared by two leases;
- `max_sessions` is global;
- `max_per_device` applies to each device model;
- capacity limits can be changed with `--max-sessions`, `--max-per-device`,
  `M5_SERVICE_MAX_SESSIONS`, or `M5_SERVICE_MAX_PER_DEVICE`;
- expired sessions are stopped by a janitor thread;
- expired sessions release their mutable Flash unless
  `M5_SERVICE_RETAIN_SESSION_FLASH=1`;
- stopped/failed sessions remain queryable across service restarts while they
  satisfy the configured age/count/byte retention limits;
- the janitor prunes the oldest stopped/failed sessions first and never touches
  active states;
- unreferenced artifact, firmware and prepared-flash cache entries become
  eligible for GC after `M5_SERVICE_CACHE_GRACE`; protected entries referenced
  by a retained session or firmware record remain;
- abandoned resumable-upload staging and expired upload-control records are
  removed by the same janitor;
- writes and new leases fail with HTTP `507 storage_exhausted` before consuming
  the configured free-space reserve;
- a session that was still active when the service stopped is re-attached only
  after PID start-time, QMP-socket ownership and `query-status=running` checks;
  unverified sessions become `failed` with `interrupted=true` and an explicit
  event. Trusted-host unified sessions additionally recreate the HTTP fixture
  with durable request generations and adopt a surviving BLE peer only after
  exact process ownership checks. Namespace-managed, Tab5 and cross-host
  companion recovery remain unsupported and fail closed;
- `GET /sessions?include_stopped=0` hides stopped/failed history from a UI;
- the web dashboard shows active leases plus sessions completed in the last
  30 minutes when a last-known frame or serial-only view is available;
  “显示全部历史” expands the list;
- `DELETE /sessions?state=stopped&purge=1` removes stopped/failed history and
  their per-session files; a later `POST /storage/prune?include_cache=1`
  garbage-collects caches that are no longer referenced;
- a guest reset does not make a session safe for a different tenant;
- delete and recreate for tenant isolation.
- `running` is an emulator-process state; use serial markers or screenshots to
  establish application and visual readiness.
- capacity errors return `429` with `Retry-After: 2`.

## Current limitations

- `runtime=network` sessions are diagnostic lanes; StickS3, CoreS3,
  Cardputer ADV, StopWatch, AtomS3R, PaperColor, PaperMono, StackChan,
  StamPLC, NanoC6 and Nesso N1 instead use `runtime=qemu-unified` with their
  unified profiles for one combined guest (`qemu-ble` remains a legacy alias);
- supported S3 unified profiles exercise an Open AP on one fixed virtual
  channel. `qemu-wifi/profile=generic-observe` additionally validates
  WPA2-PSK M1-M4, pairwise CCMP RX and the correct/incorrect-password split.
  WPA3, group-key multicast and a native S3 PHY/radio model remain out of
  scope. BLE is HCI-offload over UART1 (UART2 on StackChan);
- Core2 radio support remains environment-gated; `qemu-wifi` and `qemu-ble`
  are compatibility runtimes. `qemu-unified` with
  `profile=core2-unified` combines OpenMAC WiFi, UART1 BLE NUS and board
  peripherals in one `m5core2` guest;
  `core2-ble-advertise` stops at native controller/advertising control;
  `core2-hci-gatt` closes external Bumble GATT without WiFi.
  `core2-native-hci` closes stock-firmware external NUS GATT together with
  board/frame/QOM, WiFi/public network, pcap and evidence in five independent
  service leases without GDB. Two independent `5×10s` hold batches also pass
  `10/10`; three `60s` holds pass `3/3`, and two `120s` holds pass `2/2`,
  with zero HLI errors and empty HLI/meta queues. Patch `0008` preallocates
  real guest HCI-event buffers and ACL mbufs; two independent no-stagger
  `4×120s` gates pass `8/8`, with 36 events and 9 ACLs per lease on the fast
  path and zero errors/reset/panic. Two three-instance `3×120s` gates also
  pass `6/6`; their peer scan window is derived from session readiness and
  the current fixed-clock sustained PSRAM sweep floor is `hold/12`. The first four-instance
  `4×120s` batch failed `1/4` in NimBLE ACK/HLI handling; `0009` expands the
  real guest reserve to `8/4`, after which two independent four-instance
  batches pass `8/8`. Two independent five-instance `5×120s` batches with a
  30-second startup stagger pass `5/5` each (`10/10`) at maximum concurrency 5.
  The earlier `shift=auto` zero-stagger implementation passed one `5/5`
  batch but an independent confirmation failed `3/5`. The current default is
  fixed `icount shift=5,align=off,sleep=off`; `M5_CORE2_ICOUNT_SHIFT` accepts
  `auto` or `0-10` only as an explicit diagnostic override, while the
  concurrency gate requires the fixed value. The unified test workload starts
  its BLE server before WiFi and sustained PSRAM stress. Two new independent
  zero-stagger `5×120s` batches then pass `5/5` each (`10/10`) at maximum
  concurrency 5, with 14-15 PSRAM sweeps per lease and zero HLI/reset/panic/
  dropped counters. Two independent zero-stagger `6×120s` batches then pass
  `6/6` each (`12/12`) at maximum concurrency 6, with 12-13 PSRAM sweeps per
  lease. An eight-instance control under the old floor failed `4/8` only
  because four leases completed 11 contiguous sweeps while all other checks
  passed. After calibrating to `hold/12`, two independent `8×120s` batches
  pass `8/8` each (`16/16`) at the service per-device cap of 8. More than
  eight instances remain open. Three independent
  leases pass
  each of the 20, 30, 60, 120 and 121 same-guest reconnect gates; the
  121-cycle runs balance HLI 3405/3405, deliver 2316 events and 1089 ACLs,
  and return the connection/L2CAP/GATT pools to 3/9/3.
  `network.ble_linger_seconds` can keep the external GATT peer connected
  beyond its initial exchange; two active-link `600s` holds pass `2/2` with
  `peer-closed=0`, `tx-queue-depth=0` and `last-error=0`. A `7200s`
  artifact-bound active-BLE hold passes the functional gate with frozen
  firmware/ELF/QEMU hashes, frame/QOM/WiFi/public DNS/HTTP/GATT/pcap and
  cleanup; QEMU host RSS grows from 744160 to 1202176 KiB, so memory growth
  remains the historical unbounded-TCG `REVIEW`. The later `tb-size=128`
  artifact-bound `7200s` rerun also passes with 240 resource samples, RSS
  `323536→252992 KiB` and phys footprint `250880→188416 KiB`; the tested
  host-memory workload shows no sustained growth, while physical PSRAM/cache
  timing remains `NOT RUN`.
  `network.ble_reconnect_cycles` (1-121) asks one external peer process to run
  multiple complete scan/connect/GATT/disconnect cycles without restarting the
  guest; `network.ble_reconnect_delay_seconds` controls the pause before the
  next scan. Stock Core2 passes 20, 30, 60 and 120 complete cycles in each of
  three leases after the peer compatibility layer stopped returning a response
  for no-response opcode `0x0c35`;
  the historical failure and root cause remain in
  `evidence-2026-10-24-reconnect2-fail.json`;
  the ten-, twenty-, thirty-, sixty- and 120-cycle evidence is
  `evidence-2026-10-24-hci4-reconnect10-3x.json`,
  `evidence-2026-10-24-hci4-reconnect20-3x.json`,
  `evidence-2026-10-24-hci4-reconnect30-3x.json`,
  `evidence-2026-10-24-hci4-reconnect60-3x.json` and
  `evidence-2026-10-24-hci4-reconnect120-3x.json`. Three independent leases
  pass 120 cycles each. The first 121-cycle run completed 29 cycles and
  started cycle 30 before a fixed 180-second readiness budget terminated a
  healthy session with no guest panic. Device Service and the runner now use
  the same workload-aware budget
  `min(7200, 60 + cycles * (6 + reconnect_delay_seconds))`; 121 cycles with
  a two-second delay therefore receive 1028 seconds. The failed run remains
  in
  `evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json`. A later
  reconnect-only run completed `121/121` but exposed accelerator sampling
  only inside the hold path; after moving that sample to first-running state,
  all three independent artifact-bound 121-cycle leases pass every required
  check. The aggregate evidence is
  `evidence-2026-10-25-hci4-reconnect121-3x.json`; it binds identical
  firmware/ELF/QEMU/tool hashes across runs and includes the earlier
  single-lease evidence. The first four-instance `4x120s` batch fails `1/4`
  in NimBLE ACK/HLI handling; `0009` expands the real guest reserve and two
  independent four-instance batches then pass `8/8`. Two independent
  five-instance staggered batches then pass `10/10`; fixed-icount zero-stagger
  five-instance batches also pass `10/10`; two six-instance batches pass
  `12/12`, and two calibrated eight-instance batches pass `16/16`, while the
  earlier `shift=auto` `5/5 PASS`/`3/5 FAIL` and eight-instance threshold
  `4/8` controls remain historical evidence. The remaining validation gates
  are more than eight instances, long-run throughput and additional teardown modes;
  `core2-native-vhci` remains a GDB diagnostic/compatibility profile whose
  repeated-lease result was `1/2`; neither profile is a bit-exact BT
  controller model;
- `network.ble_post_pass_continuity=true` is an explicit trusted-host test
  mode: the BLE peer emits its initial PASS, waits for the session-local
  `ble-continuity.trigger`, then performs one extra GATT cycle. Combined with a
  bounded worker `request.evidence_delay_seconds`, a runtime restart fixture
  can adopt the peer, recreate the HTTP fixture, trigger the second GATT cycle,
  observe a second guest HTTP request, and only then collect evidence. The
  trigger is not a production guest-control API;
- NanoC6 `nanoc6-hci-ble` closes board peripherals, QEMU C6 WiFi DHCP/HTTP
  and UART1 HCI BLE in one C6 guest;
- Nesso N1 `nesso-unified` adds display/touch, PI4IOE, BQ27220/AW32001,
  BMI270, SX1262, IR, buzzer, QEMU C6 WiFi DHCP/HTTP and UART1 HCI BLE in
  one C6 guest. Stock Nesso UIFlow2 `hardware.RGB()` remains `NOT RUN`;
- CardputerZero is not enabled;
- Tab5 camera/audio/USB/SDIO and dynamic peripheral state remain incomplete;
- uploaded Tab5 firmware can boot, but screenshot/input currently require the
  matching reference ELF;
- normalized `device-state` probes currently exist for StickS3, CoreS3,
  Cardputer ADV, StopWatch, AtomS3R, PaperColor, PaperMono, StackChan and
  StamPLC, plus environment-gated Core2; other devices expose session
  metadata, framebuffer and serial without inventing component values;
- a verified running QEMU process can be re-attached across service restart;
  Tab5/network lanes, paused QEMU, stale PIDs, changed start times and missing
  QMP sockets remain interrupted history;
- reference firmware must already exist in `platform/.cache/firmware`;
- custom firmware must match the selected device's SoC, flash size, partition
  layout and modeled controllers;
- Core2 startup starvation is mitigated by deterministic TCG/icount scheduling
  (10/10 first attempts), but physical cache/PSRAM equivalence remains
  unverified. `core2-native-hci` passed `HCI-4` in five independent Device
  Service leases with no GDB bridge, and the halt-gated `5×10s`
  extended-run gate passes two independent batches. The `0008` fast path also
  closes two-instance no-stagger cold start with two independent `8/8`
  aggregate gates; two three-instance gates add `6/6`. The first four-instance
  batch failed `1/4`; `0009` expands the real guest reserve and two independent
  four-instance gates then pass `8/8`. Two five-instance 30-second-stagger
  gates pass `10/10`, and two fixed-`shift=5` zero-stagger gates pass `10/10`;
  the earlier adaptive-time `5/5 PASS`/`3/5 FAIL` evidence remains retained.
  Two fixed-icount zero-stagger six-instance gates pass `12/12`; after
  `hold/12` calibration, two eight-instance gates pass `16/16`. More than
  eight instances remain open. Long-run throughput, additional teardown modes,
  bit-exact controller/baseband, coexistence and
  same-firmware hardware validation remain open;
- CoreS3 UIFlow startup palette/alpha PNG images have a known striped-rendering
  boundary; ordinary opaque drawing is unaffected. See
  [`cores3-image-rendering-boundary.md`](cores3-image-rendering-boundary.md);
- the API creates simulation evidence only, not real-hardware PASS;
- QEMU stderr/stdout and serial logs can contain firmware-controlled text and
  must be treated as untrusted evidence.
