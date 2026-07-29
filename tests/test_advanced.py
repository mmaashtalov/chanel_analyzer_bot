import asyncio

from app.analytics.advanced import calculate_advanced
from app.domain.models import ChannelRef
from tests.fakes import FakeProvider


def test_advanced_analytics_has_summary_and_semantics():
    snapshot = asyncio.run(FakeProvider().fetch_channel(ChannelRef("demo_channel")))
    result = calculate_advanced(snapshot)
    assert result.executive_summary
    assert result.top_terms
    assert result.q75_views is not None
    assert result.best_hour is not None
