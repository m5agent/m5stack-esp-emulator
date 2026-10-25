# Worker HTTPS / mTLS transport

Last reviewed: `2026-10-25`

This fixture starts the real Device Service process with an ephemeral test CA,
server certificate and client CA, then verifies:

- the worker client validates the server certificate;
- TLS 1.2 is the configured minimum and TLS 1.3 is negotiated by the test
  client;
- a client without a certificate is rejected by the mTLS server;
- a trusted client certificate is accepted;
- Bearer and generation-derived worker HMAC authentication remain required;
- unsigned worker mutation returns HTTP 401;
- `worker_agent.py` registers, heartbeats, claims, and stops over HTTPS with a
  client certificate and exits successfully;
- a plaintext HTTP request does not fall back successfully;
- with `--real-qemu-job`, a complete StickS3 flash is uploaded and composed
  over mTLS, then a durable worker job starts a real QEMU process, downloads
  evidence, verifies SHA256 and reports terminal PASS.
- with `--real-unified-job`, the composed unified StickS3 image runs in one
  `qemu-unified` job; serial board/WiFi/BLE markers, network evidence, pcap and
  PNG frame are checked from the downloaded evidence ZIP;
- `run_rotation_test.py` atomically replaces the server certificate, client
  CA, worker client certificate/key and master token, holds an old-token
  artifact upload open while sending `SIGHUP`, verifies that upload completes
  before reload, verifies a bounded old/new CA/token overlap, removes the
  previous files, sends a final `SIGHUP`, verifies the old TLS identity and
  token are then rejected, and runs a real QEMU job with the new credentials.
- `run_fleet_migration_test.py` starts two workers from immutable credential
  generations, moves them to an A+B server-trust bridge, switches the service
  to B with A as previous, publishes one atomic B generation pointer, verifies
  both workers reload without `SIGHUP` and write secret-free receipts, then
  finalizes the service and rejects the old identity.

Run:

```bash
python3 tests/network/worker_tls/run_test.py
```

Retained evidence:
`evidence-2026-10-24-tls-mtls-pass.json`.

Real QEMU job over mTLS:

```bash
python3 tests/network/worker_tls/run_test.py --real-qemu-job
```

Retained evidence:
`evidence-2026-10-24-tls-mtls-qemu-job-pass.json`.

Unified application over mTLS:

```bash
python3 tests/network/worker_tls/run_test.py --real-unified-job
```

Retained evidence:
`evidence-2026-10-24-tls-mtls-unified-job-pass.json`.

Credential rotation and post-rotation QEMU job:

```bash
python3 tests/network/worker_tls/run_rotation_test.py
```

Retained evidence:
`evidence-2026-10-24-security-rotation-overlap-job-pass.json`.

Automated two-worker credential migration:

```bash
python3 tests/network/worker_tls/run_fleet_migration_test.py
```

Retained evidence:
`evidence-2026-10-24-fleet-credential-migration-pass.json`.

## Service configuration

```bash
python3 platform/tools/serve.py 8787 \
  --bind 0.0.0.0 \
  --api-token-file /secure/service.token \
  --tls-cert /secure/server.crt \
  --tls-key /secure/server.key \
  --tls-client-ca /secure/worker-ca.crt
```

Equivalent environment variables:

- `M5_SERVICE_API_TOKEN_FILE`
- `M5_SERVICE_API_TOKEN_PREVIOUS_FILE`
- `M5_SERVICE_TLS_CERT`
- `M5_SERVICE_TLS_KEY`
- `M5_SERVICE_TLS_CLIENT_CA`
- `M5_SERVICE_TLS_CLIENT_CA_PREVIOUS`

`--api-token` and `--api-token-file` are mutually exclusive.

## Worker configuration

```bash
python3 platform/tools/worker_agent.py \
  --service-url https://device-service.example \
  --ca-file /secure/service-ca.crt \
  --client-cert /secure/worker.crt \
  --client-key /secure/worker.key \
  --token-file /secure/service.token \
  --once
```

Equivalent environment variables:

- `M5_SERVICE_API_TOKEN_FILE`
- `M5_WORKER_TLS_CA`
- `M5_WORKER_TLS_CLIENT_CERT`
- `M5_WORKER_TLS_CLIENT_KEY`

`--token` and `--token-file` are mutually exclusive.

For automatic fleet migration, immutable generation directories are referenced
by one JSON pointer:

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

```bash
python3 platform/tools/worker_agent.py \
  --service-url https://device-service.example \
  --credential-generation-file /secure/worker-generation.json \
  --credential-receipt-dir /secure/worker-receipts
```

The worker checks the pointer before every request and reloads after an atomic
rename. A failed load keeps the old credentials active. A successful reload
writes one `0600` receipt with worker identity, generation, timestamp and a
secret-free file fingerprint.

## Credential rotation

For direct file options, replace files by atomic rename and send `SIGHUP` to
the service and worker. For the generation-pointer path, only the service
needs `SIGHUP`; workers reload automatically from the new immutable generation.

- A new TLS context applies to subsequent TLS handshakes; sockets that have
  already completed a handshake retain their TLS session.
- Before committing the reload, the service stops admitting handlers and
  waits for active requests to finish. The default drain timeout is 30
  seconds; a timeout keeps the old configuration and resumes admission.
- During the bounded overlap, both the active and previous token are accepted
  for Bearer/HMAC checks, and both client CAs are trusted.
- Workers first move to an `A+B` server-trust generation. After the service
  switches to B with A retained as previous, publish the B worker generation.
  This avoids a race where a worker still trusts only the old server CA.
- Remove the previous token/CA files and send another `SIGHUP` to finalize.
  A missing previous file disables that side of the overlap.
- The new master token applies to subsequent protected requests, including
  requests on an existing keep-alive connection.
- The two-worker fixture proves automatic file-generation migration and
  auditable receipts without worker `SIGHUP`. Worker-host discovery is covered
  by separate multicast and unicast-seed fixtures. Cross-host migration,
  production secret-manager distribution and final cutover orchestration are
  not claimed here.

## Boundaries

The retained run is loopback on one host, not cross-host network validation.
Certificate/token `SIGHUP` rotation, rejection of the retired credentials and
a post-rotation real QEMU job are `PASS`. An active old-token artifact upload
also completes before reload, and a bounded old/new CA/token overlap is
followed by a final cutover. A separate two-worker run passes A, A+B and B
generation migration with secret-free receipts and no worker `SIGHUP`.
Worker discovery is covered separately by authenticated multicast and
reachable unicast-seed fixtures; that is not arbitrary NAT traversal.
Cross-host migration, production CA/secret-manager lifecycle, multi-host
scheduling, namespace-managed/Tab5 companions, no-seed NAT traversal and
hardware remain `NOT RUN`.
The real QEMU job proves process/session execution and evidence transfer, not
an arbitrary firmware's unified application PASS. The retained unified StickS3
job additionally proves its board/WiFi/BLE markers, network evidence, pcap and
frame in that same evidence ZIP. Trusted-host companion continuity is proven
by the runtime-restart fixture rather than this TLS boundary. Bearer/HMAC is
an application authentication layer and does not replace mTLS.
