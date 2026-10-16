# -*- coding: utf-8 -*-
"""触发实现注册表：新增实现后在此登记，配置文件按 name 选用。"""
from .base import TriggerEvent, TriggerSource  # noqa: F401
from .stdin_trigger import StdinTrigger  # noqa: F401

TRIGGER_IMPLS = {
    "stdin": {"module": "voice_agent.trigger.stdin_trigger", "cls": "StdinTrigger"},
}
