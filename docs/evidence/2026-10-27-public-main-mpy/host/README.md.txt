# Host verification archive (2026-10-27)

Run `python3 verify.py` after copying this directory anywhere. It reads only this directory, checks its exact indexed file inventory, bytes/SHA/UTF-8 and receipt relationships, and never calls a service or executes probes. The verifier itself is classified as generated and SHA-bound by index.json. index.json is the only inventory control file excluded from its own file rows.

Platform r1 remains FAIL (1213 tests; missing loader entry in code-map). Final r2 independently records 1213 tests and OK. Earlier device/independent negative failures remain original bytes. Passing host tests and fixture receipts do not grant a new guest or hardware PASS.

The gen45 launch receipt has 83 source SHA entries: 81 original text snapshots plus 2 explicit source fingerprints excluded for preexisting MAC literals. The verifier checks this exact partition. Captures occurred after execution and match the source hashes recorded around the controlled launch.

independent/final-offline-audit-r1 preserves the original fresh audit receipt, 4 command logs, both negative-probe source texts and the orchestrator text. Large portable-copy trees are represented by the original audit receipt fingerprints and are not duplicated here. The reused preview-negative source is bound by that receipt; state-preservation.py and record.py were captured after the audit and were not hashed by its receipt, so no pre-execution source binding is claimed for them.

Additional schema audit evidence may be added by updating index.json with its exact file classifications/bytes/SHA. No original failure receipt should be replaced or relabeled as passing.
