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
    # Keep what was actually delivered as a (truncated) assistant turn so the
    # next turn's context reflects what the user actually heard/read.
    session.finalize_assistant()

    if trigger == "user_input":
        session.add_user_turn(payload["text"])
        await state.restart_generation()
