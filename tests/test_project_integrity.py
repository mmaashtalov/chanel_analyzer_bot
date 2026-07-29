import json
from pathlib import Path

from scripts.generate_manifest import build_manifest


def test_manifest_matches_current_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = build_manifest()
    actual = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    assert actual == expected
    assert actual["tests"] == f"{actual['test_count']}/{actual['test_count']}"
    assert actual["test_count"] >= 98


def test_docker_runtime_and_demo_commands_are_separate() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    demo_compose = (root / "docker-compose.demo.yml").read_text(encoding="utf-8")
    assert "COPY . /app" in dockerfile
    assert 'CMD ["/usr/local/bin/product-entrypoint"]' in dockerfile
    assert 'command: ["python", "-m", "app.entrypoint"]' in demo_compose
