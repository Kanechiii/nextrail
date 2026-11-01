"""ASGI entry point; durability and reviewed catalog activation are opt-in."""
from .app import create_app
from .settings import database_path_from_env, reviewed_catalog_from_env, shared_rate_limit_key_from_env, public_origin_from_env

_reviewed_path, _reviewed_pin = reviewed_catalog_from_env()
app = create_app(
    database_path=database_path_from_env(),
    reviewed_catalog_path=_reviewed_path,
    reviewed_catalog_sha256=_reviewed_pin,
    shared_rate_limit_key=shared_rate_limit_key_from_env(),
    public_origin=public_origin_from_env(),
)
