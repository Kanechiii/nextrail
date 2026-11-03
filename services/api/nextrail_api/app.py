"""Guest-first JSON API with verified bearer ownership boundaries."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Literal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from nextrail_ai import PlanningRequest
from nextrail_auth import AccountStore, AuthError
from nextrail_auth.preferences import AccountPreferencesStore, PreferenceConflict
from nextrail_discovery import discover_courses
from nextrail_orchestration import orchestrate
from nextrail_storage import LearningStore, StorageError, open_database
from nextrail_storage.idempotency import IdempotencyConflict, key_digest
from nextrail_storage.store import ProgressConflict
from nextrail_storage.workspace import WorkspaceError, build_workspace
from nextrail_storage.sync import account_sync_status
from .guards import FixedWindowLimiter
from .shared_limits import SQLiteFixedWindowLimiter
from .reliability import database_connection_ready
from .public_boundary import public_host, enforce_public_boundary
from .release import ReleaseError, load_reviewed_bundle


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictBody):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ResetRequest(StrictBody):
    email: str = Field(min_length=3, max_length=254)


class ResetConfirm(StrictBody):
    token: str
    new_password: str


class PasswordChange(StrictBody):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AccountDeletion(StrictBody):
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["DELETE MY ACCOUNT"]


class PlanInput(StrictBody):
    career_goal: str = Field(min_length=1, max_length=120)
    target_skill_ids: list[str] = Field(min_length=1, max_length=32)
    known_skill_ids: list[str] = Field(default_factory=list, max_length=128)
    weekly_hours: int = Field(default=5, ge=1, le=80)
    zero_budget: bool = True


class ProgressUpdate(StrictBody):
    status: str


class PreferencesUpdate(StrictBody):
    display_name: str | None = Field(default=None, max_length=80)
    career_goal: str | None = Field(default=None, max_length=120)
    weekly_hours: int | None = Field(default=None, ge=1, le=80)
    target_skill_ids: list[str] | None = Field(default=None, max_length=32)
    known_skill_ids: list[str] | None = Field(default=None, max_length=128)


def create_app(
    *, database_path=":memory:", catalog=None, reset_delivery=None,
    reviewed_catalog_path=None, reviewed_catalog_sha256=None, release_clock=None,
    shared_rate_limit_key=None, public_origin=None,
):
    public_dns_host = public_host(public_origin) if public_origin is not None else None
    if shared_rate_limit_key is not None and database_path == ":memory:":
        raise ValueError("Shared request limits require durable SQLite storage")
    if (reviewed_catalog_path is None) != (reviewed_catalog_sha256 is None):
        raise ReleaseError("Reviewed catalog path and SHA-256 must be configured together")
    if catalog is not None and reviewed_catalog_path is not None:
        raise ReleaseError("Cannot combine injected catalog and reviewed release activation")
    clock = release_clock if release_clock is not None else lambda: datetime.now(timezone.utc)
    if not callable(clock):
        raise ReleaseError("A callable release clock is required")
    release = (
        load_reviewed_bundle(
            reviewed_catalog_path, reviewed_catalog_sha256, now=clock()
        )
        if reviewed_catalog_path is not None else None
    )
    root = Path(__file__).resolve().parents[3]
    if release is not None:
        catalog = release.catalog
    elif catalog is None:
        catalog = json.loads((root / "data/catalog.sample.json").read_text(encoding="utf-8"))

    @asynccontextmanager
    async def lifespan(app):
        connection = open_database(database_path)
        app.state.db = connection
        app.state.auth = AccountStore(connection)
        app.state.preferences = AccountPreferencesStore(connection)
        app.state.learning = LearningStore(connection)
        app.state.limiter = (
            SQLiteFixedWindowLimiter(connection, shared_rate_limit_key)
            if shared_rate_limit_key is not None else FixedWindowLimiter()
        )
        try:
            yield
        finally:
            connection.close()

    app = FastAPI(title="Nextrail API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        # Database diagnostics may contain private paths, table names and data.
        return JSONResponse(
            status_code=503,
            content={"detail": "Database temporarily unavailable",
                     "error": {"code": "DATABASE_UNAVAILABLE", "retryable": True}},
            headers={"Retry-After": "3", "Cache-Control": "no-store"},
        )

    if public_dns_host is not None:
        @app.middleware("http")
        async def strict_public_boundary(request: Request, call_next):
            return await enforce_public_boundary(
                request, call_next, origin=public_origin, host=public_dns_host
            )

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    def active_catalog():
        if release is None:
            return catalog
        try:
            return release.current_catalog(now=clock())
        except ReleaseError:
            raise HTTPException(503, "Reviewed catalog unavailable")

    def auth():
        return app.state.auth

    def learning():
        return app.state.learning

    async def current_owner(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
        try:
            return auth().session_owner(authorization[7:])
        except AuthError:
            raise HTTPException(401, "Invalid session", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        active_catalog()
        if not database_connection_ready(app.state.db):
            raise HTTPException(503, "Database unavailable")
        return {
            "status": "ready",
            "catalog_mode": "reviewed_snapshot" if release is not None else "sample",
            "reviewed_course_count": (
                release.reviewed_course_count if release is not None else 0
            ),
        }

    @app.get("/v1/courses")
    async def courses(request: Request, query: str = "", provider_id: str | None = None,
                skill_id: str | None = None, access_cost: str | None = None,
                certificate_cost: str | None = None, limit: int = 20):
        app.state.limiter.enforce(request, "courses", 120)
        try:
            return {"items": discover_courses(
                active_catalog(), query=query, provider_id=provider_id, skill_id=skill_id,
                access_cost=access_cost, certificate_cost=certificate_cost, limit=limit
            )}
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "Invalid discovery request")

    def planning(input: PlanInput):
        try:
            request = PlanningRequest(
                career_goal=input.career_goal, target_skill_ids=tuple(input.target_skill_ids),
                known_skill_ids=tuple(input.known_skill_ids),
                weekly_hours=input.weekly_hours, zero_budget=input.zero_budget
            )
            return orchestrate(
                active_catalog(), request, env={},
                verified_free_resource_ids=(
                    release.verified_free_resource_ids if release is not None
                    else frozenset()
                ),
            ).pathway
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "Invalid pathway request")

    @app.get("/v1/skills")
    async def skills():
        return {"items": [
            {"id": skill["id"], "name": skill["name"],
             "prerequisites": skill["prerequisites"]}
            for skill in active_catalog()["skills"]
        ]}

    @app.post("/v1/pathways/preview")
    async def preview(input: PlanInput, request: Request):
        app.state.limiter.enforce(request, "pathway_preview", 30)
        return planning(input)

    @app.post("/v1/auth/register", status_code=201)
    async def register(input: Credentials, request: Request):
        app.state.limiter.enforce(request, "register", 6)
        try:
            auth().register(input.email, input.password)
            return {"created": True}
        except AuthError:
            raise HTTPException(400, "Account could not be created")

    @app.post("/v1/auth/login")
    async def login(input: Credentials, request: Request):
        app.state.limiter.enforce(request, "login", 12)
        try:
            return auth().login(input.email, input.password)
        except AuthError:
            raise HTTPException(401, "Invalid credentials")

    @app.post("/v1/auth/logout")
    async def logout(authorization: str | None = Header(default=None),
               owner: str = Depends(current_owner)):
        try:
            auth().revoke_session(authorization[7:])
            return {"revoked": True}
        except AuthError:
            raise HTTPException(401, "Invalid session")

    @app.get("/v1/me")
    async def me(owner: str = Depends(current_owner)):
        return auth().account(owner)

    @app.get("/v1/me/sessions")
    async def sessions(
        authorization: str = Header(),
        owner: str = Depends(current_owner),
    ):
        return {"active_count": auth().active_sessions(authorization[7:])}

    @app.post("/v1/me/sessions/revoke-others")
    async def revoke_other_sessions(
        request: Request, authorization: str = Header(),
        owner: str = Depends(current_owner),
    ):
        app.state.limiter.enforce(request, "revoke_other_sessions", 12)
        return {"revoked_count": auth().revoke_other_sessions(authorization[7:])}

    @app.post("/v1/me/password")
    async def change_password(
        body: PasswordChange, request: Request,
        authorization: str = Header(),
        owner: str = Depends(current_owner),
    ):
        app.state.limiter.enforce(request, "change_password", 5)
        try:
            return {
                "updated": auth().change_password(
                    authorization[7:], body.current_password, body.new_password
                ),
                "sessions_revoked": True,
            }
        except AuthError:
            raise HTTPException(400, "Invalid password change credentials")

    @app.get("/v1/me/export")
    async def export_account(
        request: Request, authorization: str = Header(),
        owner: str = Depends(current_owner),
    ):
        app.state.limiter.enforce(request, "account_export", 6)
        try:
            return auth().export_account(authorization[7:])
        except AuthError:
            raise HTTPException(413, "Account export requires an offline bulk process")

    @app.delete("/v1/me/account")
    async def delete_account(
        body: AccountDeletion, request: Request,
        authorization: str = Header(),
        owner: str = Depends(current_owner),
    ):
        app.state.limiter.enforce(request, "account_delete", 3)
        try:
            return {"deleted": auth().delete_account(
                authorization[7:], body.current_password
            )}
        except AuthError:
            raise HTTPException(400, "Invalid account deletion credentials")

    @app.get("/v1/me/preferences")
    async def get_preferences(response: Response, owner: str = Depends(current_owner)):
        preferences = app.state.preferences.get(owner)
        response.headers["ETag"] = '"' + app.state.preferences.revision(owner) + '"'
        response.headers["Cache-Control"] = "no-store"
        return preferences

    @app.patch("/v1/me/preferences")
    async def update_preferences(
        body: PreferencesUpdate, response: Response,
        owner: str = Depends(current_owner),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ):
        expected = None
        if if_match is not None:
            if not re.fullmatch(r'"[0-9a-f]{64}"', if_match):
                raise HTTPException(422, "Invalid preference revision")
            expected = if_match[1:-1]
        try:
            result = app.state.preferences.update(
                owner, body.model_dump(exclude_unset=True),
                allowed_skill_ids={skill["id"] for skill in active_catalog()["skills"]},
                expected_revision=expected,
            )
            response.headers["ETag"] = '"' + app.state.preferences.revision(owner) + '"'
            response.headers["Cache-Control"] = "no-store"
            return result
        except PreferenceConflict:
            raise HTTPException(
                409, "Preferences changed in another session. Reload before saving."
            )
        except (AuthError, StorageError):
            raise HTTPException(422, "Invalid account preferences")

    @app.get("/v1/me/sync/status")
    async def account_sync_readiness(
        response: Response, owner: str = Depends(current_owner),
    ):
        # A read-only visibility endpoint, not automatic remote synchronization.
        status = account_sync_status(app.state.db, owner)
        response.headers["ETag"] = '"' + status["state_revision"] + '"'
        response.headers["Cache-Control"] = "no-store"
        return status

    @app.get("/v1/me/overview")
    async def account_overview(owner: str = Depends(current_owner)):
        db = app.state.db
        count = db.execute(
            "SELECT count(*) FROM learning_pathways WHERE owner_id=?", (owner,)
        ).fetchone()[0]
        bookmarks = db.execute(
            "SELECT count(*) FROM saved_courses WHERE owner_id=?", (owner,)
        ).fetchone()[0]
        recent = learning().list_pathways(owner, limit=1)
        latest_id = recent[0]["id"] if recent else None
        progress = learning().get_progress(owner, latest_id) if latest_id else None
        return {
            "saved_pathway_count": count,
            "saved_course_count": bookmarks,
            "latest_pathway_id": latest_id,
            "completed_milestones": progress["completed"] if progress else 0,
            "total_milestones": progress["total"] if progress else 0,
        }

    @app.post("/v1/auth/password-reset/request")
    async def reset_request(input: ResetRequest, request: Request):
        app.state.limiter.enforce(request, "password_reset", 5)
        auth().request_password_reset(input.email, delivery=reset_delivery)
        return {"accepted": True}

    @app.post("/v1/auth/password-reset/confirm")
    async def reset_confirm(input: ResetConfirm, request: Request):
        app.state.limiter.enforce(request, "password_reset_confirm", 10)
        try:
            auth().confirm_password_reset(input.token, input.new_password)
            return {"updated": True}
        except AuthError:
            raise HTTPException(400, "Invalid or expired reset credentials")

    @app.post("/v1/me/pathways", status_code=201)
    async def save_pathway(
        input: PlanInput,
        owner: str = Depends(current_owner),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        request_digest = None
        if idempotency_key is not None:
            request_digest = hashlib.sha256(json.dumps(
                input.model_dump(), sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            try:
                key_digest(owner, idempotency_key, request_digest)
                previous = learning().idempotent_pathway(owner, idempotency_key, request_digest)
                if previous:
                    return previous
            except IdempotencyConflict:
                raise HTTPException(409, "Idempotency key already used for different inputs")
            except StorageError:
                raise HTTPException(422, "Invalid idempotency key")
        result = planning(input)
        try:
            identifier = learning().save_pathway(
                owner, result, idempotency_key=idempotency_key, request_digest=request_digest,
            )
            return {"id": identifier, "pathway": learning().get_pathway(owner, identifier)}
        except IdempotencyConflict:
            raise HTTPException(409, "Idempotency key already used for different inputs")
        except StorageError:
            raise HTTPException(422, "Invalid pathway request")

    @app.get("/v1/me/pathways")
    async def list_pathways(owner: str = Depends(current_owner)):
        return {"items": learning().list_pathways(owner)}

    @app.get("/v1/me/learning/summary")
    async def learning_summary(
        limit: int = Query(default=20, ge=1, le=50),
        after_id: str | None = Query(default=None, min_length=1, max_length=64),
        owner: str = Depends(current_owner),
    ):
        try:
            return learning().list_pathway_page(owner, limit=limit, after_id=after_id)
        except KeyError:
            raise HTTPException(404, "Pathway page cursor not found")
        except StorageError:
            raise HTTPException(422, "Invalid learning summary request")

    @app.get("/v1/me/pathways/{pathway_id}/workspace")
    async def pathway_workspace(pathway_id: str, owner: str = Depends(current_owner)):
        try:
            snapshot = learning().get_pathway(owner, pathway_id)
            progress = learning().get_progress(owner, pathway_id)
            return build_workspace(pathway_id, snapshot, progress, active_catalog())
        except KeyError:
            raise HTTPException(404, "Pathway not found")
        except (WorkspaceError, StorageError):
            raise HTTPException(422, "Saved pathway cannot be projected")

    @app.delete("/v1/me/pathways/{pathway_id}")
    async def delete_pathway(pathway_id: str, owner: str = Depends(current_owner)):
        try:
            return {"deleted": learning().delete_pathway(owner, pathway_id)}
        except KeyError:
            raise HTTPException(404, "Pathway not found")
        except StorageError:
            raise HTTPException(422, "Invalid pathway deletion request")

    @app.get("/v1/me/pathways/{pathway_id}")
    async def get_pathway(pathway_id: str, owner: str = Depends(current_owner)):
        try:
            return learning().get_pathway(owner, pathway_id)
        except KeyError:
            raise HTTPException(404, "Pathway not found")

    @app.get("/v1/me/pathways/{pathway_id}/progress")
    async def get_progress(pathway_id: str, response: Response,
                           owner: str = Depends(current_owner)):
        try:
            current = learning().get_progress(owner, pathway_id)
            response.headers["ETag"] = '"' + current["revision"] + '"'
            response.headers["Cache-Control"] = "no-store"
            return current
        except KeyError:
            raise HTTPException(404, "Pathway not found")

    @app.put("/v1/me/pathways/{pathway_id}/progress/{skill_id}")
    async def update_progress(pathway_id: str, skill_id: str, body: ProgressUpdate,
                        owner: str = Depends(current_owner),
                        if_match: str | None = Header(default=None, alias="If-Match")):
        expected = None
        if if_match is not None:
            if not re.fullmatch(r'"[0-9a-f]{64}"', if_match):
                raise HTTPException(422, "Invalid progress revision")
            expected = if_match[1:-1]
        try:
            return {"changed": learning().set_progress(
                owner, pathway_id, skill_id, body.status, expected_revision=expected,
            )}
        except ProgressConflict:
            raise HTTPException(409, "Progress changed in another view. Reload before updating.")
        except KeyError:
            raise HTTPException(404, "Pathway not found")
        except StorageError:
            raise HTTPException(422, "Invalid progress update")

    @app.get("/v1/me/courses")
    async def saved_courses(owner: str = Depends(current_owner)):
        return {"resource_ids": learning().list_saved_courses(owner)}

    @app.put("/v1/me/courses/{resource_id}")
    async def save_course(resource_id: str, owner: str = Depends(current_owner)):
        allowed = {r["id"] for r in active_catalog()["resources"] if not r["synthetic"]}
        if resource_id not in allowed:
            raise HTTPException(404, "Course not found")
        return {"saved": learning().save_course(owner, resource_id)}

    @app.delete("/v1/me/courses/{resource_id}")
    async def unsave_course(resource_id: str, owner: str = Depends(current_owner)):
        try:
            return {"removed": learning().unsave_course(owner, resource_id)}
        except StorageError:
            raise HTTPException(422, "Invalid resource")

    @app.get("/v1/me/audit")
    async def audit(after_event_id: int = 0, limit: int = 50,
              owner: str = Depends(current_owner)):
        try:
            return {"events": learning().audit_history(
                owner, after_event_id=after_event_id, limit=limit
            )}
        except StorageError:
            raise HTTPException(422, "Invalid audit cursor")

    return app
