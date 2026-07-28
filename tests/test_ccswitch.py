from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from io import BytesIO
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from utils.ccswitch import AIRequestConfig, EmptyModelListError, IncompleteAIResponseError, _api_key, _base_url, _call_openai, _looks_incomplete, _read_max_tokens, _read_timeout, _request_text, build_ai_request_config, call_ccswitch, fetch_models, is_complete_ai_text, probe_ccswitch


class _Response:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class CCSwitchTests(unittest.TestCase):
    def test_request_config_is_an_immutable_snapshot_and_does_not_write_secrets_to_environment(self):
        settings = {
            "ai_provider": "deepseek",
            "ai_base_url": "https://gateway.example.com/deepseek",
            "ai_model": "deepseek-chat",
            "ai_timeout": 41,
        }
        environment = {"AI_PROVIDER": "zhipu", "AI_API_KEY": "wrong-key"}
        with patch.dict(os.environ, environment, clear=True), patch("utils.ccswitch.load_api_key", return_value="saved-key"):
            snapshot = build_ai_request_config(settings)
            self.assertEqual(snapshot.provider, "deepseek")
            self.assertEqual(snapshot.base_url, "https://gateway.example.com/deepseek")
            self.assertEqual(snapshot.model, "deepseek-chat")
            self.assertEqual(snapshot.timeout, 41)
            self.assertEqual(snapshot.api_key, "saved-key")
            self.assertEqual(os.environ, environment)
            with self.assertRaises(FrozenInstanceError):
                snapshot.provider = "zhipu"

    def test_call_uses_only_the_explicit_request_snapshot(self):
        response = _Response({"choices": [{"message": {"content": "已连接"}}]})
        snapshot = AIRequestConfig("deepseek", "https://api.deepseek.com", "deepseek-chat", 17, "snapshot-key")
        environment = {"AI_PROVIDER": "zhipu", "AI_BASE_URL": "https://wrong.example.com", "AI_API_KEY": "wrong-key"}
        with patch.dict(os.environ, environment, clear=True), patch("utils.ccswitch.urlopen", return_value=response) as mocked:
            self.assertEqual(call_ccswitch("测试", config=snapshot), "已连接")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer snapshot-key")
        self.assertEqual(mocked.call_args.kwargs["timeout"], 17)

    def test_deepseek_models_endpoint_returns_every_model_and_uses_bearer_key(self):
        response = _Response({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]})
        with patch("utils.ccswitch.urlopen", return_value=response) as mocked:
            models = fetch_models(provider="deepseek", api_key="sk-test", timeout=9)
        request = mocked.call_args.args[0]
        self.assertEqual(models, ["deepseek-chat", "deepseek-reasoner"])
        self.assertEqual(request.full_url, "https://api.deepseek.com/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")

    def test_empty_model_catalog_is_distinguished_from_a_network_failure(self):
        with patch("utils.ccswitch.urlopen", return_value=_Response({"models": []})):
            with self.assertRaises(EmptyModelListError):
                fetch_models(provider="ccswitch", timeout=9)

    def test_zhipu_probe_uses_v4_chat_endpoint(self):
        response = _Response({"choices": [{"message": {"content": "OK"}}]})
        with patch("utils.ccswitch.urlopen", return_value=response) as mocked:
            reply = probe_ccswitch(provider="zhipu", api_key="zhipu-key", model="glm-test", timeout=9)
        self.assertEqual(reply, "OK")
        self.assertEqual(mocked.call_args.args[0].full_url, "https://open.bigmodel.cn/api/paas/v4/chat/completions")

    def test_deepseek_probe_leaves_room_for_reasoning_tokens(self):
        response = _Response({"choices": [{"message": {"content": "OK"}}]})
        with patch("utils.ccswitch.urlopen", return_value=response) as mocked:
            self.assertEqual(probe_ccswitch(provider="deepseek", api_key="sk-test", model="deepseek-v4-flash", timeout=9), "OK")
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertGreaterEqual(payload["max_tokens"], 64)
        self.assertNotIn("temperature", payload)

    def test_direct_provider_requires_api_key_before_network_call(self):
        with patch.dict(os.environ, {}, clear=True), patch("utils.ccswitch.urlopen") as mocked:
            with self.assertRaisesRegex(RuntimeError, "API Key"):
                fetch_models(provider="deepseek")
        mocked.assert_not_called()

    def test_explicit_provider_does_not_reuse_selected_ccswitch_endpoint_or_key(self):
        environment = {
            "AI_PROVIDER": "ccswitch",
            "AI_BASE_URL": "http://127.0.0.1:19999",
            "AI_API_KEY": "ccswitch-secret",
            "CCSWITCH_API_KEY": "legacy-secret",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(_base_url("deepseek"), "https://api.deepseek.com")
            self.assertEqual(_api_key("deepseek"), "")

    def test_provider_specific_key_is_used_for_direct_provider(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "deepseek-secret"}, clear=True):
            self.assertEqual(_api_key("deepseek"), "deepseek-secret")

    def test_ui_selected_key_wins_over_stale_provider_environment_key(self):
        environment = {
            "AI_PROVIDER": "deepseek",
            "AI_API_KEY": "encrypted-ui-key",
            "DEEPSEEK_API_KEY": "stale-machine-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(_api_key("deepseek"), "encrypted-ui-key")

    def test_openai_response_is_normalized(self):
        request = Request("http://127.0.0.1:15721/v1/chat/completions")
        response = _Response({"choices": [{"message": {"content": "已连接"}}]})
        with patch("utils.ccswitch.urlopen", return_value=response):
            self.assertEqual(_request_text(request, protocol="OpenAI"), "已连接")

    def test_invalid_timeout_uses_default(self):
        with patch.dict(os.environ, {"CCSWITCH_TIMEOUT": "not-a-number"}, clear=False):
            self.assertEqual(_read_timeout(), 35)

    def test_current_settings_override_base_url_and_timeout(self):
        response = _Response({"choices": [{"message": {"content": "已连接"}}]})
        with patch.dict(os.environ, {"CCSWITCH_BASE_URL": "http://127.0.0.1:19999", "CCSWITCH_TIMEOUT": "45"}, clear=False):
            with patch("utils.ccswitch.urlopen", return_value=response) as mocked:
                self.assertEqual(_call_openai("测试", "test-model"), "已连接")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:19999/v1/chat/completions")
        self.assertEqual(mocked.call_args.kwargs["timeout"], 45)

    def test_invalid_max_tokens_uses_default(self):
        with patch.dict(os.environ, {"CCSWITCH_MAX_TOKENS": "not-a-number"}, clear=False):
            self.assertEqual(_read_max_tokens("ccswitch", "gpt-5.6-sol"), 2400)

    def test_deepseek_gets_a_larger_reasoning_output_budget(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_read_max_tokens("deepseek", "deepseek-v4-pro"), 3200)

    def test_length_truncated_answer_is_regenerated_once(self):
        truncated = _Response({
            "choices": [{
                "finish_reason": "length",
                "message": {"content": "## 风险\n- 定额默认混凝土强度等级C20，与"},
            }],
        })
        complete = _Response({
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "## 结论\n- 可套混凝土垫层。\n\n## 风险\n- C20需换为C15后复核价差。"},
            }],
        })

        with patch.dict(os.environ, {}, clear=True), patch("utils.ccswitch.urlopen", side_effect=[truncated, complete]) as mocked:
            answer = _call_openai("测试", "deepseek-v4-pro", provider="deepseek", api_key="sk-test")

        self.assertTrue(answer.endswith("。"))
        self.assertNotIn("等级C20，与", answer)
        self.assertEqual(mocked.call_count, 2)
        first_payload = json.loads(mocked.call_args_list[0].args[0].data)
        retry_payload = json.loads(mocked.call_args_list[1].args[0].data)
        self.assertEqual(first_payload["max_tokens"], 3200)
        self.assertGreaterEqual(retry_payload["max_tokens"], 4096)
        self.assertEqual(retry_payload["messages"][-2]["role"], "assistant")
        self.assertIn("重新输出一份完整答案", retry_payload["messages"][-1]["content"])

    def test_obviously_incomplete_tail_retries_even_without_length_reason(self):
        truncated = _Response({"choices": [{"finish_reason": "stop", "message": {"content": "## 风险\n- 强度等级C20，与"}}]})
        complete = _Response({"choices": [{"finish_reason": "stop", "message": {"content": "## 风险\n- 强度等级C20，与设计C15不一致，需换算。"}}]})

        with patch("utils.ccswitch.urlopen", side_effect=[truncated, complete]) as mocked:
            answer = _call_openai("测试", "test-model", provider="ccswitch")

        self.assertEqual(mocked.call_count, 2)
        self.assertFalse(_looks_incomplete(answer))

    def test_second_truncated_answer_is_not_accepted_as_completed(self):
        truncated = _Response({"choices": [{"finish_reason": "length", "message": {"content": "## 风险\n- 仍需确认与"}}]})

        with patch("utils.ccswitch.urlopen", side_effect=[truncated, truncated]):
            with self.assertRaisesRegex(IncompleteAIResponseError, "连续两次"):
                _call_openai("测试", "test-model", provider="ccswitch")

    def test_saved_answer_with_dangling_conjunction_is_not_complete(self):
        self.assertFalse(is_complete_ai_text("## 风险\n- 定额默认混凝土强度等级C20，与"))
        self.assertTrue(is_complete_ai_text("## 风险\n- C20与设计C15不一致，需调整材料单价。"))

    def test_http_error_body_is_not_propagated(self):
        request = Request("http://127.0.0.1:15721/v1/chat/completions")
        error = HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO(b"secret prompt and token"))
        with patch("utils.ccswitch.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"HTTP 403") as caught:
                _request_text(request, protocol="OpenAI")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("token", str(caught.exception))

    def test_connection_probe_uses_fixed_non_project_prompt(self):
        response = _Response({"choices": [{"message": {"content": "OK"}}]})
        with patch("utils.ccswitch.urlopen", return_value=response) as mocked:
            reply = probe_ccswitch("http://127.0.0.1:15721", model="test", timeout=9)
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(reply, "OK")
        self.assertEqual(payload["messages"][0]["content"], "Connection probe. Reply only OK.")
        self.assertEqual(mocked.call_args.kwargs["timeout"], 9)


if __name__ == "__main__":
    unittest.main()
