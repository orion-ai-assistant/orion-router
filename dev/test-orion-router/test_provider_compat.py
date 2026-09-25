"""Provider payload compatibility checks without external API calls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from google.genai import types

from providers.gemini.chat import GeminiChatProvider, _gemini_schema
from providers.openai.chat import OpenAIChatProvider


class FakeResponse:
    def __init__(self, status=200, events=(), error=b""):
        self.status_code = status
        self.events = events
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def aread(self):
        return self.error

    async def aiter_lines(self):
        for event in self.events:
            yield "data: " + json.dumps(event)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def stream(self, method, url, json, headers, timeout):
        self.requests.append((url, json))
        return next(self.responses)


def collect_stream(client, **kwargs):
    async def run():
        with patch("providers.openai.chat.get_http_client", return_value=client):
            return [chunk async for chunk in OpenAIChatProvider().stream_chat(
                "model-under-test", [{"role": "user", "content": "hello"}], api_key="test", **kwargs
            )]

    return asyncio.run(run())


def test_gemini_schema_removes_unsupported_keywords_recursively():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "propertyNames": {"pattern": "^[a-z]+$"},
        "properties": {
            "additionalProperties": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object", "additional_properties": False}},
        },
    }
    cleaned = _gemini_schema(schema)
    assert "additionalProperties" not in cleaned
    assert "propertyNames" not in cleaned
    assert "additionalProperties" in cleaned["properties"]
    assert "additional_properties" not in cleaned["properties"]["items"]["items"]


def test_openai_reasoning_uses_responses_for_tools():
    events = [
        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "call_id": "call_1", "name": "weather", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"city":"Paris"}'},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 10, "output_tokens": 8, "output_tokens_details": {"reasoning_tokens": 3}}}},
    ]
    client = FakeClient([FakeResponse(events=events)])
    chunks = collect_stream(client, thinking_level="low", temperature=0.7, tools=[
        {"type": "function", "function": {"name": "weather", "description": "Get weather", "parameters": {"type": "object"}}}
    ])
    url, payload = client.requests[0]
    assert url.endswith("/v1/responses")
    assert payload["reasoning"] == {"effort": "low"}
    assert "temperature" not in payload
    assert payload["tools"][0]["name"] == "weather"
    assert any(isinstance(chunk, str) and '"call_1"' in chunk for chunk in chunks)
    assert any(isinstance(chunk, dict) and chunk["internal_usage"]["thoughts_tokens"] == 3 for chunk in chunks)


def test_openai_retries_unsupported_reasoning_effort_without_it():
    client = FakeClient([
        FakeResponse(status=400, error=b"Unrecognized parameter: reasoning_effort"),
        FakeResponse(events=[{"choices": [{"delta": {"content": "ok"}}]}]),
    ])
    chunks = collect_stream(client, thinking_level="low", temperature=0.7)
    assert len(client.requests) == 2
    assert "reasoning_effort" in client.requests[0][1]
    assert "temperature" not in client.requests[0][1]
    assert "reasoning_effort" not in client.requests[1][1]
    assert client.requests[1][1]["temperature"] == 0.7
    assert any(isinstance(chunk, str) and '"content": "ok"' in chunk for chunk in chunks)


def test_openai_tool_endpoint_falls_back_to_responses():
    client = FakeClient([
        FakeResponse(status=400, error=b"Tool calling requires the Responses API"),
        FakeResponse(events=[{"type": "response.output_text.delta", "delta": "ok"}]),
    ])
    chunks = collect_stream(client, tools=[
        {"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}
    ])
    assert client.requests[0][0].endswith("/v1/chat/completions")
    assert client.requests[1][0].endswith("/v1/responses")
    assert any(isinstance(chunk, str) and '"content": "ok"' in chunk for chunk in chunks)


def test_responses_history_preserves_function_call_ids():
    items = OpenAIChatProvider._responses_input([
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "function": {"name": "weather", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
    ])
    assert items[0] == {"type": "function_call", "call_id": "call_1", "name": "weather", "arguments": "{}"}
    assert items[1] == {"type": "function_call_output", "call_id": "call_1", "output": "sunny"}


def test_responses_retries_unsupported_none_effort():
    client = FakeClient([
        FakeResponse(status=400, error=b"Tool calling requires the Responses API"),
        FakeResponse(status=400, error=b"Reasoning effort 'none' is not supported"),
        FakeResponse(events=[{"type": "response.output_text.delta", "delta": "ok"}]),
    ])
    chunks = collect_stream(client, thinking_level="off", tools=[
        {"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}
    ])
    # Chat Completions is attempted first when reasoning is explicitly off.
    assert client.requests[0][0].endswith("/v1/chat/completions")
    assert client.requests[1][1]["reasoning"] == {"effort": "none"}
    assert "reasoning" not in client.requests[2][1]
    assert any(isinstance(chunk, str) and '"content": "ok"' in chunk for chunk in chunks)


def test_gemini_preserves_thought_signature_in_tool_history():
    first = types.Part.from_function_call(name="weather", args={"city": "Paris"})
    first.thought_signature = b"opaque-signature"
    second = types.Part.from_function_call(name="time", args={})
    captured = []

    async def generate_content_stream(**kwargs):
        captured.append(kwargs)

        async def events():
            if len(captured) == 1:
                yield SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[first, second]))], usage_metadata=None)

        return events()

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream)))

    async def run():
        provider = GeminiChatProvider()
        with patch("providers.gemini.chat.get_gemini_client", return_value=client):
            chunks = [chunk async for chunk in provider.stream_chat("gemini-test", [{"role": "user", "content": "hello"}], api_key="test")]
            calls = [json.loads(chunk[6:])["choices"][0]["delta"]["tool_calls"][0] for chunk in chunks if isinstance(chunk, str) and "tool_calls" in chunk]
            assert [call["index"] for call in calls] == [0, 1]
            history = [
                {"role": "assistant", "content": None, "tool_calls": calls},
                {"role": "tool", "tool_call_id": calls[0]["id"], "content": "{}"},
            ]
            _ = [chunk async for chunk in provider.stream_chat("gemini-test", history, api_key="test")]
            assert captured[1]["contents"][0].parts[0].thought_signature == b"opaque-signature"
            assert captured[1]["contents"][1].parts[0].function_response.name == "weather"

    asyncio.run(run())
