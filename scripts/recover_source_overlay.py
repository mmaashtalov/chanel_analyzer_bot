#!/usr/bin/env python3
"""Recover the verified product source without deleting newer productization files.

The transport repository temporarily contained only release metadata and selected
runtime files. This script downloads the signed-by-hash source archive declared
in ``release/source_v023/direct_manifest.json``, verifies it, safely extracts it,
and overlays the missing application source while preserving newer launchers,
Docker configuration, emulator assets, and repository workflows.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "source_v023" / "direct_manifest.json"

# These files are newer than the source bundle and must never be replaced.
PRESERVE_TOP_LEVEL = {
    ".git",
    ".github",
    ".env.example",
    "Dockerfile",
    "README.md",
    "docker-compose.yml",
    "emulator",
    "render.yaml",
    "scripts",
    "start-product.bat",
    "start-product.sh",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    base = destination.resolve()
    with tarfile.open(archive, "r:xz") as source:
        for member in source.getmembers():
            target = (base / member.name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Unsafe archive path: {member.name}")
            if member.issym() or member.islnk():
                link = (target.parent / member.linkname).resolve()
                if link != base and base not in link.parents:
                    raise RuntimeError(f"Unsafe archive link: {member.name}")
        source.extractall(base)


def copy_missing_tree(source: Path, destination: Path) -> None:
    """Copy files that do not exist, retaining newer repository files."""
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    url = str(manifest["url"])
    expected = str(manifest["sha256"]).lower()
    archive_root = str(manifest["root"])

    if not url.startswith("https://") or len(expected) != 64:
        raise RuntimeError("Invalid source manifest")

    with tempfile.TemporaryDirectory(prefix="product-source-recovery-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "source.tar.xz"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "channel-analyzer-productization/0.24"},
        )
        with urllib.request.urlopen(request, timeout=240) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)

        actual = digest(archive)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch: expected {expected}, got {actual}")

        extracted = temp / "extracted"
        extracted.mkdir()
        safe_extract(archive, extracted)
        source_root = extracted / archive_root
        if not (source_root / "pyproject.toml").is_file():
            raise RuntimeError("Recovered archive has no pyproject.toml")
        if not (source_root / "app" / "setup" / "server.py").is_file():
            raise RuntimeError("Recovered archive has no Control Center source")

        for item in source_root.iterdir():
            if item.name in PRESERVE_TOP_LEVEL:
                continue
            target = ROOT / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target, symlinks=True)
            else:
                shutil.copy2(item, target)

        # Bring back source scripts and CI only when they do not replace newer files.
        scripts = source_root / "scripts"
        if scripts.is_dir():
            copy_missing_tree(scripts, ROOT / "scripts")
        source_ci = source_root / ".github" / "workflows" / "ci.yml"
        target_ci = ROOT / ".github" / "workflows" / "ci.yml"
        if source_ci.is_file() and not target_ci.exists():
            target_ci.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_ci, target_ci)

    marker = ROOT / "SOURCE_RECOVERED.json"
    marker.write_text(
        json.dumps(
            {
                "version": manifest["version"],
                "archive_sha256": expected,
                "mode": "safe-overlay",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Recovered source {manifest['version']} ({expected})")


if __name__ == "__main__":
    main()
