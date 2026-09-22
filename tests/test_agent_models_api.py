# -*- coding: utf-8 -*-
"""Tests for the Agent models discovery service and endpoint."""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.v1.endpoints import agent
from src.config import Config
from src.services.agent_model_service import list_agent_model_deployments


def _build_config(**overrides):
    config = Config(
        litellm_model="deepseek/deepseek-flash",
        litellm_fallback_models=["deepseek/deepseek-flash"],
        llm_model_list=[],
        llm_channels=[],
        litellm_config_path=None,
        llm_models_source="legacy_env",
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


class AgentModelsApiTestCase(unittest.TestCase):
    def test_models_endpoint_returns_litellm_config_deployments(self) -> None:
        config = _build_config(
            litellm_config_path="config/litellm.yaml",
            llm_models_source="litellm_config",
            llm_model_list=[
                {
                    "model_name": "deepseek/deepseek-flash",
                    "litellm_params": {"model": "deepseek/deepseek-flash", "api_key": "secret-1"},
                },
                {
                    "model_name": "openai-fallback",
                    "litellm_params": {"model": "deepseek/deepseek-flash", "api_key": "secret-2"},
                },
            ],
        )

        deployments = list_agent_model_deployments(config)

        self.assertEqual(len(deployments), 2)
        self.assertEqual(deployments[0]["source"], "litellm_config")
        self.assertTrue(deployments[0]["is_primary"])
        self.assertFalse("api_key" in str(deployments))


    def test_models_endpoint_returns_channel_deployments_with_api_base(self) -> None:
        config = _build_config(
            llm_channels=[{"name": "deepseek"}],
            llm_models_source="llm_channels",
            llm_model_list=[
                {
                    "model_name": "deepseek/deepseek-flash",
                    "litellm_params": {
                        "model": "deepseek/deepseek-flash",
                        "api_key": "secret-1",
                        "api_base": "https://api.example.com/v1",
                    },
                }
            ],
        )

        deployments = list_agent_model_deployments(config)

        self.assertEqual(deployments[0]["source"], "llm_channels")
        self.assertEqual(deployments[0]["api_base"], "https://api.example.com/v1")


    def test_models_endpoint_uses_agent_primary_override_for_primary_marker(self) -> None:
        config = _build_config(
            litellm_model="deepseek/deepseek-flash",
            litellm_fallback_models=["deepseek/deepseek-flash"],
            agent_litellm_model="deepseek/deepseek-v4-pro",
            llm_channels=[{"name": "mixed"}],
            llm_models_source="llm_channels",
            llm_model_list=[
                {
                    "model_name": "deepseek/deepseek-flash",
                    "litellm_params": {"model": "deepseek/deepseek-flash", "api_key": "secret-g"},
                },
                {
                    "model_name": "deepseek/deepseek-v4-pro",
                    "litellm_params": {"model": "deepseek/deepseek-v4-pro", "api_key": "secret-o"},
                },
            ],
        )

        deployments = list_agent_model_deployments(config)
        by_model = {item["model"]: item for item in deployments}

        self.assertTrue(by_model["deepseek/deepseek-v4-pro"]["is_primary"])
        self.assertFalse(by_model["deepseek/deepseek-v4-pro"]["is_fallback"])
        self.assertFalse(by_model["deepseek/deepseek-flash"]["is_primary"])
        self.assertTrue(by_model["deepseek/deepseek-flash"]["is_fallback"])

    def test_models_endpoint_resolves_legacy_placeholders_to_real_models(self) -> None:
        config = _build_config(
            llm_model_list=[
                {"model_name": "__legacy_deepseek__", "litellm_params": {"model": "__legacy_deepseek__", "api_key": "g-1"}},
                {"model_name": "__legacy_deepseek__", "litellm_params": {"model": "__legacy_deepseek__", "api_key": "g-2"}},
                {"model_name": "__legacy_deepseek__", "litellm_params": {"model": "__legacy_deepseek__", "api_key": "o-1"}},
            ],
            openai_base_url="https://openai.example.com/v1",
        )

        deployments = list_agent_model_deployments(config)

        self.assertEqual(len(deployments), 3)
        self.assertEqual(deployments[0]["model"], "deepseek/deepseek-flash")
        self.assertEqual(deployments[1]["model"], "deepseek/deepseek-flash")
        self.assertEqual(deployments[2]["model"], "deepseek/deepseek-flash")
        self.assertIsNone(deployments[2]["api_base"])
        self.assertEqual(deployments[2]["source"], "legacy_env")
        self.assertTrue(all(not item["deployment_name"].startswith("__legacy_") for item in deployments))

    def test_models_endpoint_resolves_unprefixed_legacy_deepseek_model_names(self) -> None:
        config = _build_config(
            litellm_model="deepseek/deepseek-flash",
            litellm_fallback_models=[],
            llm_model_list=[
                {"model_name": "__legacy_deepseek__", "litellm_params": {"model": "__legacy_deepseek__", "api_key": "o-1"}},
            ],
            openai_base_url="https://openai.example.com/v1",
        )

        deployments = list_agent_model_deployments(config)

        self.assertEqual(len(deployments), 1)
        self.assertEqual(deployments[0]["model"], "deepseek/deepseek-flash")
        self.assertEqual(deployments[0]["provider"], "deepseek")
        self.assertEqual(deployments[0]["source"], "legacy_env")
        self.assertIsNone(deployments[0]["api_base"])

    def test_models_endpoint_expands_deepseek_keys_for_each_model(self) -> None:
        config = _build_config(
            litellm_fallback_models=["deepseek/deepseek-v4-pro"],
            llm_model_list=Config._deepseek_keys_to_model_list(["sk-first-key", "sk-second-key"]),
        )
        deployments = list_agent_model_deployments(config)
        self.assertEqual(len(deployments), 3)
        self.assertEqual(sum(item["is_primary"] for item in deployments), 2)
        self.assertEqual(sum(item["is_fallback"] for item in deployments), 1)
        self.assertNotIn("api_key", str(deployments))



    def test_models_endpoint_returns_empty_list_when_no_model_is_configured(self) -> None:
        config = _build_config(
            litellm_model="",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        self.assertEqual(list_agent_model_deployments(config), [])


class AgentModelsEndpointTestCase(unittest.TestCase):
    def test_endpoint_returns_sorted_models_without_secrets(self) -> None:
        config = _build_config(
            litellm_fallback_models=["deepseek/deepseek-v4-pro"],
            llm_channels=[{"name": "primary"}, {"name": "secondary"}],
            llm_model_list=[
                {
                    "model_name": "deepseek/deepseek-flash",
                    "litellm_params": {
                        "model": "deepseek/deepseek-flash",
                        "api_key": "secret-openai",
                        "api_base": "https://api.openai.example/v1",
                    },
                },
                {
                    "model_name": "deepseek/deepseek-v4-pro",
                    "litellm_params": {
                        "model": "deepseek/deepseek-v4-pro",
                        "api_key": "secret-gemini",
                    },
                },
            ],
        )

        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            payload = asyncio.run(agent.get_agent_models()).model_dump()

        self.assertEqual(len(payload["models"]), 2)
        self.assertEqual(payload["models"][0]["model"], "deepseek/deepseek-flash")
        self.assertTrue(payload["models"][0]["is_primary"])
        self.assertEqual(payload["models"][1]["model"], "deepseek/deepseek-v4-pro")
        self.assertTrue(payload["models"][1]["is_fallback"])
        self.assertNotIn("api_key", str(payload))


class AgentSkillsEndpointTestCase(unittest.TestCase):
    def test_skills_endpoint_returns_skill_metadata_shape(self) -> None:
        config = _build_config()
        skill_manager = SimpleNamespace(
            list_skills=lambda: [
                SimpleNamespace(
                    name="bull_trend",
                    display_name="多头趋势",
                    description="趋势跟随",
                    user_invocable=True,
                    default_priority=20,
                    default_active=True,
                ),
                SimpleNamespace(
                    name="chan_theory",
                    display_name="缠论",
                    description="结构分析",
                    user_invocable=True,
                    default_priority=40,
                    default_active=False,
                ),
            ]
        )

        with patch("api.v1.endpoints.agent.get_config", return_value=config), patch(
            "src.agent.factory.get_skill_manager",
            return_value=skill_manager,
        ):
            payload = asyncio.run(agent.get_skills()).model_dump()

        self.assertEqual(payload["default_skill_id"], "bull_trend")
        self.assertEqual([item["id"] for item in payload["skills"]], ["bull_trend", "chan_theory"])

    def test_legacy_strategies_endpoint_preserves_legacy_field_names(self) -> None:
        config = _build_config()
        skill_manager = SimpleNamespace(
            list_skills=lambda: [
                SimpleNamespace(
                    name="bull_trend",
                    display_name="多头趋势",
                    description="趋势跟随",
                    user_invocable=True,
                    default_priority=20,
                    default_active=True,
                ),
            ]
        )

        with patch("api.v1.endpoints.agent.get_config", return_value=config), patch(
            "src.agent.factory.get_skill_manager",
            return_value=skill_manager,
        ):
            payload = asyncio.run(agent.get_strategies()).model_dump()

        self.assertNotIn("skills", payload)
        self.assertEqual(payload["default_strategy_id"], "bull_trend")
        self.assertEqual(
            payload["strategies"],
            [
                {
                    "id": "bull_trend",
                    "name": "多头趋势",
                    "description": "趋势跟随",
                }
            ],
        )

    def test_chat_context_without_effective_skills_discards_legacy_selection_fields(self) -> None:
        request = agent.ChatRequest(
            message="hello",
            context={
                "stock_code": "600519",
                "skills": ["old_skill"],
                "strategies": ["older_strategy"],
            },
        )

        context = agent._build_agent_chat_context(
            request,
            SimpleNamespace(report_language="zh"),
            skills=None,
        )

        self.assertEqual(context["stock_code"], "600519")
        self.assertNotIn("skills", context)
        self.assertNotIn("strategies", context)

    def test_chat_request_empty_skills_clears_context_without_triggering_activate_all(self) -> None:
        config = SimpleNamespace(
            is_agent_available=lambda: True,
            report_language="zh",
        )
        executor = MagicMock()
        executor.chat.return_value = SimpleNamespace(success=True, content="ok", error=None)
        request = agent.ChatRequest(
            message="hello",
            skills=[],
            context={"skills": ["old_skill"], "strategies": ["older_strategy"]},
        )
        real_get_running_loop = asyncio.get_running_loop

        class _ImmediateLoop:
            def __init__(self, loop):
                self._loop = loop

            def run_in_executor(self, _executor, func):
                future = self._loop.create_future()
                future.set_result(func())
                return future

        with patch("api.v1.endpoints.agent.get_config", return_value=config), patch(
            "api.v1.endpoints.agent._build_executor",
            return_value=executor,
        ) as mock_build_executor, patch(
            "api.v1.endpoints.agent.asyncio.get_running_loop",
            side_effect=lambda: _ImmediateLoop(real_get_running_loop()),
        ):
            payload = asyncio.run(
                agent.agent_chat(
                    request,
                    session_service=agent.AgentChatSessionService(),
                )
            ).model_dump()

        mock_build_executor.assert_called_once_with(config, None)
        executor.chat.assert_called_once()
        self.assertEqual(executor.chat.call_args.kwargs["context"]["skills"], [])
        self.assertNotIn("strategies", executor.chat.call_args.kwargs["context"])
        self.assertEqual(executor.chat.call_args.kwargs["selected_skill_ids"], [])
        self.assertEqual(payload["content"], "ok")
class AgentModelsSourceDetectionTestCase(unittest.TestCase):
    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_load_from_env_marks_channels_as_actual_source_after_yaml_fallback(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "LITELLM_CONFIG": "config/missing.yaml",
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_API_KEY": "channel-secret-key",
            "LLM_PRIMARY_MODELS": "deepseek/deepseek-flash",
                        "AIHUBMIX_KEY": "",
                                            }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["model"], "deepseek/deepseek-flash")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_load_from_env_marks_legacy_as_actual_source_after_yaml_fallback(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        env = {
            "LITELLM_CONFIG": "config/missing.yaml",
            "LLM_CHANNELS": "",
            "DEEPSEEK_API_KEY": "legacy-openai-key",
            "LITELLM_MODEL": "deepseek/deepseek-flash",
            "AIHUBMIX_KEY": "",
                                            }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "legacy_env")
        self.assertTrue(config.llm_model_list)
        self.assertEqual(config.llm_model_list[0]["model_name"], "__legacy_deepseek__")


if __name__ == "__main__":
    unittest.main()
