from __future__ import annotations

from app.db.repositories import ProfileRepository
from app.similarity.search import ProfileSearchResult, score_profiles


class FindSimilarProfilesUseCase:
    def __init__(self, repository: ProfileRepository) -> None:
        self._repository = repository

    async def execute(self, username: str, limit: int = 10) -> ProfileSearchResult:
        normalized = username.lower().lstrip("@").strip()
        if not normalized:
            raise ValueError("Укажите канал")
        limit = max(1, min(limit, 20))
        source = await self._repository.get_latest(normalized)
        if source is None:
            raise LookupError(f"Профиль @{normalized} не найден. Сначала выполните /analyze @{normalized}")

        # HNSW is used only for candidate generation; final ranking is explainable and component-aware.
        neighbours = await self._repository.nearest(source.profile.combined_vector, limit=limit * 3, exclude_username=normalized)
        scored = []
        for username_candidate, version, _vector_score in neighbours:
            candidate = await self._repository.get_version(username_candidate, version)
            if candidate is None:
                continue
            scored.append(score_profiles(source.profile, candidate.profile, candidate.version))
        scored.sort(key=lambda item: (item.overall_score, item.confidence), reverse=True)
        return ProfileSearchResult(normalized, source.version, tuple(scored[:limit]))
