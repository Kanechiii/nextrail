"""Phase 40 optimistic progress concurrency and per-account isolation checks."""
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services/api"))
from nextrail_api import create_app

PLAN={"career_goal":"Frontend developer","target_skill_ids":["css"],"known_skill_ids":[],
      "weekly_hours":6,"zero_budget":True}
PASSWORD="synthetic-dev-password-1234"


def signup(client,name):
    email=name+"@example.org"
    assert client.post("/v1/auth/register",json={"email":email,"password":PASSWORD}).status_code==201
    response=client.post("/v1/auth/login",json={"email":email,"password":PASSWORD})
    assert response.status_code==200
    return {"Authorization":"Bearer "+response.json()["access_token"]}


class ProgressConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.ctx=TestClient(create_app())
        self.client=self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__,None,None,None)
        self.owner=signup(self.client,"primary")
        saved=self.client.post("/v1/me/pathways",json=PLAN,headers=self.owner)
        self.assertEqual(saved.status_code,201,saved.text)
        self.path=saved.json()["id"]
        self.url="/v1/me/pathways/"+self.path+"/progress"

    def get(self,headers=None):
        return self.client.get(self.url,headers=headers or self.owner)

    def write(self,revision=None,status="completed",skill="html",headers=None):
        all_headers=dict(headers or self.owner)
        if revision is not None:
            all_headers["If-Match"]='"'+revision+'"'
        return self.client.put(self.url+"/"+skill,json={"status":status},headers=all_headers)

    def test_get_returns_revision_and_http_etag(self):
        response=self.get()
        self.assertEqual(response.status_code,200,response.text)
        self.assertRegex(response.json()["revision"],r"^[0-9a-f]{64}$")
        self.assertEqual(response.headers["etag"],'"'+response.json()["revision"]+'"')
        self.assertEqual(response.headers["cache-control"],"no-store")

    def test_conditional_write_rejects_stale_tab_and_preserves_audit(self):
        first=self.get().json()
        second=self.get().json()
        self.assertEqual(first["revision"],second["revision"])
        updated=self.write(first["revision"])
        self.assertEqual(updated.status_code,200,updated.text)
        revision=self.get().json()["revision"]
        self.assertNotEqual(revision,second["revision"])
        before=self.client.get("/v1/me/audit",headers=self.owner).json()["events"]
        stale=self.write(second["revision"],status="not_started")
        self.assertEqual(stale.status_code,409,stale.text)
        self.assertIn("Reload",stale.json()["detail"])
        self.assertEqual(self.get().json()["revision"],revision)
        self.assertEqual(self.get().json()["completed"],1)
        after=self.client.get("/v1/me/audit",headers=self.owner).json()["events"]
        self.assertEqual(before,after)
        fresh=self.write(revision,status="not_started")
        self.assertEqual(fresh.status_code,200)
        self.assertEqual(self.get().json()["completed"],0)

    def test_status_unchanged_does_not_bump_revision(self):
        current=self.get().json()
        first=self.write(current["revision"],status="not_started")
        self.assertEqual(first.status_code,200)
        self.assertFalse(first.json()["changed"])
        self.assertEqual(self.get().json()["revision"],current["revision"])

    def test_malformed_if_match_is_422_not_unconditional_write(self):
        for value in ("bad","0",'"not-number"','"01"',"*","\"0\"\nInjected: yes"):
            with self.subTest(value=value):
                response=self.client.put(self.url+"/html",
                     headers={**self.owner,"If-Match":value},
                     json={"status":"completed"})
                self.assertIn(response.status_code,(400,422))
        self.assertEqual(self.get().json()["completed"],0)

    def test_missing_or_other_account_pathway_is_not_leaked(self):
        other=signup(self.client,"secondary")
        result=self.write(self.get().json()["revision"],headers=other)
        self.assertEqual(result.status_code,404)
        self.assertEqual(self.client.get(self.url,headers=other).status_code,404)

    def test_backward_compatible_legacy_put_remains_supported(self):
        response=self.write()
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()["changed"])
        self.assertEqual(self.get().json()["completed"],1)


class TwoConnectionProgressTests(unittest.TestCase):
    def test_two_api_connections_share_revision_and_prevent_stale_write(self):
        with tempfile.TemporaryDirectory() as d:
            file=str(Path(d)/"shared.sqlite")
            with TestClient(create_app(database_path=file)) as first, TestClient(create_app(database_path=file)) as second:
                token=signup(first,"twotabs")
                saved=first.post("/v1/me/pathways",json=PLAN,headers=token)
                self.assertEqual(saved.status_code,201,saved.text)
                path=saved.json()["id"]
                route="/v1/me/pathways/"+path+"/progress"
                a=first.get(route,headers=token).json()["revision"]
                b=second.get(route,headers=token).json()["revision"]
                self.assertEqual(a,b)
                ok=first.put(route+"/html",json={"status":"completed"},
                    headers={**token,"If-Match":'"'+a+'"'})
                self.assertEqual(ok.status_code,200,ok.text)
                conflict=second.put(route+"/css",json={"status":"completed"},
                    headers={**token,"If-Match":'"'+b+'"'})
                self.assertEqual(conflict.status_code,409,conflict.text)
                self.assertEqual(second.get(route,headers=token).json()["completed"],1)
                refreshed=second.get(route,headers=token).json()["revision"]
                retry=second.put(route+"/css",json={"status":"completed"},
                    headers={**token,"If-Match":'"'+refreshed+'"'})
                self.assertEqual(retry.status_code,200,retry.text)
                self.assertEqual(first.get(route,headers=token).json()["completed"],2)


if __name__=="__main__":
    unittest.main()
