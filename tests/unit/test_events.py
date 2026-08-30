import pytest
from dataclasses import asdict
from app.events.events import (
    TextChunk,
    ThinkingChunk,
    ToolCall,
    ToolResult,
    Complete,
    serialize_event,
)


class TestTextChunk:
    def test_create(self):
        e = TextChunk(delta="hello")
        assert e.type == "text"
        assert e.delta == "hello"

    def test_serialize(self):
        e = TextChunk(delta="hello")
        d = serialize_event(e)
        assert d == {"type": "text", "delta": "hello"}

    def test_equality(self):
        e1 = TextChunk(delta="hello")
        e2 = TextChunk(delta="hello")
        assert e1 == e2

class TestThinkingChunk:
    def test_create(self):
        e = ThinkingChunk(delta="thinking...")
        assert e.type == "thinking"
        assert e.delta == "thinking..."

    def test_serialize(self):
        e = ThinkingChunk(delta="thinking...")
        d = serialize_event(e)
        assert d == {"type": "thinking", "delta": "thinking..."}

    def test_equality(self):
        e1 = ThinkingChunk(delta="thinking...")
        e2 = ThinkingChunk(delta="thinking...")
        assert e1 == e2

class TestToolCall:
    def test_create(self):
        e = ToolCall(name="get_weather", args={"city": "beijing"})
        assert e.type == "tool_call"
        assert e.name == "get_weather"
        assert e.args == {"city": "beijing"}

    def test_serialize(self):
        e = ToolCall(name="get_weather", args={"city": "beijing"})
        d = serialize_event(e)
        assert d == {"type": "tool_call", "name": "get_weather", "args": {"city": "beijing"}}

    def test_equality(self):
        e1 = ToolCall(name="get_weather", args={"city": "beijing"})
        e2 = ToolCall(name="get_weather", args={"city": "beijing"})
        assert e1 == e2

class TestToolResult:
    def test_create(self):
        e = ToolResult(name="get_weather", result="sunny")
        assert e.type == "tool_result"
        assert e.name == "get_weather"
        assert e.result == "sunny"

    def test_serialize(self):
        e = ToolResult(name="get_weather", result="sunny")
        d = serialize_event(e)
        assert d == {"type": "tool_result", "name": "get_weather", "result": "sunny"}

    def test_equality(self):
        e1 = ToolResult(name="get_weather", result="sunny")
        e2 = ToolResult(name="get_weather", result="sunny")
        assert e1 == e2

class TestComplete:
    def test_create(self):
        e = Complete(final_text="Hello! How can I help you?")
        assert e.type == "complete"
        assert e.final_text == "Hello! How can I help you?"

    def test_serialize(self):
        e = Complete(final_text="Hello! How can I help you?")
        d = serialize_event(e)
        assert d == {"type": "complete", "final_text": "Hello! How can I help you?"}

    def test_equality(self):
        e1 = Complete(final_text="Hello!")
        e2 = Complete(final_text="Hello!")
        assert e1 == e2


