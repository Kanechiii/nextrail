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


def reviewed_catalog_from_env(env: Mapping[str, str] | None = None):
    """Require both explicit snapshot path and operator-reviewed SHA-256 pin."""
    import re

    values = os.environ if env is None else env
    path = values.get("NEXTRAIL_REVIEWED_CATALOG_PATH")
    sha = values.get("NEXTRAIL_REVIEWED_CATALOG_SHA256")
    if path is None and sha is None:
        return None, None
    if not isinstance(path, str) or not isinstance(sha, str):
        raise ConfigurationError("Reviewed catalog path and SHA-256 must be configured together")
    if (not path or path != path.strip() or len(path) > 1024
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ConfigurationError("Invalid reviewed catalog path")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ConfigurationError("Reviewed catalog requires a lowercase SHA-256 pin")
    location = Path(path)
    if location.is_symlink() or not location.is_file() or location.suffix != ".json":
        raise ConfigurationError("Reviewed catalog must be an existing regular JSON file")
    return path, sha


def shared_rate_limit_key_from_env(env: Mapping[str, str] | None = None) -> bytes | None:
    """Opt in to shared request protection only with a strong operator key."""
    import re

    values = os.environ if env is None else env
    raw = values.get("NEXTRAIL_RATE_LIMIT_HMAC_KEY")
    if raw is None:
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise ConfigurationError("Shared rate limiting requires a 32-byte lowercase hex key")
    if database_path_from_env(values) == ":memory:":
        raise ConfigurationError("Shared request limits require durable SQLite storage")
    return bytes.fromhex(raw)


def public_origin_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """Public mode is opt-in and requires durable storage and shared throttling."""
    from .public_boundary import PublicBoundaryError, public_host

    values = os.environ if env is None else env
    origin = values.get("NEXTRAIL_PUBLIC_ORIGIN")
    if origin is None:
        return None
    try:
        public_host(origin)
    except PublicBoundaryError as exc:
        raise ConfigurationError("Invalid canonical HTTPS public origin") from exc
    if values.get("NEXTRAIL_REQUIRE_DURABLE_STORAGE") != "true":
        raise ConfigurationError("Public request boundary requires explicit durable storage")
    if database_path_from_env(values) == ":memory:":
        raise ConfigurationError("Public request boundary requires a file-backed database")
    if shared_rate_limit_key_from_env(values) is None:
        raise ConfigurationError("Public request boundary requires shared rate limiting")
    return origin
