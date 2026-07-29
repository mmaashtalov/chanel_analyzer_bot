import re
from urllib.parse import urlsplit, urlunsplit

from app.workspaces.models import WorkspaceItemType


class WorkspaceValidationError(ValueError):
    pass


def normalize_workspace_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not 2 <= len(name) <= 120:
        raise WorkspaceValidationError("Название Workspace должно содержать от 2 до 120 символов")
    return name


def normalize_item(item_type: WorkspaceItemType, value: str) -> str:
    raw = value.strip()
    if not raw:
        raise WorkspaceValidationError("Значение не может быть пустым")
    if item_type is WorkspaceItemType.CHANNEL:
        username = raw.lower().removeprefix("https://t.me/").lstrip("@").split("/")[0]
        if not re.fullmatch(r"[a-z0-9_]{5,32}", username):
            raise WorkspaceValidationError("Некорректный Telegram username")
        return username
    if item_type is WorkspaceItemType.DOMAIN:
        host = urlsplit(raw if "://" in raw else f"https://{raw}").hostname or ""
        host = host.lower().removeprefix("www.").rstrip(".")
        if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise WorkspaceValidationError("Некорректный домен")
        return host
    if item_type is WorkspaceItemType.RSS:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WorkspaceValidationError("RSS должен быть абсолютным http(s) URL")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    normalized = " ".join(raw.split())
    if len(normalized) > 512:
        raise WorkspaceValidationError("Значение слишком длинное")
    return normalized.casefold() if item_type is WorkspaceItemType.KEYWORD else normalized
