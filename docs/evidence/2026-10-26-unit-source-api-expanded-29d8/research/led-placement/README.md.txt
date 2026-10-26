# LED placement research — U003 / U135

Start with [report.md](report.md) and [findings.json](findings.json).

Both electrical-index/refdes-to-physical-location mappings remain **OPEN**.
The Encoder photo-to-frozen-model position observation is a separate, qualitative
follow-up item and does not calibrate left/right electrical order.

This folder contains documentary research, original official public sources,
fetch receipts and offline integrity checks. It contains no firmware binary or
runtime test evidence.

- `source-index.json` inventories only public official sources.
- `frozen-model-audit.json` pins the unchanged vendor inputs.
- `validation.json` records offline artifact checks.
- `SHA256SUMS` covers files at this directory level, excluding this checksum file.
- `internal/` contains official MCP transcripts, feedback identifiers, the MCP
  client and unrelated programmer screenshots. Keep it internal; do not include
  it when archiving the public report/source bundle.

To recheck without network or runtime activity:

```sh
python3 .work/unit-led-placement-research-20261026/check_evidence.py
```

The checker refreshes `validation.json`; regenerate checksums afterwards if
preserving a new checked snapshot.
