from app.sources.base import SourceAdapter, SourceHealth, SourceRequest
from app.sources.deduplication import DuplicateGroup, deduplicate_exact, group_cross_source_duplicates
from app.sources.models import Attachment, SourceType, UnifiedDocument
from app.sources.registry import SourceRegistry

__all__ = [
    "Attachment",
    "DuplicateGroup",
    "SourceAdapter",
    "SourceHealth",
    "SourceRegistry",
    "SourceRequest",
    "SourceType",
    "UnifiedDocument",
    "deduplicate_exact",
    "group_cross_source_duplicates",
]
