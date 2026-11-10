#!/usr/bin/env python3
"""Use one pinned producer attempt for branch-only, nonpublication guest tests."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from zipfile import ZipFile

import build_public_site as public


REPOSITORY = "m5agent/m5stack-esp-emulator"
REPOSITORY_ID = 1427737977
PRODUCER_RUN = 42770355747
PRODUCER_SHA = "1979809883489d92ffe7e5461fa17b26f06a89ed"
PRODUCER_ATTEMPT = 1
WORKFLOW_ID = 399573281
WORKFLOW_PATH = ".github/workflows/public-site.yml"
RECIPE = Path("scripts/qemu-wasm-build")
ARTIFACTS = {
    "xtensa": {
        "id": 13741959101,
        "name": "qemu-staging-xtensa-1",
        "sha256": "bd3ef2e73ed24fbad70a9f09e9787317eefda8c408bfd7c84dd5160bf7ec88b1",
        "wasm_sha256": "96c7f8baf1d5f2fd760c560a0827ef7305ad06a1cefb28c905d05d796dc540d8",
        "job_id": 129676448666,
        "job_name": "build_runtimes (xtensa-softmmu)",
        "required_steps": [6, 8, 10, 12],
    },
    "c61": {
        "id": 13741639246,
        "name": "qemu-staging-c61-1",
        "sha256": "c77e9421ce4c02957186398c460c8a09b46f13919a8cf700fd6d8cdd9248d9c7",
        "wasm_sha256": "4d461cf08f665435ce6a38a68efa0128e588fba3ffc4b556dbd1f01badd61b30",
        "job_id": 129676448399,
        "job_name": "build_runtimes (riscv32-softmmu)",
        "required_steps": [7, 13],
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify_producer(input_dir):
    run = read_json(input_dir / "run.json")
    require(
        run["id"] == PRODUCER_RUN and run["run_attempt"] == PRODUCER_ATTEMPT
        and run["workflow_id"] == WORKFLOW_ID and run["path"] == WORKFLOW_PATH
        and run["event"] == "workflow_dispatch" and run["head_branch"] == "main"
        and run["head_sha"] == PRODUCER_SHA
        and all(run[key]["full_name"] == REPOSITORY and run[key]["id"] == REPOSITORY_ID
                for key in ("repository", "head_repository")),
        "unexpected producer workflow identity",
    )
    jobs = {row["id"]: row for row in read_json(input_dir / "jobs.json")["jobs"]}
    artifacts = {row["id"]: row for row in read_json(input_dir / "artifacts.json")["artifacts"]}
    for target, expected in ARTIFACTS.items():
        job = jobs[expected["job_id"]]
        require(job["run_id"] == PRODUCER_RUN and job["name"] == expected["job_name"]
                and job["head_sha"] == PRODUCER_SHA and job["conclusion"] == "success",
                f"{target} producer job did not succeed")
        successful_steps = {step["number"] for step in job["steps"] if step["conclusion"] == "success"}
        require(set(expected["required_steps"]) <= successful_steps, f"{target} producer step is missing")
        artifact = artifacts[expected["id"]]
        binding = artifact["workflow_run"]
        require(
            artifact["name"] == expected["name"] and artifact["expired"] is False
            and artifact["digest"] == "sha256:" + expected["sha256"]
            and binding["id"] == PRODUCER_RUN and binding["head_branch"] == "main"
            and binding["head_sha"] == PRODUCER_SHA
            and binding["repository_id"] == binding["head_repository_id"] == REPOSITORY_ID,
            f"{target} artifact metadata mismatch",
        )
        require(sha(input_dir / (target + ".zip")) == expected["sha256"], f"{target} artifact bytes mismatch")


def verify_producer_sources(root):
    paths = {str(RECIPE), WORKFLOW_PATH, "LICENSE", "platform/tools/bootstrap_qemu_browser_runtime.py",
             "scripts/browser-littlefs", "tests/browser-qemu/typed_helpers",
             "tests/browser-qemu/cores3_lvgl_pir", "tests/browser-qemu/cores3_lvgl_wallclock"}
    for lock in ("sources.lock.json", "sources-c61.lock.json"):
        current = read_json(root / RECIPE / lock)
        paths.update(row["path"] for row in current["patches"] + current["dependency_patches"])
    subprocess.run(["git", "diff", "--exit-code", PRODUCER_SHA, "--", *sorted(paths)], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def extract_assets(archive, prefix, manifest_name, destination):
    with ZipFile(archive) as bundle:
        require(len(set(bundle.namelist())) == len(bundle.namelist()), "duplicate ZIP member")
        manifest = json.loads(bundle.read(prefix + manifest_name))
        rows = manifest["assets"]
        if isinstance(rows, dict):
            rows = rows.values()
        for name in [manifest_name, *(row["path"] for row in rows)]:
            path = PurePosixPath(name)
            require(not path.is_absolute() and str(path) == name and ".." not in path.parts
                    and "\\" not in name and path.parts, "unsafe asset name")
            output = destination / path
            output.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(prefix + name) as source, output.open("xb") as target:
                shutil.copyfileobj(source, target)
    return manifest


def prepare(input_dir, output):
    verify_producer(input_dir)
    source_commit = verify_producer_sources(public.ROOT)
    output.mkdir(parents=True, exist_ok=False)
    xtensa, c61, littlefs = (output / name for name in ("xtensa", "c61", "littlefs"))
    extracted = {
        "xtensa": extract_assets(input_dir / "xtensa.zip", "qemu-browser-runtime/", "runtime.json", xtensa),
        "c61": extract_assets(input_dir / "c61.zip", "", "runtime.json", c61),
    }
    recipe_sha = sha(public.ROOT / RECIPE / "build.py")
    for target, manifest in extracted.items():
        require(manifest["build"]["recipe_sha256"] == recipe_sha
                and manifest["assets"]["wasm"]["sha256"] == ARTIFACTS[target]["wasm_sha256"],
                f"{target} runtime manifest identity mismatch")
    composer = extract_assets(input_dir / "xtensa.zip", "browser-littlefs/", "manifest.json", littlefs)
    with ZipFile(littlefs / "source.zip") as sources:
        for name in ("build.py", "compose.c", "README.md"):
            require(sources.read("composer/" + name) == (public.ROOT / "scripts/browser-littlefs" / name).read_bytes(),
                    f"LittleFS composer source mismatch: {name}")

    site = output / "site"
    manifest = public.build_site(public.ROOT, site, base_path="/m5stack-esp-emulator/",
                                 qemu_runtime=xtensa, qemu_c61_runtime=c61, littlefs_runtime=littlefs)
    require(manifest["publication_eligible"] is True and not manifest["service_url"]
            and not manifest["candidate_profiles"], "diagnostic requires the exact stock browser configuration")
    # The guest's provenance checker requires the unmodified stock manifest.
    # Nonpublication is enforced by the branch-only job and evidence contract.
    site_manifest = site / "public-site-manifest.json"
    provenance = output / "provenance.json"
    provenance.write_bytes(public.encode_json({
        "kind": "hosted-qemu-diagnostic", "publication_eligible": False,
        "source_commit": source_commit, "producer_commit": PRODUCER_SHA,
        "producer_run": PRODUCER_RUN, "producer_attempt": PRODUCER_ATTEMPT,
        "producer_artifacts": ARTIFACTS, "source_recipe_sha256": recipe_sha,
        "site_manifest_sha256": sha(site_manifest), "composer_assets": composer["assets"],
        "runtime_manifests": {target: row["build"] for target, row in extracted.items()},
    }))
    require(read_json(provenance)["publication_eligible"] is False, "publication must stay disabled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.input, args.output)
