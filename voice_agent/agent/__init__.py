# -*- coding: utf-8 -*-
"""Agent 实现注册表。"""
from .base import Agent  # noqa: F401
from .mock import MockAgent  # noqa: F401
from .pi_agent import PiAgent  # noqa: F401

AGENT_IMPLS = {
    "mock": {"module": "voice_agent.agent.mock", "cls": "MockAgent"},
    "pi": {"module": "voice_agent.agent.pi_agent", "cls": "PiAgent"},
}
