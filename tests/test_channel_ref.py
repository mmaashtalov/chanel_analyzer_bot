import pytest

from app.domain.models import ChannelRef


def test_channel_ref_normalizes_url() -> None:
    assert ChannelRef("https://t.me/example/").username == "example"


def test_channel_ref_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        ChannelRef("bad channel")
