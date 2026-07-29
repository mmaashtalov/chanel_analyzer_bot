"""Create the reproducible canonical product archive for the current release."""

from __future__ import annotations

import gzip
import os
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "release" / "chanel_analyzer_bot_product_v0_24_0.tar.gz"
ARCHIVE_ROOT = "telegram_osint_platform"
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
    "release",
    "venv",
}
EXCLUDED_FILE_NAMES = {
    "MANIFEST.json",
    "bot.py",
    "parser.py",
    "build_release_archive.py",
    "generate_manifest.py",
    "project_preflight.py",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def iter_files() -> list[Path]:
    """Return canonical archive members, excluding generated and legacy inputs."""

    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        if path.name in EXCLUDED_FILE_NAMES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return files


def _directory_info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=f"{name.rstrip('/')}/")
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _file_info(path: Path, arcname: str) -> tarfile.TarInfo:
    stat = path.stat()
    info = tarfile.TarInfo(name=arcname)
    info.size = stat.st_size
    info.mode = stat.st_mode & 0o777
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def build_archive(output: Path = ARCHIVE) -> Path:
    """Build ``output`` deterministically and atomically."""

    output.parent.mkdir(parents=True, exist_ok=True)
    files = iter_files()
    directories = {ARCHIVE_ROOT}
    for path in files:
        relative = path.relative_to(ROOT)
        parent = relative.parent
        while parent != Path("."):
            directories.add(f"{ARCHIVE_ROOT}/{parent.as_posix()}")
            parent = parent.parent

    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".release-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with (
            temporary.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w|") as archive,
        ):
            for directory in sorted(directories):
                archive.addfile(_directory_info(directory))
            for path in files:
                arcname = f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}"
                with path.open("rb") as source:
                    archive.addfile(_file_info(path, arcname), source)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    print(build_archive().relative_to(ROOT))
