# -*- coding: utf-8 -*-
"""Tests for env-based LLM channel parsing."""

import os
import unittest
from unittest.mock import Mock, patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.config import (
    Config,
    apply_litellm_api_surface,
    get_configured_llm_models,
    get_effective_agent_models_to_try,
    get_effective_agent_primary_model,
    normalize_litellm_temperature,
)
from src.llm.generation_params import (
    apply_litellm_generation_params,
)
from src.services.system_config_service import SystemConfigService


class LLMChannelConfigTestCase(unittest.TestCase):











    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_duplicate_route_alias_allows_same_surface_deployments(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "LLM_CHANNELS": "primary,backup",
            "LLM_PRIMARY_PROTOCOL": "deepseek",
            "LLM_PRIMARY_API_KEY": "sk-primary-test-value",
            "LLM_PRIMARY_MODELS": "deepseek/deepseek-flash",
            "LLM_BACKUP_PROTOCOL": "deepseek",
            "LLM_BACKUP_API_KEY": "sk-backup-test-value",
            "LLM_BACKUP_MODELS": "deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(len(config.llm_channels), 2)
        self.assertEqual(len(config.llm_model_list), 2)
        self.assertFalse(
            any(
                issue["code"] == "mixed_api_surfaces_for_route"
                for issue in config.llm_channel_config_issues
            )
        )

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_unknown_api_surface_from_env_is_rejected_instead_of_falling_back(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "LLM_CHANNELS": "draft",
            "LLM_DRAFT_PROTOCOL": "deepseek",
            "LLM_DRAFT_API_SURFACE": "respones",
            "LLM_DRAFT_API_KEY": "sk-draft-test-value",
            "LLM_DRAFT_MODELS": "deepseek/deepseek-v4-pro",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_model_list, [])
        self.assertEqual(len(config.llm_channel_config_issues), 1)
        issue = config.llm_channel_config_issues[0]
        self.assertEqual(issue["field"], "LLM_DRAFT_API_SURFACE")
        self.assertEqual(issue["code"], "invalid_api_surface")






    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_protocol_prefixes_bare_model_names(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "deepseek",
            "LLM_PRIMARY_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_PRIMARY_API_KEY": "sk-test-value",
            "LLM_PRIMARY_MODELS": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["protocol"], "deepseek")
        self.assertEqual(config.llm_channels[0]["models"], ["deepseek/deepseek-chat"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["model"], "deepseek/deepseek-chat")




    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_validate_structured_does_not_apply_route_alias_check_to_legacy_env(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-openai-test-value",
            "LITELLM_MODEL": "deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "legacy_env")
        issues = config.validate_structured()
        self.assertFalse(
            any(issue.field == "LITELLM_MODEL" and issue.severity == "error" for issue in issues),
            issues,
        )






    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_disabled_channel_is_skipped(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "deepseek",
            "LLM_PRIMARY_ENABLED": "false",
            "LLM_PRIMARY_API_KEY": "sk-test-value",
            "LLM_PRIMARY_MODELS": "deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_model_list, [])



    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    @patch("src.config.logger.warning")
    def test_deepseek_key_defaults_to_flash(self, *mocks) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deepseek"}, clear=True):
            config = Config._load_from_env()
        self.assertEqual(config.litellm_model, "deepseek/deepseek-flash")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    @patch("src.config.logger.warning")
    def test_explicit_deepseek_litellm_model_is_preserved(
        self,
        mock_warning,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "LITELLM_MODEL": "deepseek/deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.litellm_model, "deepseek/deepseek-chat")
        mock_warning.assert_not_called()

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    @patch("src.config.logger.warning")
    def test_deepseek_key_does_not_warn_when_channels_take_precedence(
        self,
        mock_warning,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "deepseek",
            "LLM_PRIMARY_API_KEY": "sk-channel-value",
            "LLM_PRIMARY_MODELS": "deepseek-v4-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        mock_warning.assert_not_called()

    @patch("src.config.setup_env")
    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[
            {
                "model_name": "primary",
                "litellm_params": {
                    "model": "deepseek/deepseek-v4-flash",
                    "api_key": "sk-yaml-value",
                },
            }
        ],
    )
    @patch("src.config.logger.warning")
    def test_deepseek_key_does_not_warn_when_litellm_yaml_takes_precedence(
        self,
        mock_warning,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "LITELLM_CONFIG": "/tmp/litellm.yaml",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "litellm_config")
        mock_warning.assert_not_called()

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_prefers_unified_setting_when_present(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "secret-key-value",
            "GEMINI_TEMPERATURE": "0.15",
            "LLM_TEMPERATURE": "0.35",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.35)



    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_ignores_invalid_value(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "secret-key-value",
            "LLM_TEMPERATURE": "high",
            "GEMINI_TEMPERATURE": "0.25",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.7)









    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_model_empty_inherits_primary_model(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "OPENAI_MODEL": "deepseek/deepseek-flash",
            "AGENT_LITELLM_MODEL": "",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "")
        self.assertEqual(get_effective_agent_primary_model(config), "deepseek/deepseek-flash")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_model_without_provider_prefix_is_normalized(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "OPENAI_MODEL": "deepseek/deepseek-flash",
            "AGENT_LITELLM_MODEL": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "deepseek/deepseek-chat")
        self.assertEqual(get_effective_agent_primary_model(config), "deepseek/deepseek-chat")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_models_to_try_are_deduped_in_order(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "LITELLM_MODEL": "deepseek/deepseek-flash",
            "AGENT_LITELLM_MODEL": "deepseek/deepseek-flash",
            "LITELLM_FALLBACK_MODELS": "deepseek/deepseek-flash,deepseek/deepseek-flash,deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["deepseek/deepseek-flash"],
        )

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_models_to_try_dedupes_semantically_equivalent_deepseek_models(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "DEEPSEEK_API_KEY": "sk-test-value",
            "LITELLM_MODEL": "deepseek/deepseek-flash",
            "AGENT_LITELLM_MODEL": "deepseek/deepseek-flash",
            "LITELLM_FALLBACK_MODELS": "deepseek/deepseek-flash,deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["deepseek/deepseek-flash"],
        )

    @patch("src.config.setup_env")
    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[
            {
                "model_name": "gpt4o",
                "litellm_params": {
                    "model": "deepseek/deepseek-flash",
                    "api_key": "sk-test-value",
                },
            }
        ],
    )
    def test_agent_model_preserves_yaml_alias_without_provider_prefix(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LITELLM_CONFIG": "/tmp/litellm.yaml",
            "AGENT_LITELLM_MODEL": "gpt4o",
            "LITELLM_FALLBACK_MODELS": "deepseek/deepseek-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "gpt4o")
        self.assertEqual(get_effective_agent_primary_model(config), "gpt4o")
        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["gpt4o", "deepseek/deepseek-flash"],
        )

    def test_llm_base_url_rejects_ambiguous_parser_syntax(self) -> None:
        invalid_urls = [
            "https://127.0.0.1:6666\\@1.1.1.1/",
            "https://user@example.com/v1",
            "https://api.example.com/v1 models",
            "https://api.example.com/v1\tmodels",
            "https://api.example.com/v1\x7fmodels",
        ]

        for value in invalid_urls:
            with self.subTest(value=repr(value)):
                self.assertFalse(SystemConfigService._is_valid_llm_base_url(value))

    def test_llm_base_url_rejects_legacy_numeric_ipv4_aliases(self) -> None:
        invalid_urls = [
            "http://2852039166/v1",
            "http://0xa9fea9fe/v1",
            "http://025177524776/v1",
            "http://0251.0376.0251.0376/v1",
            "http://169.254.0xa9fe/v1",
        ]

        for value in invalid_urls:
            with self.subTest(value=value):
                self.assertFalse(SystemConfigService._is_valid_llm_base_url(value))
                self.assertFalse(SystemConfigService._is_safe_base_url(value))

    def test_llm_base_url_blocks_unicode_idna_metadata_aliases(self) -> None:
        restricted_urls = [
            "http://169。254。169。254/v1",
            "http://①⑥⑨.254.169.254/v1",
            "http://metadata。google。internal/v1",
            "http://ｍetadata.google.internal/v1",
        ]

        for value in restricted_urls:
            with self.subTest(value=value):
                self.assertTrue(SystemConfigService._is_valid_llm_base_url(value))
                self.assertFalse(SystemConfigService._is_safe_base_url(value))

    def test_llm_base_url_accepts_common_openai_compatible_and_local_shapes(self) -> None:
        valid_urls = [
            "https://api.openai.com/v1",
            "https://api.deepseek.com/v1",
            "https://api.siliconflow.cn/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "http://127.0.0.1:11434",
            "http://127.0.0.1:11434/v1",
        ]

        for value in valid_urls:
            with self.subTest(value=value):
                self.assertTrue(SystemConfigService._is_valid_llm_base_url(value), msg=value)
                self.assertTrue(SystemConfigService._is_safe_base_url(value), msg=value)

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_blocks_parser_differential_url(self, mock_get) -> None:
        service = SystemConfigService(manager=Mock())

        payload = service.discover_llm_channel_models(
            name="primary",
            protocol="deepseek",
            base_url="https://127.0.0.1:6666\\@1.1.1.1/",
            api_key="sk-test-value",
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_config")
        self.assertEqual(payload["details"]["reason"], "invalid_url")
        mock_get.assert_not_called()

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_blocks_unicode_metadata_alias(self, mock_get) -> None:
        service = SystemConfigService(manager=Mock())

        for value in (
            "http://169。254。169。254/v1",
            "http://①⑥⑨.254.169.254/v1",
        ):
            with self.subTest(value=value):
                payload = service.discover_llm_channel_models(
                    name="primary",
                    protocol="deepseek",
                    base_url=value,
                    api_key="sk-test-value",
                )

                self.assertFalse(payload["success"])
                self.assertEqual(payload["error_code"], "invalid_config")
                self.assertEqual(payload["details"]["reason"], "ssrf_blocked")
                mock_get.assert_not_called()

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_blocks_numeric_metadata_alias(self, mock_get) -> None:
        service = SystemConfigService(manager=Mock())

        payload = service.discover_llm_channel_models(
            name="primary",
            protocol="deepseek",
            base_url="http://2852039166/v1",
            api_key="sk-test-value",
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_config")
        self.assertEqual(payload["details"]["reason"], "invalid_url")
        mock_get.assert_not_called()

    def test_llm_models_url_rechecks_restricted_and_valid_urls(self) -> None:
        restricted_urls = [
            "http://169.254.169.254/v1",
            "http://[::ffff:169.254.169.254]/v1",
            "http://[::ffff:100.100.100.200]/v1",
        ]
        for value in restricted_urls:
            with self.subTest(value=value):
                self.assertTrue(SystemConfigService._is_valid_llm_base_url(value))
                self.assertFalse(SystemConfigService._is_safe_base_url(value))
                with self.assertRaises(ValueError):
                    SystemConfigService._build_llm_models_url(value)

        self.assertEqual(
            SystemConfigService._build_llm_models_url(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions?api-version=1#frag"
            ),
            "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        )


if __name__ == "__main__":
    unittest.main()
