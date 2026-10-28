# TLS epoch correction

The ESP32 UIFlow port sets `MICROPY_EPOCH_IS_1970=1`. Its active
`m5stack/main.c` `platform_mbedtls_time()` still added the 946684800-second
2000-to-1970 offset. A correct 2026 RTC therefore appeared to mbedTLS as 2056,
rejecting the owned 2020–2035 certificate as expired. Patch 0010 returns the
existing Unix seconds directly on 1970-epoch builds and retains the conversion
for 2000-epoch ports.

`build_tls_candidate.py` hash-checks the fixed official source, copies the main
archive, recompiles only `m5stack/main.c`, and relinks into an isolated output.
It checks that the cached source/archive and every byte outside the application
partition remain unchanged. This is an incremental candidate build, not a cold
firmware build or a replacement of the device-matrix reference image.

The source-matched CoreS3 preimage produced two certificate-expiry errors and
three configuration-only observations at the correct 2026 RTC. Its corrected
candidate passed all five original `CERT_REQUIRED` mutual-TLS HTTPS cases at
that RTC, including both `SSLContext.wrap_socket` and `ssl.wrap_socket`.
Each run generated a new disposable certificate/key under the same validity
policy; their certificate bytes differ. The separate 1996-RTC diagnostic run
only isolates the epoch cause and is excluded from stock results. Frozen
reference firmware failures on both boards remain in the stock audit. No
Cardputer candidate or physical-hardware result is claimed.

The compact receipt, full firmware/runtime/source/ZIP hashes and session IDs are
in [tls-epoch.json](../../docs/evidence/2026-10-27-uiflow2-api-sweep/tls-epoch.json).
Raw keys, certificates, Flash images, peer logs and execution ZIPs remain in
ignored local storage.

```sh
python3.12 tests/uiflow2/api_sweep/build_tls_candidate.py \
  --build-root /path/to/pinned-cached-build \
  --base-image /path/to/source-matched-full-flash.bin \
  --out-dir .work/api-sweep/tls-candidate-new

PYTHONPATH=.work/py312 python3.12 tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:8788 --group tls --device cores3 \
  --base-image cores3=.work/api-sweep/tls-candidate-new/candidate-full-flash.bin \
  --expected-base-sha256 cores3=EXACT_BUILD_RECEIPT_SHA256 \
  --token-file "$M5_TOKEN_FILE" --out-dir .work/api-sweep/tls-candidate-run-new
```
