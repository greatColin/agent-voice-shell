from abc import ABC, abstractmethod
from typing import AsyncIterator, AsyncContextManager
from app.events.events import VoiceEvent


class AgentClient(ABC):
    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncIterator[VoiceEvent]:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> "AgentClient":
        return self

    async def __aexit__(self, *a: object) -> None:
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
