#!/usr/bin/env python3
"""Check and package explicitly listed standalone Agent skills, without local data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LINK = re.compile(r"\]\(([^)]+)\)")


def safe_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise ValueError("Skill manifest requires relative POSIX paths")
    parts = value.split("/")
    if not value or any(not p or p in {".", ".."} or p.startswith(".") for p in parts):
        raise ValueError("Skill manifest contains an internal or noncanonical path")
    if any(p.lower() in {"node_modules", "__pycache__", "config.local.json"}
           or p.lower().endswith((".pyc", ".local.json", ".local.md", ".bin", ".elf", ".rom", ".efuse", ".key", ".pem"))
           for p in parts):
        raise ValueError("Local configuration, caches and binaries are not Skill distribution files")
    return PurePosixPath(value)


def skill_files(root: Path = ROOT) -> dict[str, dict[str, bytes]]:
    catalog = json.loads((root / "skills/catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("skills"), list) or not catalog["skills"]:
        raise ValueError("Invalid Skill catalog")
    result = {}
    for entry in catalog["skills"]:
        name = entry.get("name")
        if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name) or name in result:
            raise ValueError("Invalid or duplicate Skill name")
        listed = entry.get("files")
        if not isinstance(listed, list) or "SKILL.md" not in listed or len(set(listed)) != len(listed):
            raise ValueError("Skill files must be an explicit unique whitelist containing SKILL.md")
        base = root / "skills" / name
        if base.is_symlink():
            raise ValueError("A distributable Skill must be a real directory")
        contents = {}
        for relative in listed:
            path = safe_path(relative)
            candidate = base
            for part in path.parts:
                candidate = candidate / part
                if candidate.is_symlink():
                    raise ValueError("Skill files must not traverse symlinks")
            if not candidate.is_file() or not candidate.resolve().is_relative_to(base.resolve()):
                raise ValueError(f"Missing listed Skill file: {name}/{relative}")
            data = candidate.read_bytes()
            text = data.decode("utf-8", errors="strict")
            if data.startswith(b"\xef\xbb\xbf") or "\r" in text:
                raise ValueError("Skill text must be UTF-8 without BOM and use LF newlines")
            if candidate.suffix == ".json":
                json.loads(text)
            contents[relative] = data
        # Frontmatter semantics are checked separately by skill-creator's validator.
        # Relative links must also survive copying just this one Skill directory.
        for relative, data in contents.items():
            if not relative.endswith(".md"):
                continue
            for target in LINK.findall(data.decode("utf-8")):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                absolute = (base / relative).parent / target
                if not absolute.resolve().is_relative_to(base.resolve()):
                    raise ValueError(f"Skill link leaves standalone directory: {name}/{relative}")
                normalized = absolute.resolve().relative_to(base.resolve()).as_posix()
                if normalized not in contents:
                    raise ValueError(f"Skill link target is not distributed: {name}/{normalized}")
        result[name] = contents
    return result


def package_skills(out_dir: Path, root: Path = ROOT) -> list[dict]:
    skills = skill_files(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for name, contents in skills.items():
        checksum = "".join(f"{hashlib.sha256(value).hexdigest()}  {path}\n"
                           for path, value in sorted(contents.items())).encode("utf-8")
        payload = {**contents, "SHA256SUMS": checksum}
        output = out_dir / f"{name}.zip"
        if output.is_symlink():
            raise ValueError("Refusing a symbolic-link output archive")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, data in sorted(payload.items()):
                info = zipfile.ZipInfo(f"{name}/{relative}", date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = ((0o100755 if relative.endswith(".py") else 0o100644) << 16)
                archive.writestr(info, data)
        receipts.append({"name": name, "path": str(output), "files": len(payload),
                         "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                         "bytes": output.stat().st_size})
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check the explicit distribution whitelist")
    parser.add_argument("--out-dir", type=Path, help="Write one deterministic ZIP per Skill")
    args = parser.parse_args()
    try:
        if args.out_dir is not None:
            print(json.dumps({"packages": package_skills(args.out_dir)}, indent=2))
        else:
            skills = skill_files()
            print("AGENT_SKILLS_OK " + " ".join(skills))
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        parser.exit(1, f"AGENT_SKILLS_INVALID: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
