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
- a plaintext HTTP request does not fall back successfully.

Run:

```bash
python3 tests/network/worker_tls/run_test.py
```

Retained evidence:
`evidence-2026-10-24-tls-mtls-pass.json`.

## Service configuration

```bash
python3 platform/tools/serve.py 8787 \
  --bind 0.0.0.0 \
  --api-token "$M5_SERVICE_API_TOKEN" \
  --tls-cert /secure/server.crt \
  --tls-key /secure/server.key \
  --tls-client-ca /secure/worker-ca.crt
```

Equivalent environment variables:

- `M5_SERVICE_TLS_CERT`
- `M5_SERVICE_TLS_KEY`
- `M5_SERVICE_TLS_CLIENT_CA`

## Worker configuration

```bash
python3 platform/tools/worker_agent.py \
  --service-url https://device-service.example \
  --ca-file /secure/service-ca.crt \
  --client-cert /secure/worker.crt \
  --client-key /secure/worker.key \
  --token "$M5_SERVICE_API_TOKEN" \
  --once
```

Equivalent environment variables:

- `M5_WORKER_TLS_CA`
- `M5_WORKER_TLS_CLIENT_CERT`
- `M5_WORKER_TLS_CLIENT_KEY`

## Boundaries

The retained run is loopback on one host, not cross-host network validation.
Certificate and worker credential hot rotation, production CA lifecycle,
real QEMU job execution over mTLS, multi-host scheduling, companion
continuity and hardware remain `NOT RUN`. Bearer/HMAC is an application
authentication layer and does not replace mTLS.
