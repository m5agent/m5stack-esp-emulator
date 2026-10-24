# Idempotent Device Service session creation

This fixture sends concurrent `POST /api/v1/sessions` requests with the same
`idempotency_key` and canonical payload. Exactly one session/worker lease and
one QEMU process may be created. The retry response returns the original
session with `idempotent_replay=true`.

The mapping persists across a Device Service restart while storing only
SHA256(key), the canonical request hash and session ID. Reusing the key with a
different request returns `409 session_idempotency_conflict`.

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/session_idempotency/run_test.py \
  --out-dir /tmp/m5-session-idempotency
```

The fixture does not require upload payloads, secrets in the mapping file,
cross-host idempotency or hardware validation.
