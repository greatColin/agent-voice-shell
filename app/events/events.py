from dataclasses import dataclass, field, asdict
from typing import Union


@dataclass
class TextChunk:
    type: str = "text"
    delta: str = ""


@dataclass
class ThinkingChunk:
    type: str = "thinking"
    delta: str = ""


@dataclass
class ToolCall:
    type: str = "tool_call"
    name: str = ""
    args: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    type: str = "tool_result"
    name: str = ""
    result: str = ""


@dataclass
class Complete:
    type: str = "complete"
    final_text: str = ""


VoiceEvent = Union[TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete]


def serialize_event(event: VoiceEvent) -> dict:
    return asdict(event)
