"""ASGI entry point; persistence is explicitly configured, never inferred."""
from .app import create_app
from .settings import database_path_from_env

app = create_app(database_path=database_path_from_env())
