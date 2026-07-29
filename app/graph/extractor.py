import re
from collections import defaultdict
from urllib.parse import urlparse

from app.domain.models import PostSnapshot
from app.graph.models import EntityMention, EntityType, ExtractedEntity

URL_RE = re.compile(r"https?://[^\s<>\]\[()]+", re.IGNORECASE)
TELEGRAM_RE = re.compile(r"(?<![\w])@([A-Za-z0-9_]{5,32})|https?://t\.me/([A-Za-z0-9_]{5,32})", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<!\w)#([\w\-]{2,64})", re.UNICODE)
DATE_RE = re.compile(
    r"\b(?:[0-3]?\d[./-][01]?\d(?:[./-](?:19|20)?\d{2})?|(?:19|20)\d{2})\b"
)

LOCATION_ALIASES = {
    "москва": "Москва",
    "москве": "Москва",
    "санкт-петербург": "Санкт-Петербург",
    "петербург": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "берлин": "Берлин",
    "киев": "Киев",
    "минск": "Минск",
    "алматы": "Алматы",
    "хельсинки": "Хельсинки",
}
ORGANIZATION_ALIASES = {
    "ростех": "Ростех",
    "минобороны": "Минобороны",
    "министерство обороны": "Минобороны",
    "оон": "ООН",
    "openai": "OpenAI",
    "telegram": "Telegram",
    "роскосмос": "Роскосмос",
}
EVENT_TERMS = {
    "выборы": "выборы",
    "саммит": "саммит",
    "форум": "форум",
    "конференция": "конференция",
    "релиз": "релиз",
    "запуск": "запуск",
    "учения": "учения",
}


def _entity(entity_type: EntityType, canonical: str, display: str, confidence: float, aliases=()) -> ExtractedEntity:
    return ExtractedEntity(entity_type, canonical.casefold(), display, confidence, tuple(aliases))


def extract_entities(post: PostSnapshot) -> tuple[EntityMention, ...]:
    text = post.text or ""
    found: dict[tuple[str, str], tuple[ExtractedEntity, int]] = {}

    def add(entity: ExtractedEntity) -> None:
        current = found.get(entity.key)
        found[entity.key] = (entity, (current[1] if current else 0) + 1)

    for match in URL_RE.finditer(text):
        raw = match.group(0).rstrip(".,;:!?")
        parsed = urlparse(raw)
        domain = (parsed.hostname or "").lower().removeprefix("www.")
        if domain:
            add(_entity(EntityType.DOMAIN, domain, domain, 0.99))
        add(_entity(EntityType.URL, raw, raw, 0.99))

    for match in TELEGRAM_RE.finditer(text):
        username = (match.group(1) or match.group(2)).lower()
        add(_entity(EntityType.TELEGRAM, username, f"@{username}", 0.99))

    for match in HASHTAG_RE.finditer(text):
        tag = match.group(1)
        add(_entity(EntityType.HASHTAG, tag, f"#{tag}", 0.99))

    for match in DATE_RE.finditer(text):
        value = match.group(0)
        add(_entity(EntityType.DATE, value, value, 0.86))

    lowered = text.casefold()
    for alias, display in LOCATION_ALIASES.items():
        occurrences = len(re.findall(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered))
        for _ in range(occurrences):
            add(_entity(EntityType.LOCATION, display, display, 0.88, (alias,)))

    for alias, display in ORGANIZATION_ALIASES.items():
        occurrences = len(re.findall(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered))
        for _ in range(occurrences):
            add(_entity(EntityType.ORGANIZATION, display, display, 0.9, (alias,)))

    for term, display in EVENT_TERMS.items():
        occurrences = len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", lowered))
        for _ in range(occurrences):
            add(_entity(EntityType.EVENT, display, display, 0.8))

    evidence = " ".join(text.split())[:280]
    return tuple(
        EntityMention(entity=entity, message_id=post.message_id, published_at=post.published_at, evidence_text=evidence, count=count)
        for entity, count in sorted(found.values(), key=lambda item: item[0].key)
    )


def extract_from_posts(posts: tuple[PostSnapshot, ...]) -> tuple[EntityMention, ...]:
    return tuple(mention for post in posts for mention in extract_entities(post))
