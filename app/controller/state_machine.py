import asyncio
from enum import Enum


class State(Enum):
    IDLE = "idle"
    GENERATING = "generating"
    INTERRUPTING = "interrupting"


class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        self._event = asyncio.Event()
        self._event.set()

    async def on_input_received(self) -> None:
        if self.state == State.IDLE:
            self.state = State.GENERATING
            self._event.clear()
        elif self.state == State.GENERATING:
            self.state = State.INTERRUPTING
        elif self.state == State.INTERRUPTING:
            pass

    async def on_generation_complete(self) -> None:
        if self.state == State.GENERATING:
            self.state = State.IDLE
            self._event.set()
        elif self.state == State.INTERRUPTING:
            self.state = State.GENERATING
        elif self.state == State.IDLE:
            pass

    async def flush_output(self) -> None:
        pass

    async def restart_generation(self) -> None:
        if self.state == State.INTERRUPTING:
            self.state = State.GENERATING
