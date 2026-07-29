from __future__ import annotations

import asyncio

import pytest

from app.workers.evidence_acquisition import EvidenceAcquisitionWorker


class Repo:
    def __init__(self):
        self.calls = 0

    async def list_due(self, limit=10):
        self.calls += 1
        return [{"id": "req-1"}] if self.calls == 1 else []


class Service:
    def __init__(self):
        self.ids = []

    async def run(self, request_id):
        self.ids.append(request_id)


@pytest.mark.asyncio
async def test_worker_processes_due_request_and_stops():
    repo = Repo()
    service = Service()
    worker = EvidenceAcquisitionWorker(service, repo, poll_seconds=30)
    await worker.start()
    await asyncio.sleep(0.02)
    await worker.stop()
    assert service.ids == ["req-1"]
