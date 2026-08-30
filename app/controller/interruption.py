from app.agent.base import AgentClient
from app.session.session import Session


async def handle(
    trigger: str,
    payload: dict,
    agent: AgentClient,
    session: Session,
    state: "StateMachine",
) -> None:
    await agent.cancel()
    await state.flush_output()
    session.discard_assistant_partial()

    if trigger == "user_input":
        session.add_user_turn(payload["text"])
        await state.restart_generation()
