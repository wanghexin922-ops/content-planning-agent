import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.request = self.directory / "request.json"
        self.request.write_text(json.dumps({"request_id": "cli-test", "theme": "视频字幕", "budget": 10,
                                          "deadline": "2026-10-29T18:00:00+08:00"}), encoding="utf-8")
        self.env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.env["DEEPSEEK_API_KEY"] = ""

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "planner.py"), "--input", str(self.request),
                               "--db", str(self.directory / "test.sqlite"), "--out", str(self.directory / "out"),
                               "--now", "2026-10-28T10:00:00+08:00", *args],
                              cwd=self.directory, env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=20)

    def test_cli_runs_outside_repo_and_exports_artifacts(self):
        proc = self.cli("--mode", "mock")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["total_cost"], 8)
        output = json.loads((self.directory / "out/output.json").read_text(encoding="utf-8"))
        self.assertEqual(output["evidence"], "offline_mock_flow_only")
        self.assertTrue((self.directory / "out/plan.json").exists())
        trace = [json.loads(line) for line in (self.directory / "out/trace.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(trace[0]["event"], "run_started")

    def test_resume_across_separate_processes(self):
        first = self.cli("--max-steps", "2")
        self.assertEqual(first.returncode, 2)
        second = self.cli("--resume")
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads((self.directory / "out/output.json").read_text(encoding="utf-8"))
        self.assertEqual(output["runs"], 2)
        self.assertEqual(sum(s["tool"] == "search_materials" for s in output["steps"]), 1)
        third = self.cli()
        self.assertTrue(json.loads(third.stdout)["replayed"])

    def test_live_missing_key_never_reuses_mock_success(self):
        self.assertEqual(self.cli().returncode, 0)
        live = self.cli("--mode", "live", "--env-file", str(self.directory / "absent.env"))
        self.assertEqual(live.returncode, 1)
        self.assertEqual(json.loads(live.stderr)["error"], "missing_api_key")

    def test_malformed_input_fails_cleanly(self):
        self.request.write_text("{broken", encoding="utf-8")
        proc = self.cli()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stderr)["status"], "failed")
        self.assertNotIn("Traceback", proc.stderr)

    def test_request_generator_uses_explicit_audience(self):
        generated = self.directory / "generated.json"
        command = [sys.executable, str(ROOT / "scripts/new_request.py"), "--theme", "求职视频", "--out", str(generated)]
        subprocess.run(command, check=True, env=self.env, capture_output=True)
        self.assertNotIn("audience", json.loads(generated.read_text(encoding="utf-8")))
        subprocess.run(command + ["--audience", "应届毕业生"], check=True, env=self.env, capture_output=True)
        self.assertEqual(json.loads(generated.read_text(encoding="utf-8"))["audience"], "应届毕业生")


if __name__ == "__main__":
    unittest.main()
