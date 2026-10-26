# Encoder binding research - second pass

**Research only; browser/guest/physical hardware NOT RUN in this phase.** `report.json` and `report.md.txt` preserve the original conclusions at HEAD 2f44cada, before the later authorized frontend changes. Their no-production-change statement applies to that preceding research phase; the sibling frontend directory records implementation.

Official knowledge_search succeeded for U135/U153. Raw/selected results are retained. The inspected M5_Hardware product directories have STL structures only; UNIT_ENCODER resolves to the existing driver repository. The inspected public Encoder firmware tree has no C source. 8Encoder C proves electrical index order and signed quadrature phase semantics, but the inspected sources supply neither U1-U9 -> physical CH/switch placement nor complete installed part/PPR/CW calibration.

`upstream/` retains fixed source as `.txt` and complete relevant repository tree/structure metadata. `official-diagrams/` retains unchanged schematic/protocol originals and extracted text. Discovery manifests freeze URL, commit where available, size and SHA. Full product HTML and unrelated search payloads were omitted; their provenance hashes remain. No firmware/ROM/hex binaries were copied.

Uniform colors are permutation-invariant. The original host-only proof script, archived as `.py.txt`, checked 2/362880 permutations for two/nine lamps. This proves only a separately scoped uniform/all-off subset, without identifying a nonuniform permutation. The later frontend implementation applies the same general invariant to RGB's three lamps.

Minimum missing sources: an authoritative per-revision LED refdes/XY/side/optical-channel placement table with Grove orientation, or reproducible same-driver physical one-hot capture. Shaft motion also needs the full encoder part/PPR, decoder multiplication and installed direction, plus physical-source state independent from logical guest counters. Those UNIT-HOST-29 bindings remain OPEN.

`local-source-hashes.json` freezes research-phase inputs; later deliberate product edits do not rewrite that snapshot. The section SHA256SUMS covers archived bytes. The root had copied several original research records before this archive completed; matching bytes were verified and left unchanged.
