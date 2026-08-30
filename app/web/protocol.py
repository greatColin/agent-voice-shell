from enum import Enum
from pydantic import BaseModel


class ClientMessageType(str, Enum):
    START = "start"
    USER_INPUT = "user_input"
    INTERRUPT = "interrupt"


class ServerMessageType(str, Enum):
    ASSISTANT_TEXT_DELTA = "assistant_text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    GENERATION_COMPLETE = "generation_complete"
    ERROR = "error"


class ClientMessage(BaseModel):
    type: ClientMessageType
    text: str | None = None


class ServerMessage(BaseModel):
    type: ServerMessageType
    delta: str | None = None
    name: str | None = None
    args: dict | None = None
    result: str | None = None
    final_text: str | None = None
    message: str | None = None
