# -*- coding: utf-8 -*-
"""AgentBackend contract, LiteLLM parity, and cloud execution tests."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.agent.agent_backend import (
    AgentRunRequest,
    AgentRunResult,
    LiteLLMAgentBackend,
)
from src.agent.chat_executor import AgentChatExecutor
from src.agent.factory import get_tool_registry
from src.agent.llm_adapter import LLMResponse
from src.agent.runner import run_agent_loop
from src.agent.stock_scope import StockScope
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import ToolDefinition, ToolPolicy, ToolRegistry


class _FinalAnswerAdapter:
    def __init__(self) -> None:
        self.calls = []

    def call_with_tools(self, messages, tools, timeout=None):
        self.calls.append((messages, tools, timeout))
        return LLMResponse(content="answer", provider="deepseek", model="deepseek/chat")


def _request(**overrides):
    values = {
        "system_prompt": "system",
        "history_messages": [{"role": "assistant", "content": "history"}],
        "user_message": "question",
        "session_id": "session-1",
        "stock_scope": None,
        "max_steps": 3,
        "max_wall_clock_seconds": 30,
        "progress_callback": None,
        "cancel_event": None,
    }
    values.update(overrides)
    return AgentRunRequest(**values)


def test_agent_run_request_does_not_carry_tool_dependencies() -> None:
    names = {item.name for item in fields(AgentRunRequest)}
    assert "tool_registry" not in names
    assert "tool_surface" not in names


def test_agent_run_result_contains_only_consumed_terminal_state() -> None:
    names = {item.name for item in fields(AgentRunResult)}
    assert "session_id" not in names
    assert "finish_reason" not in names


def test_litellm_multi_chat_keeps_existing_orchestrator_factory() -> None:
    sentinel = object()
    with patch("src.agent.factory.build_agent_executor", return_value=sentinel) as build_existing:
        from src.agent.factory import build_agent_chat_executor

        result = build_agent_chat_executor(
            SimpleNamespace(agent_arch="multi"),
            skills=["bull_trend"],
        )

    assert result is sentinel
    build_existing.assert_called_once()


def test_litellm_backend_matches_existing_runner_result() -> None:
    registry = ToolRegistry()
    direct_events = []
    wrapped_events = []
    direct = run_agent_loop(
        messages=[
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "history"},
            {"role": "user", "content": "question"},
        ],
        tool_registry=registry,
        llm_adapter=_FinalAnswerAdapter(),
        max_steps=3,
        progress_callback=direct_events.append,
        max_wall_clock_seconds=30,
    )
    wrapped = LiteLLMAgentBackend(registry, _FinalAnswerAdapter()).run(
        _request(progress_callback=wrapped_events.append)
    )

    assert wrapped.success == direct.success
    assert wrapped.final_answer == direct.content
    assert wrapped.tool_calls_log == direct.tool_calls_log
    assert wrapped.total_steps == direct.total_steps
    assert wrapped.model == direct.model
    assert wrapped.diagnostics["provider"] == direct.provider
    assert wrapped.error_message == direct.error
    assert wrapped.messages == direct.messages
    assert wrapped.usage == (
        {"total_tokens": direct.total_tokens} if direct.total_tokens > 0 else None
    )
    assert wrapped_events == direct_events
    assert wrapped.backend == "litellm"


def test_litellm_preparation_keeps_the_existing_chat_workflow() -> None:
    backend = LiteLLMAgentBackend(ToolRegistry(), _FinalAnswerAdapter())
    executor = AgentChatExecutor(
        backend=backend,
        config=SimpleNamespace(),
        context_llm_adapter=object(),
    )

    with patch("src.agent.executor.build_agent_chat_context_bundle") as build_context, patch(
        "src.agent.chat_executor.conversation_manager.get_or_create"
    ), patch(
        "src.agent.chat_executor.conversation_manager.add_message",
        return_value=1,
    ):
        build_context.return_value.context_messages = []
        turn = executor.prepare_turn(
            message="分析 600519",
            session_id="session-1",
            context={"stock_code": "600519"},
        )

    assert "get_realtime_quote" in turn.prepared.system_prompt
    assert "get_daily_history" in turn.prepared.system_prompt
    assert "analyze_trend" in turn.prepared.system_prompt
    assert "get_chip_distribution" not in turn.prepared.system_prompt
    assert "search_stock_news" in turn.prepared.system_prompt
