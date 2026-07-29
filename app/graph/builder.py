from collections import defaultdict
from itertools import combinations

from app.domain.models import ChannelSnapshot
from app.graph.extractor import extract_from_posts
from app.graph.models import EntityType, GraphRelationship, GraphSnapshot, RelationType


def _relation_for(entity_type: EntityType) -> RelationType:
    if entity_type in {EntityType.DOMAIN, EntityType.URL, EntityType.TELEGRAM}:
        return RelationType.LINKS_TO if entity_type != EntityType.TELEGRAM else RelationType.REFERENCES
    if entity_type == EntityType.HASHTAG:
        return RelationType.HASHTAGGED_WITH
    return RelationType.MENTIONS


def build_graph_snapshot(snapshot: ChannelSnapshot, profile_version: int) -> GraphSnapshot:
    mentions = extract_from_posts(snapshot.posts)
    entities = {mention.entity.key: mention.entity for mention in mentions}
    grouped: dict[tuple[str, str, str], list] = defaultdict(list)
    for mention in mentions:
        relation = _relation_for(mention.entity.entity_type)
        grouped[(mention.entity.entity_type.value, mention.entity.canonical_name, relation.value)].append(mention)

    relationships: list[GraphRelationship] = []
    for (_, _, relation_value), items in grouped.items():
        evidence = tuple(sorted({item.message_id for item in items}))
        weight = sum(item.count for item in items)
        target = items[0].entity
        relationships.append(
            GraphRelationship(
                source_type="channel",
                source_name=snapshot.username,
                target=target,
                relation_type=RelationType(relation_value),
                weight=weight,
                confidence=min(0.99, target.confidence * min(1.0, 0.65 + 0.08 * len(evidence))),
                evidence_message_ids=evidence,
            )
        )

    return GraphSnapshot(
        channel_username=snapshot.username.lower().lstrip("@"),
        profile_version=profile_version,
        collected_at=snapshot.collected_at,
        entities=tuple(sorted(entities.values(), key=lambda entity: entity.key)),
        mentions=mentions,
        relationships=tuple(sorted(relationships, key=lambda rel: (-rel.weight, rel.target.key))),
    )
