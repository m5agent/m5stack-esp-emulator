#!/usr/bin/env python3
"""Map successful real HTTP reports to the complete operation inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_device_api import INVENTORY, save


def summarize(paths):
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    operations = {row["operation_id"]: {"operation_id": row["operation_id"], "phase": row["phase"],
                  "positive_status": "NOT RUN", "boundary_status": "NOT RUN", "evidence": []}
                  for row in inventory["operations"]}
    reports = []
    for path in paths:
        raw = path.read_bytes()
        report = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        reports.append({"report_sha256": digest, "status": report["status"], "case_count": len(report["cases"]),
                        "validation": report.get("validation")})
        for case in report["cases"]:
            operation_id = case["operation_id"]
            if operation_id not in operations:
                raise ValueError("report operation is absent from inventory: " + operation_id)
            if case["status"] != "PASS":
                continue
            positive = case["coverage"] in {"positive", "positive-read"}
            row = operations[operation_id]
            # A failed attempt remains useful diagnostics but never grants a
            # positive functionality claim to the complete later result.
            if report["status"] == "PASS":
                row["positive_status" if positive else "boundary_status"] = "PASS"
            evidence = {"report_sha256": digest, "attempt_status": report["status"],
                        "coverage": case["coverage"], "response_sha256": case["response_sha256"]}
            if evidence not in row["evidence"]:
                row["evidence"].append(evidence)
    positive = sum(row["positive_status"] == "PASS" for row in operations.values())
    boundary = sum(row["boundary_status"] == "PASS" for row in operations.values())
    return {"schema_version": 1, "validation": "Device Service HTTP operation coverage",
            "hardware_validation": "NOT RUN", "contract_version": inventory["contract_version"],
            "contract_sha256": inventory["contract_sha256"], "operation_count": len(operations),
            "positive_operation_count": positive, "boundary_operation_count": boundary,
            "status": "PASS" if positive == len(operations) else "INCOMPLETE",
            "reports": reports, "operations": list(operations.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.report)
    save(args.out, report)
    print(json.dumps({key: report[key] for key in ("status", "operation_count", "positive_operation_count", "boundary_operation_count")}, indent=2))
