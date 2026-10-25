# Simulator host service architecture

Date: `2026-10-25`

For the one-page product, code and task overview, start with
[`engineering-handoff.md`](engineering-handoff.md). This page describes the
service architecture and lifecycle; mutable counts remain in
[`project-snapshot.md`](project-snapshot.md).

## Implementation status

The local v1 API and on-demand process runner are implemented in
`platform/tools/device_service.py` and `platform/tools/serve.py`.

Implemented:

- device catalog and capability discovery;
- exclusive session leases with TTL and capacity limits;
- content-addressed direct artifact upload and resumable chunk upload with
  write rollback, abort and abandoned-staging GC;
- merged and segmented firmware composition;
- real esptool-backed first-run flash preparation plus cached flash images;
- one isolated flash copy per session;
- serial/log/frame/input/QOM/reset/delete APIs;
- one-guest `qemu-unified` board/WiFi/BLE profiles and a separate
  `runtime=network` diagnostic lane;
- loopback SoftAP provisioning portals through `firmware_ap_password` and
  `hostfwd`;
- restart-safe session history and last-known evidence restoration;
- a persistent local worker record with stable identity, exclusive state-dir
  lock, process generation, heartbeat, lease admission, drain/resume and
  abandoned-lease classification after restart;
- a persistent remote-worker directory with identity/generation conflict
  checks, heartbeat, drain/stop, capabilities and bounded result metadata;
- a durable pull-based job queue with idempotency, capability matching,
  claim/lease heartbeat, expiry retry, cancellation, terminal result and
  stale/stopped/generation reconciliation;
- active-token HMAC-authenticated IPv4 multicast control discovery, including
  expiry, wrong-token and post-rotation checks;
- HMAC-authenticated unicast discovery seed for cross-subnet/NAT workers,
  validated through two isolated subnets, IPv4 forwarding and masquerade;
- bounded network-partition lease fencing that stops a worker-reachable
  runtime, reaps both an OS child process and a real worker-local QEMU PID,
  suppresses stale results and lets a new lease complete after expiry/requeue;
- a same-host HTTP-only executor that claims a job, runs a real StickS3 QEMU
  session, downloads an evidence ZIP/SHA256, stops with `purge=0` and reports
  the terminal result;
- a worker-local execution fixture with a central control service and an
  independent worker-runtime Device Service in two veth-connected Linux
  network namespaces; the worker runtime prepares artifact/firmware, starts a
  real StickS3 QEMU session, returns serial/frame/QOM evidence, and cleans up
  QEMU and both namespaces while the central service owns claim, heartbeat and
  terminal result;
- worker-only mutation authentication using a generation-derived HMAC,
  timestamp/nonce replay protection and path/body identity binding;
- HTTPS with TLS 1.2+ server/client contexts, optional required client
  certificates, and a real loopback process test covering TLS 1.3,
  certificate rejection/acceptance, signed worker requests, a real StickS3
  QEMU job and a unified board/WiFi/BLE job with evidence transfer;
- file-backed tokens plus `SIGHUP` rotation of the server certificate, client
  CA, worker client certificate/key and master token; retired TLS identities
  and tokens are rejected and the new credentials complete a signed QEMU job;
- a request-drain gate around `SIGHUP`: active requests finish before token/TLS
  commit, new handlers wait, and a bounded timeout keeps the old configuration
  active instead of blocking indefinitely;
- bounded old/new overlap through previous token/client-CA files; a final
  `SIGHUP` after removing those files retires the old credentials;
- central control-plane restart/re-registration and worker-local runtime
  Device Service restart with bounded status/evidence/stop retry and the
  original job/lease/evidence convergence;
- verified local QEMU/QMP restart re-attach after PID start-time, QMP socket
  ownership and `query-status=running` all match;
- trusted-host unified companion recovery: durable HTTP request generations
  are recreated on the profile port, while a surviving BLE peer is adopted
  only after exact PID, start-time and full command-SHA256 checks;
- persistent session-create idempotency keyed by request hash and bound to one
  session, including concurrent retry and service restart replay;
- bounded stopped/failed history with age, count and byte limits;
- stopped-session Flash release by default and reference-aware cache GC;
- optional Bearer token;
- Linux fail-closed network namespaces for QEMU radio sessions;
- QEMU `filter-dump` pcap plus flow/DNS/DHCP/ARP/payload-hash summaries;
- `POST /sessions/{id}/network-fault` for `wifi0` link control or
  `radio-enabled` QOM removal/restoration;
- passing trusted-host and Linux-private-namespace TLS/Host allowlist runs
  with generated test CA, HTTPS gateway, 200/403 Host decisions and pcap
  evidence;
- a controlled namespace-local DNS resolver using a temporary private
  resolver configuration, with exact A/AAAA, label-boundary domain suffix,
  bounded CNAME chains, explicit answer binding, NXDOMAIN and query-log
  evidence; three independent Device Service leases also prove the same guest
  CNAME→terminal A→HTTP lifecycle with denied-name/port, pcap and cleanup;
- nftables default-drop bounded IPv4/IPv6 address-or-CIDR/protocol/port
  egress with a per-session dual-stack veth/NAT path, IPv6 neighbor control
  and verified cleanup;
- guest-issued DHCP renewal with DORA baseline, later REQUEST/ACK, retained
  address, HTTP continuity and pcap summaries;
- a two-guest StickS3 lab fabric inside a private namespace, with reserved
  DHCP addresses, real guest TCP, two-sided pcap and blocked host/public routes;
- versioned FirmwareManifest import and structured capability mismatch.

Not implemented yet:

- prestarted warm QEMU instances;
- namespace-managed, Tab5 and cross-host companion recovery, plus a continuous
  external evidence stream across restart;
- arbitrary NAT traversal when no routable discovery seed is available,
  cross-host credential migration, cross-host QEMU execution/re-attach,
  cross-host idempotency and production multi-host capacity scheduling;
- production worker integration and replay storage for the two-guest lab fabric;
- disposable VM/copy-on-write isolation for untrusted multi-tenant review;
- pcap/evidence object storage, retention policy and audit integration.

See [`device-service-api.md`](device-service-api.md) for the delivered API and
[`code-map.md`](code-map.md) for module/evidence locations.

## Decision summary

A device model is a **template**, not a singleton service. The service should
create one emulator instance per lease and allow several replicas of the same
model, bounded by a per-model capacity policy.

Recommended default:

- one exclusive emulator instance per active test or review lease;
- cached backend images for every device class;
- a small warm pool only for interactive/high-demand models;
- cold, disposable instances for untrusted-firmware review;
- no pre-flashed UIFlow2 firmware in the review path;
- optional pre-booted UIFlow2 instances only for demo and live preview.

For the current 10-core Apple M4 workstation, the local service defaults to
`max_sessions=12` and `max_per_device=8`. Twelve simultaneous StickS3 sessions
were validated with non-black frames; the batch used about 2.27 of the host's
10 CPU cores, 1.46 GiB aggregate RSS and 1.12 GiB physical footprint. These
values are deployment policy and can be changed through CLI flags or
environment variables.

## Retention and storage

The mutable per-session Flash is the dominant storage cost. It remains present
while a lease is active and is released when the lease stops unless the caller
explicitly requests `retain_flash=1` or the service is configured with
`M5_SERVICE_RETAIN_SESSION_FLASH=1`.

Stopped/failed history is pruned oldest-first by configurable age, count and
byte limits. Active states are never selected. Artifact, firmware and prepared
Flash caches use content-addressed identities plus reference checks; entries
unreferenced by retained sessions or firmware are eligible for GC after a grace
period. The same janitor also removes abandoned `.uploads` staging data and
expired completed upload records. `GET /api/v1/storage` exposes current usage
and policy, while `POST /api/v1/storage/prune` applies an immediate pass. The
service reserves a configurable amount of free disk and rejects new writes with
HTTP `507` before the reserve is consumed.

“Ready device” and “real-time rendering” are orthogonal. A service can keep a
device ready and stream frames from it, or start it on demand and stream frames
after boot. Rendering is the transport/UI concern; pooling is the lifecycle
concern.

## Important comparison: `build-esp-docker`

The neighboring `build-esp-docker` project does not maintain a pool of running
containers. It keeps official ESP-IDF images cached and runs one-shot
`docker run --rm` build containers with project locks and a concurrency limit.

That pattern is useful for the simulator service:

- cache large backend images;
- create a disposable worker per task;
- enforce per-project and global concurrency;
- destroy the worker after evidence collection.

If low interactive latency is required, add a warm pool on top. The build
project itself is not already a ready-simulator pool.

## Instance options

| Option | Advantages | Disadvantages | Recommended use |
| --- | --- | --- | --- |
| One long-lived instance per model, serialized jobs | Lowest idle cost; simple | State leakage; queueing; one bad firmware can poison the next test; no concurrency | Local debugging only |
| Fixed `N` warm instances per model | Low startup latency; predictable capacity | High idle RAM/CPU; stale firmware; more complex refresh and teardown | Top interactive models only |
| Cold instance created per lease | Fresh state; strong isolation; exact firmware; easy evidence | Startup/flash latency; more scheduling work | Default for automated tests and untrusted review |
| Shared multi-tenant instance | Highest density | Cross-tenant state, input, network and security leakage; impossible evidence isolation | Reject |
| Hybrid warm/cold pool | Good latency for hot models; scale-to-zero for the rest | More complex policy and observability | Recommended |

## Firmware preload options

| Option | Advantages | Disadvantages | Decision |
| --- | --- | --- | --- |
| Pre-boot official UIFlow2 on every model | Instant first frame and UI preview | Stale version; mutable state; cannot review arbitrary firmware; misleading readiness | Demo/preview pool only |
| Cache the UIFlow2 image but flash per lease | Fast download; exact SHA; reproducible | Flash/boot latency remains | Recommended for UIFlow2 tests |
| Immutable UIFlow2 golden snapshot + copy-on-write overlay | Fast reset; repeatable | Version management; still not the artifact under review | Useful for regression |
| Pre-flash the firmware under review into a shared instance | Short first run | State leakage, security risk, non-reproducible evidence | Reject |
| Flash exact artifact into a fresh overlay for every lease | Reproducible; auditable; safe teardown | Highest latency | Required for firmware review |

## Recommended pool levels

Keep these stages distinct:

1. **Image warm:** runtime images and ROM/eFuse/toolchain files are cached.
2. **Worker warm:** a worker agent/container is already running.
3. **Emulator warm:** a QEMU/esp-emu process is initialized with a known blank
   or maintenance flash but no user firmware.
4. **Demo ready:** an official UIFlow2 image is booted and rendering.

Recommended policy:

- all backend images: warm/cache;
- all device models: cold on-demand by default;
- CoreS3, StickS3, Core2 and Tab5: optional `min_ready=1` preview instances;
- untrusted firmware: always cold, isolated and destroyed after the lease;
- flash is reset from an immutable base before every lease.

Do not keep all 14 models booted by default. The idle cost and stale-state risk
are higher than the saved startup time.

## Lease lifecycle

```text
idle
  -> reserved
  -> worker allocated
  -> flash overlay restored
  -> artifact verified and flashed
  -> booted
  -> inputs / serial / frames / network evidence
  -> stopped
  -> overlay destroyed or reset
  -> idle or terminated
```

Every instance has:

- a lease ID and owner;
- one device profile;
- one immutable base flash hash;
- one task-specific overlay;
- one network namespace/backend;
- one evidence bundle;
- a hard timeout and teardown policy.

Guest reset alone is insufficient for tenant isolation. Recreate the instance
or restore a clean snapshot after a review job.

## Concurrency policy

Device profiles should expose:

```yaml
min_ready: 0
max_instances: 2
idle_ttl_seconds: 120
lease_ttl_seconds: 1800
```

Each model can have several replicas, but no emulator instance is shared by two
leases. Capacity is managed by backend class and memory/CPU cost, not just
device count.

## Rendering and API

Use different output paths for different consumers:

- automation: PNG/framebuffer snapshots plus serial and state APIs;
- human preview: WebSocket or WebRTC frame stream from the leased instance;
- catalog: cached thumbnail/last-known frame, clearly marked as stale;
- evidence: immutable screenshots, logs, pcap and hashes stored with the lease.

Real-time rendering should not force every model to run continuously.

## Firmware artifact contract

The v1 service accepts a merged image or explicit flash segments. Version 1 of
the normalized FirmwareManifest additionally preserves provenance,
ELF/MAP/sdkconfig, security metadata and required capabilities. The importer
accepts M5Burner sidecars, WebBurner `manifest.json`, ESP-IDF
`flasher_args.json`, merged/segmented images and ZIP packages:

```json
{
  "kind": "merged-flash",
  "chip": "esp32s3",
  "flash_size": 16777216,
  "image": "firmware.bin",
  "sha256": "..."
}
```

or separate flash segments:

```json
{
  "kind": "segmented-flash",
  "chip": "esp32s3",
  "flash_size": 16777216,
  "segments": [
    {"offset": "0x0", "file": "bootloader.bin"},
    {"offset": "0x8000", "file": "partition-table.bin"},
    {"offset": "0x10000", "file": "app.bin"},
    {"offset": "0x210000", "file": "storage.bin"}
  ]
}
```

Optional ELF, MAP, `flasher_args.json`, sdkconfig and filesystem metadata are
stored with the artifact for review evidence. See
[`firmware-manifest.md`](firmware-manifest.md) for the schema and failure
contract.

## Migration path

### Phase S0: local process runner

Status: implemented for the v1 service, including isolated per-session flash
and retained evidence.

- one process per lease on the current workstation;
- JSON job manifest and evidence directory;
- no shared mutable flash;
- preserve existing matrix runners.

### Phase S1: remote worker API

Status: local worker lifecycle, a persistent remote-worker registration
directory, a durable pull-based job queue, a same-host HTTP executor,
worker-local QEMU execution across server/worker network namespaces, and
verified local QEMU/QMP restart re-attach, HTTPS/mTLS and same-host `SIGHUP`
TLS/token rotation with active-request draining exist; bounded old/new
credentials, manual staged migration and a two-worker atomic-generation
pointer migration with secret-free receipts are implemented; authenticated
multicast discovery and worker bootstrap without a hard-coded control URL are
implemented within one multicast domain. Workers outside that domain can use
an HMAC-authenticated unicast discovery seed; a privileged Linux fixture
verified two routed subnets, masquerade, wrong/old token rejection, rotation
and cleanup in three independent runs. A worker also survives a central
control-plane restart through bounded transient retry, idempotent re-register,
same-lease heartbeat and terminal evidence reporting while its runtime QEMU
session remains untouched. A worker-local runtime Device Service can also
restart on the same state directory and re-attach that QEMU through PID/QMP
ownership checks; worker status/evidence/stop requests retry against the
known session ID. For trusted-host unified sessions it also recreates the HTTP
fixture from durable request generations, adopts a surviving BLE peer after
exact process ownership checks, and completes a post-restart GATT/HTTP cycle.
When a worker-to-control blackhole makes ownership unconfirmable, each request
is bounded by the remaining recovery budget. The worker stops its reachable
runtime session, reaps an OS-process side effect and suppresses the stale
result; after lease expiry and network restoration, a new worker claim can
complete the job. The QEMU lane runs the real worker-local Device Service and
StickS3 image, so QEMU process termination is included; guest/device-controller
effects and externally owned network effects remain separate boundaries.
Session creation uses a persisted idempotency key; WorkerAgent
derives it from job and lease so response-loss retries return the original
session. Cross-host QEMU execution, arbitrary NAT traversal without a
reachable discovery seed, namespace-managed/Tab5/cross-host companion
recovery, a continuous external evidence stream, cross-host re-attach and
multi-host scheduling remain open.

Discovery requires an active API token and an explicitly advertised externally
reachable control-plane URL:

```bash
python3 platform/tools/serve.py 8787 \
  --api-token-file /secure/service.token \
  --worker-discovery-advertise-url https://control.example:8787

python3 platform/tools/worker_agent.py \
  --discover-control \
  --token-file /secure/service.token \
  --ca-file /secure/control-ca.pem

python3 platform/tools/worker_discovery_seed.py \
  --service-url https://control.example:8787 \
  --token-file /secure/service.token

python3 platform/tools/worker_agent.py \
  --discover-control-seed-url https://seed.example/worker-discovery/v1/beacon \
  --token-file /secure/service.token \
  --ca-file /secure/control-ca.pem
```

The beacon contains no token. Its HMAC authenticates the advertised URL and
TTL; TLS/mTLS still validates transport identity. The active token is used, so
beacons follow successful `SIGHUP` rotation. IPv4 multicast is intentionally
limited to one discovery domain. The unicast seed path works when the seed is
reachable; it does not provide arbitrary NAT traversal without a rendezvous
endpoint. HMAC proves authenticity, not confidentiality, so production seed
transport should use HTTPS or a trusted private network.

- submit, status, cancel, serial, input, screenshot and evidence endpoints;
- one task per worker;
- cached runtime images;
- per-model and global concurrency limits.
- persistent worker heartbeat, drain/resume and restart lease classification
  are implemented for the local process;
- identity/generation registration, heartbeat, drain/stop and bounded result
  metadata are implemented in `workers.json`;
- `jobs.json` implements idempotent enqueue, capability-matched claim,
  lease heartbeat, expiry retry, terminal result, cancel and stale/stopped
  worker reconciliation;
- `worker_agent.py` can use separate control and runtime `/api/v1` endpoints:
  it claims/heartbeats on the central service, while the optional runtime
  service creates and owns the QEMU session, provides evidence and performs
  cleanup;
- after a job is claimed, transient control-plane network/429/5xx failures are
  retried for a bounded interval; after restart the worker re-registers the
  same identity/generation and reports the original lease/evidence. Claim
  itself needs a future stable dedup token before automatic retry;
- after a runtime session ID exists, transient runtime service failures retry
  status/evidence/stop; runtime restart re-attaches the same QEMU PID,
  process-start token, HTTP generation and safely adopted BLE peer before
  evidence collection;
- session creation persists only key/request hashes; identical retries return
  the original session and different request content returns 409;
- the two-namespace Linux fixture proves that separation with a real
  worker-local StickS3 QEMU session and central claim/heartbeat/result; it is
  not a physically cross-host run;
- when an API token is configured, worker-only mutations use a
  worker/generation-derived HMAC with timestamp, nonce replay protection and
  path/body identity binding;
- a local QEMU process is re-attached only when PID start time, session QMP
  socket ownership and `query-status=running` agree;
- cross-host credential migration, a real cross-host QEMU execution fixture,
  arbitrary NAT traversal when no routable seed is available,
  namespace-managed/Tab5/cross-host
  companion recovery, a continuous external evidence stream, cross-host
  re-attach, cross-host idempotency storage and production capacity scheduling
  remain open.

### Phase S2: warm/cold pool

Status: planned. Current sessions are cold/on-demand.

- `min_ready` for selected preview models;
- isolated review pool;
- snapshot/overlay management;
- scheduler capacity and queue metrics.

### Phase S3: production hardening

Status: partial. The Linux namespace lane is implemented and fail-closed, but
the overall service is still trusted-local and not an untrusted-firmware
sandbox.

- container/VM isolation for untrusted firmware;
- portable worker-policy export/enforcement and object-backed
  pcap/evidence retention;
- worker health, eviction and teardown verification;
- multi-host scheduling and artifact storage.

## Recommendation

Start with Phase S0/S1, not with a large pre-booted fleet. This preserves the
current QEMU/esp-emu work and gives reproducible evidence. Add a small warm pool
only after startup/queue measurements show that interactive users need it.

For firmware review, the correct default is:

```text
warm backend + cold instance + exact artifact + isolated network + disposable overlay
```
