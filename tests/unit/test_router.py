import pytest
from app.events.router import EventRouter
from app.events.events import TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete


class TestEventRouter:
    @pytest.fixture
    def router(self):
        return EventRouter()

    @pytest.fixture
    def callback_tracker(self):
        return []

    @pytest.mark.asyncio
    async def test_on_text(self, router, callback_tracker):
        async def cb(event):
            callback_tracker.append(event)

        router.on_text(cb)
        event = TextChunk(delta="hello")
        await router.dispatch(event)
        assert len(callback_tracker) == 1
        assert callback_tracker[0].delta == "hello"

    @pytest.mark.asyncio
    async def test_on_thinking(self, router, callback_tracker):
        async def cb(event):
            callback_tracker.append(event)

        router.on_thinking(cb)
        event = ThinkingChunk(delta="thinking...")
        await router.dispatch(event)
        assert len(callback_tracker) == 1
        assert callback_tracker[0].delta == "thinking..."

    @pytest.mark.asyncio
    async def test_on_tool_call(self, router, callback_tracker):
        async def cb(event):
            callback_tracker.append(event)

        router.on_tool_call(cb)
        event = ToolCall(name="get_weather", args={"city": "beijing"})
        await router.dispatch(event)
        assert len(callback_tracker) == 1
        assert callback_tracker[0].name == "get_weather"

    @pytest.mark.asyncio
    async def test_on_tool_result(self, router, callback_tracker):
        async def cb(event):
            callback_tracker.append(event)

        router.on_tool_result(cb)
        event = ToolResult(name="get_weather", result="sunny")
        await router.dispatch(event)
        assert len(callback_tracker) == 1
        assert callback_tracker[0].result == "sunny"

    @pytest.mark.asyncio
    async def test_on_complete(self, router, callback_tracker):
        async def cb(event):
            callback_tracker.append(event)

        router.on_complete(cb)
        event = Complete(final_text="Done!")
        await router.dispatch(event)
        assert len(callback_tracker) == 1
        assert callback_tracker[0].final_text == "Done!"

    @pytest.mark.asyncio
    async def test_dispatch_routes_correctly(self, router, callback_tracker):
        results = []

        async def text_cb(event):
            results.append(("text", event.delta))

        async def thinking_cb(event):
            results.append(("thinking", event.delta))

        async def tool_call_cb(event):
            results.append(("tool_call", event.name))

        async def tool_result_cb(event):
            results.append(("tool_result", event.result))

        async def complete_cb(event):
            results.append(("complete", event.final_text))

        router.on_text(text_cb)
        router.on_thinking(thinking_cb)
        router.on_tool_call(tool_call_cb)
        router.on_tool_result(tool_result_cb)
        router.on_complete(complete_cb)

        await router.dispatch(TextChunk(delta="hello"))
        await router.dispatch(ThinkingChunk(delta="think"))
        await router.dispatch(ToolCall(name="tool1", args={}))
        await router.dispatch(ToolResult(name="tool1", result="result1"))
        await router.dispatch(Complete(final_text="done"))

        assert results == [
            ("text", "hello"),
            ("thinking", "think"),
            ("tool_call", "tool1"),
            ("tool_result", "result1"),
            ("complete", "done"),
        ]

    @pytest.mark.asyncio
    async def test_dispatch_no_callback(self, router):
        event = TextChunk(delta="hello")
        await router.dispatch(event)
