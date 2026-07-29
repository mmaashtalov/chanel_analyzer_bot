from app.domain.models import ChannelRef
from app.profiling.sampling import build_stratified_sample
from tests.fakes import FakeProvider


async def test_sampling_is_bounded_and_reproducible() -> None:
    snapshot = await FakeProvider().fetch_channel(ChannelRef("demo"))
    first = build_stratified_sample(snapshot.posts, target_size=30)
    second = build_stratified_sample(snapshot.posts, target_size=30)
    assert len(first) == 30
    assert [item.post.message_id for item in first] == [item.post.message_id for item in second]
    assert all(item.reasons for item in first)
