from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class WorkspaceItemType(StrEnum):
    CHANNEL = "channel"
    RSS = "rss"
    DOMAIN = "domain"
    ENTITY = "entity"
    KEYWORD = "keyword"

    @classmethod
    def parse(cls, value: str) -> "WorkspaceItemType":
        aliases = {"канал": cls.CHANNEL, "лента": cls.RSS, "домен": cls.DOMAIN,
                   "сущность": cls.ENTITY, "ключ": cls.KEYWORD, "keyword": cls.KEYWORD}
        normalized = value.casefold().strip()
        try:
            return cls(normalized)
        except ValueError:
            if normalized in aliases:
                return aliases[normalized]
            raise ValueError("Тип должен быть channel, rss, domain, entity или keyword")


@dataclass(slots=True, frozen=True)
class WorkspaceItem:
    id: str
    item_type: WorkspaceItemType
    value: str
    normalized_value: str
    label: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class Workspace:
    id: str
    telegram_user_id: int
    name: str
    description: str | None
    is_active: bool
    items: tuple[WorkspaceItem, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def counts(self) -> dict[str, int]:
        result = {kind.value: 0 for kind in WorkspaceItemType}
        for item in self.items:
            result[item.item_type.value] += 1
        return result
