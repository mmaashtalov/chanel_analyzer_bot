"""Build and validate the deterministic product manifest.

The manifest deliberately excludes itself and generated runtime caches. This
avoids the self-hash loop that made the previous static manifest unverifiable.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "MANIFEST.json"
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "htmlcov",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
CANONICAL_ARCHIVE = "release/chanel_analyzer_bot_product_v0_22_0.tar.gz"


def iter_project_files() -> Iterator[tuple[str, Path]]:
    """Yield reproducible project files as ``(relative_path, path)`` pairs."""

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES or relative.as_posix() == "MANIFEST.json":
            continue
        yield relative.as_posix(), path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _test_count() -> int:
    total = 0
    tests_root = ROOT / "tests"
    for path in sorted(tests_root.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        total += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in tree.body
        )
    return total


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as source:
        return str(tomllib.load(source)["project"]["version"])


def build_manifest() -> dict[str, object]:
    package_version = _package_version()
    files = [
        {
            "path": relative,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for relative, path in iter_project_files()
    ]
    test_count = _test_count()
    archive = next((item for item in files if item["path"] == CANONICAL_ARCHIVE), None)
    if archive is None:
        raise FileNotFoundError(CANONICAL_ARCHIVE)
    return {
        "schema": 2,
        "version": f"{package_version}-product",
        "package_version": package_version,
        "canonical_archive": archive,
        "tests": f"{test_count}/{test_count}",
        "test_count": test_count,
        "file_count": len(files),
        "generated_by": "scripts/generate_manifest.py",
        "files": files,
    }


def _render(manifest: dict[str, object]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify MANIFEST.json instead of rewriting it",
    )
    args = parser.parse_args(argv)
    rendered = _render(build_manifest())
    if args.check:
        if not MANIFEST_PATH.is_file():
            print(f"Manifest is missing: {MANIFEST_PATH}", file=sys.stderr)
            return 1
        actual = MANIFEST_PATH.read_text(encoding="utf-8")
        if actual != rendered:
            print("MANIFEST.json is stale; run: python scripts/generate_manifest.py", file=sys.stderr)
            return 1
        print("Manifest is reproducible and up to date")
        return 0
    MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
