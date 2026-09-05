import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "requests.db")

    def call(self, token, *args, ok=True):
        # Every call is a new application process: persistence crosses restarts.
        app = os.environ.get("BM_CANDIDATE_BUILD", "app.py")
        result = subprocess.run([sys.executable, "-B", app, "--db", self.db, *args],
                                env={**os.environ, "SERVICE_TOKEN": token}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def create(self):
        return self.call("demo-a", "create", "--description", "Trocar uma lâmpada")

    def test_create_and_follow_after_restart(self):
        item = self.create()
        self.assertEqual(item["status"], "open")
        self.assertEqual(self.call("demo-a", "get", "--id", str(item["id"])), item)

    def test_operator_updates_and_user_follows(self):
        item = self.create()
        self.assertEqual(len(self.call("demo-operator", "list")), 1)
        self.call("demo-operator", "update", "--id", str(item["id"]), "--status", "done")
        self.assertEqual(self.call("demo-a", "get", "--id", str(item["id"]))["status"], "done")

    def test_owner_isolation(self):
        item = self.create()
        self.assertEqual(self.call("demo-b", "get", "--id", str(item["id"]), ok=False)["error"], "not_found")
        self.assertEqual(self.call("demo-a", "update", "--id", str(item["id"]), "--status", "done", ok=False)["error"], "forbidden")
        self.call("demo-b", "list", ok=False)

    def test_invalid_input(self):
        self.call("demo-a", "create", "--description", "", ok=False)
        self.call("demo-a", "create", "--description", "x" * 201, ok=False)
        item = self.create()
        self.call("demo-operator", "update", "--id", str(item["id"]), ok=False)

    def test_unknown_identity(self):
        self.call("invalid", "create", "--description", "request", ok=False)


if __name__ == "__main__":
    unittest.main()
