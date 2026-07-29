from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.external_acquisition import ControlledExternalAcquisition, ExternalAcquisitionLimits
from app.db.source_collection_repository import CollectionStats
from app.sources import SourceRegistry, SourceType, UnifiedDocument
from app.sources.base import SourceHealth


class FakeAdapter:
    source_type = SourceType.RSS
    name = "fake-rss"
    version = "1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def collect(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("temporary feed failure")
        return (
            UnifiedDocument(
                source_type=SourceType.RSS,
                source_id=request.source_id,
                document_id="doc-1",
                title="Ростех испытания",
                body="Ростех сообщил о новом этапе испытаний БПЛА",
                published_at=datetime.now(UTC),
            ),
        )

    async def healthcheck(self):
        return SourceHealth(True, self.name, self.version)

    async def close(self):
        return None


class FakeCollectionRepository:
    def __init__(self) -> None:
        self.persisted = 0
        self.failures = 0

    async def persist(self, adapter, source_id, documents):
        self.persisted += len(documents)
        return CollectionStats(adapter.source_type.value, source_id, len(documents), len(documents), 0)

    async def record_failure(self, adapter, source_id, error):
        self.failures += 1


class FakeRequestRepository:
    def __init__(self, *, local_count: int = 0) -> None:
        self.local_count = local_count
        self.row = {
            "id": "req-1",
            "status": "queued",
            "attempts": 0,
            "max_attempts": 3,
            "source_plan": [{"source_type": "rss", "source_id": "https://example.org/rss"}],
        }
        self.collection_summary = None
        self.link_calls = []

    async def get(self, request_id):
        return dict(self.row)

    async def get_owned(self, request_id, user_id):
        return dict(self.row)

    async def count_local_candidates(self, request_id):
        return self.local_count

    async def begin_collection(self, request_id):
        self.row["status"] = "collecting"
        self.row["attempts"] += 1
        return dict(self.row)

    async def record_collection(self, request_id, *, collected, summary):
        self.collection_summary = summary
        return dict(self.row)

    async def link_from_store(self, request_id, *, increment_attempt, stage):
        self.link_calls.append((increment_attempt, stage))
        if increment_attempt:
            self.row["attempts"] += 1
        self.row["status"] = "resolved" if stage == "local_first" or self.collection_summary["accepted"] else "failed"
        return {**self.row, "documents_collected": self.collection_summary["accepted"] if self.collection_summary else 1,
                "documents_linked": 1 if self.row["status"] == "resolved" else 0}

    async def schedule_retry(self, request_id, *, delay_seconds, error):
        self.row["status"] = "retry_wait"
        self.row["delay"] = delay_seconds
        self.row["last_error"] = error
        return dict(self.row)


@pytest.mark.asyncio
async def test_external_acquisition_is_local_first():
    requests = FakeRequestRepository(local_count=1)
    adapter = FakeAdapter()
    registry = SourceRegistry()
    registry.register(adapter)
    service = ControlledExternalAcquisition(
        registry, requests, FakeCollectionRepository(), ExternalAcquisitionLimits()
    )

    result = await service.run("req-1")

    assert result["status"] == "resolved"
    assert adapter.calls == 0
    assert requests.link_calls == [(True, "local_first")]


@pytest.mark.asyncio
async def test_external_acquisition_collects_and_links():
    requests = FakeRequestRepository(local_count=0)
    collections = FakeCollectionRepository()
    adapter = FakeAdapter()
    registry = SourceRegistry()
    registry.register(adapter)
    service = ControlledExternalAcquisition(
        registry, requests, collections, ExternalAcquisitionLimits(max_documents_per_source=5)
    )

    result = await service.run("req-1")

    assert result["status"] == "resolved"
    assert adapter.calls == 1
    assert collections.persisted == 1
    assert requests.link_calls == [(False, "external_collection")]


@pytest.mark.asyncio
async def test_transient_source_failure_uses_exponential_backoff():
    requests = FakeRequestRepository(local_count=0)
    collections = FakeCollectionRepository()
    registry = SourceRegistry()
    registry.register(FakeAdapter(fail=True))
    service = ControlledExternalAcquisition(
        registry,
        requests,
        collections,
        ExternalAcquisitionLimits(backoff_seconds=60),
    )

    result = await service.run("req-1")

    assert result["status"] == "retry_wait"
    assert result["delay"] == 60
    assert collections.failures == 1
