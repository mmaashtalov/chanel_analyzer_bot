#!/usr/bin/env python3
"""Materialize a verified product source archive into the repository root.

This script is intended to run only inside GitHub Actions. It downloads the
archive declared by a small manifest, verifies SHA-256 before extraction,
prevents path traversal, replaces the transport repository with the normal
source tree, and leaves Git commit/push to the workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "release" / "source_v023" / "direct_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, mode="r:xz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(f"Unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                link_target = (target.parent / member.linkname).resolve()
                if link_target != destination and destination not in link_target.parents:
                    raise RuntimeError(f"Unsafe archive link: {member.name}")
        tar.extractall(destination)


def clear_repository() -> None:
    for item in REPO_ROOT.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_tree(source: Path) -> None:
    for item in source.iterdir():
        destination = REPO_ROOT / item.name
        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, destination, symlinks=True)
        else:
            shutil.copy2(item, destination, follow_symlinks=False)


def main() -> None:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(MANIFEST_PATH)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    url = str(manifest["url"])
    expected_sha256 = str(manifest["sha256"]).lower()
    archive_root = str(manifest["root"])
    version = str(manifest["version"])

    if not url.startswith("https://"):
        raise ValueError("Only HTTPS source URLs are accepted")
    if len(expected_sha256) != 64:
        raise ValueError("Invalid SHA-256 in manifest")

    with tempfile.TemporaryDirectory(prefix="source-materialize-") as temp_dir:
        temp = Path(temp_dir)
        archive = temp / "source.tar.xz"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "channel-analyzer-source-materializer/0.23.0"},
        )
        with urllib.request.urlopen(request, timeout=180) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)

        actual_sha256 = sha256_file(archive)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )

        extracted = temp / "extracted"
        extracted.mkdir()
        safe_extract(archive, extracted)
        source_root = extracted / archive_root
        if not source_root.is_dir():
            raise RuntimeError(f"Archive root not found: {archive_root}")
        if not (source_root / "pyproject.toml").is_file():
            raise RuntimeError("Source archive does not contain pyproject.toml")
        if not (source_root / "app" / "setup" / "server.py").is_file():
            raise RuntimeError("Source archive does not contain the Control Center")

        clear_repository()
        copy_tree(source_root)

    marker = REPO_ROOT / "SOURCE_MATERIALIZED.json"
    marker.write_text(
        json.dumps(
            {
                "version": version,
                "archive_sha256": expected_sha256,
                "materialized_by": "GitHub Actions",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Materialized {version} with SHA-256 {expected_sha256}")


if __name__ == "__main__":
    main()
