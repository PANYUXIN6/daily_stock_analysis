# -*- coding: utf-8 -*-
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.litellm_stub import ensure_litellm_stub, remove_litellm_stub

remove_litellm_stub()
try:
    from litellm.types.utils import Usage
except ModuleNotFoundError:
    ensure_litellm_stub()
    from litellm.types.utils import Usage

from src.agent.llm_adapter import LLMToolAdapter  # noqa: E402


def test_convert_messages_preserves_reasoning_blocks_and_provider_specific_fields() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    messages = [
        {
            "role": "assistant",
            "content": "checking",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-flash",
            "provider_blocks": [
                {"type": "thinking", "thinking": "opaque"},
                {"type": "redacted_thinking", "data": "redacted"},
                {"type": "text", "text": "checking"},
            ],
            "reasoning_content": "reasoning",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "echo",
                    "arguments": {"message": "hello"},
                    "thought_signature": "sig-1",
                    "provider_specific_fields": {"thought_signature": "sig-1", "extra": "keep"},
                }
            ],
        }
    ]

    converted = adapter._convert_messages(messages)

    assert converted[0]["role"] == "assistant"
    assert converted[0]["content"][0]["type"] == "thinking"
    assert converted[0]["reasoning_content"] == "reasoning"
    assert converted[0]["tool_calls"][0]["provider_specific_fields"] == {
        "thought_signature": "sig-1",
        "extra": "keep",
    }
    assert "_trace_provider" not in converted[0]


def test_convert_messages_only_sends_provider_trace_to_matching_target_model() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    messages = [
        {
            "role": "assistant",
            "content": "checking",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-flash",
            "provider_blocks": [{"type": "thinking", "thinking": "opaque"}],
            "reasoning_content": "provider-only",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "echo",
                    "arguments": {"message": "hello"},
                    "thought_signature": "sig-1",
                    "provider_specific_fields": {"thought_signature": "sig-1"},
                }
            ],
        }
    ]

    matching = adapter._convert_messages(messages, target_model="deepseek/deepseek-flash")
    mismatched = adapter._convert_messages(messages, target_model="deepseek/deepseek-v4-pro")

    assert matching[0]["content"] == [{"type": "thinking", "thinking": "opaque"}]
    assert matching[0]["reasoning_content"] == "provider-only"
    assert matching[0]["tool_calls"][0]["provider_specific_fields"] == {"thought_signature": "sig-1"}

    assert mismatched == []


def test_convert_messages_skips_entire_trace_segment_for_mismatched_attempt() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    messages = [
        {"role": "user", "content": "u1"},
        {
            "role": "assistant",
            "content": "checking",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": "provider-only",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "echo",
                    "arguments": {"message": "hello"},
                    "provider_specific_fields": {"thought_signature": "sig-1"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "tool-result",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
        },
        {"role": "assistant", "content": "a1-final"},
    ]

    primary = adapter._convert_messages(messages, target_model="deepseek/deepseek-flash")
    fallback = adapter._convert_messages(messages, target_model="deepseek/deepseek-chat")

    assert [msg["role"] for msg in primary] == ["user", "assistant"]
    assert primary[-1]["content"] == "a1-final"
    assert all(msg.get("tool_call_id") != "call_1" for msg in primary)

    assert [msg["role"] for msg in fallback] == ["user", "assistant", "tool", "assistant"]
    assert fallback[1]["reasoning_content"] == "provider-only"
    assert fallback[1]["tool_calls"][0]["provider_specific_fields"] == {"thought_signature": "sig-1"}
    assert fallback[2]["tool_call_id"] == "call_1"


def test_convert_messages_matches_slashless_openai_target_without_provider_leakage() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    messages = [
        {
            "role": "assistant",
            "content": "checking",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-flash",
            "reasoning_content": "provider-only",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "echo",
                    "arguments": {},
                    "provider_specific_fields": {"thought_signature": "sig-1"},
                }
            ],
        }
    ]

    matching = adapter._convert_messages(messages, target_model="deepseek/deepseek-flash")
    mismatched = adapter._convert_messages(messages, target_model="deepseek/deepseek-v4-pro")

    assert matching[0]["reasoning_content"] == "provider-only"
    assert matching[0]["tool_calls"][0]["provider_specific_fields"] == {"thought_signature": "sig-1"}
    assert mismatched == []




def test_parse_litellm_response_resolves_provider_for_slashless_router_alias() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = SimpleNamespace(
        llm_model_list=[
            {
                "model_name": "deepseek/deepseek-flash",
                "litellm_params": {"model": "deepseek/deepseek-v4-pro"},
            }
        ]
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="ok",
                    reasoning_content=None,
                    tool_calls=[],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )

    parsed_alias = adapter._parse_litellm_response(response, "deepseek/deepseek-flash")
    parsed_bare_openai = adapter._parse_litellm_response(response, "deepseek/deepseek-flash")

    assert parsed_alias.provider == "deepseek"
    assert parsed_alias.model == "deepseek/deepseek-flash"
    assert parsed_bare_openai.provider == "deepseek"
    assert parsed_bare_openai.model == "deepseek/deepseek-flash"




def test_parse_litellm_response_normalizes_litellm_usage_object(monkeypatch) -> None:
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "adapter-usage-object-secret")
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = SimpleNamespace(llm_model_list=[])
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="ok",
                    reasoning_content=None,
                    tool_calls=[],
                )
            )
        ],
        usage=Usage(
            prompt_tokens=2000,
            completion_tokens=100,
            total_tokens=2100,
            prompt_cache_hit_tokens=500, prompt_cache_miss_tokens=1500,
        ),
    )

    parsed = adapter._parse_litellm_response(
        response,
        "deepseek/deepseek-flash",
        [{"role": "user", "content": "hello"}],
    )

    assert parsed.provider == "deepseek"
    assert parsed.usage["prompt_tokens"] == 2000
    assert parsed.usage["completion_tokens"] == 100
    assert parsed.usage["total_tokens"] == 2100
    assert parsed.usage["normalized_cache_read_tokens"] == 500
    assert parsed.usage["cache_capability"] == "supported"
    assert parsed.usage["cache_observation"] == "partial_hit"
    assert parsed.usage["messages_hmac"]


def test_parse_litellm_response_reads_private_hidden_usage_best_effort(monkeypatch) -> None:
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "adapter-hidden-usage-secret")
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = SimpleNamespace(llm_model_list=[])
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="ok",
                    reasoning_content=None,
                    tool_calls=[],
                )
            )
        ],
        usage=None,
        _hidden_params={
            "usage": Usage(
                prompt_tokens=2000,
                completion_tokens=100,
                total_tokens=2100,
                prompt_cache_hit_tokens=500, prompt_cache_miss_tokens=1500,
            )
        },
    )

    parsed = adapter._parse_litellm_response(
        response,
        "deepseek/deepseek-flash",
        [{"role": "user", "content": "hello"}],
    )

    assert parsed.usage["prompt_tokens"] == 2000
    assert parsed.usage["completion_tokens"] == 100
    assert parsed.usage["total_tokens"] == 2100
    assert parsed.usage["normalized_cache_read_tokens"] == 500
    assert parsed.usage["provider_usage_json"]
    assert parsed.usage["messages_hmac"]




def test_parse_litellm_response_without_provider_usage_keeps_usage_empty() -> None:
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = SimpleNamespace(llm_model_list=[])
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="ok",
                    reasoning_content=None,
                    tool_calls=[],
                )
            )
        ],
    )

    parsed = adapter._parse_litellm_response(
        response,
        "deepseek/deepseek-flash",
        [{"role": "user", "content": "hello"}],
    )

    assert parsed.usage == {}




def test_parse_litellm_response_hmac_covers_tool_call_wire_messages(monkeypatch) -> None:
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "agent-tool-secret")
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = SimpleNamespace(llm_model_list=[])

    def _response() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="ok",
                        reasoning_content=None,
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

    first_messages = [
        {
            "role": "assistant",
            "content": "same",
            "tool_calls": [
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                    "provider_specific_fields": {"thought_signature": "sig-a"},
                }
            ],
        }
    ]
    second_messages = [
        {
            "role": "assistant",
            "content": "same",
            "tool_calls": [
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"n":1}'},
                    "provider_specific_fields": {"thought_signature": "sig-b"},
                }
            ],
        }
    ]

    first = adapter._parse_litellm_response(_response(), "deepseek/deepseek-flash", first_messages)
    second = adapter._parse_litellm_response(_response(), "deepseek/deepseek-flash", second_messages)

    assert first.usage["messages_hmac"]
    assert second.usage["messages_hmac"]
    assert first.usage["messages_hmac"] != second.usage["messages_hmac"]
