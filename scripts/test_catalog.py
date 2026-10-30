
import copy
import json
import unittest

from validate_catalog import CATALOG, validate


class CatalogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CATALOG.open(encoding="utf-8-sig") as file:
            cls.fixture = json.load(file)

    def example(self):
        return copy.deepcopy(self.fixture)

    def assert_rejected(self, data):
        self.assertTrue(validate(data))

    def test_valid_synthetic_catalog(self):
        self.assertEqual(validate(self.example()), [])

    def test_duplicate_resource(self):
        data = self.example()
        data["resources"].append(copy.deepcopy(data["resources"][0]))
        self.assert_rejected(data)

    def test_unknown_provider(self):
        data = self.example()
        data["resources"][0]["provider_id"] = "unknown-provider"
        self.assert_rejected(data)

    def test_unknown_skill(self):
        data = self.example()
        data["resources"][0]["skills"] = ["unknown-skill"]
        self.assert_rejected(data)

    def test_prerequisite_cycle(self):
        data = self.example()
        data["skills"][0]["prerequisites"] = ["css"]
        self.assert_rejected(data)

    def test_synthetic_verified_claim(self):
        data = self.example()
        data["resources"][0]["evidence"]["status"] = "verified"
        self.assert_rejected(data)

    def test_verified_claim_without_source(self):
        data = self.example()
        data["resources"][0]["synthetic"] = False
        data["resources"][0]["evidence"]["status"] = "verified"
        self.assert_rejected(data)

    def test_invalid_cost(self):
        data = self.example()
        data["resources"][0]["access_cost"] = "always-free"
        self.assert_rejected(data)

    def test_invalid_url(self):
        data = self.example()
        data["resources"][0]["url"] = "http://example.org/course"
        self.assert_rejected(data)

    def test_missing_contract_field(self):
        data = self.example()
        del data["resources"][0]["certificate_cost"]
        self.assert_rejected(data)

    def test_unauthorized_verified_provider(self):
        data = self.example()
        resource = data["resources"][0]
        resource["synthetic"] = False
        resource["evidence"] = {
            "status": "verified",
            "source_url": "https://example.org/evidence",
            "checked_at": "2026-10-30T09:00:00Z"
        }
        self.assert_rejected(data)

    def test_duplicate_skill(self):
        data = self.example()
        data["skills"].append(copy.deepcopy(data["skills"][0]))
        self.assert_rejected(data)


if __name__ == "__main__":
    unittest.main()