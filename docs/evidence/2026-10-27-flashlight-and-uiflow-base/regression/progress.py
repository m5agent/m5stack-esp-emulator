"""Read-only progress view; no inferred PASS and no mutation of runtime."""
from pathlib import Path
import json

root = Path(__file__).resolve().parent / "full"
cases = json.loads((root.parent / "full-matrix-list.json").read_bytes())
started = [case["id"] for case in cases if (root / f"{case['id']}.stdout").exists()]
frames = [case["id"] for case in cases if (root / case["id"] / "after.png").exists()]
errors = []
for case in cases:
    path = root / f"{case['id']}.stderr"
    if path.exists():
        lines = path.read_text(errors="replace").splitlines()
        if any("Traceback (most recent call last):" in line for line in lines):
            errors.append({"case": case["id"], "last_lines": lines[-4:]})
print(json.dumps({"started": len(started), "frames_finished": len(frames), "latest_started": started[-3:],
                  "runner_tracebacks": errors, "summary_exists": (root / "summary.json").exists()}))
