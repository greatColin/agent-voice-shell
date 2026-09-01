import asyncio
import re
from fastapi import WebSocket, WebSocketDisconnect
from app.session.session import Session
from app.agent.pi_adapter import PiAdapter
from app.controller.state_machine import StateMachine, State
from app.controller.interruption import handle as handle_interruption
from app.tts.service import service as tts_service
from app.web.protocol import ServerMessage, ServerMessageType


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json(self, websocket: WebSocket, data: dict):
        await websocket.send_json(data)


manager = ConnectionManager()

_SENTENCE_END_RE = re.compile(r"[。！？!?；;!?\n]")
PACE_SECONDS_PER_CHAR = 0.18


def _next_speak_unit(buf: str) -> tuple[str, str]:
    last = 0
    for m in _SENTENCE_END_RE.finditer(buf):
        last = m.end()
    if last:
        return buf[:last], buf[last:]
    if len(buf) >= 12:
        return buf[:12], buf[12:]
    return "", buf


async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    session = Session()
    agent = PiAdapter()
    state = StateMachine()

    pending_task = None
    cancel_event = asyncio.Event()
    tts_queues: list[asyncio.Queue] = []
    tts_queue_lock = asyncio.Lock()
    tts_queues_append = tts_queues.append
    tts_index = 0

    async def send_text_delta(delta: str):
        msg = ServerMessage(type=ServerMessageType.ASSISTANT_TEXT_DELTA, delta=delta)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def send_complete(final_text: str):
        msg = ServerMessage(type=ServerMessageType.GENERATION_COMPLETE, final_text=final_text)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def send_error(message: str):
        msg = ServerMessage(type=ServerMessageType.ERROR, message=message)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def send_tts_audio(seq: int, text: str, audio_b64: str):
        msg = ServerMessage(
            type=ServerMessageType.TTS_AUDIO,
            audio=audio_b64,
            tts_text=text,
            chunk_index=seq,
        )
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def submit_tts(text: str, voice: str = "") -> asyncio.Queue:
        q = await tts_service.synthesize(text, voice=voice, speed=1.0)
        async with tts_queue_lock:
            tts_queues_append(q)
        return q

    async def consume_tts_queues():
        nonlocal tts_index
        while not cancel_event.is_set():
            queue = None
            async with tts_queue_lock:
                if tts_index < len(tts_queues):
                    queue = tts_queues[tts_index]
            if queue is None:
                await asyncio.sleep(0.05)
                continue
            try:
                result = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                async with tts_queue_lock:
                    if tts_index < len(tts_queues) and tts_queues[tts_index] is queue:
                        tts_index += 1
                continue
            if result is None:
                async with tts_queue_lock:
                    tts_index += 1
                continue
            await send_tts_audio(result.seq, result.text, result.wav_b64)
            async with tts_queue_lock:
                tts_index += 1

    async def run_agent_stream():
        nonlocal pending_task
        buf = ""

        async def pump(flush_all: bool = False):
            nonlocal buf
            while buf and not cancel_event.is_set():
                if flush_all:
                    unit, buf = buf, ""
                else:
                    unit, buf = _next_speak_unit(buf)
                    if not unit:
                        return
                await send_text_delta(unit)
                session.append_assistant_partial(unit)
                await submit_tts(unit)
                await asyncio.sleep(len(unit) * PACE_SECONDS_PER_CHAR)

        try:
            async with agent:
                async for event in agent.stream(session.get_messages()):
                    if cancel_event.is_set():
                        break
                    if isinstance(event, TextChunk):
                        buf += event.delta
                        await pump()
                    elif isinstance(event, Complete):
                        await pump(flush_all=True)
                        session.finalize_assistant()
                        await send_complete(event.final_text)
                        break
        except Exception as e:
            await send_error(str(e))
        finally:
            await state.on_generation_complete()
            pending_task = None

    async def receive_messages():
        nonlocal pending_task
        try:
            while True:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                msg_type = data.get("type")

                if msg_type == "start":
                    if state.state == State.IDLE and pending_task is None:
                        user_text = data.get("text", "")
                        session.add_user_turn(user_text or "")
                        await state.on_input_received()
                        cancel_event.clear()
                        tts_queues.clear()
                        pending_task = asyncio.create_task(run_agent_stream())
                        asyncio.create_task(consume_tts_queues())

                elif msg_type == "user_input":
                    text = data.get("text", "")
                    if pending_task:
                        cancel_event.set()
                        pending_task.cancel()
                        try:
                            await pending_task
                        except asyncio.CancelledError:
                            pass
                    await handle_interruption("user_input", {"text": text}, agent, session, state)
                    await state.on_input_received()
                    cancel_event.clear()
                    tts_queues.clear()
                    pending_task = asyncio.create_task(run_agent_stream())
                    asyncio.create_task(consume_tts_queues())

                elif msg_type == "interrupt":
                    if pending_task:
                        cancel_event.set()
                        pending_task.cancel()
                        try:
                            await pending_task
                        except asyncio.CancelledError:
                            pass
                    await handle_interruption("interrupt", {}, agent, session, state)

        except WebSocketDisconnect:
            if pending_task:
                cancel_event.set()
                pending_task.cancel()
                try:
                    await pending_task
                except asyncio.CancelledError:
                    pass
            manager.disconnect(websocket)
        except Exception as e:
            await send_error(str(e))
            manager.disconnect(websocket)

    try:
        await receive_messages()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        await send_error(str(e))
        manager.disconnect(websocket)


from app.events.events import TextChunk, Complete
