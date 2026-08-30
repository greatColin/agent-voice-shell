from typing import Callable, Awaitable, Any
from app.events.events import VoiceEvent, TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete


class EventRouter:
    def __init__(self):
        self._callbacks: dict[type, Callable[[Any], Awaitable[None]]] = {}

    def on(self, event_cls: type, cb: Callable[[Any], Awaitable[None]]) -> None:
        self._callbacks[event_cls] = cb

    def on_text(self, cb: Callable[[TextChunk], Awaitable[None]]) -> None:
        self._callbacks[TextChunk] = cb

    def on_thinking(self, cb: Callable[[ThinkingChunk], Awaitable[None]]) -> None:
        self._callbacks[ThinkingChunk] = cb

    def on_tool_call(self, cb: Callable[[ToolCall], Awaitable[None]]) -> None:
        self._callbacks[ToolCall] = cb

    def on_tool_result(self, cb: Callable[[ToolResult], Awaitable[None]]) -> None:
        self._callbacks[ToolResult] = cb

    def on_complete(self, cb: Callable[[Complete], Awaitable[None]]) -> None:
        self._callbacks[Complete] = cb

    async def dispatch(self, event: VoiceEvent) -> None:
        event_type = type(event)
        if event_type in self._callbacks:
            cb = self._callbacks[event_type]
            result = cb(event)
            if hasattr(result, '__await__'):
                await result
