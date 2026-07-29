from pathlib import Path

from app.demo.server import ASSET_DIR, HTML, build_summary


def test_demo_summary_exposes_verified_workflow() -> None:
    summary = build_summary()
    assert summary["workspace"]["id"] == "demo-workspace"
    assert summary["kpis"]["claims"] >= 5
    assert summary["kpis"]["primary_documents"] >= 2
    assert summary["kpis"]["integrity_hash"]
    assert len(summary["artifacts"]) == 6


def test_demo_assets_and_page_are_packaged() -> None:
    required = {
        "provenance.json",
        "provenance.pdf",
        "verification.json",
        "verification.pdf",
        "acquisition_request.json",
        "external_acquisition.json",
        "source_independence.json",
        "source_independence.pdf",
        "claim_timeline.json",
        "claim_timeline.pdf",
    }
    assert required <= {path.name for path in ASSET_DIR.iterdir() if path.is_file()}
    assert "Telegram Intelligence Platform" in HTML
    assert "/api/demo" in HTML


def test_demo_deployment_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docker-compose.demo.yml").is_file()
    assert (root / "render.yaml").is_file()
    assert (root / "docs" / "DEMO_RELEASE.md").is_file()


def test_demo_self_test_validates_every_required_asset() -> None:
    from app.demo.server import REQUIRED_ASSETS, run_self_test

    result = run_self_test()
    assert result["status"] == "ok"
    assert result["failed"] == 0
    checked_files = {item["name"] for item in result["checks"] if not item["name"].startswith("parse:")}
    assert checked_files == set(REQUIRED_ASSETS)
    assert all(item.get("sha256") for item in result["checks"] if item["name"] in REQUIRED_ASSETS)


def test_guided_demo_is_complete_and_ordered() -> None:
    summary = build_summary()
    steps = summary["guided_demo"]
    assert [item["step"] for item in steps] == list(range(1, 7))
    assert steps[-1]["title"] == "Claim Timeline"
    assert "пошаговый показ" in HTML
