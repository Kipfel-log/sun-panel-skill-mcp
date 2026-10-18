from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sun-panel" / "scripts"))
from sun_panel import PanelClient, PanelError, normalize_base


class MockPanel:
    def __init__(self):
        self.calls = []
        self.items = {"existing": {"onlyName": "existing", "title": "原来的标题",
            "url": "https://example.com/app", "lanUrl": "http://192.0.2.1:3000",
            "iconUrl": "https://example.com/icon.png", "description": "保留这段描述",
            "itemGroupID": 1, "itemGroupOnlyName": "network"}}
        self.mode = "normal"
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                state.calls.append((self.path, body, self.headers.get("token")))
                if state.mode == "redirect":
                    self.send_response(307)
                    self.send_header("Location", "/leaked")
                    self.end_headers()
                    return
                if state.mode == "lucky":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<title>Lucky Auth</title>")
                    return
                code, data, msg = 0, None, "OK"
                action = self.path.removeprefix("/openapi/v1/")
                if state.mode == "business-error":
                    code, msg = 1100, "expired test-token"
                elif action == "version":
                    data = {"version": "1.8.0" if state.mode == "old-version" else "1.8.1", "versionCode": 26}
                elif action == "itemGroup/getList":
                    data = {"count": 2, "list": [{"itemGroupID": 1, "title": "网络", "onlyName": "network"},
                                                {"itemGroupID": 2, "title": "应用", "onlyName": "apps"}]}
                elif action == "itemGroup/getInfo":
                    data = {"itemGroupID": body.get("itemGroupID", 2), "title": "应用", "onlyName": body.get("onlyName", "apps")}
                elif action == "item/getInfoByOnlyName":
                    data = state.items.get(body["onlyName"])
                    if data is None:
                        code, msg = 1203, "no record"
                    elif state.mode == "blank-icon-readback":
                        data = {**data, "iconUrl": ""}
                elif action in ("item/create", "item/update"):
                    if state.mode != "ignore-write":
                        incoming = dict(body)
                        incoming.pop("isSaveIcon", None)
                        if "itemGroupOnlyName" in incoming:
                            incoming["itemGroupID"] = 2
                        elif "itemGroupID" in incoming:
                            incoming["itemGroupOnlyName"] = "apps" if incoming["itemGroupID"] == 2 else "network"
                        if action == "item/create":
                            incoming = {"title": "", "url": "", "lanUrl": "", "iconUrl": "", "description": "",
                                        "itemGroupID": 1, **incoming}
                        state.items.setdefault(body["onlyName"], {}).update(incoming)
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                raw = json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(raw)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}/openapi/v1"

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def client(self, write=False):
        return PanelClient(self.base, "test-token", allow_http=True, allow_write=write)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = MockPanel()
        cls.original = copy.deepcopy(cls.mock.items)

    @classmethod
    def tearDownClass(cls):
        cls.mock.close()

    def setUp(self):
        self.mock.calls.clear()
        self.mock.mode = "normal"
        self.mock.items = copy.deepcopy(self.original)
        self.client = self.mock.client()

    def test_url_validation(self):
        self.assertEqual(normalize_base("https://example.com/"), "https://example.com/openapi/v1")
        for bad in ("http://example.com", "https://user:pass@example.com", "https://example.com/?token=x", "https://example.com/admin"):
            with self.subTest(url=bad), self.assertRaises(PanelError):
                normalize_base(bad)

    def test_version_and_groups_post_header(self):
        self.assertEqual(self.client.request("version")["data"]["version"], "1.8.1")
        self.assertEqual(self.client.request("groups")["data"]["count"], 2)
        self.assertTrue(all(x[2] == "test-token" for x in self.mock.calls))

    def test_readonly_blocks_direct_and_prepared_writes(self):
        with self.assertRaises(PanelError):
            self.client.request("create", {"url": "https://example.com"})
        with self.assertRaises(PanelError):
            self.client.change_item("update", {"onlyName": "existing", "title": "new"}, execute=True)
        self.assertEqual(self.mock.calls, [])

    def test_redirect_does_not_forward_token(self):
        self.mock.mode = "redirect"
        with self.assertRaises(PanelError) as caught:
            self.client.request("version")
        self.assertEqual(caught.exception.code, "REDIRECT")
        self.assertEqual(len(self.mock.calls), 1)

    def test_lucky_is_not_token_expiry(self):
        self.mock.mode = "lucky"
        with self.assertRaises(PanelError) as caught:
            self.client.request("version")
        self.assertEqual(caught.exception.code, "NON_JSON")
        self.assertIn("Lucky", str(caught.exception))

    def test_business_failure_and_token_redaction(self):
        self.mock.mode = "business-error"
        with self.assertRaises(PanelError) as caught:
            self.client.request("version")
        self.assertEqual(caught.exception.code, 1100)
        self.assertNotIn("test-token", str(caught.exception))

    def test_unknown_endpoint_and_invalid_fields(self):
        with self.assertRaises(PanelError):
            self.client.request("../admin")
        for body in ({"onlyName": "existing", "title": 4}, {"onlyName": "existing", "sort": 2},
                     {"onlyName": "existing", "itemGroupID": True}, {"onlyName": "existing", "url": "javascript:alert(1)"}):
            with self.subTest(body=body), self.assertRaises(PanelError):
                self.client.change_item("update", body)
        self.assertEqual(self.mock.calls, [])

    def test_preview_preserves_fields_and_does_not_write(self):
        result = self.client.change_item("update", {"onlyName": "existing", "title": "新标题"})
        self.assertFalse(result["executed"])
        self.assertEqual(result["before"]["description"], "保留这段描述")
        self.assertEqual(set(result["submitted"]), {"onlyName", "title"})
        self.assertEqual(self.mock.items, self.original)
        self.assertTrue(all(x[0] in ("/openapi/v1/version", "/openapi/v1/item/getInfoByOnlyName") for x in self.mock.calls))

    def test_older_version_update_refused(self):
        self.mock.mode = "old-version"
        with self.assertRaises(PanelError) as caught:
            self.mock.client(True).change_item("update", {"onlyName": "existing", "title": "new"}, execute=True)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_VERSION")
        self.assertEqual(self.mock.items, self.original)

    def test_sparse_update_does_not_erase_hidden_icon(self):
        self.mock.mode = "blank-icon-readback"
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "title": "new"}, execute=True)
        self.assertTrue(result["verified"])
        self.assertNotIn("iconUrl", result["submitted"])
        self.assertEqual(self.mock.items["existing"]["iconUrl"], self.original["existing"]["iconUrl"])

    def test_icon_readback_missing_requires_visual_check(self):
        self.mock.mode = "blank-icon-readback"
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "iconUrl": "https://example.com/new.png"}, execute=True)
        self.assertTrue(result["executed"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["unverified_fields"], ["iconUrl"])
        self.assertEqual(result["verification_status"], "needs_visual_check")

    def test_saved_icon_not_silently_verified_when_readback_blank(self):
        self.mock.mode = "blank-icon-readback"
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "iconUrl": "https://example.com/new.png", "isSaveIcon": True}, execute=True)
        self.assertFalse(result["verified"])
        self.assertEqual(result["unverified_fields"], ["iconUrl"])

    def test_matching_external_icon_is_verified(self):
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "iconUrl": "https://example.com/new.png"}, execute=True)
        self.assertTrue(result["verified"])
        self.assertIn("iconUrl", result["verified_fields"])

    def test_update_group_by_name_overrides_old_id(self):
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "itemGroupOnlyName": "apps"}, execute=True)
        self.assertNotIn("itemGroupID", result["submitted"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["after"]["itemGroupID"], 2)

    def test_create_duplicate_guard_and_preview(self):
        with self.assertRaises(PanelError):
            self.client.change_item("create", {"onlyName": "existing", "url": "https://example.com"})
        result = self.client.change_item("create", {"onlyName": "new", "url": "https://example.com", "itemGroupID": 2})
        self.assertFalse(result["executed"])
        self.assertNotIn("new", self.mock.items)

    def test_create_and_update_verified(self):
        client = self.mock.client(True)
        created = client.change_item("create", {"onlyName": "new", "url": "https://example.com", "title": "新入口"}, execute=True)
        self.assertTrue(created["verified"])
        updated = client.change_item("update", {"onlyName": "existing", "description": ""}, execute=True)
        self.assertTrue(updated["verified"])
        self.assertEqual(updated["after"]["title"], "原来的标题")
        self.assertEqual(updated["after"]["description"], "")

    def test_accepted_write_with_mismatch_not_reported_as_verified(self):
        self.mock.mode = "ignore-write"
        result = self.mock.client(True).change_item("update", {"onlyName": "existing", "title": "new"}, execute=True)
        self.assertTrue(result["executed"])
        self.assertFalse(result["verified"])
        self.assertIn("title", result["mismatches"])


if __name__ == "__main__":
    unittest.main()
