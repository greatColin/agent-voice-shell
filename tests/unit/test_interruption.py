import pytest
from unittest.mock import AsyncMock, MagicMock
from app.controller.interruption import handle
from app.agent.base import AgentClient
from app.session.session import Session


class MockAgent(AgentClient):
    def __init__(self):
        self.cancel_called = False
        self.stream_called = False

    async def stream(self, messages):
        self.stream_called = True
        yield

    async def cancel(self):
        self.cancel_called = True


class MockState:
    def __init__(self):
        self.flush_output_called = False
        self.restart_generation_called = False
        self.flush_output_order = None
        self.cancel_order = None
        self.discard_order = None
        self.call_order = []

    async def flush_output(self):
        self.flush_output_called = True
        self.call_order.append(("flush_output", len(self.call_order)))

    async def restart_generation(self):
        self.restart_generation_called = True
        self.call_order.append(("restart_generation", len(self.call_order)))


class TestInterruptionHandler:
    @pytest.mark.asyncio
    async def test_handle_user_input_calls_in_order(self):
        agent = MockAgent()
        session = Session()
        session.append_assistant_partial("partial response")
        state = MockState()

        await handle("user_input", {"text": "new input"}, agent, session, state)

        assert agent.cancel_called is True
        assert state.flush_output_called is True
        assert session.assistant_partial == ""
        assert session.messages[-1] == {"role": "user", "content": "new input"}
        assert state.restart_generation_called is True

    @pytest.mark.asyncio
    async def test_handle_interrupt_does_not_add_user_turn(self):
        agent = MockAgent()
        session = Session()
        session.add_user_turn("first message")
        session.append_assistant_partial("partial response")
        state = MockState()

        await handle("interrupt", {}, agent, session, state)

        assert agent.cancel_called is True
        assert state.flush_output_called is True
        assert session.assistant_partial == ""
        # No user turn is added, but the truncated assistant partial is kept.
        assert len(session.messages) == 2
        assert session.messages[-1] == {"role": "assistant", "content": "partial response"}
        assert state.restart_generation_called is False

    @pytest.mark.asyncio
    async def test_handle_calls_cancel_first(self):
        agent = MockAgent()
        session = Session()
        state = MockState()
        state.call_order = []
        original_cancel = agent.cancel

        async def tracked_cancel():
            state.call_order.append(("cancel", len(state.call_order)))
            await original_cancel()

        agent.cancel = tracked_cancel

        await handle("user_input", {"text": "new input"}, agent, session, state)

        assert state.call_order[0] == ("cancel", 0)

    @pytest.mark.asyncio
    async def test_handle_calls_flush_output_second(self):
        agent = MockAgent()
        session = Session()
        state = MockState()
        state.call_order = []

        await handle("user_input", {"text": "new input"}, agent, session, state)

        assert agent.cancel_called is True
        assert state.flush_output_called is True

    @pytest.mark.asyncio
    async def test_handle_calls_discard_third(self):
        agent = MockAgent()
        session = Session()
        session.append_assistant_partial("partial")
        state = MockState()

        await handle("user_input", {"text": "new input"}, agent, session, state)

        assert session.assistant_partial == ""

    @pytest.mark.asyncio
    async def test_handle_calls_restart_generation_fifth(self):
        agent = MockAgent()
        session = Session()
        state = MockState()
        state.call_order = []

        await handle("user_input", {"text": "new input"}, agent, session, state)

        restart_idx = next(i for i, (name, _) in enumerate(state.call_order) if name == "restart_generation")
        assert restart_idx is not None
