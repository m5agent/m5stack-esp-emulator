#!/usr/bin/env python3
"""Import only the exact full-build artifact pinned for this Pages retry."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build_public_site import littlefs_runtime_files, qemu_runtime_files


ROOT = Path(__file__).resolve().parents[2]
RECIPE = Path("scripts/qemu-wasm-build")
REPOSITORY = "m5agent/m5stack-esp-emulator"
REPOSITORY_ID = 1427737977
WORKFLOW_PATH = ".github/workflows/public-site.yml"
WORKFLOW_ID = 399573281
PRODUCER_RUN = 42777985298
PRODUCER_ATTEMPT = 1
PRODUCER_SHA = "b4e280d5dcd9b07b4efa59dd96dc914f4f82e6ce"
TARGETS = {
    "xtensa-softmmu": {
        "artifact": 13745832204, "name": "qemu-staging-xtensa-1", "job": 129700917539,
        "steps": {6, 8, 10, 12}, "directory": "qemu-browser-runtime", "prefix": "qemu-browser-runtime/",
        "zip_sha256": "8368463c53b63e0e7b16a2cd11713a4861aa2551012f6ec4fe474388a3b69c48",
        "wasm_sha256": "96c7f8baf1d5f2fd760c560a0827ef7305ad06a1cefb28c905d05d796dc540d8",
    },
    "riscv32-softmmu": {
        "artifact": 13745208690, "name": "qemu-staging-c61-1", "job": 129700917708,
        "steps": {7, 13}, "directory": "qemu-c61-runtime", "prefix": "",
        "zip_sha256": "fea110b26e938cf56f4bab7b04dc2d54de33246d7c8881abc448e810df2ec266",
        "wasm_sha256": "83ed57e0ac517ba2c83d40c640995050df33217138c59366c089962b399ba163",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify_context(environment):
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REPOSITORY_ID": str(REPOSITORY_ID),
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main",
    }
    require(all(environment.get(key) == value for key, value in expected.items()),
            "runtime reuse requires the official main Pages dispatch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(head == environment.get("GITHUB_SHA") == environment.get("GITHUB_WORKFLOW_SHA"),
            "checkout differs from the dispatched workflow source")


def verify_producer_inputs():
    paths = {str(RECIPE / "build.py"), str(RECIPE / "README.md"), "LICENSE",
             "platform/tools/bootstrap_qemu_browser_runtime.py", "platform/tools/build_public_site.py",
             "scripts/browser-littlefs",
             "tests/browser-qemu/cores3_lvgl_pir", "tests/browser-qemu/cores3_lvgl_wallclock",
             "tests/browser-qemu/typed_helpers"}
    for name in ("sources.lock.json", "sources-c61.lock.json"):
        path = RECIPE / name
        lock = json.loads((ROOT / path).read_bytes())
        paths.add(str(path))
        paths.update(row["path"] for row in lock["patches"] + lock["dependency_patches"])
    subprocess.run(["git", "diff", "--exit-code", PRODUCER_SHA, "--", *sorted(paths)], cwd=ROOT, check=True)


def verify_metadata(target, run, jobs, artifact):
    expected = TARGETS[target]
    require(run["id"] == PRODUCER_RUN and run["run_attempt"] == PRODUCER_ATTEMPT
            and run["workflow_id"] == WORKFLOW_ID and run["path"] == WORKFLOW_PATH
            and run["event"] == "workflow_dispatch" and run["head_branch"] == "main"
            and run["head_sha"] == PRODUCER_SHA and run["status"] == "completed"
            and all(run[key]["full_name"] == REPOSITORY and run[key]["id"] == REPOSITORY_ID
                    for key in ("repository", "head_repository")), "producer workflow identity mismatch")
    job, = (row for row in jobs["jobs"] if row["id"] == expected["job"])
    require(job["run_id"] == PRODUCER_RUN and job["run_attempt"] == PRODUCER_ATTEMPT
            and job["name"] == f"build_runtimes ({target})" and job["head_sha"] == PRODUCER_SHA
            and job["status"] == "completed" and job["conclusion"] == "success",
            "producer build job was unsuccessful or unexpected")
    successful = {step["number"] for step in job["steps"] if step["conclusion"] == "success"}
    require(expected["steps"] <= successful, "required producer build or staging step did not pass")
    source = artifact["workflow_run"]
    require(artifact["id"] == expected["artifact"] and artifact["name"] == expected["name"]
            and artifact["expired"] is False and artifact["digest"] == "sha256:" + expected["zip_sha256"]
            and source["id"] == PRODUCER_RUN and source["head_branch"] == "main"
            and source["head_sha"] == PRODUCER_SHA
            and source["repository_id"] == source["head_repository_id"] == REPOSITORY_ID,
            "producer artifact identity mismatch or expired")


def extract_assets(archive, prefix, manifest_name, destination):
    manifest = json.loads(archive.read(prefix + manifest_name))
    rows = manifest["assets"]
    if isinstance(rows, dict):
        rows = rows.values()
    destination.mkdir()
    for name in (manifest_name, *(row["path"] for row in rows)):
        path = PurePosixPath(name)
        require(path.parts and not path.is_absolute() and str(path) == name
                and ".." not in path.parts and "\\" not in name, "unsafe archived asset path")
        output = destination / path
        output.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(prefix + name) as source, output.open("xb") as stream:
            shutil.copyfileobj(source, stream)


def extract_abi_evidence(archive, destination):
    destination.mkdir()
    for name in ("report.json", "run.log", "build.log", "typed-helpers.cjs", "tci-wasm-call.h"):
        (destination / name).write_bytes(archive.read("wasm-typed-helper-control/" + name))
    report = json.loads((destination / "report.json").read_bytes())
    result = report["result"]
    lock = json.loads((ROOT / RECIPE / "sources.lock.json").read_bytes())
    require(report["status"] == result["status"] == "PASS" and report["exit_code"] == 0
            and (result["accepted_cases"], result["rejected_without_call"], result["setjmp_fast"], result["setjmp_ffi"]) == (66, 9, 37, 37)
            and report["source_sha256"] == sha(ROOT / "tests/browser-qemu/typed_helpers/probe.c")
            and report["patch_sha256"] == sha(ROOT / "patches/qemu-wasm-probe/0025-wasm-tci-typed-helper-calls.patch")
            and report["header_sha256"] == sha(destination / "tci-wasm-call.h") == lock["patched_files"]["tcg/tci-wasm-call.h"]
            and report["artifact_sha256"] == sha(destination / "typed-helpers.cjs"), "ABI producer evidence mismatch")


def stage_runtime(target, archive_path, work, environment):
    expected = TARGETS[target]
    require(sha(archive_path) == expected["zip_sha256"], "producer archive SHA-256 mismatch")
    runtime = work / expected["directory"]
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate archive path")
        extract_assets(archive, expected["prefix"], "runtime.json", runtime)
        if target == "xtensa-softmmu":
            littlefs = work / "browser-littlefs"
            extract_assets(archive, "browser-littlefs/", "manifest.json", littlefs)
            littlefs_runtime_files(littlefs, require_sized_mount=True)
            with ZipFile(littlefs / "source.zip") as sources:
                for name in ("build.py", "compose.c", "README.md"):
                    require(sources.read("composer/" + name) == (ROOT / "scripts/browser-littlefs" / name).read_bytes(),
                            "LittleFS composer source mismatch")
            extract_abi_evidence(archive, work / "wasm-typed-helper-control")
    manifest, _ = qemu_runtime_files(runtime, target=target)
    require(manifest["build"]["recipe_sha256"] == sha(ROOT / RECIPE / "build.py")
            and manifest["assets"]["wasm"]["sha256"] == expected["wasm_sha256"],
            "runtime recipe or WASM identity mismatch")
    receipt = {"kind": "pinned-pages-runtime-reuse", "target": target, "producer_run": PRODUCER_RUN,
               "producer_attempt": PRODUCER_ATTEMPT, "producer_sha": PRODUCER_SHA,
               "producer_job": expected["job"], "producer_artifact": expected["artifact"],
               "producer_archive_sha256": expected["zip_sha256"], "wasm_sha256": expected["wasm_sha256"],
               "source_bundle_sha256": manifest["assets"]["source"]["sha256"],
               "recipe_sha256": manifest["build"]["recipe_sha256"], "lock_sha256": manifest["build"]["lock_sha256"],
               "release_run": environment["GITHUB_RUN_ID"], "release_attempt": environment["GITHUB_RUN_ATTEMPT"],
               "release_sha": environment["GITHUB_SHA"], "guest_execution": "NOT RUN by importer"}
    (runtime / "reuse-provenance.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def gh_api(path):
    return ["gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}/actions/{path}"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    args = parser.parse_args()
    verify_context(os.environ)
    subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", PRODUCER_SHA], cwd=ROOT, check=True, timeout=120)
    verify_producer_inputs()
    producer = f"runs/{PRODUCER_RUN}/attempts/{PRODUCER_ATTEMPT}"
    artifact = TARGETS[args.target]["artifact"]
    run, jobs, metadata = (json.loads(subprocess.check_output(gh_api(path), timeout=60))
                           for path in (producer, producer + "/jobs", f"artifacts/{artifact}"))
    verify_metadata(args.target, run, jobs, metadata)
    work = ROOT / ".work"
    work.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="pages-runtime-import-", dir=work) as directory:
        archive = Path(directory) / "runtime.zip"
        with archive.open("xb") as output:
            subprocess.run(gh_api(f"artifacts/{artifact}/zip") + ["--allow-escape-sequences"],
                           stdout=output, check=True, timeout=180)
        stage_runtime(args.target, archive, work, os.environ)
    print(f"Verified and staged prior full source build for {args.target}")


if __name__ == "__main__":
    main()
