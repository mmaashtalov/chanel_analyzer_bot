from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "release" / "source_v023"
MANIFEST = BUNDLE_DIR / "manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    chunks = [BUNDLE_DIR / name for name in manifest["chunks"]]
    if any(not path.is_file() for path in chunks):
        missing = [path.name for path in chunks if not path.is_file()]
        raise SystemExit(f"Missing chunks: {missing}")

    encoded = "".join(path.read_text(encoding="ascii") for path in chunks)
    archive = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(archive).hexdigest()
    if digest != manifest["sha256"]:
        raise SystemExit(f"SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "source.tar.xz"
        archive_path.write_bytes(archive)
        with tarfile.open(archive_path, "r:xz") as source:
            source.extractall(tmp_path, filter="data")
        source_root = tmp_path / manifest["root"]
        if not (source_root / "pyproject.toml").is_file():
            raise SystemExit("Invalid source archive")

        preserve = {".git"}
        for child in ROOT.iterdir():
            if child.name in preserve:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in source_root.iterdir():
            destination = ROOT / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    print(f"Materialized {manifest['version']} with SHA-256 {digest}")


if __name__ == "__main__":
    main()
