import json
from datetime import UTC, datetime
from pathlib import Path

from app.analytics.metrics import calculate_metrics
from app.application.analyze_channel import AnalyzeChannelUseCase
from app.db.source_collection_repository import CollectionStats
from app.domain.models import ChannelRef, ChannelSnapshot, PostSnapshot
from app.evidence.engine import build_channel_analysis_provenance
from app.evidence.models import EvidenceKind
from app.profiling import build_content_dna
from app.reports.pdf import build_provenance_json, build_quantitative_pdf
from app.sources.adapters.telegram import documents_from_snapshot
from app.sources.models import SourceType


def _snapshot() -> ChannelSnapshot:
    return ChannelSnapshot(
        username="demo",
        title="Demo channel",
        subscribers=1000,
        collected_at=datetime(2026, 1, 4, 12, tzinfo=UTC),
        posts=(
            PostSnapshot(
                message_id=1,
                published_at=datetime(2026, 1, 1, 10, tzinfo=UTC),
                text="Первый аналитический пост #demo",
                views=100,
                reactions=10,
                forwards=2,
                url="https://t.me/demo/1",
            ),
            PostSnapshot(
                message_id=2,
                published_at=datetime(2026, 1, 2, 10, tzinfo=UTC),
                text="Второй аналитический пост с ссылкой https://example.org",
                views=200,
                reactions=20,
                forwards=3,
                url="https://t.me/demo/2",
            ),
        ),
    )


def _bundle(job_id: str):
    snapshot = _snapshot()
    documents = documents_from_snapshot(snapshot)
    return build_channel_analysis_provenance(
        snapshot,
        documents,
        calculate_metrics(snapshot),
        build_content_dna(snapshot),
        job_id=job_id,
        document_record_ids={"1": "record-1", "2": "record-2"},
        collection_stats={"collected": 2, "accepted": 2, "duplicates": 0},
        workspace_ids=("workspace-1",),
    )


def test_channel_provenance_is_deterministic_across_job_ids() -> None:
    first = _bundle("job-one")
    second = _bundle("job-two")

    assert first.bundle_id == second.bundle_id
    assert first.integrity_hash == second.integrity_hash
    assert first.metadata["analysis_job_id"] == "job-one"
    assert second.metadata["analysis_job_id"] == "job-two"
    assert first.metadata["workspace_ids"] == ["workspace-1"]


def test_channel_provenance_links_claims_to_snapshot_calculation_and_documents() -> None:
    bundle = _bundle("job")
    evidence = {item.evidence_id: item for item in bundle.evidence}
    primary = [item for item in bundle.evidence if item.kind is EvidenceKind.PRIMARY_DOCUMENT]

    assert len(primary) == 2
    assert {item.document_id for item in primary} == {"record-1", "record-2"}
    assert all(item.excerpt for item in primary)
    assert all(set(claim.evidence_ids) <= set(evidence) for claim in bundle.claims)
    assert any(item.kind is EvidenceKind.SNAPSHOT for item in bundle.evidence)
    assert any(item.kind is EvidenceKind.COMPUTATION for item in bundle.evidence)
    assert bundle.completeness == 1.0


def test_empty_input_produces_explicit_limitation_instead_of_unbound_state() -> None:
    snapshot = ChannelSnapshot("empty", "Empty", None, datetime(2026, 1, 4, tzinfo=UTC), ())
    bundle = build_channel_analysis_provenance(
        snapshot,
        (),
        calculate_metrics(snapshot),
        build_content_dna(snapshot),
        job_id="job",
    )

    assert bundle.claims
    assert any("Первичные документы отсутствуют" in item for item in bundle.limitations)
    assert bundle.metadata["input_document_count"] == 0


def test_provenance_json_is_a_complete_serialized_bundle(tmp_path: Path) -> None:
    bundle = _bundle("job")
    path = build_provenance_json(bundle, tmp_path, "demo", "job")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.exists()
    assert payload["bundle_id"] == bundle.bundle_id
    assert payload["integrity_hash"] == bundle.integrity_hash
    assert payload["metadata"]["input_document_count"] == 2
    assert len(payload["claims"]) == len(bundle.claims)


def test_quantitative_pdf_contains_evidence_first_appendix(tmp_path: Path) -> None:
    snapshot = _snapshot()
    bundle = _bundle("job")
    path = build_quantitative_pdf(
        snapshot,
        calculate_metrics(snapshot),
        tmp_path,
        "job",
        content_dna=build_content_dna(snapshot),
        provenance=bundle,
    )

    assert path.exists()
    assert path.stat().st_size > 20_000


class _FakeProvider:
    def __init__(self, snapshot: ChannelSnapshot) -> None:
        self.snapshot = snapshot
        self.fetches = 0

    async def fetch_channel(self, channel, date_from=None, date_to=None):
        self.fetches += 1
        return self.snapshot

    async def close(self) -> None:
        return None


class _FakeJobs:
    def __init__(self) -> None:
        self.progress = []
        self.saved = None
        self.failed = None

    async def create(self, user_id, channel_username):
        return "job-1"

    async def update_progress(self, job_id, status, step, text):
        self.progress.append((step, text))

    async def save_result(self, job_id, snapshot, payload, report_path):
        self.saved = (job_id, snapshot, payload, report_path)

    async def fail(self, job_id, message):
        self.failed = (job_id, message)


class _FakeTelegramAdapter:
    source_type = SourceType.TELEGRAM
    name = "fake-telegram"
    version = "test"


class _FakeCollection:
    def __init__(self) -> None:
        self.documents = ()

    async def persist(self, adapter, source_id, documents):
        self.documents = documents
        return CollectionStats(
            "telegram",
            source_id,
            len(documents),
            len(documents),
            0,
            tuple(f"record-{item.document_id}" for item in documents),
        )


class _FakeEvidence:
    def __init__(self) -> None:
        self.bundles = []
        self.links = []

    async def save(self, bundle):
        self.bundles.append(bundle)
        return bundle.bundle_id

    async def link_to_workspace(self, bundle_id, workspace_id, source_item, link_type="channel_analysis"):
        self.links.append((bundle_id, workspace_id, source_item, link_type))
        return True


class _FakeWorkspace:
    def __init__(self, workspace_id: str) -> None:
        self.id = workspace_id


class _FakeWorkspaces:
    async def list_for_channel(self, user_id, channel_username):
        return [_FakeWorkspace("workspace-1")]


async def test_analyze_uses_one_snapshot_for_registry_and_evidence(tmp_path: Path, monkeypatch) -> None:
    provider = _FakeProvider(_snapshot())
    jobs = _FakeJobs()
    collection = _FakeCollection()
    evidence = _FakeEvidence()

    def fake_pdf(snapshot, metrics, output_dir, job_id, **kwargs):
        path = output_dir / "report.pdf"
        path.write_bytes(b"pdf")
        return path

    monkeypatch.setattr("app.application.analyze_channel.build_quantitative_pdf", fake_pdf)
    use_case = AnalyzeChannelUseCase(
        provider=provider,
        repository=jobs,
        report_output_dir=tmp_path,
        lookback_days=30,
        source_adapter=_FakeTelegramAdapter(),
        source_collection_repository=collection,
        evidence_repository=evidence,
        workspace_repository=_FakeWorkspaces(),
    )

    result = await use_case.execute(42, ChannelRef("@demo"))

    assert provider.fetches == 1
    assert tuple(item.document_id for item in collection.documents) == ("1", "2")
    assert result.provenance_path.exists()
    assert evidence.bundles == [result.provenance]
    assert evidence.links == [(
        result.provenance.bundle_id,
        "workspace-1",
        "demo",
        "channel_analysis",
    )]
    assert jobs.saved is not None
    assert jobs.saved[2]["provenance"]["bundle_id"] == result.provenance.bundle_id
    assert jobs.saved[2]["provenance"]["workspace_ids"] == ["workspace-1"]
    assert jobs.failed is None
