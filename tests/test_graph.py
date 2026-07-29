from datetime import UTC, datetime

from app.domain.models import ChannelSnapshot, PostSnapshot
from app.graph import EntityType, build_graph_snapshot, extract_entities


def post(text: str, message_id: int = 1) -> PostSnapshot:
    return PostSnapshot(message_id, datetime(2026, 7, 1, 12, tzinfo=UTC), text, views=100)


def test_extracts_deterministic_entities():
    mentions = extract_entities(post("Ростех в Москве: https://ria.ru/x @ExampleChan #БПЛА саммит 2026"))
    keys = {(m.entity.entity_type, m.entity.canonical_name) for m in mentions}
    assert (EntityType.ORGANIZATION, "ростех") in keys
    assert (EntityType.LOCATION, "москва") in keys
    assert (EntityType.DOMAIN, "ria.ru") in keys
    assert (EntityType.TELEGRAM, "examplechan") in keys
    assert (EntityType.HASHTAG, "бпла") in keys
    assert (EntityType.EVENT, "саммит") in keys


def test_deduplicates_entity_inside_post_and_counts_mentions():
    mentions = extract_entities(post("Ростех и снова Ростех"))
    item = next(m for m in mentions if m.entity.entity_type == EntityType.ORGANIZATION)
    assert item.count == 2


def test_builds_channel_relationships_with_evidence():
    snapshot = ChannelSnapshot(
        username="source", title="Source", subscribers=10, collected_at=datetime.now(UTC),
        posts=(post("Ростех #БПЛА", 10), post("Ростех https://ria.ru/a", 11)),
    )
    graph = build_graph_snapshot(snapshot, 3)
    rostec = next(r for r in graph.relationships if r.target.display_name == "Ростех")
    assert rostec.weight == 2
    assert rostec.evidence_message_ids == (10, 11)
    assert graph.profile_version == 3


def test_graph_snapshot_is_serializable():
    snapshot = ChannelSnapshot(
        username="source", title="Source", subscribers=10, collected_at=datetime.now(UTC),
        posts=(post("OpenAI в Берлине #AI", 1),),
    )
    payload = build_graph_snapshot(snapshot, 1).to_dict()
    assert payload["channel_username"] == "source"
    assert payload["entities"]
    assert payload["relationships"]


def test_relation_types_follow_entity_semantics():
    snapshot = ChannelSnapshot(
        username="source", title="Source", subscribers=10, collected_at=datetime.now(UTC),
        posts=(post("@other #tag https://example.com/x", 1),),
    )
    graph = build_graph_snapshot(snapshot, 1)
    relation_by_type = {r.target.entity_type.value: r.relation_type.value for r in graph.relationships}
    assert relation_by_type["telegram"] == "references"
    assert relation_by_type["hashtag"] == "hashtagged_with"
    assert relation_by_type["domain"] == "links_to"
