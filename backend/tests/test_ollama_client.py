from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import json

import httpx

from app import client_ollama


def response(content, **extra):
    return httpx.Response(200, request=httpx.Request("POST", "http://localhost/api/chat"), json={
        "done": True, "done_reason": "stop", "message": {"content": content}, **extra,
    })


class OllamaClientTests(TestCase):
    def test_chat_uses_schema_and_records_only_metadata(self):
        events = []
        observation = SimpleNamespace(update=Mock())

        @contextmanager
        def trace(name, **kwargs):
            events.append((name, kwargs))
            yield observation

        with patch.object(client_ollama, "trace_step", trace):
            with patch.object(client_ollama.httpx, "post", return_value=response(
                '{"reply":"private response"}', prompt_eval_count=20, eval_count=10,
            )) as post:
                result = client_ollama.get_chat_reply("private input", "private instructions", "v1")
        self.assertEqual(result, {"reply": "private response"})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["format"]["properties"]["reply"]["type"], "string")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], client_ollama.OLLAMA_CONTEXT_LENGTH)
        exported = repr(events) + repr(observation.update.call_args_list)
        for secret in ("private input", "private instructions", "private response"):
            self.assertNotIn(secret, exported)
        observation.update.assert_called_once_with(usage_details={"input": 20, "output": 10})

    def test_invalid_or_truncated_output_is_rejected(self):
        cases = [
            response('{"reply":"hello"}', done_reason="length"),
            response('{"reply":"hello"}', done=False),
            response(""), response("not json"), response('{"reply":123}'),
            response('{"plan_mode":"invented", "message":"No"}'),
        ]
        for returned in cases:
            with self.subTest(payload=returned.json()):
                with patch.object(client_ollama.httpx, "post", return_value=returned):
                    with self.assertRaises(ValueError):
                        client_ollama.get_chat_reply("input", "prompt", "v1")

    def test_http_failure_and_timeout_propagate(self):
        failed = httpx.Response(503, request=httpx.Request("POST", "http://localhost/api/chat"))
        with patch.object(client_ollama.httpx, "post", return_value=failed):
            with self.assertRaises(httpx.HTTPStatusError):
                client_ollama.get_chat_reply("input", "prompt", "v1")
        with patch.object(client_ollama.httpx, "post", side_effect=httpx.ReadTimeout("unavailable")):
            with self.assertRaises(httpx.ReadTimeout):
                client_ollama.get_chat_reply("input", "prompt", "v1")

    def test_feedback_date_retains_python_date_contract(self):
        content = json.dumps({"decision": "continue_revision", "plan_mode": "normal_running",
                              "message": "Continue", "requested_start_date": "2026-10-12"})
        with patch.object(client_ollama.httpx, "post", return_value=response(content)):
            result = client_ollama.get_feedback_safety_assessment("input", "prompt", "v1")
        self.assertEqual(result["requested_start_date"], date(2026, 10, 12))
