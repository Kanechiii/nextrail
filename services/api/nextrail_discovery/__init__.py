"""Guest-first, offline source normalization and course discovery."""

from .adapters import assemble_catalog, normalize_manual, normalize_feed
from .contracts import SourceContractError, load_registry
from .search import discover_courses

__all__ = [
    "SourceContractError",
    "assemble_catalog",
    "discover_courses",
    "load_registry",
    "normalize_feed",
    "normalize_manual",
]
