from __future__ import annotations

from app.sources.base import SourceAdapter
from app.sources.models import SourceType


class SourceRegistry:
    def __init__(self) -> None:
        self._adapters: dict[SourceType, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter, *, replace: bool = False) -> None:
        if adapter.source_type in self._adapters and not replace:
            raise ValueError(f"Adapter for {adapter.source_type.value} is already registered")
        self._adapters[adapter.source_type] = adapter

    def get(self, source_type: SourceType | str) -> SourceAdapter:
        resolved = SourceType(source_type)
        try:
            return self._adapters[resolved]
        except KeyError as exc:
            raise KeyError(f"No adapter registered for {resolved.value}") from exc

    def available(self) -> tuple[SourceType, ...]:
        return tuple(sorted(self._adapters, key=lambda item: item.value))

    async def health(self) -> dict[str, object]:
        results: dict[str, object] = {}
        for source_type, adapter in self._adapters.items():
            results[source_type.value] = await adapter.healthcheck()
        return results

    async def close(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()
