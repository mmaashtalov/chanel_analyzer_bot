"""Fail-fast project lock and Sprint 0 integrity checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from generate_manifest import build_manifest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "mmaashtalov/chanel_analyzer_bot"
EXPECTED_ARCHIVE_HASH = "da6794ad2df8a7ae26fc9fbd82207138b319e1f43fa974e1814bbaea07ab24ae"
EXPECTED_PACKAGE_VERSION = "0.22.0"
REQUIRED_FILES = (
    ".dockerignore",
    ".gitignore",
    "Dockerfile",
    "MANIFEST.json",
    "README.md",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
    "app/entrypoint.py",
    "app/setup/secure_proxy.py",
    "release/chanel_analyzer_bot_product_v0_22_0.tar.gz",
)
REMOVED_WORKFLOWS = (
    ".github/workflows/apply-owner-gate.yml",
    ".github/workflows/finalize-product-0231.yml",
    ".github/workflows/materialize-source-direct.yml",
    ".github/workflows/materialize-source.yml",
    ".github/workflows/publish-release-0231.yml",
    ".github/workflows/recover-source-overlay.yml",
)
STALE_SURFACES = (
    "README.md",
    "MANIFEST.json",
    "app/demo/server.py",
    "app/setup/server.py",
    "app/setup/secure_proxy.py",
    "docs/DEMO_RELEASE.md",
    "docs/DEMO_RELEASE_REPORT.md",
    "docs/PRODUCT_RUNBOOK.md",
    "telegram_intelligence_demo_standalone.html",
)


def _fail(message: str) -> None:
    raise RuntimeError(message)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        _fail(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _archive_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_repository(remote: str) -> str:
    value = remote.strip().removesuffix("/").removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value


def _check_repository_identity() -> None:
    remote = _normalise_repository(_git("config", "--get", "remote.origin.url"))
    if remote != EXPECTED_REPOSITORY:
        _fail(f"Unexpected repository: {remote!r}; expected {EXPECTED_REPOSITORY!r}")


def _check_generated_files_are_untracked() -> None:
    tracked = _git("ls-files").splitlines()
    generated = [
        path
        for path in tracked
        if "/__pycache__/" in f"/{path}/"
        or path.endswith((".pyc", ".pyo"))
        or path.startswith((".pytest_cache/", ".ruff_cache/", ".mypy_cache/"))
    ]
    if generated:
        _fail("Generated files are tracked: " + ", ".join(generated[:10]))


def _check_version_surfaces() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.22.0"' not in pyproject:
        _fail("pyproject.toml does not declare package version 0.22.0")
    for relative in STALE_SURFACES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for stale in ("0.23.1", "94/94", "88/88", "pytest: 88"):
            if stale in text:
                _fail(f"Stale release marker {stale!r} remains in {relative}")


def _check_manifest() -> None:
    expected = build_manifest()
    actual = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    if actual != expected:
        _fail("MANIFEST.json is not reproducible from the current tree")
    if actual["package_version"] != EXPECTED_PACKAGE_VERSION:
        _fail("MANIFEST.json package version is not 0.22.0")


def _check_runtime_layout() -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            _fail(f"Required file is missing: {relative}")
    archive = ROOT / "release/chanel_analyzer_bot_product_v0_22_0.tar.gz"
    if _archive_hash(archive) != EXPECTED_ARCHIVE_HASH:
        _fail("Canonical archive SHA-256 mismatch")
    for relative in REMOVED_WORKFLOWS:
        if (ROOT / relative).exists():
            _fail(f"One-shot or stale workflow remains: {relative}")
    for relative in ("release/chunks", "release/source_v023"):
        if (ROOT / relative).exists():
            _fail(f"Unverified recovery material remains: {relative}")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "COPY . /app" not in dockerfile or 'CMD ["/usr/local/bin/product-entrypoint"]' not in dockerfile:
        _fail("Dockerfile does not build the current tree with an overridable default command")


def main() -> int:
    try:
        _check_repository_identity()
        _check_generated_files_are_untracked()
        _check_version_surfaces()
        _check_manifest()
        _check_runtime_layout()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"PROJECT PREFLIGHT FAILED: {exc}", file=sys.stderr)
        return 1
    print("PROJECT PREFLIGHT PASSED: repository, archive, manifest and runtime layout are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
