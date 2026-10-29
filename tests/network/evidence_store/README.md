# Lease-bound worker evidence

This test starts a real Device Service and drives the authenticated worker HTTP
path. It verifies a multi-megabyte evidence ZIP is accepted only for a live
job/lease, that an upload response can be lost and retried idempotently, that
the metadata/content survive a service restart, and that a terminal result
cannot select a different evidence record.

The test does not execute a QEMU guest or establish physical cross-host
execution, object-store replication or external side-effect ownership.

```bash
PYTHONPATH=platform/tools \
  python3 tests/network/evidence_store/run_test.py \
  --out-dir /tmp/m5-evidence-store
```
