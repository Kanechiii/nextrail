"""ASGI entry point; database path is configuration only."""
import os
from .app import create_app

app = create_app(database_path=os.environ.get("NEXTRAIL_DB_PATH", ":memory:"))
