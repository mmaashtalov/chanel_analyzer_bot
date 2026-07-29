from __future__ import annotations

import hashlib
import tarfile

from scripts.build_release_archive import build_archive


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_release_archive_is_reproducible_and_excludes_legacy(tmp_path) -> None:
    first = build_archive(tmp_path / "first.tar.gz")
    second = build_archive(tmp_path / "second.tar.gz")

    assert _sha256(first) == _sha256(second)
    with tarfile.open(first, "r:gz") as archive:
        names = archive.getnames()
    assert "telegram_osint_platform/MANIFEST.json" not in names
    assert "telegram_osint_platform/bot.py" not in names
    assert "telegram_osint_platform/parser.py" not in names
    assert "telegram_osint_platform/app/main.py" in names
