"""Strict, opt-in configuration for local account-data durability."""
import os
from collections.abc import Mapping
from pathlib import Path


class ConfigurationError(ValueError):
    """Unsafe or incomplete API storage configuration."""


def database_path_from_env(env: Mapping[str, str] | None = None) -> str:
    """Keep test/demo in-memory defaults, but fail closed when durability is required."""
    values = os.environ if env is None else env
    raw = values.get("NEXTRAIL_DB_PATH", ":memory:")
    durable = values.get("NEXTRAIL_REQUIRE_DURABLE_STORAGE", "false")
    if durable not in ("true", "false"):
        raise ConfigurationError("Durable storage flag must be 'true' or 'false'")
    if (not isinstance(raw, str) or not raw or raw != raw.strip()
            or len(raw) > 1024 or any(ord(char) < 32 or ord(char) == 127 for char in raw)):
        raise ConfigurationError("Invalid database path")
    if raw == ":memory:":
        if durable == "true":
            raise ConfigurationError("Durable storage required: configure a SQLite file path")
        return raw
    if raw.lower().startswith("file:"):
        raise ConfigurationError("SQLite URI paths are not supported")
    path = Path(raw)
    if not path.parent.is_dir() or path.is_dir() or path.is_symlink():
        raise ConfigurationError("Database parent must exist and file must not be a directory or symlink")
    return raw
