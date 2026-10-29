#!/usr/bin/env python3
"""Pinned, isolated source build of the project's browser QEMU. Never runs guests."""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RECIPE = Path(__file__).resolve().parent
LOCK_PATH = RECIPE / "sources.lock.json"
OWNER = ".m5-qemu-wasm-build.json"
RUNTIME_KIND = "m5stack-qemu-browser-runtime"
ASSET_NAMES = {
    "javascript": "qemu-system-xtensa.js",
    "wasm": "qemu-system-xtensa.wasm",
    "worker": "qemu-system-xtensa.worker.js",
    "source": "corresponding-source.tar.xz",
    "notice": "NOTICE",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def load_lock(root: Path = ROOT) -> dict:
    lock = json.loads((root / "scripts/qemu-wasm-build/sources.lock.json").read_text())
    if lock.get("schema_version") != 1 or lock.get("native_patch_count") != 31:
        raise ValueError("unsupported QEMU source lock")
    for row in lock["patches"] + lock["dependency_patches"]:
        path = root / row["path"]
        if path.is_symlink() or sha(path) != row["sha256"]:
            raise ValueError("locked patch mismatch: " + row["path"])
    return lock


def safe_directory(path: Path, root: Path = ROOT) -> Path:
    path = path.resolve()
    if path == root or path in root.parents or any(
        path == source or source in path.parents
        for source in (root / "platform", root / "scripts", root / "patches", root / "devices", root / ".git")
    ):
        raise ValueError("build/export must use a separate ignored or external directory")
    return path


def acquire(url: str, output: Path, expected: str, *, limit: int = 128 * 1024 * 1024) -> Path:
    if output.is_file() and sha(output) == expected:
        return output
    if output.exists():
        raise ValueError("existing archive has the wrong hash: " + output.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "m5stack-qemu-wasm-source-builder"})
    total = 0
    with urllib.request.urlopen(request, timeout=60) as source, temporary.open("wb") as target:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            total += len(block)
            if total > limit:
                raise ValueError("source archive exceeds its size limit")
            target.write(block)
    if sha(temporary) != expected:
        raise ValueError("download SHA256 mismatch: " + output.name)
    temporary.replace(output)
    return output


def extract_archive(archive: Path, target: Path) -> None:
    """Extract reviewed source archives with traversal/link filtering."""
    target.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or ((member.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("unsafe source ZIP member")
            package.extractall(target)
    else:
        with tarfile.open(archive) as package:
            package.extractall(target, filter="data")


def source_member_allowed(relative: Path) -> bool:
    """Exclude opaque firmware images, including extensionless/compressed BIOS."""
    if relative.parts[:3] == ("tests", "qemu-iotests", "sample_images"):
        return False
    name = relative.name.lower()
    while Path(name).suffix in {".bz2", ".gz", ".xz", ".zst", ".lz4", ".lzma", ".zip", ".z"}:
        name = str(Path(name).with_suffix(""))
    if name.endswith((".bin", ".rom", ".elf", ".img", ".fd", ".efi", ".raw", ".qcow", ".qcow2", ".qed", ".vdi", ".vmdk", ".vhd", ".vhdx", ".iso", ".dsk", ".dtb", ".pyc", ".pyo")):
        return False
    if relative.parts[0] == "pc-bios":
        return relative.suffix in {".c", ".h", ".S", ".s", ".py", ".sh", ".mak", ".txt", ".md", ".rst", ".ld", ".lds", ".in", ".dts"} or relative.name in {"meson.build", "Makefile", "README", "COPYING", "LICENSE", "NOTICE"}
    return True


def audit_link_arguments(argv: list[str], flags: list[str]) -> dict:
    for expected in flags:
        setting = expected.split("=", 1)[0] + "="
        actual = [arg for arg in argv if arg.startswith(setting)]
        if not actual or any(arg != expected for arg in actual):
            raise ValueError("effective QEMU link setting mismatch: " + expected)
    return {"verified": True, "source": "ninja-link-command", "required_flags": flags,
            "effective": {flag.split("=", 1)[0][2:]: flag.split("=", 1)[1] for flag in flags},
            "argv_sha256": hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()}


class Builder:
    def __init__(self, cache: Path, *, jobs: int = 2, sdk: Path | None = None, downloads: Path | None = None, reuse_dependencies: Path | None = None):
        self.cache = safe_directory(cache)
        self.lock = load_lock()
        self.lock_sha = sha(LOCK_PATH)
        self.recipe_sha = sha(Path(__file__))
        self.jobs = jobs
        if not 1 <= jobs <= 64:
            raise ValueError("jobs must be between 1 and 64")
        marker = self.cache / OWNER
        if self.cache.exists() and any(self.cache.iterdir()):
            previous = json.loads(marker.read_text()) if marker.is_file() else {}
            if previous.get("lock_sha256") != self.lock_sha or previous.get("recipe_sha256") != self.recipe_sha:
                raise ValueError("refusing an unowned cache or a different source lock; use a new --cache")
        self.cache.mkdir(parents=True, exist_ok=True)
        write_json(marker, {"kind": "qemu-wasm-build", "lock_sha256": self.lock_sha, "recipe_sha256": self.recipe_sha})
        self.downloads = downloads.resolve() if downloads else self.cache / "downloads"
        self.sdk = sdk.resolve() if sdk else self.cache / "emsdk"
        self.external_sdk = sdk is not None
        self.prefix = self.cache / "target"
        self.native = self.cache / "native"
        self.reuse_dependencies = reuse_dependencies.resolve() if reuse_dependencies else None
        if self.reuse_dependencies:
            previous = json.loads((self.reuse_dependencies / OWNER).read_text())
            if previous.get("lock_sha256") != self.lock_sha or not (self.reuse_dependencies / "dependencies.json").is_file():
                raise ValueError("dependency cache is not a completed source build of this exact lock")
            self.prefix = self.reuse_dependencies / "target"
            self.native = self.reuse_dependencies / "native"
        self.venv = self.cache / "tools"
        self.source = self.cache / "qemu"
        self.build = self.cache / "qemu-build"
        self.logs = self.cache / "logs"
        self.logs.mkdir(exist_ok=True)
        command_file = self.cache / "commands.json"
        self.commands: list[dict] = json.loads(command_file.read_text()) if command_file.is_file() else []

    def run(self, args, *, cwd: Path | None = None, env: dict | None = None) -> str:
        args = list(map(str, args))
        number = len(self.commands)
        name = f"{number:04d}-{Path(args[0]).name}.log"
        # Local logs contain exact paths; the distributable receipt uses relative
        # recipe identity and asset hashes, never these machine paths.
        self.commands.append({"argv": args, "cwd": str(cwd) if cwd else None, "log": name})
        write_json(self.cache / "commands.json", self.commands)
        print("build:", name, flush=True)
        with (self.logs / name).open("wb") as log:
            result = subprocess.run(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}); see {self.logs / name}")
        return (self.logs / name).read_text(errors="replace").strip()

    def clone(self, url: str, path: Path, commit: str) -> None:
        if not path.exists():
            self.run(["git", "init", "-q", path])
            self.run(["git", "remote", "add", "origin", url], cwd=path)
            self.run(["git", "fetch", "--depth", "1", "origin", commit], cwd=path)
            self.run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=path)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
        if actual != commit:
            raise ValueError("existing source revision mismatch; use a new cache")

    def prepare_source(self) -> None:
        qemu = self.lock["qemu"]
        stamp = self.cache / "source.json"
        if stamp.exists():
            self.verify_source()
            return
        self.clone(qemu["repository"], self.source, qemu["commit"])
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=self.source):
            raise ValueError("unreceipted QEMU source has changes; use a new cache")
        for row in self.lock["patches"]:
            self.run(["git", "apply", "--check", ROOT / row["path"]], cwd=self.source)
            self.run(["git", "apply", ROOT / row["path"]], cwd=self.source)
        for row in self.lock["subprojects"]:
            self.clone(row["repository"], self.source / "subprojects" / row["path"], row["commit"])
        self.verify_source()
        write_json(stamp, {"lock_sha256": self.lock_sha, "patched_files": self.lock["patched_files"]})

    def verify_source(self) -> None:
        for name, expected in self.lock["patched_files"].items():
            if sha(self.source / name) != expected:
                raise ValueError("patched source mismatch: " + name)
        changed = set(subprocess.check_output(["git", "diff", "--name-only", "--no-renames", "HEAD"], cwd=self.source, text=True).splitlines())
        untracked = set(subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=self.source, text=True).splitlines())
        allowed = set(self.lock["patched_files"]) | {"subprojects/.wraplock"}
        if (changed | untracked) - allowed:
            raise ValueError("QEMU source contains unrelated modifications")
        for row in self.lock["subprojects"]:
            source = self.source / "subprojects" / row["path"]
            actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
            dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source)
            others = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=source, text=True).splitlines()
            if actual != row["commit"] or dirty or set(others) - {".meson-subproject-wrap-hash.txt"}:
                raise ValueError("QEMU subproject drift: " + row["path"])

    def tools(self) -> dict:
        if not (self.venv / "bin/python").exists():
            self.run([sys.executable, "-m", "venv", self.venv])
            self.run([self.venv / "bin/python", "-m", "pip", "install", *[f"{name}=={version}" for name, version in self.lock["host_tools"].items()]])
        if not self.external_sdk:
            pin = self.lock["emsdk"]
            self.clone(pin["repository"], self.sdk, pin["commit"])
            if not (self.sdk / ".emscripten").exists():
                self.run([self.sdk / "emsdk", "install", pin["version"]])
                self.run([self.sdk / "emsdk", "activate", pin["version"], "--embedded"])
        version_file = self.sdk / "upstream/emscripten/emscripten-version.txt"
        if json.loads(version_file.read_text()) != self.lock["emsdk"]["version"]:
            raise ValueError("Emscripten 3.1.50 is required")
        if not (self.sdk / ".emscripten").is_file():
            raise ValueError("SDK must have a local .emscripten config; global config is not used")
        env = os.environ.copy()
        for key in ("CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CC", "CXX", "AR", "RANLIB", "NM", "LD", "CPATH", "LIBRARY_PATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "EMCC_CFLAGS", "EMMAKEN_CFLAGS", "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG", "CONFIG_SITE"):
            env.pop(key, None)
        env.update({"EM_CONFIG": str(self.sdk / ".emscripten"), "EM_CACHE": str(self.cache / "em-cache"),
            "PATH": os.pathsep.join(map(str, [self.sdk / "upstream/emscripten", self.sdk / "upstream/bin", self.venv / "bin", self.native / "bin"])) + os.pathsep + env.get("PATH", ""),
            "CC": "emcc", "CXX": "em++", "AR": "emar", "RANLIB": "emranlib", "NM": "emnm", "CC_FOR_BUILD": shutil.which("cc") or "/usr/bin/cc", "CFLAGS_FOR_BUILD": "", "LDFLAGS_FOR_BUILD": "",
            "CFLAGS": "-O2 -pthread -DWASM_BIGINT", "CXXFLAGS": "-O2 -pthread -DWASM_BIGINT", "CPPFLAGS": f"-I{self.prefix}/include",
            "LDFLAGS": f"-pthread -sWASM_BIGINT -sASYNCIFY=1 -L{self.prefix}/lib", "PKG_CONFIG": str(self.native / "bin/pkgconf"),
            "PKG_CONFIG_LIBDIR": str(self.prefix / "lib/pkgconfig"), "PKG_CONFIG_PATH": "", "EM_PKG_CONFIG_PATH": str(self.prefix / "lib/pkgconfig")})
        self.run([self.sdk / "upstream/emscripten/emcc", "--version"], env=env)
        return env

    def downloads_all(self) -> None:
        for row in self.lock["archives"]:
            acquire(row["url"], self.downloads / row["filename"], row["sha256"])

    def dep_source(self, name: str) -> Path:
        row = next(row for row in self.lock["archives"] if row["name"] == name)
        source = self.cache / "deps-source" / f"{name}-{row['version']}"
        if not source.exists():
            temporary = Path(tempfile.mkdtemp(dir=self.cache, prefix="unpack-"))
            extract_archive(self.downloads / row["filename"], temporary)
            children = list(temporary.iterdir())
            if len(children) != 1 or not children[0].is_dir():
                raise ValueError("unexpected source archive root")
            source.parent.mkdir(exist_ok=True)
            children[0].rename(source)
            temporary.rmdir()
        return source

    def dependencies(self, env: dict) -> None:
        if self.reuse_dependencies:
            previous = self.reuse_dependencies / "dependencies.json"
            receipt = json.loads(previous.read_text())
            if receipt.get("lock_sha256") != self.lock_sha:
                raise ValueError("dependency receipt lock mismatch")
            for path, expected in receipt["files"].items():
                if sha(self.reuse_dependencies / path) != expected:
                    raise ValueError("reused dependency changed")
            self.downloads_all()
            stub = self.cache / "unsupported-resolver.c"
            stub.write_bytes((self.reuse_dependencies / stub.name).read_bytes())
            write_json(self.cache / "dependencies.json", {"lock_sha256": self.lock_sha, "reused_source_build_receipt_sha256": sha(previous), "files": receipt["files"]})
            return
        stamp = self.cache / "dependencies.json"
        if stamp.exists():
            for path, expected in json.loads(stamp.read_text())["files"].items():
                if sha(self.cache / path) != expected:
                    raise ValueError("dependency changed; use a new cache")
            return
        self.prefix.mkdir(exist_ok=True); self.native.mkdir(exist_ok=True)
        self.downloads_all()
        native_env = env.copy()
        for key in ["CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS"]: native_env.pop(key, None)
        native_env.update(CC=shutil.which("cc") or "/usr/bin/cc", CXX=shutil.which("c++") or "/usr/bin/c++", AR="ar", RANLIB="ranlib", NM="nm")
        source = self.dep_source("pkgconf")
        if not (self.native / "bin/pkgconf").exists():
            self.run([source / "configure", f"--prefix={self.native}", "--disable-shared", "--enable-static"], cwd=source, env=native_env)
            self.run(["make", f"-j{self.jobs}"], cwd=source, env=native_env)
            self.run(["make", "install"], cwd=source, env=native_env)
        for name in ["zlib", "libffi", "pixman", "glib", "libgpg-error", "libgcrypt"]:
            source = self.dep_source(name)
            if name == "zlib":
                self.run(["emconfigure", source / "configure", f"--prefix={self.prefix}", "--static", "--uname=emscripten"], cwd=source, env=env)
                self.run(["make", "-B", "libz.a", f"-j{self.jobs}"], cwd=source, env=env)
                self.run(["make", "install"], cwd=source, env=env)
            elif name in ["libffi", "libgpg-error", "libgcrypt"]:
                build = self.cache / "deps-build" / name; build.mkdir(parents=True, exist_ok=True)
                guess = source / ("build-aux/config.guess" if name != "libffi" else "config.guess")
                triplet = subprocess.check_output(["sh", guess], text=True).strip()
                host = "wasm32-unknown-linux" if name == "libffi" else "wasm32-unknown-emscripten"
                options = [f"--host={host}", f"--build={triplet}", f"--prefix={self.prefix}", "--enable-static", "--disable-shared"]
                if name == "libffi": options += ["--disable-dependency-tracking", "--disable-builddir", "--disable-multi-os-directory", "--disable-raw-api", "--disable-docs"]
                else:
                    row = self.lock["dependency_patches"][0 if name == "libgpg-error" else 1]
                    done = self.cache / (name + "-patch.json")
                    if not done.exists():
                        self.run(["git", "apply", "--check", ROOT / row["path"]], cwd=source)
                        self.run(["git", "apply", ROOT / row["path"]], cwd=source)
                        write_json(done, row)
                    options += ["--disable-doc"]
                    if name == "libgpg-error": options += ["--disable-tests", "--disable-nls", "--enable-threads=posix"]
                    else: options += [f"--with-libgpg-error-prefix={self.prefix}"] + ["--disable-" + feature for feature in ["asm", "amd64-as-feature-detection", "drng-support", "jent-support", "pclmul-support", "padlock-support", "aesni-support", "avx-support", "avx2-support", "avx512-support", "sse41-support", "shaext-support", "gfni-support", "arm-crypto-support", "neon-support", "sve-support", "sve2-support", "ppc-crypto-support"]]
                if not (build / "Makefile").exists(): self.run(["emconfigure", source / "configure", *options], cwd=build, env=env)
                self.run(["emmake", "make", f"-j{self.jobs}", *(["SUBDIRS=compat mpi cipher random src"] if name == "libgcrypt" else [])], cwd=build, env=env)
                self.run(["emmake", "make", *(["-C", "src"] if name == "libgcrypt" else []), "install"], cwd=build, env=env)
            else:
                cross = self.cache / "deps-cross.ini"
                cross.write_text("[host_machine]\nsystem='emscripten'\ncpu_family='wasm32'\ncpu='wasm32'\nendian='little'\n[binaries]\n" + "\n".join(f"{key}='{value}'" for key, value in {"c": self.sdk / "upstream/emscripten/emcc", "cpp": self.sdk / "upstream/emscripten/em++", "ar": self.sdk / "upstream/emscripten/emar", "ranlib": self.sdk / "upstream/emscripten/emranlib"}.items()) + f"\npkg-config=['{self.native}/bin/pkgconf','--static']\n[properties]\nneeds_exe_wrapper=true\n[built-in options]\nc_args=['-O2','-pthread','-DWASM_BIGINT','-Wno-incompatible-function-pointer-types']\nc_link_args=['-pthread','-sWASM_BIGINT','-sASYNCIFY=1','-L{self.prefix}/lib']\n")
                build = self.cache / "deps-build" / name
                options = ["-Dtests=disabled", "-Ddemos=disabled"] if name == "pixman" else ["--force-fallback-for=pcre2", "-Dselinux=disabled", "-Dxattr=false", "-Dlibmount=disabled", "-Dnls=disabled", "-Dtests=false", "-Dglib_debug=disabled", "-Dglib_assert=false", "-Dglib_checks=false"]
                if name == "glib":
                    packages = source / "subprojects/packagecache"; packages.mkdir(exist_ok=True)
                    for row in self.lock["archives"]:
                        if row["name"].startswith("pcre2"): shutil.copy2(self.downloads / row["filename"], packages / row["filename"])
                    stub = self.cache / "unsupported-resolver.c"
                    stub.write_text("#include <netdb.h>\nint res_query(const char*n,int c,int t,unsigned char*d,int l){h_errno=HOST_NOT_FOUND;return -1;}\n")
                    self.run(["emcc", "-O2", "-pthread", "-c", stub, "-o", self.cache / "unsupported-resolver.o"], env=env)
                    self.run(["emar", "rcs", self.prefix / "lib/libresolv.a", self.cache / "unsupported-resolver.o"], env=env)
                if not (build / "build.ninja").exists(): self.run([self.venv / "bin/meson", "setup", build, source, f"--prefix={self.prefix}", f"--cross-file={cross}", "--default-library=static", "--buildtype=release", "--wrap-mode=nodownload", *options], env=env)
                if name == "glib":
                    config = build / "config.h"; text = config.read_text()
                    for macro in ["HAVE_POSIX_SPAWN", "HAVE_PTHREAD_GETNAME_NP"]: text = text.replace(f"#define {macro} 1", f"/* {macro} unavailable in Emscripten */")
                    config.write_text(text)
                self.run([self.venv / "bin/ninja", "-C", build, f"-j{self.jobs}"], env=env)
                self.run([self.venv / "bin/meson", "install", "-C", build], env=env)
        libraries = ["libz.a", "libffi.a", "libpixman-1.a", "libglib-2.0.a", "libpcre2-8.a", "libgpg-error.a", "libgcrypt.a", "libresolv.a"]
        write_json(stamp, {"lock_sha256": self.lock_sha, "files": {str((self.prefix / "lib" / name).relative_to(self.cache)): sha(self.prefix / "lib" / name) for name in libraries}})

    def compile(self, env: dict) -> dict:
        self.verify_source()
        if sha(Path(__file__)) != self.recipe_sha:
            raise ValueError("build recipe changed during execution; use a new cache")
        env = env.copy(); env["CFLAGS"] += " -Wno-incompatible-function-pointer-types"
        self.build.mkdir(exist_ok=True)
        options = ["--target-list=xtensa-softmmu", "--enable-tcg-interpreter", "--cpu=wasm32", "--static", "--disable-docs", "--disable-tools", "--disable-werror", "--without-default-features", "--disable-install-blobs", "--enable-gcrypt", "--enable-pixman", "--disable-plugins", "--disable-slirp", "--disable-sdl", "--disable-gtk", "--disable-cocoa", "--disable-vnc", "--disable-curl", "--disable-libssh", "--disable-gnutls", "--disable-nettle", "--disable-guest-agent", "--disable-download", f"--python={self.venv}/bin/python", f"--host-cc={shutil.which('cc') or '/usr/bin/cc'}", f"--cc={self.sdk}/upstream/emscripten/emcc", f"--cxx={self.sdk}/upstream/emscripten/em++", f"--extra-cflags=-I{self.prefix}/include -Wno-incompatible-function-pointer-types", f"--extra-ldflags=-L{self.prefix}/lib " + " ".join(self.lock["link_flags"])]
        # QEMU adds its Emscripten cross file after configure's generated cross
        # file. Its built-in c_args/c_link_args REPLACE those earlier values.
        # Meson command-line options have the final precedence; pass the full
        # reviewed host glue list plus explicit settings through that layer.
        cross_options = {}
        for line in (self.source / "configs/meson/emscripten.txt").read_text().splitlines():
            if line.startswith(("c_args =", "c_link_args =", "cpp_link_args =")):
                key, value = line.split("=", 1); cross_options[key.strip()] = ast.literal_eval(value)
        options += ["-Dc_args=" + repr(cross_options["c_args"] + shlex.split(env["CFLAGS"]) + [f"-I{self.prefix}/include"])]
        for language in ["c", "cpp"]:
            options += [f"-D{language}_link_args=" + repr(cross_options[language + "_link_args"] + self.lock["link_flags"])]
        if not (self.build / "build.ninja").exists(): self.run([self.source / "configure", *options], cwd=self.build, env=env)
        plan = subprocess.check_output([self.venv / "bin/ninja", "-C", self.build, "-t", "commands", "qemu-system-xtensa.js"], env=env, text=True)
        final_link = shlex.split(plan.splitlines()[-1])
        link_audit = audit_link_arguments(final_link, self.lock["link_flags"])
        write_json(self.cache / "effective-link.json", {"argv": final_link, **link_audit})
        self.run([self.venv / "bin/ninja", "-C", self.build, f"-j{self.jobs}", "qemu-system-xtensa.js"], env=env)
        self.verify_source()
        if sha(Path(__file__)) != self.recipe_sha:
            raise ValueError("build recipe changed during compilation; preserve this attempt and use a new cache")
        files = {key: self.build / name for key, name in ASSET_NAMES.items() if key in ["javascript", "wasm", "worker"]}
        if not files["wasm"].read_bytes().startswith(b"\0asm\x01\0\0\0"):
            raise ValueError("QEMU output is not WASM")
        report = {"status": "PASS", "lock_sha256": self.lock_sha, "kind": "source-build", "all_objects_rebuilt": True, "link_audit": link_audit, "guest_execution": "NOT RUN", "artifacts": {key: {"path": name.name, "bytes": name.stat().st_size, "sha256": sha(name)} for key, name in files.items()}}
        write_json(self.cache / "build-receipt.json", report)
        return report

    def source_bundle(self, output: Path) -> None:
        """Actual modified QEMU and all dependency inputs; no firmware/ROM blobs."""
        self.verify_source()
        for row in self.lock["archives"]:
            if sha(self.downloads / row["filename"]) != row["sha256"]:
                raise ValueError("dependency source archive drift before export: " + row["name"])
        with tarfile.open(output, "w:xz") as package:
            def add(path: Path, name: str):
                info = package.gettarinfo(str(path), arcname=name)
                info.uid = info.gid = 0; info.uname = info.gname = ""; info.mtime = 0
                if info.isfile():
                    with path.open("rb") as stream: package.addfile(info, stream)
                elif info.issym(): package.addfile(info)
            for base, dirs, files in os.walk(self.source):
                dirs[:] = [name for name in dirs if name not in [".git", "__pycache__", "roms"]]
                for name in sorted(files):
                    path = Path(base) / name
                    # These firmware/test images are not used to build the host
                    # executable. In particular the unreviewed S3 ROM cannot
                    # enter a source tarball via QEMU's pc-bios directory.
                    if not source_member_allowed(path.relative_to(self.source)): continue
                    if path.is_file(): add(path, "qemu/" + path.relative_to(self.source).as_posix())
            for row in self.lock["archives"]: add(self.downloads / row["filename"], "dependency-archives/" + row["filename"])
            for row in self.lock["patches"] + self.lock["dependency_patches"]: add(ROOT / row["path"], row["path"])
            for name in ["build.py", "sources.lock.json", "README.md"]: add(RECIPE / name, "scripts/qemu-wasm-build/" + name)
            add(ROOT / "platform/tools/bootstrap_qemu_browser_runtime.py", "platform/tools/bootstrap_qemu_browser_runtime.py")
            add(ROOT / "LICENSE", "LICENSE.project")
            # Emscripten JS support and linked libc/pthread sources and licenses.
            emscripten = self.sdk / "upstream/emscripten"
            for tree in ["src", "system"]:
                for base, dirs, files in os.walk(emscripten / tree):
                    dirs[:] = [name for name in dirs if name not in ["__pycache__", "cache"]]
                    for name in sorted(files):
                        path = Path(base) / name
                        if path.is_file() and not name.endswith((".pyc", ".wasm", ".bc", ".a", ".o")): add(path, "emscripten/" + path.relative_to(emscripten).as_posix())
            for name in ["LICENSE", "AUTHORS"]:
                if (emscripten / name).is_file(): add(emscripten / name, "emscripten/" + name)
            add(self.cache / "unsupported-resolver.c", "support/unsupported-resolver.c")


def runtime_files(directory: Path, *, allow_incremental: bool = False) -> tuple[dict, dict[str, bytes]]:
    """Strict allowlist reader shared with the public-site exporter."""
    lock = load_lock()
    manifest = json.loads((directory / "runtime.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("kind") != RUNTIME_KIND or manifest.get("engine") != "qemu-wasm":
        raise ValueError("unsupported browser QEMU runtime manifest")
    if manifest.get("source", {}).get("commit") != lock["qemu"]["commit"] or manifest["source"].get("patches") != lock["patches"] or manifest["source"].get("patched_files_sha256") != lock["patched_files"]:
        raise ValueError("QEMU source or patch lock mismatch")
    kind = manifest.get("build", {}).get("kind")
    rebuilt = manifest.get("build", {}).get("all_objects_rebuilt")
    if kind != "source-build" or (rebuilt is not True and not (allow_incremental and rebuilt is False)):
        raise ValueError("a full source build is required; incremental reference needs explicit opt-in")
    build = manifest["build"]
    if build.get("lock_sha256") != sha(LOCK_PATH) or build.get("emscripten") != lock["emsdk"]["version"]:
        raise ValueError("runtime build recipe/toolchain lock mismatch")
    if manifest.get("execution_profile") != {"id": "cores3-wasm-vm-div8", "clock_divisor": 8, "scope": "offline-lvgl-pir"}:
        raise ValueError("runtime execution profile mismatch")
    if manifest.get("compiled_profiles", ["cores3"]) != lock.get("compiled_profiles", ["cores3"]) or manifest.get("frame_transport") != lock.get("frame_transport"):
        raise ValueError("runtime compiled boards or framebuffer ABI mismatch")
    if rebuilt is True:
        audit = build.get("link_audit", {})
        effective = {flag.split("=", 1)[0][2:]: flag.split("=", 1)[1] for flag in lock["link_flags"]}
        if audit.get("verified") is not True or audit.get("source") != "ninja-link-command" or audit.get("required_flags") != lock["link_flags"] or audit.get("effective") != effective or not isinstance(audit.get("argv_sha256"), str) or len(audit["argv_sha256"]) != 64:
            raise ValueError("runtime lacks the verified effective link settings")
    if manifest.get("profiles") != ["cores3"] or manifest.get("required_rom") != lock["required_rom"] or manifest.get("firmware_bundled") is not False:
        raise ValueError("runtime profile/ROM/firmware distribution contract mismatch")
    if set(manifest.get("assets", {})) != set(ASSET_NAMES): raise ValueError("unexpected runtime assets")
    if rebuilt is False:
        reference = lock["reference_runtime"]
        if build.get("reference_build_receipt_sha256") != reference["build_receipt_sha256"]:
            raise ValueError("incremental reference receipt mismatch")
        for key in ["javascript", "wasm", "worker"]:
            if manifest["assets"][key].get("sha256") != reference["artifacts"][ASSET_NAMES[key]]["sha256"]:
                raise ValueError("incremental reference artifact mismatch")
    files = {"runtime.json": (directory / "runtime.json").read_bytes()}
    for key, expected_name in ASSET_NAMES.items():
        row = manifest["assets"][key]; path = directory / expected_name
        if row.get("path") != expected_name or path.is_symlink(): raise ValueError("unsafe runtime asset path")
        data = path.read_bytes()
        if len(data) != row.get("bytes") or hashlib.sha256(data).hexdigest() != row.get("sha256"):
            raise ValueError("runtime asset hash/size mismatch: " + key)
        files[expected_name] = data
    if not files[ASSET_NAMES["wasm"]].startswith(b"\0asm\x01\0\0\0"): raise ValueError("invalid WASM module")
    # The archive closes the recipe used for this output. Later improvements to
    # this validator must not invalidate a frozen, self-contained source build.
    try:
        with tarfile.open(fileobj=io.BytesIO(files[ASSET_NAMES["source"]])) as package:
            for member_name, expected in [("scripts/qemu-wasm-build/build.py", build.get("recipe_sha256")), ("scripts/qemu-wasm-build/sources.lock.json", build.get("lock_sha256"))]:
                member = package.getmember(member_name)
                if not member.isfile() or member.size > 512 * 1024:
                    raise ValueError("invalid archived build recipe")
                stream = package.extractfile(member)
                if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected:
                    raise ValueError("archived build recipe/lock hash mismatch")
    except (tarfile.TarError, KeyError) as error:
        raise ValueError("corresponding source archive lacks the bound build recipe") from error
    return manifest, files


def export_runtime(builder: Builder, output: Path, report: dict, *, runtime_directory: Path | None = None) -> dict:
    output = safe_directory(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("runtime output already contains files; preserve it and choose a new --output")
    output.mkdir(parents=True, exist_ok=True)
    for key in ["javascript", "wasm", "worker"]:
        shutil.copy2((runtime_directory or builder.build) / ASSET_NAMES[key], output / ASSET_NAMES[key])
    builder.source_bundle(output / ASSET_NAMES["source"])
    (output / "NOTICE").write_text("M5Stack browser QEMU source build\n\nQEMU is GPL-2.0; its COPYING and per-file licenses, the complete modified host source, linked dependencies, dependency patches and build recipe are in corresponding-source.tar.xz served beside this executable. This archive is part of the runtime export and must be preserved on redistribution. Individual libraries retain their own licenses (GLib/libgcrypt/libgpg-error LGPL, libffi/pixman/zlib/PCRE2 permissive terms); source archives include their exact license texts. Emscripten linked support/library sources and license texts are also included.\n\nROM and UIFlow2 firmware are not bundled. Their public availability is not treated as redistribution permission. Obtain the exact required ROM and firmware separately from authoritative upstream or user files; verify SHA-256 in the browser. The reviewed offline CoreS3 vm-div8 fixture does not establish physical timing, other firmware/device coverage or full hardware equivalence.\n", encoding="utf-8")
    lock = builder.lock
    manifest = {"schema_version": 1, "kind": RUNTIME_KIND, "engine": "qemu-wasm", "source": {**lock["qemu"], "native_patch_count": 31, "patches": lock["patches"], "patched_files_sha256": lock["patched_files"]},
        "build": {"kind": "source-build", "all_objects_rebuilt": report["all_objects_rebuilt"], "emscripten": "3.1.50", "recipe_sha256": builder.recipe_sha, "lock_sha256": builder.lock_sha, "commands_sha256": sha(builder.cache / "commands.json"), "guest_execution": "NOT RUN by builder", **({"link_audit": report["link_audit"]} if "link_audit" in report else {}), **({"reference_build_receipt_sha256": report["reference_build_receipt_sha256"], "reference_note": "Reviewed incremental source build; inherited object/library identities are in its original receipt. This is not a fresh full-object build."} if "reference_build_receipt_sha256" in report else {})},
        "profiles": ["cores3"], "compiled_profiles": lock.get("compiled_profiles", ["cores3"]), "frame_transport": lock.get("frame_transport"), "execution_profile": {"id": "cores3-wasm-vm-div8", "clock_divisor": 8, "scope": "offline-lvgl-pir"}, "assets": {key: {"path": name, "bytes": (output / name).stat().st_size, "sha256": sha(output / name)} for key, name in ASSET_NAMES.items()},
        "required_rom": lock["required_rom"], "firmware_bundled": False}
    write_json(output / "runtime.json", manifest)
    runtime_files(output, allow_incremental=not report["all_objects_rebuilt"])
    return manifest


def package_reference(builder: Builder, directory: Path, output: Path) -> dict:
    """Explicit local packaging of the exact reviewed incremental artifact."""
    reference = builder.lock["reference_runtime"]
    receipt = directory / "build-receipt.json"
    if sha(receipt) != reference["build_receipt_sha256"]:
        raise ValueError("reviewed reference build receipt mismatch")
    for name, row in reference["artifacts"].items():
        if (directory / name).is_symlink() or sha(directory / name) != row["sha256"]:
            raise ValueError("reviewed reference runtime asset mismatch")
    if json.loads((builder.sdk / "upstream/emscripten/emscripten-version.txt").read_text()) != "3.1.50":
        raise ValueError("reference source package requires the reviewed Emscripten SDK sources")
    builder.prepare_source()
    builder.downloads_all()
    stub = builder.cache / "unsupported-resolver.c"
    stub.write_text("#include <netdb.h>\nint res_query(const char*n,int c,int t,unsigned char*d,int l){h_errno=HOST_NOT_FOUND;return -1;}\n")
    report = {"kind": "source-build", "all_objects_rebuilt": False, "reference_build_receipt_sha256": sha(receipt)}
    return export_runtime(builder, output, report, runtime_directory=directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".work/qemu-browser-runtime-build")
    parser.add_argument("--output", type=Path, default=ROOT / ".work/qemu-browser-runtime")
    parser.add_argument("--sdk-dir", type=Path, help="existing isolated 3.1.50 SDK with local .emscripten config")
    parser.add_argument("--downloads", type=Path, help="reviewed archive cache; every input is SHA checked")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--check", action="store_true", help="verify tracked locks only, without network/build")
    parser.add_argument("--reference-runtime", type=Path, help="explicitly package only the exact reviewed incremental runtime; requires --sdk-dir and is not a fresh-build claim")
    parser.add_argument("--reuse-dependencies", type=Path, help="explicitly reuse verified completed libraries from another owned source-build cache with the identical lock; all QEMU objects are still built in the new cache")
    args = parser.parse_args()
    if sys.version_info < (3, 12): parser.error("Python 3.12+ is required")
    try:
        lock = load_lock()
        if args.check:
            print(json.dumps({"status": "PASS", "patch_count": len(lock["patches"]), "native_patch_count": 31, "patched_files": len(lock["patched_files"]), "rom_bundled": False, "firmware_bundled": False})); return
        builder = Builder(args.cache, jobs=args.jobs, sdk=args.sdk_dir, downloads=args.downloads, reuse_dependencies=args.reuse_dependencies)
        if args.reference_runtime:
            if not args.sdk_dir: raise ValueError("--reference-runtime requires --sdk-dir for matching library sources")
            manifest = package_reference(builder, args.reference_runtime.resolve(), args.output)
            print(json.dumps({"status": "PASS", "output": str(args.output), "all_objects_rebuilt": False, "wasm_sha256": manifest["assets"]["wasm"]["sha256"]})); return
        builder.prepare_source()
        if args.prepare_only:
            print(json.dumps({"status": "SOURCE_PREPARED", "source": str(builder.source), "guest_execution": "NOT RUN"})); return
        env = builder.tools(); builder.dependencies(env); report = builder.compile(env)
        manifest = export_runtime(builder, args.output, report)
        print(json.dumps({"status": "PASS", "output": str(args.output), "wasm_sha256": manifest["assets"]["wasm"]["sha256"], "rom_bundled": False, "firmware_bundled": False, "guest_execution": "NOT RUN"}))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"QEMU browser build failed: {error}\n")


if __name__ == "__main__": main()
