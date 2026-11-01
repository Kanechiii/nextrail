"""Phase 36 loopback-only demo preflight negative tests with synthetic fixtures."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_local_demo import DemoSafetyError, evaluate_local_demo


class LocalDemoSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / "apps/web").mkdir(parents=True)
        self.names = [
            "catalog.sample.json", "sources.sample.json",
            "provider-authorizations.sample.json", "pre-release-acceptance.sample.json",
        ]
        for name in self.names:
            shutil.copyfile(ROOT / "data" / name, self.root / "data" / name)
        shutil.copyfile(
            ROOT / "apps/web/vite.config.ts",
            self.root / "apps/web/vite.config.ts",
        )

    def rewrite(self, name, transform):
        path = self.root / "data" / name
        obj = json.loads(path.read_text(encoding="utf-8"))
        transform(obj)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def evaluate(self, env=None):
        return evaluate_local_demo(self.root, env={} if env is None else env)

    def test_synthetic_loopback_demo_is_not_production_approval(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "local_demo_only")
        self.assertEqual(result["localhost_frontend"], "http://127.0.0.1:5173")
        self.assertEqual(result["localhost_api"], "http://127.0.0.1:8000")
        self.assertGreater(result["synthetic_courses"], 0)
        self.assertEqual(result["real_courses_enabled"], 0)
        self.assertEqual(result["provider_grants_enabled"], 0)
        self.assertEqual(result["production_acceptance"], "blocked")
        self.assertFalse(result["deployment_performed"])
        self.assertFalse(result["production_approval"])

    def test_does_not_pass_when_real_course_is_inserted(self):
        self.rewrite("catalog.sample.json", lambda obj: obj["resources"][0].update(
            {"synthetic": False}
        ))
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_does_not_pass_when_provider_or_source_is_approved(self):
        self.rewrite("catalog.sample.json", lambda obj: obj["providers"][0].update(
            {"authorization": "approved"}
        ))
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

        shutil.copyfile(ROOT/"data/catalog.sample.json", self.root/"data/catalog.sample.json")
        self.rewrite("sources.sample.json", lambda obj: obj["sources"][0].update(
            {"authorization": "approved"}
        ))
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_does_not_pass_when_authorization_ledger_has_grants(self):
        self.rewrite("provider-authorizations.sample.json", lambda obj: obj.update(
            {"authorizations": [{"status": "approved"}]}
        ))
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_does_not_pass_when_production_approval_is_added(self):
        self.rewrite("pre-release-acceptance.sample.json", lambda obj:
            obj["gates"]["manual_release_approval"].update({"status": "approved"}))
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_does_not_pass_for_nonloopback_web_host(self):
        path = self.root/"apps/web/vite.config.ts"
        path.write_text(
            path.read_text(encoding="utf-8").replace("host: '127.0.0.1'", "host: '0.0.0.0'"),
            encoding="utf-8",
        )
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_does_not_pass_for_untrusted_proxy_target(self):
        path = self.root/"apps/web/vite.config.ts"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "http://127.0.0.1:8000", "https://external.example.com"
            ),
            encoding="utf-8",
        )
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_public_or_paid_configuration_rejected(self):
        for key, value in [
            ("NEXTRAIL_PUBLIC_ORIGIN", "https://production.example.com"),
            ("NEXTRAIL_DB_PATH", "data/live.sqlite"),
            ("NEXTRAIL_REVIEWED_CATALOG_PATH", "data/real.json"),
            ("NEXTRAIL_RATE_LIMIT_HMAC_KEY", "sensitive-placeholder"),
            ("VITE_API_BASE_URL", "https://remote.example.com"),
        ]:
            with self.subTest(key=key), self.assertRaises(DemoSafetyError):
                self.evaluate({key: value})

    def test_missing_and_duplicate_fixture_rejected(self):
        file = self.root/"data/catalog.sample.json"
        file.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}',
                        encoding="utf-8")
        with self.assertRaises(DemoSafetyError):
            self.evaluate()
        file.unlink()
        with self.assertRaises(DemoSafetyError):
            self.evaluate()

    def test_ui_quality_sample_must_remain_blocked_if_present(self):
        path = self.root/"data/ui-quality-acceptance.sample.json"
        original = ROOT/"data/ui-quality-acceptance.sample.json"
        if original.exists():
            shutil.copyfile(original,path)
        else:
            path.write_text(json.dumps({"schema_version":"1.0.0","scenarios":{}}))
        with self.assertRaises(DemoSafetyError):
            self.evaluate() if not original.exists() else self._tamper_and_evaluate(path)

    def _tamper_and_evaluate(self,path):
        doc=json.loads(path.read_text(encoding="utf-8"))
        next(iter(doc["scenarios"].values()))["status"]="approved"
        path.write_text(json.dumps(doc),encoding="utf-8")
        return self.evaluate()

    def test_cli_reports_local_only_no_network(self):
        result=subprocess.run([
            sys.executable,str(ROOT/"scripts/verify_local_demo.py"),
            "--root",str(self.root),
        ],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('"status": "local_demo_only"',result.stdout)
        self.assertIn('"deployment_performed": false',result.stdout)
        self.assertNotIn(str(self.root),result.stdout)


if __name__=="__main__":
    unittest.main()
