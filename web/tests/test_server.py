import importlib
import os
import tempfile
import unittest
from http.client import HTTPConnection
from http import HTTPStatus
from threading import Thread
from pathlib import Path


class ServerFunctionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "raw/inbox").mkdir(parents=True)
        (root / "wiki/sources").mkdir(parents=True)
        (root / "raw/work").mkdir(parents=True)
        (root / "raw/study").mkdir(parents=True)
        (root / "raw/clips").mkdir(parents=True)
        (root / "raw/assets").mkdir(parents=True)
        (root / "raw/inbox/test-note.md").write_text("# Test Note\n\nAgent workflow note.", encoding="utf-8")
        (root / "wiki/sources/test-note.md").write_text("# Source\n\nSource summary.", encoding="utf-8")
        os.environ["KB_ROOT"] = str(root)
        os.environ.pop("KB_AUTH_PASSWORD", None)
        os.environ.pop("KB_AUTH_REQUIRED", None)
        os.environ.pop("KB_AI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        import web.server as server

        self.server = importlib.reload(server)
        self.root = root

    def tearDown(self):
        self.tempdir.cleanup()

    def test_safe_repo_path_rejects_parent_escape(self):
        with self.assertRaises(self.server.ApiError) as context:
            self.server.safe_repo_path("../outside.md")
        self.assertEqual(context.exception.status, HTTPStatus.BAD_REQUEST)

    def test_list_files_can_search_text(self):
        results = self.server.list_files("all", "workflow")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "raw/inbox/test-note.md")
        self.assertEqual(results[0]["matches"][0]["line"], 3)

    def test_safe_delete_moves_to_trash(self):
        result = self.server.safe_delete("raw/inbox/test-note.md")
        self.assertFalse((self.root / "raw/inbox/test-note.md").exists())
        self.assertTrue((self.root / result["trash_path"]).exists())

    def test_save_upload_writes_to_allowed_target(self):
        boundary = "----test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="target_dir"\r\n\r\n'
            "raw/inbox\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="new note.md"\r\n'
            "Content-Type: text/markdown\r\n\r\n"
            "# New Note\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        class Headers:
            def get(self, name, default=None):
                if name == "Content-Type":
                    return f"multipart/form-data; boundary={boundary}"
                return default

        saved = self.server.save_upload(Headers(), body)
        self.assertEqual(saved[0]["path"], "raw/inbox/new-note.md")
        self.assertTrue((self.root / "raw/inbox/new-note.md").exists())

    def test_local_ai_suggestion_includes_source_page(self):
        suggestion = self.server.suggest_for_payload({"path": "raw/inbox/test-note.md"})
        self.assertEqual(suggestion["source_page"], "wiki/sources/test-note.md")
        self.assertIn("provider", suggestion)

    def test_dashboard_data_contains_indexed_summary(self):
        data = self.server.dashboard_data()
        self.assertEqual(data["summary"]["total_files"], 2)
        self.assertGreaterEqual(data["index_status"]["indexed_files"], 2)
        self.assertTrue(any(item["name"] == "raw/inbox" for item in data["areas"]))

    def test_rebuild_index_returns_status(self):
        result = self.server.rebuild_index()
        self.assertGreaterEqual(result["scanned"], 2)
        status = self.server.get_index_status()
        self.assertGreaterEqual(status["indexed_files"], 2)
        self.assertIsNotNone(status["last_indexed_at"])

    def test_pipeline_process_creates_source_and_archives(self):
        source = self.root / "wiki/sources/work-plan.md"
        (self.root / "raw/inbox/work-plan.md").write_text("# Work Plan\n\nweekly review", encoding="utf-8")

        result = self.server.process_material("raw/inbox/work-plan.md")

        self.assertEqual(result["final_path"], "raw/work/work-plan.md")
        self.assertTrue((self.root / "raw/work/work-plan.md").exists())
        self.assertTrue(source.exists())
        self.assertIn("raw/work/work-plan.md", source.read_text(encoding="utf-8"))

    def test_pipeline_status_reports_source_gaps(self):
        (self.root / "raw/inbox/no-source.md").write_text("# No Source\n\nplain note", encoding="utf-8")

        status = self.server.pipeline_status()

        self.assertGreaterEqual(status["source_gaps_count"], 1)
        self.assertTrue(any(item["path"] == "raw/inbox/no-source.md" for item in status["source_gaps"]))


class ServerAuthTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "raw/inbox").mkdir(parents=True)
        (root / "wiki/sources").mkdir(parents=True)
        (root / "raw/inbox/test-note.md").write_text("# Test Note\n\nAgent workflow note.", encoding="utf-8")
        os.environ["KB_ROOT"] = str(root)
        os.environ["KB_AUTH_REQUIRED"] = "1"
        os.environ["KB_AUTH_USERNAME"] = "admin"
        os.environ["KB_AUTH_PASSWORD"] = "secret"
        os.environ.pop("KB_AI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        import web.server as server

        self.server = importlib.reload(server)
        self.httpd = self.server.ThreadingHTTPServer(("127.0.0.1", 0), self.server.KnowledgeBaseHandler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tempdir.cleanup()
        os.environ.pop("KB_AUTH_REQUIRED", None)
        os.environ.pop("KB_AUTH_USERNAME", None)
        os.environ.pop("KB_AUTH_PASSWORD", None)

    def request(self, method, path, body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response, data

    def test_protected_api_requires_login(self):
        response, _ = self.request("GET", "/api/dashboard")
        self.assertEqual(response.status, HTTPStatus.UNAUTHORIZED)

    def test_login_sets_cookie_and_allows_access(self):
        response, _ = self.request(
            "POST",
            "/api/auth/login",
            body=b'{"username":"admin","password":"secret"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status, HTTPStatus.OK)
        cookie = response.getheader("Set-Cookie")
        self.assertIn("kb_session=", cookie)

        dashboard_response, _ = self.request("GET", "/api/dashboard", headers={"Cookie": cookie})
        self.assertEqual(dashboard_response.status, HTTPStatus.OK)


if __name__ == "__main__":
    unittest.main()
