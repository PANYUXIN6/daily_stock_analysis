# -*- coding: utf-8 -*-
"""Compatibility assertions for market review runtime assembly."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.core.market_review_runtime import build_market_review_runtime, has_configured_llm_runtime
from src.llm.generation_backend import GenerationError, GenerationErrorCode


class _FakeAnalyzer:
    def __init__(self, *, backend_error=None, available: bool = True) -> None:
        self.backend_error = backend_error
        self.available = available
        self.backend_error_calls = 0
        self.available_calls = 0

    def get_generation_backend_config_error(self):
        self.backend_error_calls += 1
        return self.backend_error

    def is_available(self) -> bool:
        self.available_calls += 1
        return self.available


class TestMarketReviewRuntimeCompatibility(unittest.TestCase):
    @staticmethod
    def _base_config() -> SimpleNamespace:
        return SimpleNamespace(
            litellm_model="",
            llm_model_list=[],
            deepseek_api_keys=[],
            deepseek_api_key=None,
            bocha_api_keys=None,
            tavily_api_keys=None,


            news_max_age_days=3,
            news_strategy_profile="short",
            has_search_capability_enabled=lambda: False,

        )

    def test_build_market_review_runtime_includes_legacy_provider_configs(self) -> None:
        config = self._base_config()
        config.deepseek_api_keys = ["test-deepseek-key"]
        notifier = MagicMock()
        analyzer = MagicMock()
        analyzer.is_available.return_value = True

        with patch("src.analyzer.DeepSeekAnalyzer", return_value=analyzer) as analyzer_cls, \
             patch("src.notification.NotificationService", return_value=notifier) as notifier_cls, \
             patch("src.search_service.SearchService") as search_cls:
            runtime_notifier, runtime_analyzer, runtime_search = build_market_review_runtime(config)

        notifier_cls.assert_called_once_with(source_message=None)
        analyzer_cls.assert_called_once_with(config=config)
        search_cls.assert_not_called()
        self.assertIs(runtime_notifier, notifier)
        self.assertIs(runtime_analyzer, analyzer)
        self.assertIsNone(runtime_search)


    def test_build_market_review_runtime_supports_litellm_channel_model_list(self) -> None:
        config = self._base_config()
        config.litellm_model = ""
        config.llm_model_list = [
            {
                "model_name": "deepseek/deepseek-v4-pro",
                "litellm_params": {
                    "api_key": "openai-channel-key",
                    "model": "deepseek/deepseek-v4-pro",
                    "api_base": "https://api.openrouter.ai/v1",
                },
            }
        ]
        notifier = MagicMock()
        analyzer = MagicMock()
        analyzer.is_available.return_value = True

        with patch("src.analyzer.DeepSeekAnalyzer", return_value=analyzer) as analyzer_cls, \
             patch("src.notification.NotificationService", return_value=notifier) as notifier_cls, \
             patch("src.search_service.SearchService") as search_cls:
            runtime_notifier, runtime_analyzer, runtime_search = build_market_review_runtime(config)

        notifier_cls.assert_called_once_with(source_message=None)
        analyzer_cls.assert_called_once_with(config=config)
        search_cls.assert_not_called()
        self.assertIs(runtime_notifier, notifier)
        self.assertIs(runtime_analyzer, analyzer)
        self.assertIsNone(runtime_search)

    def test_build_market_review_runtime_supports_explicit_litellm_model_only(self) -> None:
        config = self._base_config()
        config.litellm_model = "deepseek/deepseek-v4-pro"

        notifier = MagicMock()
        analyzer = MagicMock()
        analyzer.is_available.return_value = True

        with patch("src.analyzer.DeepSeekAnalyzer", return_value=analyzer) as analyzer_cls, \
             patch("src.notification.NotificationService", return_value=notifier) as notifier_cls, \
             patch("src.search_service.SearchService") as search_cls:
            runtime_notifier, runtime_analyzer, runtime_search = build_market_review_runtime(config)

        notifier_cls.assert_called_once_with(source_message=None)
        analyzer_cls.assert_called_once_with(config=config)
        search_cls.assert_not_called()
        self.assertIs(runtime_notifier, notifier)
        self.assertIs(runtime_analyzer, analyzer)
        self.assertIsNone(runtime_search)

    def test_build_market_review_runtime_preserves_backend_config_error_analyzer(self) -> None:
        config = self._base_config()
        config.deepseek_api_keys = ["test-deepseek-key"]
        backend_error = GenerationError(
            error_code=GenerationErrorCode.UNSAFE_CONFIG,
            stage="generation",
            retryable=False,
            fallbackable=False,
            backend="litellm",
            details={
                "field": "LLM_CHANNELS",
                "code": "invalid_api_surface",
            },
        )
        notifier = MagicMock()
        analyzer = _FakeAnalyzer(backend_error=backend_error, available=False)

        with patch("src.analyzer.DeepSeekAnalyzer", return_value=analyzer), \
             patch("src.notification.NotificationService", return_value=notifier), \
             patch("src.search_service.SearchService") as search_cls:
            runtime_notifier, runtime_analyzer, runtime_search = build_market_review_runtime(config)

        self.assertIs(runtime_notifier, notifier)
        self.assertIs(runtime_analyzer, analyzer)
        self.assertIsNone(runtime_search)
        self.assertEqual(analyzer.backend_error_calls, 1)
        self.assertEqual(analyzer.available_calls, 0)
        search_cls.assert_not_called()


    def test_build_market_review_runtime_drops_unavailable_analyzer_without_backend_error(self) -> None:
        config = self._base_config()
        config.deepseek_api_keys = ["test-deepseek-key"]
        notifier = MagicMock()
        analyzer = _FakeAnalyzer(backend_error=None, available=False)

        with patch("src.analyzer.DeepSeekAnalyzer", return_value=analyzer), \
             patch("src.notification.NotificationService", return_value=notifier), \
             patch("src.search_service.SearchService") as search_cls:
            runtime_notifier, runtime_analyzer, runtime_search = build_market_review_runtime(config)

        self.assertIs(runtime_notifier, notifier)
        self.assertIsNone(runtime_analyzer)
        self.assertIsNone(runtime_search)
        self.assertEqual(analyzer.backend_error_calls, 1)
        self.assertEqual(analyzer.available_calls, 1)
        search_cls.assert_not_called()

    def test_has_configured_llm_runtime_returns_false_without_any_model_source(self) -> None:
        config = self._base_config()
        self.assertFalse(has_configured_llm_runtime(config))


    def test_has_configured_llm_runtime_supports_deepseek_sources(self) -> None:
        for key, value in [("deepseek_api_keys", ["test-key"]), ("litellm_model", "deepseek/deepseek-flash"), ("llm_model_list", [{"model_name": "analysis"}])]:
            config = self._base_config()
            setattr(config, key, value)
            self.assertTrue(has_configured_llm_runtime(config))
