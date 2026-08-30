import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.session.session import Session
from app.agent.pi_adapter import PiAdapter
from app.controller.state_machine import StateMachine, State
from app.controller.interruption import handle as handle_interruption
from app.events.router import EventRouter
from app.events.events import TextChunk, Complete
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


async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    session = Session()
    agent = PiAdapter()
    state = StateMachine()

    pending_task = None
    cancel_event = asyncio.Event()

    async def send_text_delta(delta: str):
        msg = ServerMessage(type=ServerMessageType.ASSISTANT_TEXT_DELTA, delta=delta)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def send_complete(final_text: str):
        msg = ServerMessage(type=ServerMessageType.GENERATION_COMPLETE, final_text=final_text)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def send_error(message: str):
        msg = ServerMessage(type=ServerMessageType.ERROR, message=message)
        await manager.send_json(websocket, msg.model_dump(exclude_none=True))

    async def run_agent_stream():
        nonlocal pending_task
        try:
            async with agent:
                async for event in agent.stream(session.get_messages()):
                    if cancel_event.is_set():
                        break
                    if isinstance(event, TextChunk):
                        await send_text_delta(event.delta)
                        session.append_assistant_partial(event.delta)
                    elif isinstance(event, Complete):
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
                        if user_text:
                            session.add_user_turn(user_text)
                        else:
                            session.add_user_turn("")
                        await state.on_input_received()
                        cancel_event.clear()
                        pending_task = asyncio.create_task(run_agent_stream())

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
                    session.add_user_turn(text)
                    await state.on_input_received()
                    cancel_event.clear()
                    pending_task = asyncio.create_task(run_agent_stream())

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
