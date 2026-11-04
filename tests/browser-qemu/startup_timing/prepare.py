#!/usr/bin/env python3
"""Materialize the source-pinned runtime75 timing observers; never run a guest."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RULES_PATH = HERE / "runtime75-transforms.json"
WRAPPER_PATH = HERE / "runtime75-fixed-preflight.mjs.in"
OBSERVER_START = "const time=globalThis.startupTiming="
OBSERVER_END = "return receive.call(this,data,...rest);};"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def controls(source: str) -> list[str]:
    """Keep complete lines verbatim, including multiline-call opening lines."""
    return [line for line in source.splitlines() if re.search(r"\b(?:check\(|assert\.)", line)]


def observer(source: str) -> str:
    if source.count(OBSERVER_START) != 1 or source.count(OBSERVER_END) != 1:
        raise ValueError("expected exactly one original timing observer body")
    start = source.index(OBSERVER_START)
    end = source.index(OBSERVER_END, start) + len(OBSERVER_END)
    return source[start:end]


def replace_repo_binding(source: str, replacement: str, *, wrapper: bool = False) -> str:
    """Accept one complete historical binding or one JSON-string assignment."""
    if wrapper:
        prefix = "const here=dirname(fileURLToPath(import.meta.url)),repo="
        legacy = {prefix + "resolve(here,'../..');"}
        pattern = re.compile(r"^const here=dirname\(fileURLToPath\(import.meta.url\)\),repo=")
    else:
        prefix = "const repo="
        legacy = {
            "const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');",
            "const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');",
        }
        pattern = re.compile(r"^const repo\s*=")
    lines = source.splitlines(keepends=True)
    candidates = [i for i, line in enumerate(lines) if pattern.match(line)]
    if len(candidates) != 1:
        raise ValueError("expected exactly one repository binding")
    index = candidates[0]
    body = lines[index].removesuffix("\n")
    if body not in legacy:
        if not body.startswith(prefix):
            raise ValueError("repository binding is not a whitelisted assignment")
        rhs = body[len(prefix):]
        value, end = json.JSONDecoder().raw_decode(rhs)
        if not isinstance(value, str) or rhs[end:] != ";":
            raise ValueError("repository binding must contain only one JSON-string assignment")
    lines[index] = replacement + ("\n" if lines[index].endswith("\n") else "")
    return "".join(lines)


def normalized(source: str, *, wrapper: bool = False) -> str:
    """Normalize only the two import locations and the generated repo binding."""
    if not wrapper:
        for name in ("public_qemu_artifacts.mjs", "public_qemu_worker_targets.mjs"):
            pattern = rf"from 'file:[^'\n]+/platform/tests/{re.escape(name)}'"
            source, count = re.subn(pattern, f"from '@REPO_URI@/platform/tests/{name}'", source)
            if count != 1:
                raise ValueError(f"expected one relocated import: {name}")
        replacement = "const repo=@REPO_JSON@;\n"
    else:
        replacement = "const here=dirname(fileURLToPath(import.meta.url)),repo=@REPO_JSON@;\n"
    return replace_repo_binding(source, replacement.removesuffix("\n"), wrapper=wrapper)


def transform(basis: str, spec: dict, repo: Path) -> str:
    raw = basis.encode()
    if len(raw) != spec["basis_bytes"] or sha256(raw) != spec["basis_sha256"]:
        raise ValueError(f"fixed basis changed: {spec['basis']}; review and repin explicitly")
    lines = basis.splitlines(keepends=True)
    previous_start = len(lines) + 1
    for edit in reversed(spec["edits"]):
        start, end = edit["start_line"], edit["end_line"]
        if not 0 <= start <= end < previous_start:
            raise ValueError("unordered or overlapping source edits")
        if "".join(lines[start:end]) != edit["before"]:
            raise ValueError("source edit context changed")
        after = edit["after"].replace("@REPO_URI@", repo.as_uri())
        lines[start:end] = after.splitlines(keepends=True)
        previous_start = start
    generated = "".join(lines)
    generated = replace_repo_binding(generated, "const repo=" + json.dumps(str(repo)) + ";")
    if controls(generated) != controls(basis):
        raise ValueError("original ordered assertion/check lines changed")
    observer(generated)
    return generated


def new_work_output(repo: Path, requested: Path) -> Path:
    """Reject escapes, existing destinations and symlinked output components."""
    work = repo / ".work"
    output = Path(os.path.abspath(requested if requested.is_absolute() else repo / requested))
    try:
        parts = output.relative_to(work).parts
    except ValueError as exc:
        raise ValueError("output must be a new directory below this repository's .work") from exc
    if not parts:
        raise ValueError("output cannot be .work itself")
    current = work
    if current.is_symlink():
        raise ValueError("symlinked .work is not an output destination")
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError("symlinked output components are not allowed")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    return output


def prepare(repo: Path, requested: Path, reference_dir: Path | None = None) -> dict:
    repo = repo.resolve(strict=True)
    output = new_work_output(repo, requested)
    rules_raw = RULES_PATH.read_bytes()
    rules = json.loads(rules_raw)
    payloads: dict[str, bytes] = {}
    runners = []
    for kind, spec in rules["runners"].items():
        basis = (repo / spec["basis"]).read_text()
        generated = transform(basis, spec, repo)
        source_controls = controls(basis)
        record = {
            "kind": kind, "basis": spec["basis"], "basis_sha256": spec["basis_sha256"],
            "historical_harness_sha256": spec["historical_harness_sha256"],
            "generated_name": spec["historical_harness_name"],
            "observer_body_sha256": sha256(observer(generated).encode()),
            "ordered_control_lines": source_controls,
            "ordered_control_lines_sha256": sha256("\n".join(source_controls).encode()),
            "ordered_control_lines_identical": True,
            "expected_same_case_guest_checks": spec["executed_checks"],
            "reference_comparison": "NOT REQUESTED",
        }
        if reference_dir is not None:
            reference_raw = (reference_dir / spec["historical_harness_name"]).read_bytes()
            if sha256(reference_raw) != spec["historical_harness_sha256"]:
                raise ValueError(f"reference is not the recorded executed runtime75 {kind} artifact")
            reference = reference_raw.decode()
            if observer(generated) != observer(reference) or controls(reference) != source_controls:
                raise ValueError("executed-reference observer/control lines differ")
            if normalized(generated) != normalized(reference):
                raise ValueError("executed reference differs beyond import/repository relocation")
            record["reference_comparison"] = "EXACT_AFTER_DECLARED_PATH_RELOCATION"
            record["reference_observer_body_identical"] = True
        payloads[spec["historical_harness_name"]] = generated.encode()
        payloads[f"{kind}-basis.mjs"] = basis.encode()
        payloads[f"{kind}-vs-basis.diff"] = "".join(difflib.unified_diff(
            basis.splitlines(keepends=True), generated.splitlines(keepends=True),
            fromfile=spec["basis"], tofile=spec["historical_harness_name"],
        )).encode()
        runners.append(record)
    wrapper = WRAPPER_PATH.read_text().replace("@REPO_JSON@", json.dumps(str(repo)))
    if "@REPO_" in wrapper:
        raise ValueError("unexpanded identity-wrapper placeholder")
    wrapper_spec = rules["identity_wrapper"]
    if reference_dir is not None:
        reference_raw = (reference_dir / wrapper_spec["historical_harness_name"]).read_bytes()
        if sha256(reference_raw) != wrapper_spec["historical_harness_sha256"]:
            raise ValueError("identity reference is not the recorded runtime75 artifact")
        if normalized(wrapper, wrapper=True) != normalized(reference_raw.decode(), wrapper=True):
            raise ValueError("identity wrapper changed beyond repository relocation")
    payloads[wrapper_spec["historical_harness_name"]] = wrapper.encode()
    for name in ("public_qemu_artifacts.mjs", "public_qemu_worker_targets.mjs"):
        if not (repo / "platform/tests" / name).is_file():
            raise ValueError(f"missing existing runner dependency: {name}")
    receipt = {
        "schema_version": 1, "kind": "portable-runtime75-startup-observer-preparation",
        "status": "PREPARED_NOT_EXECUTED", "guest_execution": "NOT RUN",
        "generator_sha256": sha256(Path(__file__).read_bytes()),
        "transform_rules_sha256": sha256(rules_raw),
        "identity_wrapper_template_sha256": sha256(WRAPPER_PATH.read_bytes()),
        "repo": str(repo), "output": str(output), "runners": runners,
        "artifacts": [{"path": name, "bytes": len(data), "sha256": sha256(data)}
                      for name, data in payloads.items()],
        "identity_wrapper_reference_comparison": "EXACT_AFTER_DECLARED_PATH_RELOCATION"
            if reference_dir is not None else "NOT REQUESTED",
        "declared_changes_from_executed_runtime75": [
            "Relocate two helper import URLs to the selected repository.",
            "Replace each repository binding with the selected repository's absolute path.",
            "No observer-body, control assertion, label, runtime, guest or fixture change.",
        ],
        "commands": {
            "prepare_argv": ["python3", "tests/browser-qemu/startup_timing/prepare.py",
                             "--out", str(output)],
            "run_argv": ["node", str(output / wrapper_spec["historical_harness_name"])],
            "required_env": ["M5_PUBLIC_SITE", "M5_PUBLIC_QEMU_OUT", "M5_QEMU_DEVICE",
                             "M5_EXPECT_WASM_SHA256", "M5_PUBLIC_UI=1", "M5_WASM_GPU=hardware",
                             "M5_WASM_CHROME"],
        },
        "limits": [
            "Static source equivalence and syntax checks are not guest PASS results.",
            "The 15/26 counts belong to the fixed Atom Matrix/StickC Plus cases only.",
            "This generator does not implement the separate same-page warm lifecycle experiment.",
            "Timing uses existing call-through observers and is not physical-hardware evidence.",
        ],
    }
    if reference_dir is not None:
        receipt["commands"]["prepare_argv"] += ["--reference-dir", str(reference_dir)]
    payloads["preparation.json"] = (json.dumps(receipt, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    for name, data in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new .work subdirectory; never overwritten")
    parser.add_argument("--reference-dir", type=Path,
                        help="optional ignored directory containing the recorded executed runtime75 artifacts")
    args = parser.parse_args()
    try:
        receipt = prepare(REPO, args.out, args.reference_dir.resolve() if args.reference_dir else None)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"startup observer preparation refused: {exc}\n")
    print(json.dumps({"status": receipt["status"], "output": receipt["output"],
                      "artifacts": len(receipt["artifacts"]), "guest_execution": "NOT RUN"}))


if __name__ == "__main__":
    main()
