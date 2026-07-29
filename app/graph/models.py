from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class EntityType(StrEnum):
    TELEGRAM = "telegram"
    DOMAIN = "domain"
    URL = "url"
    HASHTAG = "hashtag"
    ORGANIZATION = "organization"
    PERSON = "person"
    LOCATION = "location"
    DATE = "date"
    EVENT = "event"


class RelationType(StrEnum):
    MENTIONS = "mentions"
    LINKS_TO = "links_to"
    HASHTAGGED_WITH = "hashtagged_with"
    REFERENCES = "references"
    CO_OCCURS_WITH = "co_occurs_with"


@dataclass(slots=True, frozen=True)
class ExtractedEntity:
    entity_type: EntityType
    canonical_name: str
    display_name: str
    confidence: float
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> tuple[str, str]:
        return self.entity_type.value, self.canonical_name


@dataclass(slots=True, frozen=True)
class EntityMention:
    entity: ExtractedEntity
    message_id: int
    published_at: datetime
    evidence_text: str
    count: int = 1


@dataclass(slots=True, frozen=True)
class GraphRelationship:
    source_type: str
    source_name: str
    target: ExtractedEntity
    relation_type: RelationType
    weight: int
    confidence: float
    evidence_message_ids: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class GraphSnapshot:
    channel_username: str
    profile_version: int
    collected_at: datetime
    entities: tuple[ExtractedEntity, ...]
    mentions: tuple[EntityMention, ...]
    relationships: tuple[GraphRelationship, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "channel_username": self.channel_username,
            "profile_version": self.profile_version,
            "collected_at": self.collected_at.isoformat(),
            "entities": [
                {
                    "type": entity.entity_type.value,
                    "canonical_name": entity.canonical_name,
                    "display_name": entity.display_name,
                    "confidence": entity.confidence,
                    "aliases": list(entity.aliases),
                }
                for entity in self.entities
            ],
            "relationships": [
                {
                    "source": relationship.source_name,
                    "target": relationship.target.display_name,
                    "target_type": relationship.target.entity_type.value,
                    "relation": relationship.relation_type.value,
                    "weight": relationship.weight,
                    "confidence": relationship.confidence,
                    "evidence_message_ids": list(relationship.evidence_message_ids),
                }
                for relationship in self.relationships
            ],
        }
