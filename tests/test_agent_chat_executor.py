# -*- coding: utf-8 -*-
"""Backend-neutral Chat preparation and persistence boundary tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from src.agent.agent_backend import AgentRunResult
from src.agent.chat_executor import AgentChatExecutor
from src.agent.executor import PreparedAgentChat


class _Backend:
    def __init__(self) -> None:
        self.backend_id = "litellm"
        self.request = None

    def run(self, request):
        self.request = request
        return AgentRunResult(
            success=True,
            final_answer="answer",
            backend="litellm",
            model="model",
            messages=[{"role": "assistant", "content": "answer"}],
            total_steps=1,
        )


def _failure_backend(
    *,
    error_code: str,
    error_message: str,
) -> _Backend:
    backend = _Backend()
    backend.run = lambda _request: AgentRunResult(
        success=False,
        backend="litellm",
        error_code=error_code,
        error_message=error_message,
        total_steps=1,
    )
    return backend


def _executor(backend: _Backend) -> AgentChatExecutor:
    return AgentChatExecutor(
        backend=backend,
        config=SimpleNamespace(),
        context_llm_adapter=object(),
        max_steps=7,
        timeout_seconds=45,
    )


def test_dsa_owned_backend_keeps_provider_trace_roundtrip() -> None:
    backend = _Backend()
    prepared = PreparedAgentChat(
        system_prompt="system",
        history_messages=[{"role": "assistant", "content": "provider trace"}],
        stock_scope=None,
    )
    with patch("src.agent.chat_executor.prepare_agent_chat", return_value=prepared) as prepare, \
         patch("src.agent.chat_executor.conversation_manager.get_or_create"), \
         patch("src.agent.chat_executor.conversation_manager.add_user_message", return_value=11), \
         patch("src.agent.chat_executor.conversation_manager.add_message", return_value=12), \
         patch("src.agent.chat_executor.persist_provider_trace_turns") as persist_trace:
        result = _executor(backend).chat("question", "session")

    assert result.backend == "litellm"
    assert prepare.call_args.kwargs["include_provider_trace"] is True
    persist_trace.assert_called_once()
    assert persist_trace.call_args.kwargs["baseline_len"] == 3
    assert persist_trace.call_args.kwargs["user_message_id"] == 11
    assert persist_trace.call_args.kwargs["assistant_message_id"] == 12


def test_timed_out_litellm_turn_keeps_existing_analysis_failure_note() -> None:
    backend = _failure_backend(
        error_code="timeout",
        error_message="Agent execution timed out after 45 seconds",
    )
    prepared = PreparedAgentChat(
        system_prompt="system",
        history_messages=[],
        stock_scope=None,
    )
    with patch("src.agent.chat_executor.prepare_agent_chat", return_value=prepared), \
         patch("src.agent.chat_executor.conversation_manager.get_or_create"), \
         patch("src.agent.chat_executor.conversation_manager.add_user_message", return_value=1), \
         patch("src.agent.chat_executor.conversation_manager.add_message", return_value=2) as add_message:
        result = _executor(backend).chat("question", "session")

    assert result.error_code == "timeout"
    assert add_message.call_args_list[-1].args == (
        "session",
        "assistant",
        "[分析失败] Agent execution timed out after 45 seconds",
    )


def test_failed_litellm_turn_keeps_existing_analysis_failure_note() -> None:
    backend = _failure_backend(
        error_code="unknown_backend_error",
        error_message="provider failed",
    )
    prepared = PreparedAgentChat(
        system_prompt="system",
        history_messages=[],
        stock_scope=None,
    )
    with patch("src.agent.chat_executor.prepare_agent_chat", return_value=prepared), \
         patch("src.agent.chat_executor.conversation_manager.get_or_create"), \
         patch("src.agent.chat_executor.conversation_manager.add_user_message", return_value=1), \
         patch("src.agent.chat_executor.conversation_manager.add_message", return_value=2) as add_message:
        result = _executor(backend).chat("question", "session")

    assert result.error_code == "unknown_backend_error"
    assert add_message.call_args_list[-1].args == (
        "session",
        "assistant",
        "[分析失败] provider failed",
    )


def test_context_preparation_failure_does_not_persist_or_start_backend() -> None:
    backend = _Backend()
    with patch(
        "src.agent.chat_executor.prepare_agent_chat",
        side_effect=RuntimeError("context preparation failed"),
    ), patch("src.agent.chat_executor.conversation_manager.get_or_create"), patch(
        "src.agent.chat_executor.conversation_manager.add_user_message"
    ) as add_user_message:
        try:
            _executor(backend).prepare_turn(message="question", session_id="session")
        except RuntimeError as exc:
            assert str(exc) == "context preparation failed"
        else:
            raise AssertionError("context preparation failure must propagate")

    add_user_message.assert_not_called()
    assert backend.request is None


def test_user_message_persistence_failure_does_not_start_backend() -> None:
    backend = _Backend()
    prepared = PreparedAgentChat(
        system_prompt="system",
        history_messages=[],
        stock_scope=None,
    )
    with patch("src.agent.chat_executor.prepare_agent_chat", return_value=prepared), patch(
        "src.agent.chat_executor.conversation_manager.get_or_create"
    ), patch(
        "src.agent.chat_executor.conversation_manager.add_user_message",
        side_effect=RuntimeError("database write failed"),
    ):
        try:
            _executor(backend).prepare_turn(message="question", session_id="session")
        except RuntimeError as exc:
            assert str(exc) == "database write failed"
        else:
            raise AssertionError("database failure must propagate")

    assert backend.request is None
