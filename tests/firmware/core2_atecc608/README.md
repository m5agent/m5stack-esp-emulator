# Core2 for AWS ATECC608 service probe

`run_service.py` uploads the public Core2 for AWS factory BIN, composes the
service-normalized 16 MiB image and runs three independent `/api/v1` sessions.
It requires the final ATECC marker plus a nonempty frame, captures frame,
serial and evidence, then stops with `purge=0` and verifies history, PID and
lease cleanup.

The expected source artifact SHA256 is
`22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a`;
the normalized firmware SHA256 is
`104062aa0e6f52470f0c7f409d202af5d2dad5c3e5ee8f7e65815508a512ef3c`.

The model uses a deterministic locked test config and contains no production
private key or certificate. Results are virtual-device validation only.

See
[`docs/evidence/2026-10-29-core2-atecc608/README.md`](../../../docs/evidence/2026-10-29-core2-atecc608/README.md).
