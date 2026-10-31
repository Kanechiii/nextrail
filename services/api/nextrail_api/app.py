"""Guest-first JSON API with verified bearer ownership boundaries."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from nextrail_ai import PlanningRequest
from nextrail_auth import AccountStore, AuthError
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_discovery import discover_courses
from nextrail_orchestration import orchestrate
from nextrail_storage import LearningStore, StorageError, open_database
from .guards import FixedWindowLimiter


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


def create_app(*, database_path=":memory:", catalog=None, reset_delivery=None):
    root = Path(__file__).resolve().parents[3]
    if catalog is None:
        catalog = json.loads((root / "data/catalog.sample.json").read_text(encoding="utf-8"))

    @asynccontextmanager
    async def lifespan(app):
        connection = open_database(database_path)
        app.state.db = connection
        app.state.auth = AccountStore(connection)
        app.state.preferences = AccountPreferencesStore(connection)
        app.state.learning = LearningStore(connection)
        try:
            yield
        finally:
            connection.close()

    app = FastAPI(title="Nextrail API", version="0.1.0", lifespan=lifespan)
    limiter = FixedWindowLimiter()

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

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

    @app.get("/v1/courses")
    async def courses(request: Request, query: str = "", provider_id: str | None = None,
                skill_id: str | None = None, access_cost: str | None = None,
                certificate_cost: str | None = None, limit: int = 20):
        limiter.enforce(request, "courses", 120)
        try:
            return {"items": discover_courses(
                catalog, query=query, provider_id=provider_id, skill_id=skill_id,
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
            return orchestrate(catalog, request, env={}).pathway
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "Invalid pathway request")

    @app.get("/v1/skills")
    async def skills():
        return {"items": [
            {"id": skill["id"], "name": skill["name"],
             "prerequisites": skill["prerequisites"]}
            for skill in catalog["skills"]
        ]}

    @app.post("/v1/pathways/preview")
    async def preview(input: PlanInput, request: Request):
        limiter.enforce(request, "pathway_preview", 30)
        return planning(input)

    @app.post("/v1/auth/register", status_code=201)
    async def register(input: Credentials, request: Request):
        limiter.enforce(request, "register", 6)
        try:
            auth().register(input.email, input.password)
            return {"created": True}
        except AuthError:
            raise HTTPException(400, "Account could not be created")

    @app.post("/v1/auth/login")
    async def login(input: Credentials, request: Request):
        limiter.enforce(request, "login", 12)
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

    @app.get("/v1/me/preferences")
    async def get_preferences(owner: str = Depends(current_owner)):
        return app.state.preferences.get(owner)

    @app.patch("/v1/me/preferences")
    async def update_preferences(
        body: PreferencesUpdate, owner: str = Depends(current_owner)
    ):
        try:
            return app.state.preferences.update(
                owner, body.model_dump(exclude_unset=True),
                allowed_skill_ids={skill["id"] for skill in catalog["skills"]},
            )
        except (AuthError, StorageError):
            raise HTTPException(422, "Invalid account preferences")

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
        limiter.enforce(request, "password_reset", 5)
        auth().request_password_reset(input.email, delivery=reset_delivery)
        return {"accepted": True}

    @app.post("/v1/auth/password-reset/confirm")
    async def reset_confirm(input: ResetConfirm, request: Request):
        limiter.enforce(request, "password_reset_confirm", 10)
        try:
            auth().confirm_password_reset(input.token, input.new_password)
            return {"updated": True}
        except AuthError:
            raise HTTPException(400, "Invalid or expired reset credentials")

    @app.post("/v1/me/pathways", status_code=201)
    async def save_pathway(input: PlanInput, owner: str = Depends(current_owner)):
        result = planning(input)
        return {"id": learning().save_pathway(owner, result), "pathway": result}

    @app.get("/v1/me/pathways")
    async def list_pathways(owner: str = Depends(current_owner)):
        return {"items": learning().list_pathways(owner)}

    @app.get("/v1/me/pathways/{pathway_id}")
    async def get_pathway(pathway_id: str, owner: str = Depends(current_owner)):
        try:
            return learning().get_pathway(owner, pathway_id)
        except KeyError:
            raise HTTPException(404, "Pathway not found")

    @app.get("/v1/me/pathways/{pathway_id}/progress")
    async def get_progress(pathway_id: str, owner: str = Depends(current_owner)):
        try:
            return learning().get_progress(owner, pathway_id)
        except KeyError:
            raise HTTPException(404, "Pathway not found")

    @app.put("/v1/me/pathways/{pathway_id}/progress/{skill_id}")
    async def update_progress(pathway_id: str, skill_id: str, body: ProgressUpdate,
                        owner: str = Depends(current_owner)):
        try:
            return {"changed": learning().set_progress(owner, pathway_id, skill_id, body.status)}
        except KeyError:
            raise HTTPException(404, "Pathway not found")
        except StorageError:
            raise HTTPException(422, "Invalid progress update")

    @app.get("/v1/me/courses")
    async def saved_courses(owner: str = Depends(current_owner)):
        return {"resource_ids": learning().list_saved_courses(owner)}

    @app.put("/v1/me/courses/{resource_id}")
    async def save_course(resource_id: str, owner: str = Depends(current_owner)):
        allowed = {r["id"] for r in catalog["resources"] if not r["synthetic"]}
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
