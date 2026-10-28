import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from content_planner.common import PlannerError
from content_planner.model import DeepSeekModel, load_env
from content_planner.tools import TOOL_SCHEMAS


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-not-a-real-key", "DEEPSEEK_BASE_URL": "https://api.deepseek.com", "DEEPSEEK_MODEL": "deepseek-flash", "DEEPSEEK_TIMEOUT": "60"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_native_tool_payload_and_observation_roundtrip(self):
        messages = [{"role": "user", "content": "主题"}, {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_materials", "arguments": "{}"}}]}, {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\":true}"}]
        response = {"choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "private", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "finish", "arguments": "{}"}}]}}]}
        with patch("content_planner.model.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(json.dumps(response).encode())
            result = DeepSeekModel().next_message(messages, TOOL_SCHEMAS)
            request = factory.return_value.open.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(body["model"], "deepseek-flash")
            self.assertEqual(body["thinking"], {"type": "disabled"})
            self.assertEqual(body["messages"], messages)
            self.assertEqual(body["tools"], TOOL_SCHEMAS)
            self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
            self.assertNotIn("reasoning_content", result)

    def test_auth_error_does_not_leak_body_or_key(self):
        with patch("content_planner.model.build_opener") as factory:
            factory.return_value.open.side_effect = HTTPError("https://api.deepseek.com", 401, "secret raw error", {}, io.BytesIO(b"test-not-a-real-key"))
            with self.assertRaises(PlannerError) as caught:
                DeepSeekModel().next_message([], TOOL_SCHEMAS)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("test-not-a-real-key", str(caught.exception))
        self.assertNotIn("secret raw error", str(caught.exception))

    def test_network_failure_is_not_mock_fallback(self):
        with patch("content_planner.model.build_opener") as factory:
            factory.return_value.open.side_effect = URLError("offline")
            with self.assertRaises(PlannerError) as caught:
                DeepSeekModel().next_message([], TOOL_SCHEMAS)
        self.assertEqual(caught.exception.code, "model_network_error")

    def test_invalid_response_and_truncation(self):
        for body, code in [(b"broken", "model_protocol_error"), (b'{"choices":[]}', "model_protocol_error"), (b'{"choices":[{"finish_reason":"length"}]}', "model_truncated")]:
            with self.subTest(code=code), patch("content_planner.model.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(body)
                with self.assertRaises(PlannerError) as caught:
                    DeepSeekModel().next_message([], TOOL_SCHEMAS)
                self.assertEqual(caught.exception.code, code)

    def test_missing_key_and_insecure_url_rejected(self):
        os.environ["DEEPSEEK_API_KEY"] = ""
        with self.assertRaisesRegex(PlannerError, "DEEPSEEK_API_KEY"):
            DeepSeekModel()
        os.environ["DEEPSEEK_API_KEY"] = "test-only"
        os.environ["DEEPSEEK_BASE_URL"] = "http://example.com"
        with self.assertRaisesRegex(PlannerError, "HTTPS"):
            DeepSeekModel()

    def test_env_file_bom_quotes_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text('# comment\nDEEPSEEK_API_KEY="file-secret"\nDEEPSEEK_MODEL=example\n', encoding="utf-8-sig")
            load_env(env)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "test-not-a-real-key")
            del os.environ["DEEPSEEK_API_KEY"]
            load_env(env)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "file-secret")


if __name__ == "__main__":
    unittest.main()
