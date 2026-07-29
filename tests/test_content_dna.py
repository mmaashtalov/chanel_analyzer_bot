from app.domain.models import ChannelRef
from app.profiling import build_content_dna
from tests.fakes import FakeProvider


async def test_content_dna_has_evidence_and_serializes() -> None:
    snapshot = await FakeProvider().fetch_channel(ChannelRef("demo"))
    profile = build_content_dna(snapshot, target_sample_size=50)
    payload = profile.to_dict()

    assert profile.sample_size == 50
    assert 0 <= profile.confidence <= 1
    assert len(profile.traits) >= 5
    assert payload["methodology_version"] == "content-dna-v1"
    assert payload["traits"][0]["name"]


async def test_content_dna_does_not_claim_identity() -> None:
    snapshot = await FakeProvider().fetch_channel(ChannelRef("demo"))
    profile = build_content_dna(snapshot)
    assert any("не личность" in item for item in profile.limitations)
