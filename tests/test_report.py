from pathlib import Path

from app.analytics.metrics import calculate_metrics
from app.domain.models import ChannelRef
from app.profiling import build_content_dna
from app.reports.pdf import build_quantitative_pdf
from tests.fakes import FakeProvider


async def test_report_is_generated(tmp_path: Path) -> None:
    snapshot = await FakeProvider().fetch_channel(ChannelRef("demo"))
    path = build_quantitative_pdf(
        snapshot, calculate_metrics(snapshot), tmp_path, "job", content_dna=build_content_dna(snapshot)
    )
    assert path.exists()
    assert path.stat().st_size > 10_000
