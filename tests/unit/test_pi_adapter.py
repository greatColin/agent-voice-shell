import pytest
from typing import AsyncIterator
from app.agent.base import AgentClient
from app.events.events import VoiceEvent, TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete
from app.events.router import EventRouter


class FakeAgentClient(AgentClient):
    def __init__(self, events: list[VoiceEvent]):
        self._events = events

    async def stream(self, messages: list[dict]) -> AsyncIterator[VoiceEvent]:
        for event in self._events:
            yield event

    async def cancel(self) -> None:
        pass


@pytest.mark.asyncio
async def test_event_router_with_fake_agent():
    events_received = []

    async def capture(event):
        events_received.append(event)

    router = EventRouter()
    router.on_text(capture)
    router.on_thinking(capture)
    router.on_tool_call(capture)
    router.on_tool_result(capture)
    router.on_complete(capture)

    fake_events = [
        TextChunk(delta="Hello "),
        TextChunk(delta="world!"),
        ThinkingChunk(delta="Let me think..."),
        ToolCall(name="get_weather", args={"city": "beijing"}),
        ToolResult(name="get_weather", result="sunny"),
        Complete(final_text="Done!"),
    ]

    agent = FakeAgentClient(fake_events)
    async for event in agent.stream([]):
        await router.dispatch(event)

    assert len(events_received) == 6
    assert isinstance(events_received[0], TextChunk)
    assert isinstance(events_received[2], ThinkingChunk)
    assert isinstance(events_received[3], ToolCall)
    assert isinstance(events_received[4], ToolResult)
    assert isinstance(events_received[5], Complete)
