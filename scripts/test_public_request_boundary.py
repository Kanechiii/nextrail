"""Offline public request boundary tests; no deployment or network access."""
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api import create_app
from nextrail_api.public_boundary import PublicBoundaryError, public_host
from nextrail_api.settings import ConfigurationError, public_origin_from_env

ORIGIN = "https://learn.example.org"
KEY = bytes(range(32)).hex()


class PublicOriginConfigurationTests(unittest.TestCase):
    def test_valid_public_origin(self):
        self.assertEqual(public_host(ORIGIN), "learn.example.org")
        self.assertIsNone(public_origin_from_env({}))

    def test_invalid_origin_values_fail_closed(self):
        for value in (
            "", "http://learn.example.org", "https://Learn.example.org",
            "https://learn.example.org/", "https://learn.example.org/path",
            "https://learn.example.org?token=1", "https://learn.example.org#here",
            "https://user:pass@learn.example.org", "https://learn.example.org:443",
            "https://127.0.0.1", "https://localhost", "https://other.org.evil:8443",
            "https://learn.example.org\n", "https://learn.example.org ",
            "https://[::1]", "https://learn.example.org@", 1, None,
        ):
            with self.subTest(value=value), self.assertRaises(PublicBoundaryError):
                public_host(value)

    def test_public_mode_requires_explicit_durability_and_key(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "accounts.sqlite")
            settings = {
                "NEXTRAIL_DB_PATH": db, "NEXTRAIL_PUBLIC_ORIGIN": ORIGIN,
            }
            with self.assertRaises(ConfigurationError):
                public_origin_from_env(settings)
            settings["NEXTRAIL_REQUIRE_DURABLE_STORAGE"] = "true"
            with self.assertRaises(ConfigurationError):
                public_origin_from_env(settings)
            settings["NEXTRAIL_RATE_LIMIT_HMAC_KEY"] = KEY
            self.assertEqual(public_origin_from_env(settings), ORIGIN)

    def test_public_mode_rejects_in_memory_or_bad_origin(self):
        settings = {
            "NEXTRAIL_PUBLIC_ORIGIN": ORIGIN,
            "NEXTRAIL_REQUIRE_DURABLE_STORAGE": "true",
            "NEXTRAIL_RATE_LIMIT_HMAC_KEY": KEY,
        }
        with self.assertRaises(ConfigurationError):
            public_origin_from_env(settings)
        with tempfile.TemporaryDirectory() as temp:
            settings["NEXTRAIL_DB_PATH"] = str(Path(temp) / "data.sqlite")
            settings["NEXTRAIL_PUBLIC_ORIGIN"] = "http://learn.example.org"
            with self.assertRaises(ConfigurationError):
                public_origin_from_env(settings)

    def test_local_default_stays_unchanged(self):
        with TestClient(create_app()) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("strict-transport-security", response.headers)
            self.assertEqual(client.get("/v1/courses").status_code, 200)


class PublicRequestBoundaryTests(unittest.TestCase):
    def test_valid_host_https_and_same_origin_are_accepted(self):
        with TestClient(create_app(public_origin=ORIGIN), base_url=ORIGIN) as client:
            response = client.get("/ready")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["strict-transport-security"], "max-age=31536000")
            self.assertEqual(response.headers["cache-control"], "no-store")
            response = client.post(
                "/v1/pathways/preview",
                headers={"Origin": ORIGIN},
                json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
            )
            self.assertEqual(response.status_code, 200)

    def test_untrusted_host_fails_without_redirect(self):
        with TestClient(create_app(public_origin=ORIGIN), base_url=ORIGIN) as client:
            response = client.get("/health", headers={
                "Host": "attacker.example.net",
                "X-Forwarded-Host": "learn.example.org",
            })
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"detail": "Public request boundary rejected"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn("location", response.headers)

    def test_scheme_spoofing_does_not_bypass_https(self):
        with TestClient(
            create_app(public_origin=ORIGIN), base_url="http://learn.example.org",
        ) as client:
            response = client.get("/health", headers={
                "X-Forwarded-Proto": "https",
            })
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_cross_origin_posts_rejected_even_on_trusted_host(self):
        with TestClient(create_app(public_origin=ORIGIN), base_url=ORIGIN) as client:
            response = client.post(
                "/v1/pathways/preview",
                headers={"Origin": "https://attacker.example.net"},
                json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"detail": "Public request boundary rejected"})

    def test_origin_null_and_subdomain_are_not_whitelisted(self):
        with TestClient(create_app(public_origin=ORIGIN), base_url=ORIGIN) as client:
            for origin in ("null", "https://sub.learn.example.org",
                           "https://learn.example.org.evil.org", "http://learn.example.org"):
                with self.subTest(origin=origin):
                    self.assertEqual(client.get("/health", headers={
                        "Origin": origin,
                    }).status_code, 403)

    def test_bearer_auth_remains_protected(self):
        with TestClient(create_app(public_origin=ORIGIN), base_url=ORIGIN) as client:
            self.assertEqual(client.get("/v1/me").status_code, 401)
            self.assertEqual(client.get("/v1/courses").status_code, 200)


if __name__ == "__main__":
    unittest.main()
