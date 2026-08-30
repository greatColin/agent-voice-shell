import pytest
import asyncio
from app.controller.state_machine import StateMachine, State


class TestStateMachine:
    @pytest.fixture
    def sm(self):
        return StateMachine()

    def test_initial_state_is_idle(self, sm):
        assert sm.state == State.IDLE

    def test_idle_to_generating_on_input(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        assert sm.state == State.GENERATING

    def test_generating_to_interrupting_on_input(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        assert sm.state == State.INTERRUPTING

    def test_interrupting_stays_interrupting_on_input(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        assert sm.state == State.INTERRUPTING

    def test_generating_to_idle_on_complete(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_generation_complete())
        assert sm.state == State.IDLE

    def test_interrupting_to_generating_on_complete(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_generation_complete())
        assert sm.state == State.GENERATING

    def test_idle_to_idle_on_complete(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_generation_complete())
        assert sm.state == State.IDLE

    def test_interrupting_idle_on_input(self, sm):
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        asyncio.get_event_loop().run_until_complete(sm.on_input_received())
        assert sm.state == State.INTERRUPTING

    @pytest.mark.asyncio
    async def test_flush_output(self, sm):
        await sm.on_input_received()
        await sm.flush_output()
        assert sm.state == State.GENERATING

    @pytest.mark.asyncio
    async def test_restart_generation_from_interrupting(self, sm):
        await sm.on_input_received()
        await sm.on_input_received()
        assert sm.state == State.INTERRUPTING
        await sm.restart_generation()
        assert sm.state == State.GENERATING

    @pytest.mark.asyncio
    async def test_restart_generation_from_idle(self, sm):
        await sm.restart_generation()
        assert sm.state == State.IDLE

    @pytest.mark.asyncio
    async def test_restart_generation_from_generating(self, sm):
        await sm.on_input_received()
        await sm.restart_generation()
        assert sm.state == State.GENERATING

    def test_idle_generating_interrupting_cycle(self, sm):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(sm.on_input_received())
        assert sm.state == State.GENERATING

        loop.run_until_complete(sm.on_input_received())
        assert sm.state == State.INTERRUPTING

        loop.run_until_complete(sm.on_generation_complete())
        assert sm.state == State.GENERATING

        loop.run_until_complete(sm.on_generation_complete())
        assert sm.state == State.IDLE
