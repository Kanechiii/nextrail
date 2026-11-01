"""Phase 35 cross-workspace API journeys on isolated in-memory synthetic fixtures.

This is an in-process API acceptance suite, not an automated browser audit or
a production availability, email delivery, or identity verification test.
"""
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_api import create_app

PASSWORD = "synthetic-password-123456"
PLAN = {
    "career_goal": "Frontend developer",
    "target_skill_ids": ["css", "javascript"],
    "known_skill_ids": [],
    "weekly_hours": 6,
    "zero_budget": True,
}


class CrossWorkspaceJourneyTests(unittest.TestCase):
    def setUp(self):
        self.ctx = TestClient(create_app())
        self.client = self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def register_login(self, name):
        email = name + "@example.org"
        self.assertEqual(self.client.post(
            "/v1/auth/register", json={"email": email, "password": PASSWORD}
        ).status_code, 201)
        response = self.client.post(
            "/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_guest_discovers_and_previews_without_account(self):
        skills = self.client.get("/v1/skills")
        self.assertEqual(skills.status_code, 200)
        self.assertIn("html", {row["id"] for row in skills.json()["items"]})
        courses = self.client.get("/v1/courses")
        self.assertEqual(courses.status_code, 200)
        self.assertEqual(courses.json()["items"], [])
        preview = self.client.post("/v1/pathways/preview", json=PLAN)
        self.assertEqual(preview.status_code, 200)
        path = preview.json()
        self.assertEqual(path["career_goal"], PLAN["career_goal"])
        self.assertEqual(path["generation_mode"], "deterministic")
        self.assertEqual(path["weekly_hours"], PLAN["weekly_hours"])
        self.assertGreaterEqual(len(path["milestones"]), 2)
        self.assertEqual(self.client.get("/v1/me/preferences").status_code, 401)

    def test_guest_plan_requires_explicit_authenticated_save(self):
        preview = self.client.post("/v1/pathways/preview", json=PLAN)
        self.assertEqual(preview.status_code, 200)
        # Guest preview itself creates nothing in the private account store.
        first = self.register_login("first")
        self.assertEqual(self.client.get("/v1/me/overview", headers=first).json()[
            "saved_pathway_count"
        ], 0)
        saved = self.client.post("/v1/me/pathways", headers=first, json=PLAN)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["pathway"]["milestones"], preview.json()["milestones"])
        self.assertEqual(
            self.client.get("/v1/me/overview", headers=first).json()["saved_pathway_count"],
            1,
        )
        self.assertEqual(
            self.client.get("/v1/me/pathways", headers=first).json()["items"][0]["id"],
            saved.json()["id"],
        )

    def test_preferences_progress_dashboard_and_logout_journey(self):
        owner = self.register_login("learner")
        defaults = self.client.get("/v1/me/preferences", headers=owner).json()
        self.assertFalse(defaults["onboarding_completed"])
        self.assertEqual(defaults["target_skill_ids"], [])
        updated = self.client.patch("/v1/me/preferences", headers=owner, json={
            "display_name": "Learner",
            "career_goal": "Frontend developer",
            "weekly_hours": 6,
            "target_skill_ids": ["css", "javascript"],
            "known_skill_ids": ["html"],
        })
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["onboarding_completed"])
        self.assertEqual(updated.json()["known_skill_ids"], ["html"])
        self.assertEqual(self.client.get("/v1/me/preferences", headers=owner).json()[
            "career_goal"
        ], "Frontend developer")
        saved = self.client.post("/v1/me/pathways", headers=owner, json=PLAN)
        self.assertEqual(saved.status_code, 201)
        route_id = saved.json()["id"]
        milestone = saved.json()["pathway"]["milestones"][0]["skill_id"]
        result = self.client.put(
            f"/v1/me/pathways/{route_id}/progress/{milestone}",
            headers=owner, json={"status": "completed"},
        )
        self.assertEqual(result.status_code, 200)
        progress = self.client.get(
            f"/v1/me/pathways/{route_id}/progress", headers=owner
        )
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()["completed"], 1)
        overview = self.client.get("/v1/me/overview", headers=owner).json()
        self.assertEqual(overview["saved_pathway_count"], 1)
        self.assertEqual(overview["completed_milestones"], 1)
        self.assertEqual(overview["latest_pathway_id"], route_id)
        self.assertEqual(self.client.post(
            "/v1/auth/logout", headers=owner
        ).status_code, 200)
        self.assertEqual(self.client.get(
            "/v1/me/preferences", headers=owner
        ).status_code, 401)
        self.assertEqual(self.client.get(
            f"/v1/me/pathways/{route_id}/progress", headers=owner
        ).status_code, 401)
        self.assertEqual(self.client.get("/v1/courses").status_code, 200)

    def test_no_cross_account_access_or_fake_provider_save(self):
        a = self.register_login("account-a")
        b = self.register_login("account-b")
        saved = self.client.post("/v1/me/pathways", headers=a, json=PLAN)
        self.assertEqual(saved.status_code, 201)
        route_id = saved.json()["id"]
        self.assertEqual(self.client.get(
            f"/v1/me/pathways/{route_id}", headers=b
        ).status_code, 404)
        self.assertEqual(self.client.get(
            f"/v1/me/pathways/{route_id}/progress", headers=b
        ).status_code, 404)
        self.assertEqual(self.client.put(
            f"/v1/me/pathways/{route_id}/progress/html",
            json={"status": "completed"}, headers=b,
        ).status_code, 404)
        self.assertEqual(self.client.get("/v1/me/overview", headers=b).json()[
            "saved_pathway_count"
        ], 0)
        self.assertEqual(self.client.patch(
            "/v1/me/preferences", headers=b, json={"display_name": "Second"}
        ).status_code, 200)
        self.assertEqual(self.client.get("/v1/me/preferences", headers=a).json()[
            "display_name"
        ], "")
        self.assertEqual(self.client.put(
            "/v1/me/courses/example-html-course", headers=a
        ).status_code, 404)
        self.assertEqual(self.client.get(
            "/v1/me/courses", headers=a
        ).json()["resource_ids"], [])

    def test_bad_inputs_do_not_mutate_account_state(self):
        headers = self.register_login("input-check")
        self.assertEqual(self.client.patch("/v1/me/preferences", headers=headers,
            json={"target_skill_ids": ["not-in-catalog"]}).status_code, 422)
        self.assertEqual(self.client.patch("/v1/me/preferences", headers=headers,
            json={"weekly_hours": 100}).status_code, 422)
        self.assertEqual(self.client.get("/v1/me/preferences", headers=headers).json()[
            "target_skill_ids"
        ], [])
        self.assertEqual(self.client.post("/v1/me/pathways", headers=headers,
            json={"career_goal": "Frontend", "target_skill_ids": ["not-in-catalog"]}
        ).status_code, 422)
        self.assertEqual(self.client.get("/v1/me/overview", headers=headers).json()[
            "saved_pathway_count"
        ], 0)


if __name__ == "__main__":
    unittest.main()
