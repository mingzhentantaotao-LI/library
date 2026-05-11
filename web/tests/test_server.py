import importlib
import os
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path


class ServerFunctionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "raw/inbox").mkdir(parents=True)
        (root / "wiki/sources").mkdir(parents=True)
        (root / "raw/inbox/test-note.md").write_text("# Test Note\n\nAgent workflow note.", encoding="utf-8")
        (root / "wiki/sources/test-note.md").write_text("# Source\n\nSource summary.", encoding="utf-8")
        os.environ["KB_ROOT"] = str(root)
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


if __name__ == "__main__":
    unittest.main()
