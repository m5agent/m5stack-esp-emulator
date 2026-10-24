# Worker HTTPS / mTLS transport

Last reviewed: `2026-10-24`

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
  CA, worker client certificate/key and master token, sends `SIGHUP` to both
  processes, verifies the old TLS identity and old token are rejected, then
  runs a real QEMU job with the new credentials.

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
`evidence-2026-10-24-security-rotation-job-pass.json`.

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
- `M5_SERVICE_TLS_CERT`
- `M5_SERVICE_TLS_KEY`
- `M5_SERVICE_TLS_CLIENT_CA`

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

## Credential rotation

Replace files by atomic rename, then send `SIGHUP` to the service and worker.
The service validates the new token and TLS files before committing either
credential to live use. The worker makes the same all-or-nothing update.

- A new TLS context applies to subsequent TLS handshakes; sockets that have
  already completed a handshake retain their TLS session.
- The new master token applies to subsequent protected requests, including
  requests on an existing keep-alive connection.
- Existing requests and sessions are not drained. Zero-downtime draining,
  production secret-manager integration and cross-host continuity are not
  claimed by this fixture.

## Boundaries

The retained run is loopback on one host, not cross-host network validation.
Certificate/token `SIGHUP` rotation, rejection of the retired credentials and
a post-rotation real QEMU job are `PASS`. Zero-downtime request draining,
production CA/secret-manager lifecycle, multi-host scheduling, companion
continuity and hardware remain `NOT RUN`.
The real QEMU job proves process/session execution and evidence transfer, not
an arbitrary firmware's unified application PASS. The retained unified StickS3
job additionally proves its board/WiFi/BLE markers, network evidence, pcap and
frame in that same evidence ZIP. Bearer/HMAC is an application authentication
layer and does not replace mTLS.
