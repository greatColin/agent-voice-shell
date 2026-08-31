import pytest
from unittest.mock import AsyncMock, MagicMock
from app.session.session import Session
from app.agent.base import AgentClient
from app.controller.state_machine import StateMachine, State
from app.controller.interruption import handle as handle_interruption
from app.events.router import EventRouter
from app.events.events import TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete
from typing import AsyncIterator


class FakeAgent(AgentClient):
    def __init__(self, events: list):
        self._events = events
        self.cancel_called = False

    async def stream(self, messages) -> AsyncIterator:
        for event in self._events:
            yield event

    async def cancel(self) -> None:
        self.cancel_called = True


@pytest.mark.asyncio
async def test_ws_user_input_triggers_interruption():
    session = Session()
    session.add_user_turn("first message")

    events = [
        TextChunk(delta="response 1"),
        TextChunk(delta="..."),
        Complete(final_text="response 1..."),
    ]
    agent = FakeAgent(events)
    state = StateMachine()
    router = EventRouter()
    handler_called = False

    async def dummy_handler(*args):
        nonlocal handler_called
        handler_called = True

    await state.on_input_received()
    assert state.state == State.GENERATING

    await state.on_input_received()
    assert state.state == State.INTERRUPTING

    await handle_interruption("user_input", {"text": "second message"}, agent, session, state)

    assert agent.cancel_called is True
    assert session.assistant_partial == ""
    assert session.messages[-1] == {"role": "user", "content": "second message"}


@pytest.mark.asyncio
async def test_ws_interrupt_cancels_generation():
    session = Session()
    session.add_user_turn("first")
    session.append_assistant_partial("partial")

    agent = FakeAgent([])
    state = StateMachine()

    await state.on_input_received()
    await state.on_input_received()

    await handle_interruption("interrupt", {}, agent, session, state)

    assert agent.cancel_called is True
    assert session.assistant_partial == ""
    # finalize_assistant() promotes the delivered partial to a truncated
    # assistant turn so the next turn's context reflects what the user heard.
    assert len(session.messages) == 2
    assert session.messages[-1]["role"] == "assistant"
    assert session.messages[-1]["content"] == "partial"


@pytest.mark.asyncio
async def test_full_conversation_flow():
    session = Session()

    events = [
        TextChunk(delta="Hello! "),
        TextChunk(delta="How can I help?"),
        Complete(final_text="Hello! How can I help?"),
    ]

    agent = FakeAgent(events)
    state = StateMachine()
    router = EventRouter()
    received_events = []

    router.on_text(lambda e: received_events.append(("text", e.delta)))
    router.on_complete(lambda e: received_events.append(("complete", e.final_text)))

    session.add_user_turn("Hi")
    await state.on_input_received()

    async with agent:
        async for event in agent.stream(session.get_messages()):
            await router.dispatch(event)
            if isinstance(event, TextChunk):
                session.append_assistant_partial(event.delta)
            elif isinstance(event, Complete):
                session.finalize_assistant()

    await state.on_generation_complete()

    assert len(received_events) == 3
    assert received_events[0] == ("text", "Hello! ")
    assert received_events[1] == ("text", "How can I help?")
    assert received_events[2] == ("complete", "Hello! How can I help?")
    assert state.state == State.IDLE
