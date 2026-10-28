# requests2 form and UTF8 correction candidate

`0002-requests2-form-encoding.patch` targets the exact official UIFlow source
commit and SHA-256 preimage recorded in its adjacent JSON file. It percent
encodes form keys and values as UTF8 bytes, encodes spaces as `+`, and measures
string request bodies after UTF8 encoding. No dependency is added.

The original frozen CoreS3 and Cardputer-ADV libraries both failed the reserved
character / UTF8 form roundtrip. The official source candidate also failed that
roundtrip and transmitted only `中` for a `中文🚀` text body, because its declared
Content-Length counted characters. After applying this patch, both candidate
checks passed against an owned HTTP peer in visible Device Service sessions on
both boards. Serial, peer request/response hashes and pcap are retained outside
source Git. This is virtual-device validation.

The candidate source has not been proven byte-identical to either frozen
reference library. This patch is an upstream source correction candidate; it
does not replace default firmware, alter uploaded firmware, or turn the stock
failure into PASS. Other requests2 behavior is outside this two-case correction
lane. In particular, the candidate file-object path differs from stock.

Prepare an isolated source copy (the supplied official checkout is read-only):

```sh
python3 tests/uiflow2/api_sweep/prepare_requests2_candidate.py \
  --source-root /path/to/pinned/uiflow \
  --out-dir .work/requests2-candidate
```

Run the same actual HTTP recipes before and after, with the Device Service
already running and its bearer token supplied through a file:

```sh
PYTHONPATH=.work/py312 python3 tests/uiflow2/api_sweep/run_protocols.py \
  --execute --group requests-candidate \
  --requests2-source .work/requests2-candidate/before.py \
  --token-file /path/to/service-token \
  --out-dir .work/requests2-preimage-result
PYTHONPATH=.work/py312 python3 tests/uiflow2/api_sweep/run_protocols.py \
  --execute --group requests-candidate \
  --requests2-source .work/requests2-candidate/after.py \
  --token-file /path/to/service-token \
  --out-dir .work/requests2-correction-result
```

The preimage run is expected to exit nonzero. Neither command contacts an
external account. Both collect the evidence ZIP before stopping the session
with `purge=0`, retaining history and releasing the mutable Flash copy.
