#!/usr/bin/env python3
"""Recover verified product source while preserving newer productization files.

Recovery order:
1. A GitHub Release archive downloaded and verified by the workflow.
2. The versioned runtime bundle stored in ``release/chunks``.
3. The historical HTTPS source archive from the manifest.
4. Incomplete source chunks, used only for diagnostics/disaster recovery.

Every accepted archive is checked by SHA-256 before extraction.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ARCHIVE = ROOT / "release" / "chanel_analyzer_bot_product_v0_22_0.tar.gz"
LOCAL_EXPECTED_SHA256 = "da6794ad2df8a7ae26fc9fbd82207138b319e1f43fa974e1814bbaea07ab24ae"
LOCAL_ARCHIVE_ROOT = "telegram_osint_platform"
LOCAL_VERSION = "0.22.0-product"
BUNDLE_DIR = ROOT / "release" / "source_v023"
RUNTIME_BUNDLE_DIR = ROOT / "release" / "chunks"
MANIFEST = BUNDLE_DIR / "direct_manifest.json"
RUNTIME_EXPECTED_SHA256 = "da6794ad2df8a7ae26fc9fbd82207138b319e1f43fa974e1814bbaea07ab24ae"
RUNTIME_ARCHIVE_ROOT = "telegram_osint_platform"

PRESERVE_TOP_LEVEL = {
    ".git",
    ".github",
    ".env.example",
    "Dockerfile",
    "README.md",
    "docker-compose.yml",
    "emulator",
    "render.yaml",
    "release",
    "scripts",
    "start-product.bat",
    "start-product.sh",
}
PRESERVE_FILES = {Path("app/setup/secure_proxy.py")}


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
    with tarfile.open(archive, "r:*") as source:
        for member in source.getmembers():
            target = (base / member.name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Unsafe archive path: {member.name}")
            if member.issym() or member.islnk():
                link = (target.parent / member.linkname).resolve()
                if link != base and base not in link.parents:
                    raise RuntimeError(f"Unsafe archive link: {member.name}")
        source.extractall(base, filter="data")


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


def overlay_tree(
    source: Path,
    destination: Path,
    source_root: Path,
    protected: set[Path],
) -> None:
    """Overlay source files without deleting newer productization files."""
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        relative = item.relative_to(source_root)
        target = destination / item.name
        if item.is_dir():
            overlay_tree(item, target, source_root, protected)
        elif relative not in protected:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def decode_chunk_set(paths: list[Path], label: str) -> bytes:
    if not paths:
        raise RuntimeError(f"No {label} chunks found")
    print(
        f"{label} inventory ({len(paths)}): "
        + ", ".join(f"{path.name}:{path.stat().st_size}" for path in paths),
        flush=True,
    )
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in paths)
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError(f"{label} chunks contain invalid base64") from exc


def use_runtime_bundle(archive: Path) -> tuple[str, str, str] | None:
    paths = sorted(RUNTIME_BUNDLE_DIR.glob("*.b64"))
    if not paths:
        print("No repository runtime bundle chunks found", flush=True)
        return None
    try:
        raw = decode_chunk_set(paths, "runtime bundle")
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return None

    actual = digest_bytes(raw)
    print(
        f"Runtime bundle assembled: {len(raw)} bytes, SHA-256 {actual}",
        flush=True,
    )
    if actual != RUNTIME_EXPECTED_SHA256:
        print(
            "Runtime bundle is incomplete or out of order: "
            f"expected {RUNTIME_EXPECTED_SHA256}, got {actual}",
            flush=True,
        )
        return None
    archive.write_bytes(raw)
    return "verified-repository-runtime-bundle", actual, RUNTIME_ARCHIVE_ROOT


def repository_chunk_paths() -> list[Path]:
    chunks: list[Path] = []
    for index in range(10):
        chunks.append(BUNDLE_DIR / f"part_{index:02d}.b64")
        if index == 4:
            chunks.extend(sorted(BUNDLE_DIR.glob("tail4_*.b64")))
    return chunks


def restore_from_repository_source_chunks(archive: Path, expected: str) -> None:
    chunks = repository_chunk_paths()
    missing = [str(path.relative_to(ROOT)) for path in chunks if not path.is_file()]
    if missing:
        raise RuntimeError(f"Repository source chunks are missing: {missing}")

    raw = decode_chunk_set(chunks, "source bundle")
    actual = digest_bytes(raw)
    print(
        f"Source chunks assembled: {len(raw)} bytes, SHA-256 {actual}",
        flush=True,
    )
    if actual != expected:
        raise RuntimeError(
            f"Repository source chunk SHA-256 mismatch: expected {expected}, got {actual}"
        )
    archive.write_bytes(raw)


def use_workflow_release(archive: Path) -> tuple[str, str, str] | None:
    source_value = os.getenv("RECOVERY_ARCHIVE_PATH", "").strip()
    expected = os.getenv("RECOVERY_ARCHIVE_SHA256", "").strip().lower()
    archive_root = os.getenv("RECOVERY_ARCHIVE_ROOT", "").strip()
    if not source_value:
        return None

    source = Path(source_value)
    if not source.is_file():
        raise RuntimeError(f"Workflow release archive does not exist: {source}")
    if len(expected) != 64 or not archive_root:
        raise RuntimeError("Workflow release metadata is incomplete")

    actual = digest_file(source)
    if actual != expected:
        raise RuntimeError(
            f"GitHub Release SHA-256 mismatch: expected {expected}, got {actual}"
        )
    shutil.copy2(source, archive)
    print(
        f"Using verified GitHub Release archive: {source.name}, SHA-256 {actual}",
        flush=True,
    )
    return "verified-github-release", expected, archive_root


def use_repository_archive(archive: Path) -> tuple[str, str, str] | None:
    if not LOCAL_ARCHIVE.is_file():
        print(f"Repository release archive is absent: {LOCAL_ARCHIVE}", flush=True)
        return None

    actual = digest_file(LOCAL_ARCHIVE)
    if actual != LOCAL_EXPECTED_SHA256:
        raise RuntimeError(
            "Repository release archive SHA-256 mismatch: "
            f"expected {LOCAL_EXPECTED_SHA256}, got {actual}"
        )
    shutil.copy2(LOCAL_ARCHIVE, archive)
    print(
        f"Using verified repository release archive: {LOCAL_ARCHIVE.name}, SHA-256 {actual}",
        flush=True,
    )
    return "verified-repository-archive", actual, LOCAL_ARCHIVE_ROOT


def obtain_historical_archive(
    archive: Path,
    url: str,
    expected: str,
    archive_root: str,
) -> tuple[str, str, str]:
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
        return "verified-https", expected, archive_root
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        print(f"Historical HTTPS source unavailable or invalid: {exc}", flush=True)
        print("Falling back to versioned repository source chunks", flush=True)
        restore_from_repository_source_chunks(archive, expected)
        return "verified-repository-source-chunks", expected, archive_root


def locate_source_root(extracted: Path, preferred_root: str) -> Path:
    direct = extracted / preferred_root
    if direct.is_dir():
        return direct

    candidates = [
        path.parent
        for path in extracted.rglob("pyproject.toml")
        if (path.parent / "app" / "setup" / "server.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(
        f"Cannot uniquely locate product root; preferred={preferred_root!r}, "
        f"candidates={[str(path) for path in candidates]}"
    )


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    url = str(manifest["url"])
    manifest_expected = str(manifest["sha256"]).lower()
    manifest_root = str(manifest["root"])

    if not url.startswith("https://") or len(manifest_expected) != 64:
        raise RuntimeError("Invalid source manifest")

    with tempfile.TemporaryDirectory(prefix="product-source-recovery-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "product-archive"

        result = use_workflow_release(archive)
        if result is None:
            result = use_repository_archive(archive)
        if result is None:
            result = use_runtime_bundle(archive)
        if result is None:
            result = obtain_historical_archive(
                archive,
                url,
                manifest_expected,
                manifest_root,
            )
        recovery_mode, accepted_sha, preferred_root = result

        extracted = temp / "extracted"
        extracted.mkdir()
        safe_extract(archive, extracted)
        source_root = locate_source_root(extracted, preferred_root)

        if not (source_root / "pyproject.toml").is_file():
            raise RuntimeError("Recovered archive has no pyproject.toml")
        if not (source_root / "app" / "setup" / "server.py").is_file():
            raise RuntimeError("Recovered archive has no Control Center source")

        for item in source_root.iterdir():
            if item.name in PRESERVE_TOP_LEVEL:
                continue
            target = ROOT / item.name
            if item.is_dir():
                overlay_tree(item, target, source_root, PRESERVE_FILES)
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
                "version": LOCAL_VERSION if recovery_mode == "verified-repository-archive" else manifest["version"],
                "archive_sha256": accepted_sha,
                "mode": recovery_mode,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Recovered source via {recovery_mode}; SHA-256 {accepted_sha}",
        flush=True,
    )


if __name__ == "__main__":
    main()
