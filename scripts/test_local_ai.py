import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from nextrail_ai import PlanningRequest, build_pathway, select_provider
from nextrail_ai.provider import (
    OLLAMA_ENDPOINT, OllamaPriorityProvider, ProviderConfigurationError, ProviderError,
)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.payload[:size]


class AIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())

    def request(self, **changes):
        fields = dict(career_goal="Frontend Developer", target_skill_ids=("css", "javascript"))
        fields.update(changes)
        return PlanningRequest(**fields)

    def test_default_is_offline(self):
        self.assertIsNone(select_provider({}))

    def test_cloud_provider_rejected(self):
        for name in ("bedrock", "openai", "https://example.com"):
            with self.subTest(name=name), self.assertRaises(ProviderConfigurationError):
                select_provider({"NEXTRAIL_AI_PROVIDER": name})

    def test_local_provider_configuration(self):
        provider = select_provider({"NEXTRAIL_AI_PROVIDER": "ollama"})
        self.assertEqual(provider.endpoint, OLLAMA_ENDPOINT)

    def test_external_endpoint_rejected(self):
        with self.assertRaises(ProviderConfigurationError):
            OllamaPriorityProvider(endpoint="http://example.com/api/chat")

    def test_invalid_model_rejected(self):
        with self.assertRaises(ProviderConfigurationError):
            OllamaPriorityProvider(model="bad/model")

    def test_timeout_rejected(self):
        with self.assertRaises(ProviderConfigurationError):
            OllamaPriorityProvider(timeout_seconds=100)

    def test_deterministic_prerequisites(self):
        result = build_pathway(self.catalog, self.request())
        ids = [m["skill_id"] for m in result["milestones"]]
        self.assertEqual(ids[0], "html")
        self.assertEqual(set(ids), {"html", "css", "javascript"})
        self.assertEqual(result["generation_mode"], "deterministic")

    def test_known_prerequisite_not_repeated(self):
        result = build_pathway(self.catalog, self.request(known_skill_ids=("html",)))
        self.assertEqual([m["skill_id"] for m in result["milestones"]], ["css", "javascript"])

    def test_no_unverified_courses_in_zero_budget(self):
        result = build_pathway(self.catalog, self.request())
        self.assertTrue(all(not m["resource_ids"] for m in result["milestones"]))

    def test_synthetic_never_recommended(self):
        result = build_pathway(self.catalog, self.request(zero_budget=False))
        self.assertTrue(all(not m["resource_ids"] for m in result["milestones"]))

    def test_unknown_target_rejected(self):
        with self.assertRaises(ValueError):
            build_pathway(self.catalog, self.request(target_skill_ids=("unlisted",)))

    def test_cyclic_graph_rejected(self):
        data = copy.deepcopy(self.catalog)
        data["skills"][0]["prerequisites"] = ["css"]
        with self.assertRaises(ValueError):
            build_pathway(data, self.request())

    def test_model_may_choose_only_ready_skill(self):
        class Pick:
            def choose(self, candidates, goal):
                self.assertNotCalled = None
                return "javascript"
        result = build_pathway(self.catalog, self.request(known_skill_ids=("html",)), Pick())
        self.assertEqual(result["milestones"][0]["skill_id"], "javascript")
        self.assertEqual(result["generation_mode"], "ai_assisted")

    def test_noneligible_model_output_falls_back(self):
        class Pick:
            def choose(self, candidates, goal):
                return "nonexistent"
        result = build_pathway(self.catalog, self.request(known_skill_ids=("html",)), Pick())
        self.assertEqual(result["milestones"][0]["skill_id"], "css")
        self.assertEqual(result["generation_mode"], "deterministic")

    def test_model_failure_falls_back(self):
        class Fails:
            def choose(self, candidates, goal):
                raise ProviderError("Offline")
        result = build_pathway(self.catalog, self.request(known_skill_ids=("html",)), Fails())
        self.assertEqual(result["generation_mode"], "deterministic")

    def test_request_validation(self):
        with self.assertRaises(ValueError):
            PlanningRequest(career_goal="", target_skill_ids=("html",))
        with self.assertRaises(ValueError):
            PlanningRequest(career_goal="Frontend", target_skill_ids=("html",), weekly_hours=0)

    def test_ollama_valid_response(self):
        payload = json.dumps({"done": True, "message": {"content": '{"prioritized_skill_id":"css"}'}}).encode()
        with patch("nextrail_ai.provider.build_opener") as opener:
            opener.return_value.open.return_value = Response(payload)
            result = OllamaPriorityProvider().choose(("css", "javascript"), "Frontend")
            self.assertEqual(result, "css")
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, OLLAMA_ENDPOINT)
            body = json.loads(request.data)
            self.assertEqual(body["stream"], False)
            self.assertEqual(body["keep_alive"], "0")

    def test_ollama_invented_id_rejected(self):
        payload = json.dumps({"done": True, "message": {"content": '{"prioritized_skill_id":"fake"}'}}).encode()
        with patch("nextrail_ai.provider.build_opener") as opener:
            opener.return_value.open.return_value = Response(payload)
            with self.assertRaises(ProviderError):
                OllamaPriorityProvider().choose(("css", "javascript"), "Frontend")

    def test_ollama_redirect_not_allowed(self):
        from nextrail_ai.provider import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://example.org"))

    def test_ollama_oversize_rejected(self):
        with patch("nextrail_ai.provider.build_opener") as opener:
            opener.return_value.open.return_value = Response(b"x" * 9000)
            with self.assertRaises(ProviderError):
                OllamaPriorityProvider().choose(("css", "javascript"), "Frontend")


if __name__ == "__main__":
    unittest.main()
