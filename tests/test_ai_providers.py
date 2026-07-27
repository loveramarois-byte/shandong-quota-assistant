from __future__ import annotations

import unittest

from utils import ai_providers
from utils.ai_providers import effective_base_url, endpoint_url, provider_config, provider_key_from_label


class AiProviderTests(unittest.TestCase):
    def test_provider_labels_map_to_stable_keys(self):
        self.assertEqual(provider_key_from_label("ccSwitch（本机）"), "ccswitch")
        self.assertEqual(provider_key_from_label("DeepSeek"), "deepseek")
        self.assertEqual(provider_key_from_label("智谱 AI"), "zhipu")

    def test_default_endpoints_are_provider_specific(self):
        self.assertEqual(effective_base_url("deepseek"), "https://api.deepseek.com")
        self.assertEqual(effective_base_url("zhipu"), "https://open.bigmodel.cn/api/paas/v4")
        self.assertFalse(provider_config("ccswitch").requires_api_key)
        self.assertTrue(provider_config("deepseek").requires_api_key)

    def test_ccswitch_has_verified_fallback_models_for_an_empty_catalog(self):
        self.assertEqual(provider_config("ccswitch").fallback_models, ("gpt-5.6-sol", "gpt-5.6-terra"))
        self.assertEqual(provider_config("deepseek").fallback_models, ())

    def test_switching_provider_does_not_carry_a_custom_endpoint_across(self):
        switch_endpoint = getattr(ai_providers, "endpoint_after_provider_switch", None)
        self.assertIsNotNone(switch_endpoint)
        if switch_endpoint is None:
            return
        self.assertEqual(
            switch_endpoint("deepseek", "zhipu", "https://gateway.example.com/deepseek"),
            provider_config("zhipu").default_base_url,
        )
        self.assertEqual(
            switch_endpoint("deepseek", "deepseek", "https://gateway.example.com/deepseek"),
            "https://gateway.example.com/deepseek",
        )

    def test_endpoint_join_does_not_duplicate_v1(self):
        self.assertEqual(endpoint_url("http://127.0.0.1:15721", "/v1/models"), "http://127.0.0.1:15721/v1/models")
        self.assertEqual(endpoint_url("http://127.0.0.1:15721/v1", "/v1/models"), "http://127.0.0.1:15721/v1/models")


if __name__ == "__main__":
    unittest.main()
