#!/usr/bin/env python3
"""Vendor a reviewed public m5stack-models Git commit, never its dirty worktree.

Usage: python3 platform/tools/sync_visual_models.py --source /path/to/public/repo
Use --commit FULL_SHA to review a newer snapshot; --check verifies without writes.
Only runtime JavaScript, explicitly reviewed product sticker PNGs, public
metadata and redistribution notices are allowed. Research, raw CAD/photographs,
demo and dependencies are not copied. Node parses ESM dependencies without
executing upstream code before any snapshot is written.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import posixpath
import re
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "platform/web/vendor/m5stack-models"
PINNED_COMMIT = "48667b728736fbfd4365a06575473ce538d3c972"
PUBLIC_REPOSITORY = "https://github.com/yuyun2000/m5stack-models"
THREE_ADDON = "examples/jsm/utils/BufferGeometryUtils.js"
THREE_DESTINATION = ROOT / "platform/web/vendor/three/addons/utils/BufferGeometryUtils.js"
THREE_ADDONS = {
    THREE_ADDON: THREE_DESTINATION,
    "examples/jsm/geometries/DecalGeometry.js":
        ROOT / "platform/web/vendor/three/addons/geometries/DecalGeometry.js",
}
RASTER_SOURCE_COMMIT = PINNED_COMMIT
RASTER_NOTICE_SHA256 = "9b845c6a38033a03a338abd535e00e2031f75caee7b681c74b75b8f552ef1111"
# Exact public Git objects reviewed with the provider-permission notice above.
# New source commits/assets require an explicit review of this allowlist.
REVIEWED_RUNTIME_PNGS = {
    "src/devices/atoms3r/artwork/certification.png": "a8c9adb7c4d0675c47584cbd6a9c3762fbf943bbc0366093a5c6f8ea348e1990",
    "src/devices/atoms3r/artwork/rear-main.png": "f4559ab19c552641a26ee56d96cb52700afe1a28af1e6dd5f75617fb15b0e463",
    "src/devices/cardputer-adv/artwork/back.png": "d35128e9e158873df01d32d31bd230c20a5135fc6074ef3cfa4083e19f1db1ca",
    "src/devices/cardputer-adv/artwork/front-name.png": "05062fdb2753812e0e281fe0d8a5148ea2658f69d85548b9f46ac1bdd6dae431",
    "src/devices/cardputer-adv/artwork/grove-side.png": "b6f7df4b1aad2d7125b6fe9da21acbea329d8a766396bed9aff645ddf1da1f0a",
    "src/devices/cardputer-adv/artwork/keyboard-1.png": "07de8cebb19269bf8222dde0f7d15b285fcf7d6ca5fdd4c648f584dbbac10ef1",
    "src/devices/cardputer-adv/artwork/keyboard-2.png": "39404c232bd18847336309433d244d46976a02f274ade962656f9196896a35ed",
    "src/devices/cardputer-adv/artwork/keyboard-3.png": "7f31707a98c8ca7bd22aff847a6abbdea0e67ab6f880b7c0d96682281b33e385",
    "src/devices/cardputer-adv/artwork/keyboard-4.png": "7e526f3f1a75b66a6ae49490b256050b9d5041fbb5c4cfd23c423dd69e011cf3",
    "src/devices/cardputer-adv/artwork/stamp.png": "3bd22b202861c24d994cfe3e309a67d924dc7dddd5eec39883efbb7636bba2eb",
    "src/devices/cardputer-adv/artwork/top-edge.png": "79d221d5c1ea1092923d3a932c95ea420790d5842340194b435b6cc51da946c3",
    "src/devices/cardputer-zero/artwork/front-power.png": "8b829e506d97828057147351adf83beed072f5d3b4ca5f7e6d03bafb88749af8",
    "src/devices/cardputer-zero/artwork/front-zero.png": "489c5c27f986d6d6e26cd3821b7c146636407ec5c9aea6cd670bfbd96d17ee0a",
    "src/devices/cardputer-zero/artwork/keyboard-row-1.png": "ff7e31185eaf49f1127a31338ed34725d761eddaeab9e692ba891a437fd97251",
    "src/devices/cardputer-zero/artwork/keyboard-row-2.png": "bf954658f1a22ac9fa95e3bd0e858359598d3a1480426276dd6b9d38e3f73704",
    "src/devices/cardputer-zero/artwork/keyboard-row-3.png": "cb993cb8b43154550afd63f2f21c875e2dfd1e9a76a340e29ca5f34ab653ec4a",
    "src/devices/cardputer-zero/artwork/keyboard-row-4.png": "732f15a185a099644c734d9990b74b51356161ded9029abc222e35b27d06938f",
    "src/devices/cardputer-zero/artwork/left-usb-network.png": "fcd3118034f9ee410f33a5f51caf9d7a5f3a1996dedff03e573058bae11fb5df",
    "src/devices/cardputer-zero/artwork/power-cap.png": "b6abc5f604c8dd3adf18905c5883c7727f925234ccb0c3812fcfc0fb67e35fd8",
    "src/devices/cardputer-zero/artwork/rear.png": "20236e5a18199ac9cee26a82efcd7ddf7f5e2786354642821ae8553b42141730",
    "src/devices/cardputer-zero/artwork/right-display-audio-grove.png": "0ce068068b7907f90cecb421d8b7975198fdd0988881b976e10b1b3700bb22d4",
    "src/devices/cardputer-zero/artwork/top-gpio.png": "fc31f3d3f4b4335209b9cba03a94eee00831ac52887608789359d1092359e4ca",
    "src/devices/cardputer-zero/artwork/top-sd.png": "673d71cafe58a14d8ee7a3a2f8ec9ae1e3bc84320b94e5a820c4b10feadd3fa9",
    "src/devices/core2/artwork/certification.png": "b3bf157041cedfd8efcf4b623b2b61033e6dd2542ce4d6d7882bb497f2fcdd81",
    "src/devices/core2/artwork/rear-main.png": "6861115ae897d09c28bdcfa66d0366e1a98b54d19daf2379d12e157369dc478d",
    "src/devices/cores3/artwork/certification.png": "964e5b906bc2e9d91c6ece331089bee131b1c662471234fe2260d0fa83d002c7",
    "src/devices/cores3/artwork/din-dc.png": "4e91a6d58842571519bed3cafcf25cea8c449c6d8b89e8f5eb3d8b6e353ef66c",
    "src/devices/cores3/artwork/din-name.png": "9e60e39962f93773f0da8e28e907912e35dc2ecc1801f0e4df4dc5499fec7e9c",
    "src/devices/cores3/artwork/din-power.png": "ed376ff64f00f504a442f0accf7c7b3378464deebf862cd85d5babc41b583c01",
    "src/devices/cores3/artwork/port-b.png": "f930e559e994c0e9488828c9831ac03bbcf9962279fa79582beec9a16d622ec8",
    "src/devices/cores3/artwork/port-c.png": "9244524465e35a8d870192641653c636f4c55237725e43a2ac21bd30c24f6154",
    "src/devices/cores3/artwork/rear.png": "8663eeb85a1b09d6564d8cc1ac60cce8ec7fd1a0f8de9e95103cc2e7da3e9d15",
    "src/devices/papercolor/artwork/bottom.png": "ea59298cba7f6222a42783f84de57a5dbef9b90c6ea47df768afe88f468c696c",
    "src/devices/papercolor/artwork/rear-lower.png": "b0839c0a100c3e67562a551aa372768047849a36c2a1e6f80871dbe437da6cae",
    "src/devices/papercolor/artwork/rear-upper.png": "02415ce1ccbc54770aa0159a43423cd4737893d2d6e53c1defe8f3855e780cc8",
    "src/devices/papermono/artwork/rear.png": "0dca37738f5ef4cd826e61952079341c4aaf1faf0a231667eb3bcf4283626fcd",
    "src/devices/stackchan/artwork/bottom.png": "0deafe45a2d1b4d7ee704e91386bad17e388fec103cbb5db0294f3745fac0a29",
    "src/devices/stackchan/artwork/certification.png": "a3ac70830eed4e5a018889519b67ee7d8c48b231de546c9b41fb38d6fc544635",
    "src/devices/stackchan/artwork/side.png": "1ddee7a66b1c6bbe9385013b49f07c3176914b23e2d52cbe3d5972b50e72cd17",
    "src/devices/sticks3/artwork/rear.png": "3355803393cf98bc6d8c07f173173c1228bd69c81320ba166710e5dc78cd7fe9",
    "src/devices/sticks3/artwork/side.png": "672ea111bf918e6f4bfda888a0d863fd494c4f01be58f99008aca31579637194",
    "src/devices/stopwatch/artwork/rear.png": "6904bb6fca8b8d3ca153a439ade9b58ec0c065c35b7ca4abc072227590602b39",
    "src/devices/tab5/artwork/battery-bay.png": "1a7be15037a0c871cc9472e64b910fb189e7767d8685620ebbe63b36f3d32dd7",
    "src/devices/tab5/artwork/certification.png": "6159d5d031fcda48680279d9f3c8277ee80a90d45852247eecf0cbe4cc570bc1",
    "src/devices/tab5/artwork/gpio.png": "61fb3b827d97cbb4c1728e9340f090d4c3cc5acb56ed5853810bd154a5cc8bba",
    "src/devices/tab5/artwork/headset.png": "a3d1a6f65a11a1794167018d54cb15baae25d22f47578fcfd6d657b579a86559",
    "src/devices/tab5/artwork/name.png": "52ab0b0a991bb6c2575d59c44bd2352373aa48731c348ebf21d754eb0b9f037f",
    "src/devices/tab5/artwork/port-a.png": "7c6d36e7cc17fc2957db62bf3320d9f0342d40f3fddec3dfd9e3ee75b9838f87",
    "src/devices/tab5/artwork/rear.png": "c3907cb82c894cd5c9101736fa4ca070443713ee5597745d8eecbef8a8d57a5e",
    "src/devices/tab5/artwork/usb-a.png": "a5d35fd52edb476111b4740e351a1224d1a7aafdd06304586265382d34f9e60e",
    "src/devices/tab5/artwork/usb-c.png": "a11451303712b7e4684f64639d3949a9858c5542e84bffe2b76da0325417d50c",
    "src/units/angle/education-cn-back.png": "70d2d303f0f474a22cb344cc37854f6844b9e0d1a73986e31c43e54eac093756",
    "src/units/dual-button/official-back.png": "07efcda08c3cb06b69f84b56ea2ca6a4a4573bc0e75f458efef0ea00a764dadb",
    "src/units/env-iii/education-cn-back.png": "4280ee9b608a15c256f43a44f8a7b840a121578be8453bbee904d6555a0e9e3e",
    "src/units/fan/education-cn-back.png": "e4a51df5d1781e8bb8f4df08a736ba7339a2aee45bd7268dfa2d9a0fdde80712",
    "src/units/hub/official-back.png": "56243d519e2fc690b9b0cd5f55c57a5e942f8642114fd1bb8d4a1aede18bf0ce",
    "src/units/ir/official-back.png": "da1d2f124e020e74b29a624a4045a53c9cfff9311a4c59c3746e4b3a4a841017",
    "src/units/light/education-cn-back.png": "5f8047883cb05d59c8577bd11edc91b0a70d88066b5335931c8d1bc2b49c824b",
    "src/units/pir/education-cn-back.png": "734922c95c3c39b067da0d5a2e6016879da1d3595af5f319033457389fb55e5e",
    "src/units/rfid2/official-back.png": "33c7e0d72c5fa71590a50c5c67b0cf60caf51b10a5d61adf7806b36d20c26959",
    "src/units/rfid2/official-front.png": "898330c070a6d71c99b6fae3f9ce91f26f77320b2ac6d517d8bf477a72f0b662",
    "src/units/rgb/official-back.png": "f5f4d5e7f0924881b82764e6d44e40df0e594a6b2b4f96a46df7c8e9a83f538c",
    "src/units/scroll/education-cn-back.png": "9662ad9d9f949649dcdc49eb8124adb482d026c122d2c14d9430a83dc52b4598",
    "src/units/thermal/education-cn-back.png": "9f1e14950bd95fa15371c0f0f54ba4fc1c5b816d191d41430f178d7b78b59d35",
    "src/units/ultrasonic-i2c/official-back.png": "718b6c859a3ccbc166b4595ba44e4d63bbe503261f4c4258374b9b4dbd4962f0"
}
EXPLICIT_FILES = {
    "LICENSE", "THIRD_PARTY_NOTICES.md", "source-manifest.json",
    "catalog/products.json", "package.json", "package-lock.json",
    "docs/AGENT-INTEGRATION.md", "docs/INTEGRATION.md",
    "docs/GROVE-CABLE.md", "docs/VISUAL-MOTION.md",
}


def git(source: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *arguments])


def reviewed_runtime_assets(commit: str, names: list[str], files: dict[str, bytes]) -> None:
    assets = {name for name in names if name.startswith("src/") and name.endswith(".png")}
    if not assets:
        return
    if commit != RASTER_SOURCE_COMMIT or assets != set(REVIEWED_RUNTIME_PNGS):
        raise ValueError("runtime PNGs differ from the explicitly reviewed commit/allowlist")
    notice = hashlib.sha256(files["THIRD_PARTY_NOTICES.md"]).hexdigest()
    if notice != RASTER_NOTICE_SHA256:
        raise ValueError("runtime PNG redistribution notice differs from the reviewed notice")
    for name in sorted(assets):
        data = files[name]
        if hashlib.sha256(data).hexdigest() != REVIEWED_RUNTIME_PNGS[name]:
            raise ValueError(f"runtime PNG differs from reviewed Git object: {name}")
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
            raise ValueError(f"reviewed runtime asset is not a PNG: {name}")


def resource_closure(files: dict[str, bytes]) -> dict[str, object]:
    """Parse static ESM imports, then check the reviewed literal/template forms.

    SourceTextModule parses dependency requests without evaluating any module.
    Dynamic import() and import.meta URL forms are deliberately bounded: a new
    expression shape requires review instead of silently escaping validation.
    Template URL patterns cover all allowlisted matches, and browser checks
    separately exercise the actual runtime expressions and image decoders.
    """
    sources = {name: data.decode("utf-8") for name, data in files.items()
               if name.startswith("src/") and name.endswith(".js")}
    parser = """import {SourceTextModule} from 'node:vm';
let input=''; for await (const chunk of process.stdin) input+=chunk;
const sources=JSON.parse(input),result={};
for(const [name,source] of Object.entries(sources))
  result[name]=new SourceTextModule(source,{identifier:name}).dependencySpecifiers;
process.stdout.write(JSON.stringify(result));"""
    try:
        parsed = subprocess.run(
            ["node", "--no-warnings", "--experimental-vm-modules", "--input-type=module", "-e", parser],
            input=json.dumps(sources).encode(), capture_output=True, check=True,
        )
        dependencies = json.loads(parsed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ValueError("Node could not parse the public visual ESM dependency graph") from error
    external: set[str] = set()
    referenced_assets: set[str] = set()
    allowed_external = {"three", "three/addons/environments/RoomEnvironment.js"} | {
        "three/addons/" + name.removeprefix("examples/jsm/") for name in THREE_ADDONS
    }

    def resolve_local(name: str, reference: str) -> str:
        path = posixpath.normpath(posixpath.join(posixpath.dirname(name), reference))
        if not reference.startswith(("./", "../")) or not path.startswith("src/"):
            raise ValueError(f"visual resource escapes the runtime source tree: {name}: {reference}")
        return path

    dynamic_import = re.compile(r"\bimport\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)")
    asset_url = re.compile(r"\bnew\s+URL\s*\(\s*(['\"`])([^\n]*?)\1\s*,\s*import\.meta\.url\s*\)")
    for name, source in sources.items():
        dynamic = list(dynamic_import.finditer(source))
        if len(dynamic) != len(re.findall(r"\bimport\s*\(", source)):
            raise ValueError(f"unreviewed dynamic visual import expression: {name}")
        for reference in dependencies[name] + [match[2] for match in dynamic]:
            if reference.startswith(("./", "../")):
                path = resolve_local(name, reference)
                if path not in sources:
                    raise ValueError(f"visual JavaScript dependency is absent: {name}: {reference}")
            elif reference in allowed_external:
                external.add(reference)
            else:
                raise ValueError(f"unreviewed external visual dependency: {name}: {reference}")
        urls = list(asset_url.finditer(source))
        if len(urls) != len(re.findall(r"\bnew\s+URL\s*\(", source)):
            raise ValueError(f"unreviewed visual resource URL expression: {name}")
        for match in urls:
            reference = match[2]
            path = resolve_local(name, reference)
            if match[1] == "`" and "${" in path:
                # Current public sources use a filename or a numeric row only.
                expressions = re.findall(r"\$\{([^}]+)\}", path)
                if not expressions or any(not re.fullmatch(r"[A-Za-z_]\w*(?:\+1)?", value)
                                          for value in expressions):
                    raise ValueError(f"unreviewed visual resource template: {name}: {reference}")
                pattern = re.escape(path)
                for expression in expressions:
                    pattern = pattern.replace(re.escape("${" + expression + "}"), "[^/]+")
                matches = {candidate for candidate in files if re.fullmatch(pattern, candidate)}
            else:
                matches = {path} if path in files else set()
            if not matches or any(not candidate.endswith(".png") for candidate in matches):
                raise ValueError(f"visual PNG resource is absent: {name}: {reference}")
            referenced_assets.update(matches)
    assets = {name for name in files if name.endswith(".png")}
    if assets != referenced_assets:
        raise ValueError(f"runtime PNGs lack a reviewed resource reference: {sorted(assets - referenced_assets)}")
    return {"status": "closed", "javascript_files": len(sources),
            "runtime_pngs": len(assets), "external_dependencies": sorted(external),
            "template_scope": "All matching reviewed files; browser execution validates expression results"}


def snapshot(source: Path, commit: str) -> dict[str, bytes]:
    resolved = git(source, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise ValueError("--commit must be a complete Git commit SHA")
    names = git(source, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    selected = [name for name in names if name in EXPLICIT_FILES
                or name.startswith("src/") and name.endswith(".js")
                or name in REVIEWED_RUNTIME_PNGS
                or name.startswith("licenses/") and "/" not in name[len("licenses/"):]]
    missing = EXPLICIT_FILES - set(selected)
    if missing:
        raise ValueError(f"public snapshot is missing required files: {sorted(missing)}")
    files = {name: git(source, "show", f"{commit}:{name}") for name in selected}
    reviewed_runtime_assets(commit, names, files)
    closure = resource_closure(files)
    products = json.loads(files["catalog/products.json"])["products"]
    manifest = {
        "schema_version": 1,
        "source_repository": PUBLIC_REPOSITORY,
        "source_commit": commit,
        "scope": "visual-only; firmware and electrical behavior belong to Device Service",
        "sync_command": f"python3 platform/tools/sync_visual_models.py --source /path/to/public/repo --commit {commit}",
        "three_version": json.loads(files["package.json"])["dependencies"]["three"],
        "controllers": [item["id"] for item in products if item["category"] == "controller"],
        "units": [item["id"] for item in products if item["category"] == "unit"],
        "resource_closure": closure,
        "runtime_assets": {
            "kind": "product sticker PNGs",
            "redistribution_notice": "THIRD_PARTY_NOTICES.md#product-sticker-rasters",
            "notice_sha256": hashlib.sha256(files["THIRD_PARTY_NOTICES.md"]).hexdigest(),
            "license_scope": "Provider permission for public distribution; images and marks retain owner rights, not project MIT",
            "files": {name: {"sha256": REVIEWED_RUNTIME_PNGS[name], "bytes": len(files[name]),
                             "source_url": f"{PUBLIC_REPOSITORY}/blob/{commit}/{name}"}
                      for name in sorted(files) if name.endswith(".png")},
        },
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())},
    }
    index = {item["id"]: {key: item[key] for key in
                          ("id", "category", "name", "sku", "integration") if key in item}
             for item in products}
    files["runtime-index.js"] = (
        "// Generated by platform/tools/sync_visual_models.py from the pinned public catalog.\n"
        "export const MODEL_METADATA = Object.freeze(" + json.dumps(index, ensure_ascii=False) + ");\n"
        "export const MODEL_DEVICES = Object.freeze(" + json.dumps(manifest["controllers"]) + ");\n"
        "export const UNIT_MODELS = Object.freeze(" + json.dumps(manifest["units"]) + ");\n"
    ).encode()
    files["vendor-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    files["UPSTREAM.md"] = (
        "# Public visual model snapshot\n\n"
        f"Source: {PUBLIC_REPOSITORY}\n\nCommit: `{commit}`\n\n"
        "Copied from Git objects with an explicit allowlist. Local changes and private "
        "research are never copied. `vendor-manifest.json` records every source file's "
        "SHA-256. The original `source-manifest.json` records geometry provenance.\n\n"
        "Preserve `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` when redistributing. "
        "Reviewed product sticker PNGs retain the provider-permission notice and "
        "per-file hashes; official remote photos are not bundled or relicensed. All models are visual "
        "shells: firmware, controller, bus and sensor evidence come from this project's "
        "Device Service.\n\n"
        "This source uses the site's single Three.js 0.186.1 import-map instance. "
        "Load `src/loaders.js` to keep models lazy; do not import `src/index.js` in the "
        "first-screen bundle.\n\n"
        "Update explicitly with the `sync_command` in the manifest, inspect its diff, "
        "then run `node platform/tests/test_model_shell.mjs` and the browser integration "
        "probe. Use `--check` to confirm a reproducible snapshot.\n"
    ).encode()
    return files


def three_addon(files: dict[str, bytes], check: bool) -> None:
    """Keep the import-map's existing single Three instance and locked addons."""
    dependency = json.loads(files["package-lock.json"])["packages"]["node_modules/three"]
    metadata_path = DESTINATION / "three-addon-manifest.json"
    if check:
        metadata = json.loads(metadata_path.read_text())
        if metadata["package_integrity"] != dependency["integrity"]:
            raise SystemExit("Three.js addon differs from the pinned package")
        expected_addons = {name: str(path.relative_to(ROOT)) for name, path in THREE_ADDONS.items()}
        actual_addons = metadata.get("addons", {})
        if set(actual_addons) != set(expected_addons):
            raise SystemExit("Three.js addon inventory differs from the reviewed dependency graph")
        for name, target in expected_addons.items():
            entry = actual_addons[name]
            if entry.get("destination") != target or entry.get("sha256") != hashlib.sha256((ROOT / target).read_bytes()).hexdigest():
                raise SystemExit(f"Three.js addon differs from the pinned package: {name}")
        for name, expected in metadata.get("shared_three_files", {}).items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise SystemExit(f"shared Three.js dependency differs: {name}")
        return
    # Downloaded archive stays in memory; no node_modules or upstream worktree
    # content is trusted. npm's lockfile SHA512 authenticates the exact archive.
    with urllib.request.urlopen(dependency["resolved"], timeout=30) as response:
        archive = response.read()
    actual = "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode()
    if actual != dependency["integrity"]:
        raise SystemExit("Three.js archive integrity mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        addons = {name: package.extractfile("package/" + name).read() for name in THREE_ADDONS}
        shared = {}
        for source, target in {
            "build/three.core.js": "platform/web/vendor/three/three.core.js",
            "build/three.module.js": "platform/web/vendor/three/three.module.js",
            "examples/jsm/environments/RoomEnvironment.js": "platform/web/vendor/three/addons/environments/RoomEnvironment.js",
        }.items():
            expected = hashlib.sha256(package.extractfile("package/" + source).read()).hexdigest()
            if hashlib.sha256((ROOT / target).read_bytes()).hexdigest() != expected:
                raise SystemExit(f"shared Three.js file must match {dependency['version']}: {target}")
            shared[target] = expected
    for name, path in THREE_ADDONS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(addons[name])
    metadata = {"package": "three", "version": dependency["version"],
                "package_url": dependency["resolved"], "package_integrity": actual,
                "source_path": THREE_ADDON,
                "destination": str(THREE_DESTINATION.relative_to(ROOT)),
                "sha256": hashlib.sha256(addons[THREE_ADDON]).hexdigest(), "shared_three_files": shared,
                "addons": {name: {"destination": str(path.relative_to(ROOT)),
                                  "sha256": hashlib.sha256(addons[name]).hexdigest(), "bytes": len(addons[name])}
                           for name, path in THREE_ADDONS.items()}}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--commit", default=PINNED_COMMIT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = snapshot(args.source, args.commit)
    existing = {str(path.relative_to(DESTINATION)) for path in DESTINATION.rglob("*") if path.is_file()}
    stale = existing - set(files) - {"three-addon-manifest.json"}
    if stale:
        raise SystemExit(f"unmanaged or removed files require explicit review: {sorted(stale)}")
    differences = [name for name, data in files.items()
                   if not (DESTINATION / name).is_file() or (DESTINATION / name).read_bytes() != data]
    if args.check:
        if differences:
            raise SystemExit(f"visual snapshot differs: {differences}")
        three_addon(files, check=True)
        print(f"visual snapshot OK: {args.commit}, {len(files)} files and pinned Three addon")
        return 0
    for name in differences:
        path = DESTINATION / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[name])
    three_addon(files, check=False)
    print(f"visual snapshot synced: {args.commit}, {len(differences)} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
