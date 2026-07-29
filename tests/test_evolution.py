from datetime import UTC, datetime

import pytest

from app.evolution import ChangeSeverity, compare_profile_versions
from app.profiles.models import IntelligenceProfile


def profile(*, username="demo", posts=80, confidence=0.9, metrics=None, dna=None, style=None, temporal=None, structural=None):
    metrics = metrics or {
        "posts_count": posts,
        "posts_per_day": 2.0,
        "mean_views": 1000.0,
        "mean_post_length": 500.0,
        "top_terms": [["технологии", 10], ["бизнес", 8], ["рынок", 7]],
    }
    dna = dna or {
        "lexical_diversity": 0.5,
        "mean_sentence_length": 12.0,
        "mean_paragraphs": 3.0,
        "uppercase_ratio": 0.01,
        "emoji_rate": 0.1,
        "question_rate": 0.05,
        "exclamation_rate": 0.05,
        "ellipsis_rate": 0.01,
        "dash_rate": 0.1,
        "link_rate": 0.2,
        "direct_address_rate": 0.1,
        "traits": [],
    }
    style = style or (0.1,) * 16
    temporal = temporal or (0.1,) * 168
    structural = structural or (0.1,) * 8
    narrative = (0.1,) * 64
    return IntelligenceProfile(
        username=username,
        title="Demo",
        subscribers=1000,
        collected_at=datetime.now(UTC),
        source_post_count=posts,
        methodology_version="test",
        style_vector=tuple(style),
        temporal_vector=tuple(temporal),
        structural_vector=tuple(structural),
        narrative_vector=narrative,
        combined_vector=tuple(style) + tuple(temporal) + tuple(structural) + narrative,
        metrics=metrics,
        content_dna=dna,
        confidence=confidence,
    )


def test_rejects_different_channels():
    with pytest.raises(ValueError):
        compare_profile_versions(profile(username="a"), profile(username="b"), 1, 2)


def test_detects_activity_growth():
    old = profile(metrics={"posts_count": 50, "posts_per_day": 1.0, "mean_views": 1000, "mean_post_length": 500, "top_terms": ["рынок"]})
    new = profile(metrics={"posts_count": 100, "posts_per_day": 2.0, "mean_views": 1000, "mean_post_length": 500, "top_terms": ["рынок"]})
    report = compare_profile_versions(old, new, 1, 2)
    assert any(e.event_type == "metric_shift" and e.delta == 1.0 for e in report.events)


def test_ignores_small_metric_noise():
    old = profile()
    metrics = dict(old.metrics)
    metrics["mean_views"] = 1090.0
    report = compare_profile_versions(old, profile(metrics=metrics), 1, 2)
    assert not any(e.title.startswith("Средний охват") for e in report.events)


def test_detects_content_dna_change():
    old = profile()
    dna = dict(old.content_dna)
    dna["emoji_rate"] = 0.45
    report = compare_profile_versions(old, profile(dna=dna), 1, 2)
    assert any(e.event_type == "content_dna_shift" for e in report.events)


def test_detects_narrative_shift_as_high_or_critical():
    old = profile(metrics={"top_terms": ["рынок", "бизнес", "финансы"], "posts_count": 80})
    new = profile(metrics={"top_terms": ["бпла", "оборона", "дроны"], "posts_count": 80})
    report = compare_profile_versions(old, new, 1, 2)
    event = next(e for e in report.events if e.event_type == "narrative_shift")
    assert event.severity in {ChangeSeverity.HIGH, ChangeSeverity.CRITICAL}


def test_detects_temporal_vector_shift():
    old = profile()
    new = profile(temporal=(0.9,) * 168)
    report = compare_profile_versions(old, new, 1, 2)
    assert any(e.category == "temporal" for e in report.events)


def test_serialization_and_summary():
    old = profile()
    new = profile(structural=(0.8,) * 8)
    report = compare_profile_versions(old, new, 3, 4)
    payload = report.to_dict()
    assert payload["from_version"] == 3
    assert payload["to_version"] == 4
    assert payload["executive_summary"]
    assert payload["events"][0]["severity"] in {"critical", "high", "medium", "low"}
