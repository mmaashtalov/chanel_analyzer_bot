#!/usr/bin/env python3
"""Recover the verified product source without deleting newer productization files.

The preferred source is the HTTPS archive declared in the manifest. Because
temporary release hosts can expire, the repository also contains an ordered
base64 transport copy. Both paths are verified against the same SHA-256 before
anything is extracted or copied.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "release" / "source_v023"
MANIFEST = BUNDLE_DIR / "direct_manifest.json"

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


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
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
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def repository_chunk_paths() -> list[Path]:
    """Return transport chunks in byte order.

    ``part_04`` exceeded a previous transport limit and therefore has five
    continuation files which belong immediately after it.
    """
    chunks: list[Path] = []
    for index in range(10):
        chunks.append(BUNDLE_DIR / f"part_{index:02d}.b64")
        if index == 4:
            chunks.extend(sorted(BUNDLE_DIR.glob("tail4_*.b64")))
    return chunks


def restore_from_repository_chunks(archive: Path, expected: str) -> None:
    chunks = repository_chunk_paths()
    missing = [str(path.relative_to(ROOT)) for path in chunks if not path.is_file()]
    if missing:
        raise RuntimeError(f"Repository source chunks are missing: {missing}")

    encoded = "".join(path.read_text(encoding="ascii").strip() for path in chunks)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError("Repository source chunks contain invalid base64") from exc

    actual = digest_bytes(raw)
    print(
        f"Repository chunks assembled: {len(chunks)} files, "
        f"{len(raw)} bytes, SHA-256 {actual}",
        flush=True,
    )
    if actual != expected:
        raise RuntimeError(
            f"Repository chunk SHA-256 mismatch: expected {expected}, got {actual}"
        )
    archive.write_bytes(raw)


def obtain_archive(archive: Path, url: str, expected: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "channel-analyzer-productization/0.24"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = digest_file(archive)
        if actual != expected:
            raise RuntimeError(
                f"Downloaded source SHA-256 mismatch: expected {expected}, got {actual}"
            )
        return "verified-https"
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        print(f"HTTPS source unavailable or invalid: {exc}", flush=True)
        print("Falling back to versioned repository chunks", flush=True)
        restore_from_repository_chunks(archive, expected)
        return "verified-repository-chunks"


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
        recovery_mode = obtain_archive(archive, url, expected)

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
                "mode": recovery_mode,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Recovered source {manifest['version']} ({expected}) via {recovery_mode}",
        flush=True,
    )


if __name__ == "__main__":
    main()
